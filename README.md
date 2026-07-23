# ☀️ Helios EEIP - Enterprise Ecosystem Intelligence Platform
[Dashboard](https://eeip-dashboard.wonderfulbush-04a41aac.eastus.azurecontainerapps.io/) 

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![dbt](https://img.shields.io/badge/dbt-1.7-orange.svg)](https://docs.getdbt.com)
[![DuckDB](https://img.shields.io/badge/DuckDB-embedded-yellow.svg)](https://duckdb.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-latest-red.svg)](https://streamlit.io)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](./LICENSE)

Helios EEIP is a **supply chain security intelligence platform** that ingests open-source package metadata from [deps.dev](https://deps.dev) (Google Open Source Insights), analyzes dependency graphs for transitive vulnerabilities, and exposes critical risks through an interactive dashboard. Runs locally or in production environments.

**What you can answer in under 10 seconds:**
- Which packages in my portfolio have CRITICAL or HIGH CVEs in their dependency tree?
- Is the vulnerability direct or transitive? What's the propagation chain?
- What's the blast radius — how many other packages share this same vulnerable dependency?
- Should I install, monitor, or avoid this package right now?

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                          HELIOS EEIP                            │
├────────────────┬──────────────────────────────────────────────┤
│  INGESTION     │  Timer trigger (local cron or cloud schedule) │
│                │  → Pulls deps.dev API for 10+ high-impact    │
│                │    packages                                   │
│                │  → Writes raw JSON to Bronze layer           │
│                │  → Runs dbt-duckdb: Bronze → Silver → Gold   │
│                │  → Exports Gold tables as Parquet            │
├────────────────┼──────────────────────────────────────────────┤
│  TRANSFORM     │  dbt 1.7 + DuckDB (embedded OLAP)            │
│                │  Medallion architecture: Bronze / Silver / Gold
│                │  → stg_packages, stg_dependencies, stg_edges │
│                │  → stg_advisories, stg_dependency_advisories │
│                │  → dim_dependency_chain, dim_dependency_edges│
│                │  → fct_dependency_risk (risk score per pkg)  │
├────────────────┼──────────────────────────────────────────────┤
│  STORAGE       │  Local filesystem (./data) or cloud blob      │
│                │  Structure: bronze (raw JSON), gold (Parquet)│
├────────────────┼──────────────────────────────────────────────┤
│  DASHBOARD     │  Streamlit (local or containerized)          │
│                │  → Reads Gold Parquet via pandas/pyarrow    │
│                │  → Package impact cards with severity badges│
│                │  → CVE details, blast radius, dep chains    │
│                │  → Bubble chart risk radar                   │
│                │  → Actionable recommendations per severity   │
├────────────────┼──────────────────────────────────────────────┤
│  SECURITY      │  Environment variables / secrets mgmt        │
│  MONITORING    │  Application-level logging                   │
│  REGISTRY      │  Docker container registry (optional)        │
└────────────────┴──────────────────────────────────────────────┘
```

**Cost:** Minimal. Local execution has no external costs beyond internet for deps.dev API. Cloud deployments scale with usage.

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| Ingestion + Orchestration | APScheduler (local) or Functions/Cloud | varies |
| Transformation | dbt + dbt-duckdb adapter | 1.7.4 |
| Execution Engine | DuckDB | embedded |
| Dashboard | Streamlit + pandas + PyArrow | latest |
| Storage | Filesystem (local) or Cloud Blob Storage | — |
| Secrets | Environment variables / Key Vault / Cloud Secrets | — |
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
├── ingestion/                     # Ingestion script (local or cloud)
│   ├── function_app.py            # Timer trigger + deps.dev scraper
│   ├── requirements.txt
│   ├── host.json
│   └── transformation/            # Embedded dbt project
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
├── orchestration/                 # Orchestration examples (local or cloud)
│   ├── Dockerfile                 # Optional containerization
│   ├── docker-compose.yml
│   └── dags/
│       └── eeip_pipeline.py       # Example: Apache Airflow DAG
│
├── transformation/                # dbt project (standalone copy)
│   ├── dbt_project.yml
│   ├── profiles.yml
│   ├── packages.yml
│   └── models/                    # Same structure as ingestion/transformation/
│
├── dashboard/                     # Streamlit application
│   ├── Dockerfile                 # python:3.11-slim
│   ├── app.py                     # Full dashboard with HTML cards
│   ├── requirements.txt           # streamlit, pandas, pyarrow, azure-storage-blob
│   └── fonts/                     # CSS font files (deprecated)
│
└── config.yaml                    # Configuration template
```

---

## Medallion Architecture

| Layer | Description | Storage |
|---|---|---|
| **Bronze** | Raw JSON from deps.dev, partitioned by `YYYY-MM-DD/ecosystem_package.json` | `./data/bronze/` or cloud blob |
| **Silver** | Deduplicated, normalized views — packages, dependencies, edges, advisories | DuckDB views |
| **Gold** | Business-ready tables — dependency chains, dependency edges with CVE mapping, risk per root package | `./data/gold/` or cloud blob |

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

- Python 3.11
- pip or poetry for dependency management
- Docker (optional, for containerized deployment)

### Local Setup (Recommended for Development)

```bash
# 1. Clone and setup
git clone https://github.com/felipemchdev/helios-eeip.git
cd helios-eeip
cp .env.example .env
# Edit .env with your configuration

# 2. Install dependencies
pip install -r ingestion/requirements.txt
pip install -r dashboard/requirements.txt

# 3. Run ingestion locally
cd ingestion
python function_app.py

# 4. Run transformations (dbt)
cd ../transformation
pip install dbt-duckdb
dbt deps
dbt run
dbt test

# 5. Launch dashboard
cd ../dashboard
streamlit run app.py
# Dashboard opens at http://localhost:8501
```

### Docker / Containerized Deployment

```bash
# Build dashboard image
cd dashboard
docker build -t helios-dashboard:latest .
docker run -p 8501:8501 --env-file ../.env helios-dashboard:latest

# Build and run with docker-compose
cd ..
docker-compose up --build
```

### Cloud Deployment (Optional)

For cloud deployments (Azure, AWS, GCP, etc.):
1. Containerize the ingestion and dashboard components
2. Configure storage backend (blob storage, S3, GCS, etc.)
3. Set up cloud scheduler or equivalent for timer-triggered ingestion
4. Configure secrets management service
5. Deploy dashboard to container service of choice

Refer to cloud provider documentation for specific setup.

---

## Local Development

### 1. Environment

```bash
cp .env.example .env     # Edit with your values
```

### 2. Ingestion

```bash
cd ingestion
pip install -r requirements.txt
python function_app.py
# Or trigger via HTTP POST if running locally
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

### 5. Orchestration (Optional)

```bash
cd orchestration
docker compose up --build -d
# Airflow UI at http://localhost:8080
```

> Note: Orchestration is optional. Ingestion can run standalone via
> cron, APScheduler, or cloud timers.

---

## Auth & Security

- **Local:** Environment variables in `.env` (added to `.gitignore`)
- **Production:** Use your cloud provider's secrets management service
  - Azure: Key Vault
  - AWS: Secrets Manager
  - GCP: Secret Manager
- **Development:** `.env` and `local.settings.json` are in `.gitignore`

---

## Cost Breakdown

| Scenario | Estimated Monthly Cost |
|---|---|
| **Local Development** | $0.00 (no external resources) |
| **Local + Cloud Storage** | ~$0.10–$1.00 (storage only) |
| **Cloud Hosted (Minimal)** | ~$1.00–$10.00 (varies by provider) |
| **Cloud Hosted (Production)** | $10–$100+ (depends on scale) |

---

## Roadmap

### Phase 1 — Production Hardening
- [ ] Secrets management integration (all providers)
- [ ] Infrastructure-as-code templates (Terraform, Docker, Helm)
- [ ] CI/CD pipeline (GitHub Actions, GitLab CI, etc.)
- [ ] Monitoring and alerting setup

### Phase 2 — Data Enrichment
- [ ] OSV.dev API integration for full CVSS vectors and exploit availability
- [ ] Weighted risk score: severity × depth in dependency graph × exploitability
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
