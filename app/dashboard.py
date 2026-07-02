"""ClinicalFlow — Streamlit dashboard (Phase 5).

Reads read-only from the DuckDB store built by the pipeline and surfaces the
cardiovascular cohort analysis plus the data-quality governance layer.

Run:  streamlit run app/dashboard.py   (or `make dashboard` / `.\\make.ps1 dashboard`)
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

from clinicalflow import cohort
from clinicalflow.config import BP_FLAG_DIASTOLIC, BP_FLAG_SYSTOLIC, DB_PATH

st.set_page_config(page_title="ClinicalFlow", page_icon="🫀", layout="wide")


# --------------------------------------------------------------------------- #
# Data access (cached)
# --------------------------------------------------------------------------- #
@st.cache_resource
def get_con():
    if not DB_PATH.exists():
        return None
    return duckdb.connect(str(DB_PATH), read_only=True)


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
        f"Database not found at `{DB_PATH}`.\n\n"
        "Run the pipeline first:  `make all`  (or `.\\make.ps1 all`)."
    )
    st.stop()

m = get_metrics()

section = st.sidebar.radio(
    "Section",
    ["Overview", "Condition prevalence", "Comorbidities", "Medications",
     "Vitals & labs", "Data quality"],
)
st.sidebar.markdown("---")
st.sidebar.metric("Total patients", f"{m['population']:,}")
st.sidebar.metric("CV cohort", f"{m['cohort_size']:,}", f"{m['cohort_pct'] * 100:.1f}% of pop")


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
# 2. Condition prevalence
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
