"""Phase 4: cardiovascular cohort definition and population-health analysis.

Condition and medication mappings below were derived by *querying the distinct
codes/displays actually present in the data* (see README), not guessed. The
cohort is patients with >= 1 condition in any cardiovascular category; diabetes
is tracked as a comorbidity/risk factor rather than a defining condition.
"""
from __future__ import annotations

import duckdb
import pandas as pd

from .config import BP_FLAG_DIASTOLIC, BP_FLAG_SYSTOLIC, DB_PATH, get_logger
from .report import write_cohort_report

log = get_logger()

# --------------------------------------------------------------------------- #
# Clinical mappings (SNOMED codes present in this dataset)
# --------------------------------------------------------------------------- #
CV_CONDITIONS: dict[str, set[str]] = {
    "Hypertension": {"59621000"},
    "Coronary/ischemic heart disease": {
        "414545008",  # Ischemic heart disease
        "22298006",   # Myocardial infarction
        "401314000",  # Acute NSTEMI
        "401303003",  # Acute STEMI
        "399211009",  # History of MI
        "399261000",  # History of CABG
    },
    "Heart failure": {"88805009", "84114007"},
    "Stroke/cerebrovascular": {"230690007"},
    "Atrial fibrillation": {"49436004"},
    "Hyperlipidemia": {"55822004"},
}

DIABETES_CODES: set[str] = {
    "44054006",         # Diabetes mellitus type 2
    "127013003", "90781000119102", "157141000119108", "368581000119106",
    "1551000119108", "97331000119101", "1501000119109", "427089005",
    "60951000119105",  # diabetes complications
}

# Flag column name per CV category (safe SQL identifiers).
CV_FLAGS: dict[str, str] = {
    "Hypertension": "hypertension",
    "Coronary/ischemic heart disease": "chd",
    "Heart failure": "heart_failure",
    "Stroke/cerebrovascular": "stroke",
    "Atrial fibrillation": "afib",
    "Hyperlipidemia": "hyperlipidemia",
}

# Medication classes mapped from RxNorm display strings present in the data.
MED_CLASSES: dict[str, list[str]] = {
    "Statins": ["%statin%"],
    "Antihypertensives": [
        "%lisinopril%", "%metoprolol%", "%amlodipine%", "%hydrochlorothiazide%",
        "%losartan%", "%valsartan%", "%carvedilol%", "%atenolol%", "%enalapril%",
        "%ramipril%", "%benazepril%", "%irbesartan%", "%verapamil%", "%diltiazem%",
        "%furosemide%", "%olmesartan%", "%sacubitril%", "%chlorthalidone%",
        "%nifedipine%", "%clonidine%", "%captopril%",
    ],
    "Anticoagulants/antiplatelets": [
        "%warfarin%", "%apixaban%", "%rivaroxaban%", "%dabigatran%", "%edoxaban%",
        "%heparin%", "%enoxaparin%", "%clopidogrel%", "%aspirin%", "%ticagrelor%",
        "%prasugrel%",
    ],
}

# LOINC codes for latest-value analyses.
LOINC_SYSTOLIC = "8480-6"
LOINC_DIASTOLIC = "8462-4"
LOINC_CHOLESTEROL = "2093-3"

AGE_BUCKETS = [(0, 40, "<40"), (40, 55, "40–54"), (55, 65, "55–64"),
               (65, 75, "65–74"), (75, 200, "75+")]


def _in_list(codes: set[str]) -> str:
    return ", ".join(f"'{c}'" for c in codes)


# --------------------------------------------------------------------------- #
# Cohort construction
# --------------------------------------------------------------------------- #
def build_cohort(con) -> None:
    """Create the cv_cohort table: one row per patient with condition flags."""
    flag_exprs = []
    for label, col in CV_FLAGS.items():
        flag_exprs.append(
            f"MAX(CASE WHEN c.snomed_code IN ({_in_list(CV_CONDITIONS[label])}) "
            f"THEN 1 ELSE 0 END) AS {col}"
        )
    flag_exprs.append(
        f"MAX(CASE WHEN c.snomed_code IN ({_in_list(DIABETES_CODES)}) "
        "THEN 1 ELSE 0 END) AS diabetes"
    )
    cv_or = " + ".join(CV_FLAGS.values())

    con.execute("DROP TABLE IF EXISTS cv_cohort")
    con.execute(f"""
        CREATE TABLE cv_cohort AS
        WITH flags AS (
            SELECT p.patient_id, {', '.join(flag_exprs)}
            FROM patients p
            LEFT JOIN conditions c USING (patient_id)
            GROUP BY p.patient_id
        )
        SELECT *, (CASE WHEN ({cv_or}) > 0 THEN 1 ELSE 0 END) AS has_cv
        FROM flags
    """)
    n = con.execute("SELECT COUNT(*) FROM cv_cohort WHERE has_cv = 1").fetchone()[0]
    log.info("Built cv_cohort: %d cardiovascular patients", n)


# --------------------------------------------------------------------------- #
# Analyses
# --------------------------------------------------------------------------- #
def analyze(con) -> dict:
    population = con.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    cohort_size = con.execute("SELECT COUNT(*) FROM cv_cohort WHERE has_cv = 1").fetchone()[0]

    # Sex distribution (cohort).
    sex = con.execute("""
        SELECT COALESCE(p.gender, 'unknown') AS gender, COUNT(*) AS n
        FROM cv_cohort v JOIN patients p USING (patient_id)
        WHERE v.has_cv = 1 GROUP BY 1 ORDER BY n DESC
    """).fetchall()

    # Age (as of death for deceased, else today), bucketed.
    con.execute("""
        CREATE OR REPLACE TEMP VIEW cohort_age AS
        SELECT p.patient_id,
               date_diff('year', p.birth_date,
                         COALESCE(CAST(p.deceased_date AS DATE), current_date)) AS age
        FROM cv_cohort v JOIN patients p USING (patient_id)
        WHERE v.has_cv = 1
    """)
    age_mean = con.execute("SELECT AVG(age) FROM cohort_age").fetchone()[0]
    age_buckets = []
    for lo, hi, label in AGE_BUCKETS:
        n = con.execute(
            "SELECT COUNT(*) FROM cohort_age WHERE age >= ? AND age < ?", [lo, hi]
        ).fetchone()[0]
        age_buckets.append((label, n))

    # Prevalence of each CV condition (+ diabetes) within cohort and population.
    prevalence = []
    for label, col in CV_FLAGS.items():
        n = con.execute(f"SELECT SUM({col}) FROM cv_cohort WHERE has_cv = 1").fetchone()[0] or 0
        prevalence.append((label, int(n), n / cohort_size, n / population))
    diab_n = con.execute("SELECT SUM(diabetes) FROM cv_cohort WHERE has_cv = 1").fetchone()[0] or 0
    diabetes = (int(diab_n), diab_n / cohort_size)

    # Comorbidity co-occurrence matrix (CV categories + diabetes) in pandas.
    cols = list(CV_FLAGS.values()) + ["diabetes"]
    labels = list(CV_FLAGS.keys()) + ["Diabetes"]
    df = con.execute(
        f"SELECT {', '.join(cols)} FROM cv_cohort WHERE has_cv = 1"
    ).fetch_df()
    mat = df.T.dot(df)  # co-occurrence counts
    matrix = mat.values.tolist()

    # Medication class prevalence within cohort.
    med_classes = []
    for cls, patterns in MED_CLASSES.items():
        pred = " OR ".join(f"m.display ILIKE '{p}'" for p in patterns)
        n = con.execute(f"""
            SELECT COUNT(DISTINCT m.patient_id)
            FROM medications m JOIN cv_cohort v USING (patient_id)
            WHERE v.has_cv = 1 AND ({pred})
        """).fetchone()[0]
        med_classes.append((cls, n, n / cohort_size))

    # Latest BP + cholesterol per cohort patient.
    con.execute(f"""
        CREATE OR REPLACE TEMP VIEW latest_bp AS
        WITH s AS (
            SELECT o.patient_id, o.value_num,
                   ROW_NUMBER() OVER (PARTITION BY o.patient_id ORDER BY o.effective DESC) rn
            FROM observations o JOIN cv_cohort v USING (patient_id)
            WHERE v.has_cv = 1 AND o.loinc_code = '{LOINC_SYSTOLIC}' AND o.value_num IS NOT NULL
        ),
        d AS (
            SELECT o.patient_id, o.value_num,
                   ROW_NUMBER() OVER (PARTITION BY o.patient_id ORDER BY o.effective DESC) rn
            FROM observations o JOIN cv_cohort v USING (patient_id)
            WHERE v.has_cv = 1 AND o.loinc_code = '{LOINC_DIASTOLIC}' AND o.value_num IS NOT NULL
        )
        SELECT s.patient_id, s.value_num AS systolic, d.value_num AS diastolic
        FROM s LEFT JOIN d ON s.patient_id = d.patient_id AND d.rn = 1
        WHERE s.rn = 1
    """)
    bp = con.execute("""
        SELECT COUNT(*) n, AVG(systolic), MEDIAN(systolic), AVG(diastolic), MEDIAN(diastolic),
               COUNT(*) FILTER (WHERE systolic >= ? OR diastolic >= ?) flagged
        FROM latest_bp
    """, [BP_FLAG_SYSTOLIC, BP_FLAG_DIASTOLIC]).fetchone()
    bp_stats = {
        "n": bp[0], "sys_mean": bp[1], "sys_median": bp[2],
        "dia_mean": bp[3], "dia_median": bp[4],
        "flag_count": bp[5], "flag_pct": (bp[5] / bp[0]) if bp[0] else 0,
    }

    chol = con.execute(f"""
        WITH c AS (
            SELECT o.patient_id, o.value_num,
                   ROW_NUMBER() OVER (PARTITION BY o.patient_id ORDER BY o.effective DESC) rn
            FROM observations o JOIN cv_cohort v USING (patient_id)
            WHERE v.has_cv = 1 AND o.loinc_code = '{LOINC_CHOLESTEROL}' AND o.value_num IS NOT NULL
        )
        SELECT COUNT(*), AVG(value_num), MEDIAN(value_num),
               QUANTILE_CONT(value_num, 0.25), QUANTILE_CONT(value_num, 0.75)
        FROM c WHERE rn = 1
    """).fetchone()
    chol_stats = {"n": chol[0], "mean": chol[1], "median": chol[2],
                  "p25": chol[3], "p75": chol[4]}

    return {
        "population": population,
        "cohort_size": cohort_size,
        "cohort_pct": cohort_size / population,
        "sex": sex,
        "age_mean": age_mean,
        "age_buckets": age_buckets,
        "prevalence": prevalence,
        "diabetes": diabetes,
        "comorbidity_labels": labels,
        "comorbidity_matrix": matrix,
        "med_classes": med_classes,
        "bp": bp_stats,
        "chol": chol_stats,
    }


def main() -> None:
    if not DB_PATH.exists():
        log.error("Database not found at %s. Run `make ingest` first.", DB_PATH)
        raise SystemExit(1)
    con = duckdb.connect(str(DB_PATH))
    build_cohort(con)
    metrics = analyze(con)
    log.info(
        "Cohort: %d/%d patients (%.1f%%); flagged BP>=%d/%d: %d",
        metrics["cohort_size"], metrics["population"], metrics["cohort_pct"] * 100,
        BP_FLAG_SYSTOLIC, BP_FLAG_DIASTOLIC, metrics["bp"]["flag_count"],
    )
    write_cohort_report(metrics)
    con.close()


if __name__ == "__main__":
    main()
