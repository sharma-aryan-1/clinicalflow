"""Build a small, committable DuckDB for the hosted demo (Streamlit Cloud).

The full database (~160 MB) is gitignored. This extracts only what the dashboard
needs — cohort-relevant rows — into ``data/clinicalflow_slim.duckdb`` (a few MB),
plus a ``pipeline_stats`` table that carries the *real full-scale* row counts so
the hosted Pipeline page still reports the true ingest scale.

Usage:  python -m clinicalflow.slim
"""
from __future__ import annotations

import duckdb

from .config import DATA_DIR, DB_PATH, get_logger

log = get_logger()

SLIM_PATH = DATA_DIR / "clinicalflow_slim.duckdb"

# LOINC codes the dashboard actually plots/aggregates for the cohort.
RELEVANT_LOINCS = ("8480-6", "8462-4", "8867-4", "39156-5", "2093-3")

FULL_TABLES = ["patients", "encounters", "conditions", "observations",
               "medications", "procedures"]


def main() -> None:
    if not DB_PATH.exists():
        log.error("Full DB not found at %s. Run `make all` first.", DB_PATH)
        raise SystemExit(1)

    # Real full-scale counts (for the Pipeline page on the hosted demo).
    src = duckdb.connect(str(DB_PATH), read_only=True)
    stats = {t: src.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in FULL_TABLES}
    src.close()

    if SLIM_PATH.exists():
        SLIM_PATH.unlink()

    loinc_in = "(" + ", ".join(f"'{c}'" for c in RELEVANT_LOINCS) + ")"
    dst = duckdb.connect(str(SLIM_PATH))
    dst.execute(f"ATTACH '{DB_PATH}' AS src_db (READ_ONLY)")

    # Small, whole tables.
    dst.execute("CREATE TABLE patients  AS SELECT * FROM src_db.patients")
    dst.execute("CREATE TABLE cv_cohort AS SELECT * FROM src_db.cv_cohort")
    dst.execute("CREATE TABLE qa_results AS SELECT * FROM src_db.qa_results")

    # Cohort-only slices of the big tables.
    dst.execute("""
        CREATE TABLE medications AS
        SELECT m.* FROM src_db.medications m
        JOIN src_db.cv_cohort v USING (patient_id)
        WHERE v.has_cv = 1
    """)
    dst.execute(f"""
        CREATE TABLE observations AS
        SELECT o.* FROM src_db.observations o
        JOIN src_db.cv_cohort v USING (patient_id)
        WHERE v.has_cv = 1 AND o.loinc_code IN {loinc_in}
    """)

    # Real full-scale row counts.
    dst.execute("CREATE TABLE pipeline_stats (table_name VARCHAR, row_count BIGINT)")
    dst.executemany(
        "INSERT INTO pipeline_stats VALUES (?, ?)",
        [(t, int(n)) for t, n in stats.items()],
    )

    dst.execute("DETACH src_db")
    for t in ["patients", "cv_cohort", "qa_results", "medications", "observations"]:
        n = dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        log.info("  slim %-12s %8d rows", t, n)
    dst.close()

    size_mb = SLIM_PATH.stat().st_size / 1e6
    log.info("Wrote %s (%.1f MB)", SLIM_PATH, size_mb)


if __name__ == "__main__":
    main()
