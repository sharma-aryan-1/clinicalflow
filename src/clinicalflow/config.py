"""Central configuration: paths, constants, QA thresholds, logging.

All tunable knobs live here so the rest of the codebase stays declarative and
the QA layer can honestly be described as a configurable "data quality contract".
"""
from __future__ import annotations

import logging
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
# config.py lives at src/clinicalflow/config.py -> repo root is three parents up.
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "clinicalflow.duckdb"
REPORTS_DIR = ROOT_DIR / "reports"

# --------------------------------------------------------------------------- #
# Synthea generation (reproducibility)
# --------------------------------------------------------------------------- #
SYNTHEA_SEED = 1234
SYNTHEA_POPULATION = 3000
SYNTHEA_STATE = "Massachusetts"

# --------------------------------------------------------------------------- #
# FHIR coding system URIs
# --------------------------------------------------------------------------- #
SYSTEM_LOINC = "http://loinc.org"
SYSTEM_SNOMED = "http://snomed.info/sct"
SYSTEM_RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"

# Expected coding system per table (used by code-system validation in QA).
EXPECTED_CODE_SYSTEM = {
    "conditions": SYSTEM_SNOMED,
    "procedures": SYSTEM_SNOMED,
    "observations": SYSTEM_LOINC,
    "medications": SYSTEM_RXNORM,
}

# --------------------------------------------------------------------------- #
# QA: value-range bounds for key vitals/labs, keyed by LOINC code.
# (min, max) inclusive. Values outside are flagged.
# --------------------------------------------------------------------------- #
VALUE_RANGES = {
    "8480-6": (50, 300),    # Systolic blood pressure
    "8462-4": (30, 200),    # Diastolic blood pressure
    "8867-4": (20, 250),    # Heart rate
    "39156-5": (10, 100),   # Body mass index (BMI)
    "2093-3": (50, 500),    # Total cholesterol
}

# Human-readable labels for the ranged measures (for reports).
VALUE_RANGE_LABELS = {
    "8480-6": "Systolic BP",
    "8462-4": "Diastolic BP",
    "8867-4": "Heart rate",
    "39156-5": "BMI",
    "2093-3": "Total cholesterol",
}

# --------------------------------------------------------------------------- #
# QA: error-budget threshold. A check fails if violations exceed this fraction
# of the rows it inspects. 0.01 == 1%.
# --------------------------------------------------------------------------- #
ERROR_BUDGET = 0.01

# --------------------------------------------------------------------------- #
# Cohort: population-health flag threshold (hypertension stage 2-ish).
# --------------------------------------------------------------------------- #
BP_FLAG_SYSTOLIC = 140
BP_FLAG_DIASTOLIC = 90

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
def get_logger(name: str = "clinicalflow") -> logging.Logger:
    """Return a configured logger. Uses rich if available, else stdlib."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    # Windows consoles default to cp1252; force UTF-8 so unicode in logs is safe.
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover
            pass
    try:
        from rich.logging import RichHandler

        handler: logging.Handler = RichHandler(
            rich_tracebacks=True, show_path=False, markup=True
        )
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
    except ImportError:  # pragma: no cover - fallback path
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    logger.addHandler(handler)
    logger.propagate = False
    return logger
