from datetime import timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.utils.dates import days_ago

ALERT_EMAIL = Variable.get("eeip_alert_email")
INGESTION_FUNCTION_URL = Variable.get("eeip_ingestion_function_url")


default_args = {
    "owner": "eeip",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email": [ALERT_EMAIL],
    "email_on_failure": True,
    "email_on_retry": False,
}


with DAG(
    dag_id="eeip_pipeline",
    default_args=default_args,
    description="EEIP pipeline orchestration",
    schedule="10 8 */3 * *",
    start_date=days_ago(1),
    catchup=False,
    tags=["eeip", "supply-chain", "deps-dev"],
) as dag:
    trigger_ingestion = SimpleHttpOperator(
        task_id="trigger_ingestion",
        method="POST",
        endpoint=INGESTION_FUNCTION_URL,
        http_conn_id=None,
        log_response=True,
    )

    dbt_silver = BashOperator(
        task_id="dbt_silver",
        bash_command="dbt run --select silver.*",
        cwd="/opt/dbt",
    )

    dbt_gold = BashOperator(
        task_id="dbt_gold",
        bash_command="dbt run --select gold.*",
        cwd="/opt/dbt",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command="dbt test",
        cwd="/opt/dbt",
    )

    trigger_ingestion >> dbt_silver >> dbt_gold >> dbt_test
