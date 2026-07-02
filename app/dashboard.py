"""ClinicalFlow — Streamlit dashboard (Phase 5).

Reads read-only from the DuckDB store built by the pipeline and surfaces the
cardiovascular cohort analysis plus the data-quality governance layer.

Run:  streamlit run app/dashboard.py   (or `make dashboard` / `.\\make.ps1 dashboard`)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the package importable without an editable install (e.g. on Streamlit Cloud).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from clinicalflow import cohort
from clinicalflow.config import BP_FLAG_DIASTOLIC, BP_FLAG_SYSTOLIC, DATA_DIR, DB_PATH

st.set_page_config(page_title="ClinicalFlow", page_icon="🫀", layout="wide")

SLIM_PATH = DATA_DIR / "clinicalflow_slim.duckdb"


def resolve_db() -> Path | None:
    """Prefer the full local DB; fall back to the committed slim demo DB."""
    if DB_PATH.exists():
        return DB_PATH
    if SLIM_PATH.exists():
        return SLIM_PATH
    return None


# --------------------------------------------------------------------------- #
# Data access (cached)
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_con():
    db = resolve_db()
    if db is None:
        return None
    return duckdb.connect(str(db), read_only=True)


@st.cache_data(show_spinner=False)
def pipeline_stats_df() -> pd.DataFrame:
    """Full-scale per-table row counts (from pipeline_stats if present, else live)."""
    con = get_con()
    try:
        return con.execute(
            "SELECT table_name, row_count FROM pipeline_stats ORDER BY row_count DESC"
        ).fetch_df()
    except (duckdb.CatalogException, duckdb.Error):
        tables = ["patients", "encounters", "conditions", "observations",
                  "medications", "procedures"]
        rows = []
        for t in tables:
            try:
                rows.append((t, con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]))
            except duckdb.Error:
                pass
        return pd.DataFrame(rows, columns=["table_name", "row_count"])


@st.cache_data(show_spinner=False)
def get_metrics():
    return cohort.analyze(get_con())


@st.cache_data(show_spinner=False)
def latest_value_df(loinc: str, colname: str) -> pd.DataFrame:
    con = get_con()
    return con.execute(
        f"""
        WITH x AS (
            SELECT o.patient_id, o.value_num,
                   ROW_NUMBER() OVER (PARTITION BY o.patient_id ORDER BY o.effective DESC) rn
            FROM observations o JOIN cv_cohort v USING (patient_id)
            WHERE v.has_cv = 1 AND o.loinc_code = ? AND o.value_num IS NOT NULL
        )
        SELECT value_num AS {colname} FROM x WHERE rn = 1
        """,
        [loinc],
    ).fetch_df()


@st.cache_data(show_spinner=False)
def qa_df() -> pd.DataFrame:
    con = get_con()
    return con.execute(
        "SELECT check_name, subject, status, observed, threshold, violations, total "
        "FROM qa_results"
    ).fetch_df()


# --------------------------------------------------------------------------- #
# Guard: DB must exist
# --------------------------------------------------------------------------- #
con = get_con()
st.title("🫀 ClinicalFlow")
st.caption(
    "FHIR R4 EHR pipeline · cardiovascular cohort · data governance — "
    "**synthetic Synthea data, no PHI**"
)

if con is None:
    st.error(
        "Database not found.\n\n"
        "Run the pipeline first: `make all` (builds the full DB), or "
        "`python -m clinicalflow.slim` to build the committed demo DB."
    )
    st.stop()

m = get_metrics()

section = st.sidebar.radio(
    "Section",
    ["Overview", "Pipeline", "Condition prevalence", "Comorbidities",
     "Medications", "Vitals & labs", "Data quality"],
)
st.sidebar.markdown("---")
st.sidebar.metric("Total patients", f"{m['population']:,}")
st.sidebar.metric("CV cohort", f"{m['cohort_size']:,}", f"{m['cohort_pct'] * 100:.1f}% of pop")
if resolve_db() == SLIM_PATH:
    st.sidebar.caption("📦 Demo mode — running on the slim committed database.")


# --------------------------------------------------------------------------- #
# 1. Overview
# --------------------------------------------------------------------------- #
if section == "Overview":
    st.header("Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total population", f"{m['population']:,}")
    c2.metric("Cardiovascular cohort", f"{m['cohort_size']:,}")
    c3.metric("Cohort share", f"{m['cohort_pct'] * 100:.1f}%")
    c4.metric("Mean age", f"{m['age_mean']:.1f} yrs")

    left, right = st.columns(2)
    with left:
        st.subheader("Sex distribution (cohort)")
        sex_df = pd.DataFrame(m["sex"], columns=["sex", "patients"])
        fig = px.pie(sex_df, names="sex", values="patients", hole=0.45)
        fig.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Age distribution (cohort)")
        age_df = pd.DataFrame(m["age_buckets"], columns=["age_band", "patients"])
        fig = px.bar(age_df, x="age_band", y="patients", text="patients")
        fig.update_layout(margin=dict(t=10, b=10), xaxis_title="", yaxis_title="patients")
        st.plotly_chart(fig, use_container_width=True)

    diab_n, diab_pct = m["diabetes"]
    st.info(f"**Diabetes within cohort:** {diab_n:,} patients ({diab_pct * 100:.1f}%), "
            "tracked as a cardiovascular risk factor.")


# --------------------------------------------------------------------------- #
# 2. Pipeline (ingest → quality → cohort, visualized)
# --------------------------------------------------------------------------- #
elif section == "Pipeline":
    st.header("Pipeline — FHIR → DuckDB → QA → Cohort")
    st.caption("How raw synthetic FHIR bundles become the analysis below.")

    # Flow as a row of cards.
    steps = [
        ("📁 FHIR R4 bundles", "3,450 synthetic patients\n(Synthea, seed 1234)"),
        ("⚙️ Ingest", "resolve refs · split BP\ncomponents · 6 tables"),
        ("🗄️ DuckDB", "normalized SQL store"),
        ("✅ Quality", "28 checks · error budget"),
        ("🫀 Cohort", "cardiovascular\npopulation-health"),
    ]
    cols = st.columns(len(steps) * 2 - 1)
    for i, (title, body) in enumerate(steps):
        with cols[i * 2]:
            st.markdown(f"**{title}**")
            st.caption(body)
        if i < len(steps) - 1:
            cols[i * 2 + 1].markdown(
                "<div style='text-align:center;font-size:1.6rem;padding-top:6px'>→</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # Ingest scale — real full-DB row counts.
    st.subheader("① Ingest — normalized tables & scale")
    stats = pipeline_stats_df()
    total_rows = int(stats["row_count"].sum())
    obs_rows = int(stats.loc[stats.table_name == "observations", "row_count"].iloc[0])
    c = st.columns(4)
    c[0].metric("FHIR resource types", "6")
    c[1].metric("DuckDB tables", f"{len(stats)}")
    c[2].metric("Total rows ingested", f"{total_rows:,}")
    c[3].metric("Observations", f"{obs_rows:,}")
    fig = px.bar(stats, x="row_count", y="table_name", orientation="h", text="row_count",
                 log_x=True, title="Rows per table (log scale)")
    fig.update_layout(margin=dict(t=40), xaxis_title="rows (log)", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Quality summary.
    st.subheader("② Quality — data governance contract")
    q = qa_df()
    passed = int((q["status"] == "pass").sum())
    failed = int((q["status"] == "fail").sum())
    c = st.columns(3)
    c[0].metric("Checks", f"{len(q)}")
    c[1].metric("Passed", f"{passed}")
    c[2].metric("Failed", f"{failed}", delta_color="inverse")
    fam = (q.assign(pass_=(q["status"] == "pass"))
             .groupby("check_name")
             .agg(checks=("status", "size"), passed=("pass_", "sum"))
             .reset_index().rename(columns={"check_name": "check family"}))
    st.dataframe(fam, hide_index=True, use_container_width=True)
    st.caption("A check fails when violations exceed a 1% error budget (configurable). "
               "See the **Data quality** section for the full table.")

    st.divider()

    # Cohort funnel.
    st.subheader("③ Cohort — from population to cardiovascular cohort")
    funnel = pd.DataFrame({
        "stage": ["Total population", "Cardiovascular cohort"],
        "patients": [m["population"], m["cohort_size"]],
    })
    fig = px.funnel(funnel, x="patients", y="stage")
    fig.update_layout(margin=dict(t=10), yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"{m['cohort_size']:,} of {m['population']:,} patients "
               f"({m['cohort_pct'] * 100:.1f}%) have ≥1 cardiovascular condition.")


# --------------------------------------------------------------------------- #
# 3. Condition prevalence
# --------------------------------------------------------------------------- #
elif section == "Condition prevalence":
    st.header("Cardiovascular condition prevalence")
    df = pd.DataFrame(m["prevalence"], columns=["condition", "patients", "pct_cohort", "pct_pop"])
    df["% of cohort"] = df["pct_cohort"] * 100
    fig = px.bar(
        df.sort_values("patients"), x="patients", y="condition", orientation="h",
        text="patients", hover_data={"% of cohort": ":.1f"},
    )
    fig.update_layout(xaxis_title="patients in cohort", yaxis_title="", margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(
        df[["condition", "patients", "pct_cohort", "pct_pop"]]
        .assign(**{"% of cohort": (df["pct_cohort"] * 100).round(1),
                   "% of population": (df["pct_pop"] * 100).round(1)})
        [["condition", "patients", "% of cohort", "% of population"]],
        hide_index=True, use_container_width=True,
    )


# --------------------------------------------------------------------------- #
# 3. Comorbidities
# --------------------------------------------------------------------------- #
elif section == "Comorbidities":
    st.header("Comorbidity co-occurrence")
    st.caption("Cell = patients having **both** conditions (diagonal = total with that condition).")
    labels = m["comorbidity_labels"]
    mat = m["comorbidity_matrix"]
    fig = px.imshow(
        mat, x=labels, y=labels, text_auto=True, color_continuous_scale="Blues", aspect="auto",
    )
    fig.update_layout(margin=dict(t=10), coloraxis_showscale=True)
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------- #
# 4. Medications
# --------------------------------------------------------------------------- #
elif section == "Medications":
    st.header("Medication patterns (cohort)")
    df = pd.DataFrame(m["med_classes"], columns=["drug_class", "patients", "pct"])
    df["% of cohort"] = (df["pct"] * 100).round(1)
    fig = px.bar(df, x="drug_class", y="patients", text="patients",
                 hover_data={"% of cohort": True})
    fig.update_layout(xaxis_title="", yaxis_title="patients on ≥1", margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df[["drug_class", "patients", "% of cohort"]],
                 hide_index=True, use_container_width=True)


# --------------------------------------------------------------------------- #
# 5. Vitals & labs
# --------------------------------------------------------------------------- #
elif section == "Vitals & labs":
    st.header("Vitals & labs — latest value per cohort patient")
    bp, chol = m["bp"], m["chol"]

    c1, c2, c3 = st.columns(3)
    c1.metric("Median systolic", f"{bp['sys_median']:.0f} mmHg")
    c2.metric("Median diastolic", f"{bp['dia_median']:.0f} mmHg")
    c3.metric(f"BP ≥ {BP_FLAG_SYSTOLIC}/{BP_FLAG_DIASTOLIC}",
              f"{bp['flag_count']:,}", f"{bp['flag_pct'] * 100:.1f}% of cohort")

    sys_df = latest_value_df(cohort.LOINC_SYSTOLIC, "systolic")
    dia_df = latest_value_df(cohort.LOINC_DIASTOLIC, "diastolic")
    left, right = st.columns(2)
    with left:
        st.subheader("Latest systolic BP")
        fig = px.histogram(sys_df, x="systolic", nbins=40)
        fig.add_vline(x=BP_FLAG_SYSTOLIC, line_dash="dash", line_color="red")
        fig.update_layout(margin=dict(t=10), xaxis_title="mmHg")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Latest diastolic BP")
        fig = px.histogram(dia_df, x="diastolic", nbins=40)
        fig.add_vline(x=BP_FLAG_DIASTOLIC, line_dash="dash", line_color="red")
        fig.update_layout(margin=dict(t=10), xaxis_title="mmHg")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Latest total cholesterol")
    chol_df = latest_value_df(cohort.LOINC_CHOLESTEROL, "cholesterol")
    fig = px.histogram(chol_df, x="cholesterol", nbins=40)
    fig.update_layout(margin=dict(t=10), xaxis_title="mg/dL")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Cholesterol (n={chol['n']:,}): mean {chol['mean']:.1f}, median {chol['median']:.1f}, "
        f"IQR [{chol['p25']:.1f}, {chol['p75']:.1f}] mg/dL."
    )


# --------------------------------------------------------------------------- #
# 6. Data quality
# --------------------------------------------------------------------------- #
elif section == "Data quality":
    st.header("Data quality & governance")
    df = qa_df()
    passed = int((df["status"] == "pass").sum())
    failed = int((df["status"] == "fail").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Checks", f"{len(df)}")
    c2.metric("Passed", f"{passed}")
    c3.metric("Failed", f"{failed}", delta_color="inverse")

    if failed == 0:
        st.success("All checks pass the error-budget contract.")
    else:
        st.warning(f"{failed} check(s) exceed the error budget.")

    show = df.copy()
    show["rate"] = (show["observed"] * 100).round(2).astype(str) + "%"
    show["budget"] = (show["threshold"] * 100).round(0).astype(int).astype(str) + "%"
    show = show.rename(columns={"check_name": "check"})[
        ["check", "subject", "status", "violations", "total", "rate", "budget"]
    ]

    def _hl(row):
        color = "#e6ffed" if row["status"] == "pass" else "#ffe6e6"
        return [f"background-color: {color}"] * len(row)

    st.dataframe(show.style.apply(_hl, axis=1), hide_index=True, use_container_width=True)
