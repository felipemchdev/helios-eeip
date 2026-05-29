# ☀️ Helios EEIP — Enterprise Ecosystem Intelligence Platform

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![dbt](https://img.shields.io/badge/dbt-1.7-orange.svg)](https://docs.getdbt.com)
[![DuckDB](https://img.shields.io/badge/DuckDB-embedded-yellow.svg)](https://duckdb.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-latest-red.svg)](https://streamlit.io)
[![Azure](https://img.shields.io/badge/Azure-East%20US-0078D4.svg)](https://azure.microsoft.com)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](./LICENSE)

Helios EEIP is a self-hosted, Azure-native **supply chain security intelligence platform** that ingests open-source package metadata from [deps.dev](https://deps.dev) (Google Open Source Insights), maps the complete transitive dependency graph, cross-references known CVEs, and surfaces actionable risk analytics through an interactive dashboard.

**What you can answer in under 10 seconds:**
- Which packages in my portfolio have CRITICAL or HIGH CVEs in their dependency tree?
- Is the vulnerability direct or transitive? What's the propagation chain?
- What's the blast radius — how many other packages share this same vulnerable dependency?
- Should I install, monitor, or avoid this package right now?

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                          HELIOS EEIP                                  │
├───────────────┬──────────────────────────────────────────────────────┤
│  INGESTION    │  Azure Functions (Python v2)                          │
│               │  Timer trigger every 3 days                           │
│               │  → Pulls deps.dev API for 10+ high-impact packages   │
│               │  → Writes raw JSON to ADLS Gen2 (Bronze)             │
│               │  → Downloads Bronze to local temp storage            │
│               │  → Runs dbt-duckdb: Bronze → Silver → Gold           │
│               │  → Exports Gold tables as Parquet to ADLS            │
├───────────────┼──────────────────────────────────────────────────────┤
│  TRANSFORM    │  dbt 1.7 + DuckDB (embedded OLAP)                    │
│               │  Medallion architecture: Bronze / Silver / Gold       │
│               │  → stg_packages, stg_dependencies, stg_edges          │
│               │  → stg_advisories, stg_dependency_advisories          │
│               │  → dim_dependency_chain, dim_dependency_edges         │
│               │  → fct_dependency_risk (risk score per package)      │
├───────────────┼──────────────────────────────────────────────────────┤
│  STORAGE      │  Azure Data Lake Storage Gen2                          │
│               │  Container: bronze (raw JSON), gold (Parquet)        │
│               │  Hierarchical namespace enabled                       │
├───────────────┼──────────────────────────────────────────────────────┤
│  DASHBOARD    │  Streamlit (Azure Container App, Consumption tier)    │
│               │  → Reads Gold Parquet via pandas/pyarrow              │
│               │  → Package impact cards with severity badges         │
│               │  → CVE details, blast radius, dependency chains       │
│               │  → Bubble chart risk radar                            │
│               │  → Actionable recommendations per severity            │
├───────────────┼──────────────────────────────────────────────────────┤
│  SECURITY     │  Azure Key Vault, Managed Identity, RBAC             │
│  MONITORING   │  Application Insights, Azure Monitor                  │
│  REGISTRY     │  Azure Container Registry (eeipregistry)             │
└───────────────┴──────────────────────────────────────────────────────┘
```

**Cost:** Under R$6 (~$1 USD) per month. Entire stack runs on Azure Consumption tier with scale-to-zero. No VMs. No always-on compute.

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| Ingestion + Orchestration | Azure Functions (Python v2) | 1.18.0 |
| Transformation | dbt + dbt-duckdb adapter | 1.7.4 |
| Execution Engine | DuckDB | embedded |
| Dashboard | Streamlit + pandas + PyArrow | latest |
| Storage | Azure Data Lake Storage Gen2 | — |
| Container Registry | Azure Container Registry | — |
| Secrets | Azure Key Vault | — |
| Auth | Managed Identity (system-assigned) | — |
| Monitoring | Application Insights | — |
| Container Runtime | Azure Container Apps (Consumption) | — |
| External API | deps.dev v3alpha (Google) | — |
| Ecosystems Tracked | PyPI, NPM, Maven | — |
| SQL Dialect | DuckDB | — |
| dbt Packages | dbt_utils | ≥1.0.0, <2.0.0 |

---

## Repository Structure

```
eeip/
├── README.md
├── .gitignore
├── .env.example
│
├── ingestion/                     # Azure Functions (Python v2)
│   ├── function_app.py            # Timer trigger + deps.dev scraper
│   ├── requirements.txt
│   ├── host.json
│   └── transformation/            # embedded dbt project (deployed with Function)
│       ├── dbt_project.yml
│       ├── profiles.yml
│       ├── packages.yml
│       └── models/
│           ├── bronze/sources.yml
│           ├── silver/            # stg_packages, stg_dependencies, stg_edges,
│           │                      # stg_advisories, stg_dependency_advisories
│           └── gold/              # dim_dependency_chain, dim_dependency_edges,
│                                  # fct_dependency_risk, schema.yml
│
├── orchestration/                 # Apache Airflow (legacy — pipeline now self-contained in Function)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── dags/
│       └── eeip_pipeline.py       # Unused — ingestion runs dbt internally
│
├── transformation/                # dbt project (standalone copy)
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml
│   └── models/                    # Same structure as ingestion/transformation/
│
├── dashboard/                     # Streamlit
│   ├── Dockerfile                 # python:3.11-slim
│   ├── app.py                     # Full dashboard with HTML cards
│   ├── requirements.txt           # streamlit, pandas, pyarrow, azure-storage-blob
│   └── fonts/                     # CSS font files (deprecated)
│
└── airflow-config.yaml            # Exported Container App configuration
```

---

## Medallion Architecture

| Layer | Description | Storage |
|---|---|---|
| **Bronze** | Raw JSON from deps.dev, partitioned by `YYYY-MM-DD/ecosystem_package.json` | ADLS: `bronze/raw/deps_dev/` |
| **Silver** | Deduplicated, normalized views — packages, dependencies, edges, advisories | DuckDB views |
| **Gold** | Business-ready tables — dependency chains, dependency edges with CVE mapping, risk per root package | ADLS: `gold/{model}/*.parquet` |

### dbt Models

**Silver:**
| Model | Purpose |
|---|---|
| `stg_packages` | Normalized package + advisory data, deduplicated by `ingested_at DESC` |
| `stg_dependencies` | Unnested dependency graph with direct/indirect classification |
| `stg_dependency_edges` | Parent → child edge resolution from `dependencies.edges[]` |
| `stg_advisories` | CVE metadata with severity derived from CVSS score |
| `stg_dependency_advisories` | Dependency → advisory ID mapping |

**Gold:**
| Model | Purpose |
|---|---|
| `dim_dependency_chain` | Denormalized dependency → advisory chain (root package → dep → CVE) |
| `dim_dependency_edges` | Denormalized edge → advisory chain (parent → child → CVE) |
| `fct_dependency_risk` | Per-package risk metrics: dep counts, advisory exposure, risk density, severity level |

### dbt Data Quality Tests

| Column | Test |
|---|---|
| `root_package` | `not_null`, `unique` |
| `risk_level` | `accepted_values: ['HIGH', 'MEDIUM', 'LOW']` |
| `risk_density` | `not_null`, `>= 0` |
| `total_dep_count` | `not_null`, `>= 1` |

---

## Dashboard Features

The Streamlit dashboard provides a platform operations view of supply chain risk:

**KPI Bar:** Total packages · Total dependencies · Total vulnerabilities · Critical/High count · Affected packages

**Package Impact Analysis:**
- Cards sorted by severity (CRITICAL → HIGH → MEDIUM), with emoji badges
- Severity derived from actual CVE data, not ratio thresholds
- Blast radius: how many other packages share each vulnerable transitive dependency
- Dependency chain visualization: `root → parent → vulnerable_dep` paths
- Top 5 CVEs per package with title, CVSS score, and direct/transitive indicator
- Actionable recommendations per severity: install, monitor, or avoid

**Safe Packages:** Green cards for packages with zero known advisories

**Blast Radius View:** Shared vulnerable dependencies ranked by number of affected packages

**CVE Explorer:** Full per-CVE detail with affected packages, dependency chains, and fix recommendations

**Package Risk Radar:** Bubble chart — X = advisory exposure, Y = critical dependencies, size = total dependencies, color = risk level. Raw data available in expander.

---

## Deployment

### Prerequisites

- Azure CLI 2.x with `az login`
- Docker (for building Container App images)
- Python 3.11 (for local development)

### Dashboard (most common deploy)

```bash
cd eeip/dashboard
docker build -t eeipregistry.azurecr.io/dashboard:vXX .
docker push eeipregistry.azurecr.io/dashboard:vXX
az containerapp update \
  --name eeip-dashboard \
  --resource-group rg-eeip \
  --image eeipregistry.azurecr.io/dashboard:vXX
```

### Ingestion + Transformation (Azure Functions)

```bash
cd eeip/ingestion
func azure functionapp publish eeip-ingestion --python
```

The Function handles everything end-to-end: pulls deps.dev API, downloads bronze from ADLS, runs dbt silver → gold with DuckDB, and exports gold Parquet back to ADLS. No separate orchestrator needed.

---

## Local Development

### 1. Environment

```bash
cp .env.example .env     # Edit with your values
az login                 # Authenticate to Azure
```

### 2. Ingestion

```bash
cd ingestion
pip install -r requirements.txt
curl -X POST http://localhost:7071/admin/functions/ingest_deps_dev
```

### 3. Transformations (dbt)

```bash
cd transformation
pip install dbt-duckdb
dbt deps
dbt run
dbt test
```

### 4. Dashboard

```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

### 5. Airflow (legacy — optional)

```bash
cd orchestration
docker compose up --build -d
# UI at http://localhost:8080
```

> Airflow is no longer part of the active pipeline. The Function runs dbt
> internally and exports gold Parquet to ADLS.

---

## Auth & Security

- **Production:** System-assigned Managed Identity for Function → ADLS and Container Apps → ACR. Secrets in Azure Key Vault.
- **Current dashboard:** `ADLS_CONNECTION_STRING` via environment variable (migration to Managed Identity planned).
- **Development:** `az login` + `DefaultAzureCredential()`. `.env` and `local.settings.json` are in `.gitignore`.

---

## Cost Breakdown

| Resource | Tier | Monthly Cost (est.) |
|---|---|---|
| Azure Functions | Consumption, timer + HTTP trigger | $0.00 (well within free grant) |
| Container Apps (dashboard) | Consumption, 0.5 vCPU, 1 GB, scale-to-zero | ~$0.50 |
| ADLS Gen2 | ~10 MB storage + ~20 writes/run | ~$0.05 |
| Key Vault | Free tier | $0.00 |
| Container Registry | Basic | ~$0.15 |
| **Total** | | **~$1.00 / R$6.00** |

---

## Roadmap

### Phase 1 — Production Hardening
- [ ] Managed Identity for all ADLS access (no connection strings)
- [ ] Terraform/Bicep IaC for all resources
- [ ] GitHub Actions CI/CD pipeline
- [ ] Azure Monitor alert rules

### Phase 2 — Data Enrichment
- [ ] OSV.dev API integration for full CVSS vectors and exploit availability
- [ ] Weighted risk score: severity �- depth in dependency graph �- exploitability
- [ ] dbt incremental models for silver and gold layers
- [ ] Historical snapshot tracking

### Phase 3 — Expansion
- [ ] Dynamic package discovery (scrape top-downloaded, not hardcoded)
- [ ] Additional ecosystems: Go, Cargo, NuGet
- [ ] SBOM export (CycloneDX/SPDX)
- [ ] Slack/Teams notification integration
- [ ] OpenSSF Scorecard metrics

### Phase 4 — Platform
- [ ] REST API layer (FastAPI)
- [ ] Multi-tenant support
- [ ] Replace DuckDB with Databricks/Synapse at scale

---

## License

MIT
