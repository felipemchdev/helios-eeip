import azure.functions as func
import requests
import json
import logging
import time
import os
import shutil
import tempfile
import threading
import yaml
from datetime import datetime, timezone
from urllib.parse import quote
from azure.storage.filedatalake import DataLakeServiceClient

os.environ["REQUESTS_CA_BUNDLE"] = "/etc/ssl/certs/ca-certificates.crt"
os.environ.pop("SSL_CERT_FILE", None)
os.environ.pop("CURL_CA_BUNDLE", None)

_dbt_lock = threading.Lock()

from dbt.cli.main import dbtRunner

app = func.FunctionApp()

PACKAGES = [
    {"system": "PYPI", "name": "apache-airflow", "version": "2.9.3"},
    {"system": "PYPI", "name": "dbt-core", "version": "1.7.4"},
    {"system": "PYPI", "name": "pandas", "version": "2.1.4"},
    {"system": "PYPI", "name": "requests", "version": "2.31.0"},
    {"system": "NPM", "name": "react", "version": "18.2.0"},
    {"system": "NPM", "name": "typescript", "version": "5.3.3"},
    {"system": "NPM", "name": "axios", "version": "1.6.5"},
    {"system": "PYPI", "name": "fastapi", "version": "0.109.0"},
    {"system": "PYPI", "name": "sqlalchemy", "version": "2.0.25"},
    {"system": "MAVEN", "name": "org.apache.spark:spark-core_2.13", "version": "3.5.0"},
]

BASE_URL = "https://api.deps.dev/v3alpha"
ADLS_FILESYSTEM = os.getenv("ADLS_FILESYSTEM", "bronze")
DBT_PROJECT_PATH = os.path.join(os.path.dirname(__file__), "transformation")


def fetch_with_retry(url: str, max_retries: int = 5, base_backoff_seconds: int = 1) -> dict:
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"Calling deps.dev: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            if attempt == max_retries:
                logging.error(f"Max retries reached for {url}")
                raise
            wait = base_backoff_seconds * (2 ** (attempt - 1))
            logging.warning(f"Attempt {attempt}/{max_retries} failed: {exc}. Retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Unexpected retry loop termination for {url}")


def write_to_adls(
    service_client: DataLakeServiceClient,
    payload: dict,
    date_str: str,
    system: str,
    name: str,
    folder: str = "deps_dev",
) -> None:
    safe_name = name.replace("/", "_").replace(":", "_")
    path = f"raw/{folder}/{date_str}/{system}_{safe_name}.json"
    logging.info(f"Writing to ADLS: {path}")
    fs_client = service_client.get_file_system_client(ADLS_FILESYSTEM)
    file_client = fs_client.get_file_client(path)
    data = json.dumps(payload, indent=2, ensure_ascii=False)
    file_client.upload_data(data.encode("utf-8"), overwrite=True)
    logging.info(f"ADLS write done: {path}")


def prepare_dbt_tmp() -> str:
    tmp_path = tempfile.mkdtemp(prefix="dbt-project-")
    ignore_patterns = shutil.ignore_patterns('eeip.duckdb', 'target', 'logs', '.dbt_local')
    shutil.copytree(DBT_PROJECT_PATH, tmp_path, dirs_exist_ok=True, ignore=ignore_patterns)

    dbt_project_file = os.path.join(tmp_path, "dbt_project.yml")
    with open(dbt_project_file, "r") as f:
        project_cfg = yaml.safe_load(f)
    project_cfg["packages-install-path"] = os.path.join(tmp_path, "dbt_packages")
    with open(dbt_project_file, "w") as f:
        yaml.dump(project_cfg, f)

    profiles_file = os.path.join(tmp_path, "profiles.yml")
    with open(profiles_file, "r") as f:
        profiles = yaml.safe_load(f)
    profiles["eeip_duckdb"]["outputs"]["dev"]["path"] = os.path.join(tmp_path, "eeip.duckdb")
    if "settings" in profiles["eeip_duckdb"]["outputs"]["dev"]:
        del profiles["eeip_duckdb"]["outputs"]["dev"]["settings"]
    profiles["eeip_duckdb"]["outputs"]["dev"].pop("extensions", None)
    with open(profiles_file, "w") as f:
        yaml.dump(profiles, f)

    logging.info(f"dbt project copied to {tmp_path}")
    return tmp_path


def cleanup_dbt_tmp(tmp_path: str) -> None:
    try:
        if os.path.exists(tmp_path):
            shutil.rmtree(tmp_path)
            logging.info(f"Cleaned up dbt temp directory: {tmp_path}")
    except Exception as exc:
        logging.warning(f"Failed to cleanup {tmp_path}: {exc}")


def _invoke_dbt(args: list, description: str) -> tuple[bool, list]:
    errors = []

    def capture(event):
        try:
            if hasattr(event, 'info') and hasattr(event.info, 'msg'):
                errors.append(event.info.msg)
            elif hasattr(event, 'data') and hasattr(event.data, 'msg'):
                errors.append(event.data.msg)
        except Exception:
            pass

    dbt = dbtRunner(callbacks=[capture])
    with _dbt_lock:
        result = dbt.invoke(args)

    for err in errors:
        if 'error' in err.lower() or 'fail' in err.lower():
            logging.error(f"dbt {description}: {err}")
        else:
            logging.info(f"dbt {description}: {err}")

    if not result.success:
        if result.exception:
            logging.error(f"dbt {description} exception: {result.exception}")
        return False, errors
    return True, errors


def run_dbt(selector: str, tmp_path: str) -> bool:
    logging.info(f"Running dbt: select {selector}")
    args = ["run", "--select", selector,
            "--project-dir", tmp_path, "--profiles-dir", tmp_path]
    success, _ = _invoke_dbt(args, f"run.{selector}")
    return success


def run_dbt_deps(tmp_path: str) -> bool:
    logging.info("Running dbt deps")
    args = ["deps", "--project-dir", tmp_path, "--profiles-dir", tmp_path]
    success, _ = _invoke_dbt(args, "deps")
    if success:
        logging.info("dbt deps completed")
    return success


def download_adls_data(service_client: DataLakeServiceClient, tmp_path: str, date_str: str) -> str:
    bronze_path = os.path.join(tmp_path, "bronze")
    os.makedirs(bronze_path, exist_ok=True)
    fs_client = service_client.get_file_system_client(ADLS_FILESYSTEM)
    prefixes = [f"raw/deps_dev/{date_str}/", f"raw/advisories/{date_str}/"]
    for prefix in prefixes:
        paths = list(fs_client.get_paths(path=prefix))
        if not paths:
            logging.warning(f"No data found at {prefix}")
            continue
        for p in paths:
            rel = p.name
            if rel.endswith("/"):
                continue
            dest = os.path.join(bronze_path, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            file_client = fs_client.get_file_client(rel)
            data = file_client.download_file().readall()
            with open(dest, "wb") as f:
                f.write(data)
    logging.info(f"Downloaded {date_str} ADLS data to {bronze_path}")
    return bronze_path


def export_gold_to_adls(
    service_client: DataLakeServiceClient,
    duckdb_path: str,
    tmp_path: str,
) -> bool:
    import duckdb as ddb

    tables = ["fct_dependency_risk", "dim_dependency_chain", "dim_dependency_edges"]
    conn = ddb.connect(duckdb_path)
    export_dir = os.path.join(tmp_path, "gold_export")
    os.makedirs(export_dir, exist_ok=True)

    for table in tables:
        try:
            parquet_path = os.path.join(export_dir, f"{table}.parquet")
            conn.execute(f"COPY (SELECT * FROM eeip.main_gold.{table}) TO '{parquet_path}' (FORMAT PARQUET)")
            logging.info(f"Exported {table} → {parquet_path}")

            fs_client = service_client.get_file_system_client("gold")
            blob_path = f"{table}/{table}.parquet"
            file_client = fs_client.get_file_client(blob_path)
            with open(parquet_path, "rb") as f:
                file_client.upload_data(f.read(), overwrite=True)
            logging.info(f"Uploaded {blob_path} to ADLS gold container")
        except Exception as exc:
            logging.error(f"Failed to export/upload {table}: {exc}")
            return False

    conn.close()
    return True


def run_dbt_tests(tmp_path: str) -> bool:
    logging.info("Running dbt tests")
    args = ["test",
            "--project-dir", tmp_path, "--profiles-dir", tmp_path]
    success, _ = _invoke_dbt(args, "test")
    if success:
        logging.info("dbt tests passed")
    return success


@app.timer_trigger(
    schedule="0 8 */3 * *",
    arg_name="timer",
    run_on_startup=False,
)
def ingest_deps_dev(timer: func.TimerRequest) -> None:
    logging.info("═══ EEIP Pipeline started ═══")

    if timer.past_due:
        logging.warning("Timer is past due — running anyway")

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logging.info(f"Partition date: {date_str}")

    logging.info("── Phase 1: Ingestion (deps.dev) ──")

    conn_string = os.environ["ADLS_CONNECTION_STRING"]
    service_client = DataLakeServiceClient.from_connection_string(conn_string)

    success, errors = 0, 0

    for pkg in PACKAGES:
        system = pkg["system"]
        name = pkg["name"]
        version = pkg["version"]
        logging.info(f"Ingesting {system}/{name}@{version}")

        try:
            encoded_system = quote(system, safe="")
            encoded_name = quote(name, safe="")
            encoded_version = quote(version, safe="")

            pkg_url = f"{BASE_URL}/systems/{encoded_system}/packages/{encoded_name}/versions/{encoded_version}"
            deps_url = f"{pkg_url}:dependencies"

            pkg_data = fetch_with_retry(pkg_url)
            deps_data = fetch_with_retry(deps_url)

            enriched_nodes = []
            dep_nodes = deps_data.get("nodes", [])
            non_self_nodes = [n for n in dep_nodes if n.get("relation", "") != "SELF"]
            for dep_node in non_self_nodes[:20]:
                vk = dep_node.get("versionKey", {})
                dep_sys = quote(vk.get("system", ""), safe="")
                dep_nm = quote(vk.get("name", ""), safe="")
                dep_ver = quote(vk.get("version", ""), safe="")
                try:
                    dep_info = fetch_with_retry(
                        f"{BASE_URL}/systems/{dep_sys}/packages/{dep_nm}/versions/{dep_ver}"
                    )
                    dep_node["advisoryKeys"] = dep_info.get("advisoryKeys", [])
                except Exception as exc:
                    logging.warning(f"Could not enrich dep {vk.get('name')}: {exc}")
                    dep_node["advisoryKeys"] = []
                enriched_nodes.append(dep_node)

            self_node = [n for n in dep_nodes if n.get("relation", "") == "SELF"]
            deps_data["nodes"] = self_node + enriched_nodes

            payload = {
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "source": "deps.dev",
                "package_key": {"system": system, "name": name, "version": version},
                **pkg_data,
                "dependencies": deps_data,
            }

            write_to_adls(service_client, payload, date_str, system, name, folder="deps_dev")

            root_adv_ids = {adv["id"] for adv in pkg_data.get("advisoryKeys", []) if "id" in adv}
            dep_adv_ids = {
                adv["id"]
                for node in enriched_nodes
                for adv in node.get("advisoryKeys", [])
                if "id" in adv
            }
            advisory_ids = root_adv_ids | dep_adv_ids

            advisories_payload = []
            for adv_id in advisory_ids:
                try:
                    adv_data = fetch_with_retry(f"{BASE_URL}/advisories/{quote(adv_id, safe='')}")
                    advisories_payload.append(adv_data)
                except Exception as exc:
                    logging.error(f"Failed to fetch advisory {adv_id}: {exc}")

            if advisories_payload:
                write_to_adls(
                    service_client,
                    {
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                        "source": "deps.dev",
                        "package_key": {"system": system, "name": name, "version": version},
                        "advisories": advisories_payload,
                    },
                    date_str, system, name, folder="advisories",
                )

            success += 1
            logging.info(f"✓ {system}/{name}@{version}")

        except Exception as exc:
            errors += 1
            logging.error(f"✗ {system}/{name}@{version}: {exc}")

    logging.info(f"Phase 1 done. Success: {success} | Errors: {errors}")

    if errors == len(PACKAGES):
        logging.error("All packages failed — aborting pipeline before dbt.")
        return

    logging.info("── Phase 2: Transformation (dbt) ──")

    tmp_path = None
    try:
        tmp_path = prepare_dbt_tmp()
        bronze_path = download_adls_data(service_client, tmp_path, date_str)
        models_dir = os.path.join(tmp_path, "models", "silver")
        for sql_file in os.listdir(models_dir):
            if not sql_file.endswith(".sql"):
                continue
            fpath = os.path.join(models_dir, sql_file)
            with open(fpath, "r") as f:
                content = f.read()
            content = content.replace("az://bronze/", bronze_path + "/")
            content = content.replace("*/*.json", date_str + "/*.json")
            with open(fpath, "w") as f:
                f.write(content)

        if not run_dbt_deps(tmp_path):
            logging.error("dbt deps failed — cannot proceed without packages.")
            return

        if not run_dbt("silver.*", tmp_path):
            logging.error("dbt silver failed — skipping gold models.")
            return

        if not run_dbt("gold.*", tmp_path):
            logging.error("dbt gold failed.")
            return

        duckdb_file = os.path.join(tmp_path, "eeip.duckdb")
        if not export_gold_to_adls(service_client, duckdb_file, tmp_path):
            logging.error("Failed to export gold Parquets to ADLS.")
            return

        logging.info("── Phase 3: Data Quality (dbt test) ──")
        tests_ok = run_dbt_tests(tmp_path)

        if tests_ok:
            logging.info("═══ EEIP Pipeline completed successfully ═══")
        else:
            logging.warning("═══ Pipeline completed with test failures — check Gold layer ═══")
    except Exception as exc:
        logging.error(f"Phase 2 failed: {exc}")
    finally:
        if tmp_path:
            cleanup_dbt_tmp(tmp_path)
