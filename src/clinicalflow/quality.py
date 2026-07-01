"""Phase 3: data governance and quality-assurance check suite.

Six check families, each producing structured results stored in a DuckDB
``qa_results`` table and rendered to ``reports/data_quality_report.md``:

  1. Referential integrity  — child patient_id resolves to patients
  2. Code-system validation — SNOMED/LOINC/RxNorm present and well-formed
  3. Value-range            — vitals/labs within configurable bounds
  4. Completeness           — null rate of required fields
  5. Temporal sanity        — no future/illogical dates
  6. Duplicates             — no duplicate resource ids per table

A check fails when violations exceed the error-budget threshold (config.py).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb

from .config import (
    DB_PATH,
    ERROR_BUDGET,
    EXPECTED_CODE_SYSTEM,
    VALUE_RANGE_LABELS,
    VALUE_RANGES,
    get_logger,
)
from .report import write_quality_report

log = get_logger()

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
TODAY = date.today()

# Child tables that must reference a real patient.
CHILD_TABLES = ["encounters", "conditions", "observations", "medications", "procedures"]

# (table, id column) pairs for the duplicate check.
ID_COLUMNS = {
    "patients": "patient_id",
    "encounters": "encounter_id",
    "conditions": "condition_id",
    "observations": "observation_id",
    "medications": "medication_id",
    "procedures": "procedure_id",
}

# Well-formed code regexes per coding system.
CODE_REGEX = {
    "conditions": ("snomed_code", "^[0-9]+$"),
    "procedures": ("snomed_code", "^[0-9]+$"),
    "observations": ("loinc_code", "^[0-9]+-[0-9]+$"),
    "medications": ("rxnorm_code", "^[0-9]+$"),
}


def _result(check, subject, violations, total, note="", threshold=ERROR_BUDGET):
    observed = (violations / total) if total else 0.0
    status = "pass" if (total == 0 or observed <= threshold) else "fail"
    return {
        "check": check,
        "subject": subject,
        "status": status,
        "threshold": threshold,
        "observed": observed,
        "violations": int(violations),
        "total": int(total),
        "note": note,
    }


def _scalar(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def check_referential_integrity(con) -> list[dict]:
    out = []
    for tbl in CHILD_TABLES:
        total = _scalar(con, f"SELECT COUNT(*) FROM {tbl}")
        orphans = _scalar(
            con,
            f"SELECT COUNT(*) FROM {tbl} t "
            "LEFT JOIN patients p ON t.patient_id = p.patient_id "
            "WHERE p.patient_id IS NULL",
        )
        out.append(_result(
            "Referential integrity", f"{tbl}.patient_id → patients",
            orphans, total, "orphan rows with no matching patient",
        ))
    return out


def check_code_systems(con) -> list[dict]:
    out = []
    for tbl, (col, rgx) in CODE_REGEX.items():
        total = _scalar(con, f"SELECT COUNT(*) FROM {tbl}")
        bad = _scalar(
            con,
            f"SELECT COUNT(*) FROM {tbl} "
            f"WHERE {col} IS NULL OR NOT regexp_full_match({col}, ?)",
            [rgx],
        )
        system = EXPECTED_CODE_SYSTEM[tbl].rsplit("/", 1)[-1] or EXPECTED_CODE_SYSTEM[tbl]
        sysname = {"sct": "SNOMED", "loinc.org": "LOINC", "rxnorm": "RxNorm"}.get(
            system, system
        )
        out.append(_result(
            "Code-system validation", f"{tbl}.{col} ({sysname})",
            bad, total, "null or malformed codes",
        ))
    return out


def check_value_ranges(con) -> list[dict]:
    out = []
    for code, (lo, hi) in VALUE_RANGES.items():
        label = VALUE_RANGE_LABELS.get(code, code)
        total = _scalar(
            con,
            "SELECT COUNT(*) FROM observations WHERE loinc_code = ? AND value_num IS NOT NULL",
            [code],
        )
        bad = _scalar(
            con,
            "SELECT COUNT(*) FROM observations "
            "WHERE loinc_code = ? AND value_num IS NOT NULL "
            "AND (value_num < ? OR value_num > ?)",
            [code, lo, hi],
        )
        examples = con.execute(
            "SELECT value_num FROM observations "
            "WHERE loinc_code = ? AND value_num IS NOT NULL AND (value_num < ? OR value_num > ?) "
            "LIMIT 3",
            [code, lo, hi],
        ).fetchall()
        ex = ", ".join(str(e[0]) for e in examples)
        note = f"bounds [{lo}, {hi}]" + (f"; e.g. {ex}" if ex else "")
        out.append(_result("Value-range", f"{label} ({code})", bad, total, note))
    return out


def check_completeness(con) -> list[dict]:
    fields = [
        ("patients", "birth_date", "patients.birth_date", "birth_date IS NULL"),
        ("patients", "gender", "patients.gender", "gender IS NULL OR gender = ''"),
        ("observations", "value", "observations.value",
         "value_num IS NULL AND value_string IS NULL"),
        ("conditions", "snomed_code", "conditions.snomed_code", "snomed_code IS NULL"),
    ]
    out = []
    for tbl, _col, subject, predicate in fields:
        total = _scalar(con, f"SELECT COUNT(*) FROM {tbl}")
        missing = _scalar(con, f"SELECT COUNT(*) FROM {tbl} WHERE {predicate}")
        out.append(_result("Completeness", subject, missing, total, "null / missing"))
    return out


def check_temporal(con) -> list[dict]:
    out = []
    npat = _scalar(con, "SELECT COUNT(*) FROM patients")

    future_birth = _scalar(con, "SELECT COUNT(*) FROM patients WHERE birth_date > ?", [TODAY])
    out.append(_result("Temporal sanity", "birth_date not in future", future_birth, npat))

    death_before_birth = _scalar(
        con,
        "SELECT COUNT(*) FROM patients "
        "WHERE deceased_date IS NOT NULL AND deceased_date < birth_date::TIMESTAMP",
    )
    out.append(_result("Temporal sanity", "death after birth", death_before_birth, npat))

    nenc = _scalar(con, "SELECT COUNT(*) FROM encounters")
    future_enc = _scalar(con, "SELECT COUNT(*) FROM encounters WHERE start_time > ?", [NOW])
    out.append(_result(
        "Temporal sanity", "encounter not future-dated", future_enc, nenc,
        "encounters with start after run time",
    ))

    enc_before_birth = _scalar(
        con,
        "SELECT COUNT(*) FROM encounters e JOIN patients p USING(patient_id) "
        "WHERE e.start_time < p.birth_date::TIMESTAMP",
    )
    out.append(_result(
        "Temporal sanity", "encounter after birth", enc_before_birth, nenc,
        "encounters dated before the patient's birth",
    ))
    return out


def check_duplicates(con) -> list[dict]:
    out = []
    for tbl, col in ID_COLUMNS.items():
        total = _scalar(con, f"SELECT COUNT(*) FROM {tbl}")
        distinct = _scalar(con, f"SELECT COUNT(DISTINCT {col}) FROM {tbl}")
        dupes = total - distinct
        out.append(_result("Duplicates", f"{tbl}.{col}", dupes, total, "duplicate resource ids"))
    return out


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run_checks(con) -> list[dict]:
    results: list[dict] = []
    results += check_referential_integrity(con)
    results += check_code_systems(con)
    results += check_value_ranges(con)
    results += check_completeness(con)
    results += check_temporal(con)
    results += check_duplicates(con)
    return results


def store_results(con, results: list[dict]) -> None:
    con.execute("DROP TABLE IF EXISTS qa_results")
    con.execute(
        """
        CREATE TABLE qa_results (
            check_name VARCHAR, subject VARCHAR, status VARCHAR,
            threshold DOUBLE, observed DOUBLE, violations BIGINT,
            total BIGINT, note VARCHAR
        )
        """
    )
    con.executemany(
        "INSERT INTO qa_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (r["check"], r["subject"], r["status"], r["threshold"],
             r["observed"], r["violations"], r["total"], r["note"])
            for r in results
        ],
    )


def main() -> None:
    if not DB_PATH.exists():
        log.error("Database not found at %s. Run `make ingest` first.", DB_PATH)
        raise SystemExit(1)

    con = duckdb.connect(str(DB_PATH))
    log.info("Running data-quality checks (error budget = %.0f%%)", ERROR_BUDGET * 100)
    results = run_checks(con)
    store_results(con, results)

    failed = [r for r in results if r["status"] == "fail"]
    for r in results:
        mark = "PASS" if r["status"] == "pass" else "FAIL"
        log.info("  [%s] %-28s %-40s %d/%d",
                 mark, r["check"], r["subject"], r["violations"], r["total"])
    log.info("QA complete: %d checks, %d failed.", len(results), len(failed))

    write_quality_report(results)
    con.close()


if __name__ == "__main__":
    main()
