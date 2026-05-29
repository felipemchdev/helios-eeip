import os
import tempfile
import textwrap

from azure.storage.blob import BlobServiceClient

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Helios EEIP",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp { background: linear-gradient(160deg, #FFF3E4 0%, #FFE8D0 30%, #FDE2C3 60%, #FDD9B5 100%); }
    header[data-testid="stHeader"] { background: #E8C895; }
    [data-testid="stSidebar"] { background: #FFECD6; border-right: 1px solid #F5C892; }
    [data-testid="stSidebar"] * { color: #6B4C30 !important; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    h1 { font-size:2rem!important; color:#4A2818!important; }
    h2 { font-size:1.3rem!important; color:#5C3D28!important; }
    [data-testid="stSidebar"] h2 { font-size:1.55rem!important; }
    h3,h4 { color:#6B4C30!important; }
    hr { border-color:#F0CDA0!important; border-width:1px!important; }

    .badge-crit { background:#DC3C32; color:#fff; border-radius:4px; padding:2px 10px; font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; }
    .badge-high { background:#E07010; color:#fff; border-radius:4px; padding:2px 10px; font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; }
    .badge-med { background:#CA9C00; color:#fff; border-radius:4px; padding:2px 10px; font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; }
    .badge-low { background:#4A9058; color:#fff; border-radius:4px; padding:2px 10px; font-size:0.7rem; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; }
    .badge-ok { background:#5A9A6E; color:#fff; border-radius:4px; padding:2px 10px; font-size:0.7rem; font-weight:700; text-transform:uppercase; }

    .pkg-card { background:rgba(255,255,255,0.78); border:1px solid #F0CDA0; border-radius:10px; padding:20px 24px; margin-bottom:14px; box-shadow:0 2px 8px rgba(200,140,70,0.06); }
    .pkg-card.critical { border-left:5px solid #DC3C32; }
    .pkg-card.high { border-left:5px solid #E07010; }
    .pkg-card.medium { border-left:5px solid #CA9C00; }
    .pkg-card.low { border-left:5px solid #4A9058; }

    .chain-line { color:#7A5A3E; font-size:0.82rem; background:rgba(200,140,70,0.08); padding:6px 12px; border-radius:6px; margin:4px 0; display:inline-block; font-family:monospace; }
    .blast-num { font-size:1.1rem; color:#4A2818; font-weight:700; }
    .blast-label { font-size:0.72rem; color:#A08060; text-transform:uppercase; }
    .recommend-box { background:rgba(74,144,88,0.08); border:1px solid rgba(74,144,88,0.2); border-radius:6px; padding:8px 12px; margin-top:8px; font-size:0.8rem; color:#3A7048; }
    .recommend-box-med { background:rgba(200,160,60,0.08); border:1px solid rgba(200,160,60,0.2); border-radius:6px; padding:8px 12px; margin-top:8px; font-size:0.8rem; color:#8A7020; }
    .recommend-box-low { background:rgba(100,180,130,0.08); border:1px solid rgba(100,180,130,0.2); border-radius:6px; padding:8px 12px; margin-top:8px; font-size:0.8rem; color:#3A7048; }

    [data-testid="stMetric"] { background:rgba(255,255,255,0.75); border:1px solid #F5C892; border-radius:12px; padding:12px 16px!important; box-shadow:0 2px 8px rgba(200,140,70,0.06); }
    [data-testid="stMetricValue"] { font-size:1.6rem!important; font-weight:700!important; color:#4A2818!important; }
    [data-testid="stMetricLabel"] { color:#A08060!important; font-size:0.72rem!important; text-transform:uppercase; letter-spacing:0.05em; }

    [data-testid="stExpander"] { background:rgba(255,255,255,0.65); border:1px solid #F0CDA0; border-radius:10px; }

    /* Multiselect tag chips */
    [data-baseweb="tag"],span[data-baseweb="tag"],[data-testid="stMultiSelect"] [data-baseweb="tag"] {
        background:#A8D5B5!important; color:#2D5A3C!important; border:1px solid #7ABD90!important; border-radius:6px!important;
    }
    [data-baseweb="tag"] span,[data-baseweb="tag"] * { color:#2D5A3C!important; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────
SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

def sev_badge(s):
    m = {"CRITICAL": "badge-crit", "HIGH": "badge-high", "MEDIUM": "badge-med", "LOW": "badge-low"}
    return f'<span class="{m.get(s,"badge-ok")}">{s}</span>'

def sev_icon(s):
    return "🔴" if s in ("CRITICAL","HIGH") else "🟠" if s=="MEDIUM" else "🟢"

def sev_class(s):
    return "critical" if s=="CRITICAL" else s.lower()

# ── Data loading ──────────────────────────────────────────────────────
def _download_pq(blob_path):
    conn_str = os.getenv("ADLS_CONNECTION_STRING")
    if not conn_str:
        raise RuntimeError("ADLS_CONNECTION_STRING not set")
    svc = BlobServiceClient.from_connection_string(conn_str)
    bc = svc.get_blob_client(container="gold", blob=blob_path)
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
        try:
            tmp.write(bc.download_blob().readall())
        except Exception:
            pass
        return tmp.name

@st.cache_data(ttl=600)
def load_risk():
    p = _download_pq("fct_dependency_risk/fct_dependency_risk.parquet")
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_dim():
    p = _download_pq("dim_dependency_chain/dim_dependency_chain.parquet")
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=600)
def load_edges():
    p = _download_pq("dim_dependency_edges/dim_dependency_edges.parquet")
    try:
        return pd.read_parquet(p)
    except Exception:
        return pd.DataFrame()

try:
    risk_df = load_risk()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

if risk_df.empty:
    st.info("No data. Pipeline may not have run yet.")
    st.stop()

dim_df = load_dim()
edges_df = load_edges()

# ── Sidebar ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## Filter")
    st.divider()
    ecosystems = sorted(risk_df["root_ecosystem"].dropna().unique())
    selected_eco = st.multiselect("Ecosystem", options=ecosystems, default=ecosystems)
    sev_opts = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    selected_sev = st.multiselect("Minimum severity", options=sev_opts, default=["CRITICAL","HIGH","MEDIUM"])
    st.divider()
    st.caption("Severity guide")
    st.markdown('<span class="badge-crit">CRITICAL</span> &nbsp; Fix now', unsafe_allow_html=True)
    st.markdown('<span class="badge-high">HIGH</span> &nbsp; This sprint', unsafe_allow_html=True)
    st.markdown('<span class="badge-med">MEDIUM</span> &nbsp; Schedule', unsafe_allow_html=True)
    st.markdown('<span class="badge-low">LOW</span> &nbsp; Monitor', unsafe_allow_html=True)

risk_df = risk_df[risk_df["root_ecosystem"].isin(selected_eco)]

if risk_df.empty:
    st.warning("No packages match.")
    st.stop()

# ── Header + KPIs ─────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("# ☀️ Helios EEIP")
st.markdown(
    '<span style="color:#9A8065;font-size:0.9rem;">'
    'What would happen if you installed this package? - Full dependency risk analysis.</span>',
    unsafe_allow_html=True)
st.divider()

c1,c2,c3,c4,c5 = st.columns(5)

n_pkgs = int(risk_df["root_package"].nunique())
n_deps = int(risk_df["total_dep_count"].sum())

if not dim_df.empty:
    fdim = dim_df[dim_df["root_package"].isin(risk_df["root_package"])]
    vulns = fdim[fdim["advisory_id"].notna() & fdim["severity"].isin(selected_sev)].drop_duplicates(subset=["root_package","cve_id"])
    n_vulns = int(vulns["cve_id"].nunique())
    n_crit = int(vulns[vulns["severity"]=="CRITICAL"]["cve_id"].nunique())
    n_high = int(vulns[vulns["severity"]=="HIGH"]["cve_id"].nunique())
    n_affected = int(vulns["root_package"].nunique())
else:
    n_vulns = int(risk_df["total_advisory_exposure"].sum())
    n_crit = 0
    n_high = int(risk_df["critical_dep_count"].sum())
    n_affected = int((risk_df["risk_level"].isin(["HIGH","MEDIUM"])).sum())

c1.metric("Packages", str(n_pkgs))
c2.metric("Dependencies", str(n_deps))
c3.metric("Vulnerabilities", str(n_vulns))
c4.metric("Critical", str(n_crit))
c5.metric("Affected Pkgs", str(n_affected))
st.divider()

# ── 🚫 PACKAGE IMPACT ANALYSIS ─────────────────────────────────────────
st.markdown("## Package Impact Analysis")
st.caption("Click any package to see exactly what happens if you install it.")

packages = risk_df.sort_values("total_advisory_exposure", ascending=False)

# ── Build HTML cards list, then render once ──
cards_html = []

for _, pkg in packages.iterrows():
    pn = pkg["root_package"]
    eco = pkg["root_ecosystem"]
    sev = pkg["risk_level"]
    icon = sev_icon(sev)
    dc = pkg["direct_dep_count"]
    tc = pkg["transitive_dep_count"]

    impact_html = ""
    if not dim_df.empty:
        dpkg = dim_df[
            (dim_df["root_package"] == pn)
            & dim_df["advisory_id"].notna()
            & dim_df["severity"].isin(selected_sev)
        ].drop_duplicates(subset=["cve_id"]).sort_values(by="severity", key=lambda x: x.map(SEV_ORDER))

        # Derive actual severity from CVEs, not density ratio
        actual_sevs = dpkg["severity"].dropna().unique().tolist()
        for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if s in actual_sevs:
                sev = s
                icon = sev_icon(sev)
                break

        n_crit_pkg = int(dpkg[dpkg["severity"]=="CRITICAL"]["cve_id"].nunique())
        n_high_pkg = int(dpkg[dpkg["severity"]=="HIGH"]["cve_id"].nunique())
        n_med_pkg = int(dpkg[dpkg["severity"]=="MEDIUM"]["cve_id"].nunique())
        n_trans_vulns = int(dpkg[dpkg["is_direct"]==False]["cve_id"].nunique())

        vuln_deps = dpkg[dpkg["is_direct"]==False][["dep_name","dep_version","cve_id"]].drop_duplicates()
        blast_count = 0
        if not vuln_deps.empty and not dim_df.empty:
            for _, vd in vuln_deps.iterrows():
                others = dim_df[
                    (dim_df["dep_name"] == vd["dep_name"])
                    & (dim_df["dep_version"] == vd["dep_version"])
                    & (dim_df["cve_id"] == vd["cve_id"])
                    & (dim_df["root_package"] != pn)
                ]
                blast_count += others["root_package"].nunique()

        sample_chain = ""
        if not edges_df.empty:
            top_vuln = dpkg.head(1)
            if not top_vuln.empty:
                vuln_dep = top_vuln.iloc[0]
                vdep_name = vuln_dep["dep_name"]
                chain_edges = edges_df[
                    (edges_df["root_package"] == pn)
                    & (edges_df["dep_name"] == vdep_name)
                    & (edges_df["cve_id"].notna())
                ].head(5)
                if not chain_edges.empty:
                    chain_parts = []
                    seen = set()
                    for _, ce in chain_edges.iterrows():
                        parent = ce["parent_dep_name"]
                        child = ce["dep_name"]
                        if parent not in seen:
                            chain_parts.append(parent)
                            seen.add(parent)
                        chain_parts.append(child)
                    if chain_parts:
                        chain_str = " → ".join(chain_parts)
                        sample_chain = f'<div class="chain-line">{pn} → {chain_str}</div>'

        wscore = n_crit_pkg * 10 + n_high_pkg * 5 + n_med_pkg * 2

        cve_fragments = ""
        for _, v in dpkg.head(5).iterrows():
            cve_fragments += (
                f'<div style="margin:6px 0;font-size:0.84rem;">'
                f'{sev_icon(v["severity"])} <b>{v["cve_id"]}</b> '
                f'<span style="color:#9A8065;">{v["title"][:120]}{"..." if len(str(v["title"]))>120 else ""}</span><br>'
                f'<span style="font-size:0.75rem;color:#A08060;">'
                f'via <b>{v["dep_name"]}@{v["dep_version"]}</b>'
            )
            if not v["is_direct"]:
                cve_fragments += ' <span style="color:#E07010;font-weight:600;">(transitive)</span>'
            if v["cvss3_score"] and v["cvss3_score"] > 0:
                cve_fragments += f' &middot; CVSS {v["cvss3_score"]:.1f}'
            cve_fragments += '</span></div>'

        rec = {
            'LOW':    '<div class="recommend-box-low">💚 <b>Recommendation:</b> Install normally. The vulnerabilities present are not exploitable in typical deployments and pose minimal risk.</div>',
            'MEDIUM': '<div class="recommend-box-med">⚠️ <b>Recommendation:</b> Install only if you are aware of the impact. Avoid if your project handles sensitive data or is exposed to untrusted inputs.</div>',
            'HIGH':   '<div class="recommend-box">💡 <b>Recommendation:</b> Fix or avoid this package entirely until transitive vulnerabilities are resolved — it poses real risk to production systems.</div>',
        }.get(sev, '<div class="recommend-box">💡 <b>Recommendation:</b> Fix or avoid this package until transitive vulnerabilities are resolved.</div>')

        impact_html = (
            f'<div style="margin-top:12px;padding:12px 16px;background:rgba(200,140,70,0.06);border-radius:8px;">'
            f'<div style="display:flex;gap:32px;flex-wrap:wrap;margin-bottom:8px;">'
            f'<div><span class="blast-num">{n_crit_pkg+n_high_pkg}</span><br><span class="blast-label">Critical/High CVEs</span></div>'
            f'<div><span class="blast-num">{n_trans_vulns}</span><br><span class="blast-label">Transitive vulns</span></div>'
            f'<div><span class="blast-num">{blast_count}</span><br><span class="blast-label">Blast radius*</span></div>'
            f'<div><span class="blast-num">{wscore}</span><br><span class="blast-label">Risk score</span></div>'
            f'</div>'
            f'{sample_chain}'
            f'<div style="margin-top:10px;">'
            f'<div style="font-size:0.78rem;color:#9A8065;text-transform:uppercase;letter-spacing:0.04em;">Top vulnerabilities:</div>'
            f'{cve_fragments}'
            f'</div>'
            f'{rec}'
            f'</div>'
        )
    else:
        impact_html = (
            f'<div style="margin-top:12px;">'
            f'<span style="color:#9A8065;">{int(pkg["total_advisory_exposure"])} advisories, {int(pkg["critical_dep_count"])} critical deps.</span>'
            f'</div>'
        )

    cards_html.append(
        f'<div class="pkg-card {sev_class(sev)}" style="cursor:default;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<div style="flex:1;">'
        f'<span style="font-size:1.1rem;color:#3E2A1A;font-weight:600;">{icon} {pn}</span>'
        f'<span style="color:#9A8065;font-size:0.8rem;margin-left:10px;">{eco}</span>'
        f'<span style="color:#9A8065;font-size:0.8rem;margin-left:6px;">· {int(dc)}+{int(tc)} deps</span>'
        f'</div>'
        f'<div>{sev_badge(sev)}</div>'
        f'</div>'
        f'{impact_html}'
        f'</div>'
    )

st.markdown("\n".join(cards_html), unsafe_allow_html=True)
st.divider()

# ── ✅ SAFE PACKAGES ──────────────────────────────────────────────────
safe = risk_df[risk_df["risk_level"] == "LOW"].sort_values("total_dep_count")
if not safe.empty:
    st.markdown("## Safe to install")
    st.caption("These packages have no known advisories in their dependency tree.")
    cols = st.columns(min(len(safe), 4))
    for i, (_, p) in enumerate(safe.iterrows()):
        with cols[i % 4]:
            st.markdown(
                '<div style="background:rgba(100,180,130,0.1);border:1px solid rgba(100,180,130,0.25);border-radius:8px;padding:12px 16px;margin-bottom:8px;">'
                f'<span style="font-size:0.95rem;color:#3E2A1A;font-weight:600;">{p["root_package"]}</span><br>'
                f'<span style="font-size:0.75rem;color:#7A9A6E;">{p["root_ecosystem"]} · {int(p["total_dep_count"])} deps</span><br>'
                f'<span class="badge-ok">SAFE</span>'
                f'</div>',
                unsafe_allow_html=True)
    st.divider()

# ── 🌐 BLAST RADIUS VIEW ──────────────────────────────────────────────
if not dim_df.empty and not edges_df.empty:
    st.markdown("## Blast Radius - Shared Vulnerable Dependencies")
    st.caption("Vulnerable transitive dependencies that affect multiple packages across your ecosystem.")

    vuln_edges = edges_df[edges_df["cve_id"].notna()].drop_duplicates(subset=["dep_name","dep_version","cve_id"])
    vuln_counts = vuln_edges.groupby(["dep_name","dep_version","cve_id","severity"]).agg(
        affected_packages=("root_package","nunique"),
        root_list=("root_package", lambda x: list(x.unique()[:5]))
    ).reset_index().sort_values(by="severity", key=lambda x: x.map(SEV_ORDER))

    for _, vrow in vuln_counts.head(10).iterrows():
        sv = vrow["severity"]
        affected = vrow["affected_packages"]
        pkg_list = ", ".join(vrow["root_list"])
        st.markdown(
            f'<div style="background:rgba(255,255,255,0.72);border:1px solid #F0CDA0;'
            f'border-left:5px solid {"#DC3C32" if sv == "CRITICAL" else "#E07010" if sv == "HIGH" else "#CA9C00"};'
            f'border-radius:8px;padding:12px 18px;margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div><b>{vrow["dep_name"]}@{vrow["dep_version"]}</b>'
            f'<span style="color:#9A8065;margin-left:8px;">{vrow["cve_id"]}</span>'
            f'<div style="font-size:0.8rem;color:#A08060;margin-top:2px;">Affects: {pkg_list}</div></div>'
            f'<div style="text-align:right;">'
            f'<span class="blast-num">{affected}</span><br>'
            f'<span class="blast-label">packages</span><br>'
            f'{sev_badge(sv)}</div></div></div>',
            unsafe_allow_html=True)

    st.divider()

# ── 🔬 CVE DETAIL EXPLORER ────────────────────────────────────────────
if not dim_df.empty:
    st.markdown("## CVE Explorer")
    st.caption("Click any CVE for full details, affected packages, and transitive chains.")

    all_cves = (
        dim_df[dim_df["advisory_id"].notna() & dim_df["severity"].isin(selected_sev)]
        .drop_duplicates(subset=["cve_id"])
        .sort_values(by="severity", key=lambda x: x.map(SEV_ORDER))
    )

    if not all_cves.empty:
        for _, cve in all_cves.iterrows():
            cid = cve["cve_id"]
            sv = cve["severity"]
            title = cve["title"]
            cvs = cve["cvss3_score"]

            with st.expander(f"{sev_icon(sv)} {cid} - {str(title)[:100]}", expanded=False):
                col_a, col_b = st.columns([1, 2])
                with col_a:
                    st.markdown(f"{sev_badge(sv)}", unsafe_allow_html=True)
                    if cvs and cvs > 0:
                        st.metric("CVSS Score", f"{cvs:.1f}")
                    affected_rows = dim_df[
                        (dim_df["cve_id"] == cid)
                    ].drop_duplicates(subset=["root_package", "dep_name"])
                    st.markdown(f"**{affected_rows['root_package'].nunique()}** affected packages")
                    st.markdown(f"**{affected_rows['dep_name'].nunique()}** affected dependencies")

                with col_b:
                    st.markdown(f"**{title}**")
                    st.caption("Affected dependency chains:")

                    for _, ar in affected_rows.head(5).iterrows():
                        chain = f"{ar['root_package']}"
                        if not ar["is_direct"]:
                            if not edges_df.empty:
                                edge_chain = edges_df[
                                    (edges_df["root_package"] == ar["root_package"])
                                    & (edges_df["dep_name"] == ar["dep_name"])
                                    & (edges_df["cve_id"] == cid)
                                ]
                                if not edge_chain.empty:
                                    parts = []
                                    for _, ec in edge_chain.iterrows():
                                        parts.extend([ec["parent_dep_name"], ec["dep_name"]])
                                    if parts:
                                        chain += " → " + " → ".join(dict.fromkeys(parts))
                        chain += f" ({'direct' if ar['is_direct'] else 'transitive'})"
                        st.markdown(f"<div style='color:#7A5A3E;font-size:0.82rem;background:rgba(200,140,70,0.08);padding:6px 12px;border-radius:6px;margin:4px 0;display:inline-block;font-family:monospace;'>{chain}</div>", unsafe_allow_html=True)

                st.markdown(
                    f'<div style="background:rgba(74,144,88,0.08);border:1px solid rgba(74,144,88,0.2);border-radius:6px;padding:8px 12px;margin-top:8px;font-size:0.8rem;color:#3A7048;">'
                    f'💡 <b>Recommendation:</b> Apply the fix for {cid} to affected dependencies. '
                    f'If the vulnerable dependency is transitive, update the root package that introduces it.</div>',
                    unsafe_allow_html=True)

        st.divider()

# ── RADAR ─────────────────────────────────────────────────────────────
st.markdown("## Package Risk Radar")
st.caption("Each bubble is a package. Higher & bigger = more risk. Hover for details.")

radar_data = risk_df.copy()
if not dim_df.empty:
    trans_counts = (
        dim_df[(dim_df["advisory_id"].notna()) & (~dim_df["is_direct"])]
        .groupby("root_package")["cve_id"].nunique().reset_index()
        .rename(columns={"cve_id": "transitive_vulns"})
    )
    radar_data = radar_data.merge(trans_counts, on="root_package", how="left").fillna(0)
else:
    radar_data["transitive_vulns"] = 0

st.scatter_chart(
    radar_data,
    x="total_advisory_exposure",
    y="critical_dep_count",
    size="total_dep_count",
    color="risk_level",
    x_label="Total Advisory Exposure",
    y_label="Critical Dependencies",
)

with st.expander("View raw data"):
    st.dataframe(
        radar_data.sort_values("risk_density", ascending=False)
        .rename(columns={
            "root_package": "Package",
            "root_ecosystem": "Ecosystem",
            "direct_dep_count": "Direct Deps",
            "transitive_dep_count": "Transitive Deps",
            "total_advisory_exposure": "Advisories",
            "critical_dep_count": "Critical Deps",
            "risk_density": "Risk Score",
            "risk_level": "Risk Level",
            "transitive_vulns": "Transitive Vulns",
        })
        .assign(**{"Risk Score": lambda d: d["Risk Score"].round(2)}),
        use_container_width=True,
        hide_index=True,
    )
