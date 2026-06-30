"""Phase 2: parse FHIR R4 bundles and load normalized tables into DuckDB.

Handles the expensive FHIR gotchas explicitly:
  * reference resolution (urn:uuid / fullUrl / "Type/id" -> bare resource id)
  * polymorphic value[x] (valueQuantity / valueString / valueCodeableConcept)
  * multi-component observations (e.g. blood pressure) split into separate rows
  * codes under coding[] with system tracking (LOINC vs SNOMED vs RxNorm)
  * mixed date forms (effectiveDateTime/effectivePeriod, onsetDateTime/Period)

Re-running is idempotent: tables are dropped and recreated each run.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from . import schema
from .config import DB_PATH, RAW_DIR, SYSTEM_LOINC, SYSTEM_RXNORM, SYSTEM_SNOMED, get_logger

log = get_logger()

BATCH_SIZE = 250  # bundles per flush, keeps memory bounded over ~3.5k files
URN_PREFIX = "urn:uuid:"
INFO_PREFIXES = ("hospitalInformation", "practitionerInformation")

RACE_URL = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
ETHNICITY_URL = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"


# --------------------------------------------------------------------------- #
# Small FHIR helpers
# --------------------------------------------------------------------------- #
def build_resolver(entries: list[dict]) -> dict[str, str]:
    """Map every entry's fullUrl to its resource id (for cross-entry refs)."""
    resolver: dict[str, str] = {}
    for e in entries:
        full = e.get("fullUrl")
        rid = e.get("resource", {}).get("id")
        if full and rid:
            resolver[full] = rid
    return resolver


def resolve_ref(ref, resolver: dict[str, str]) -> str | None:
    """Normalize a FHIR reference to a bare resource id."""
    if not ref:
        return None
    s = ref.get("reference") if isinstance(ref, dict) else ref
    if not s:
        return None
    if s in resolver:
        return resolver[s]
    if s.startswith(URN_PREFIX):
        return s[len(URN_PREFIX):]
    if "/" in s:
        return s.split("/")[-1]
    return s


def get_coding(concept: dict | None, system: str | None = None):
    """Return (system, code, display) from a CodeableConcept.

    Prefers a coding matching ``system``; falls back to the first coding, then
    to the concept's free-text.
    """
    if not concept:
        return None, None, None
    codings = concept.get("coding", []) or []
    if system is not None:
        for c in codings:
            if c.get("system") == system:
                return c.get("system"), c.get("code"), c.get("display")
    if codings:
        c = codings[0]
        return c.get("system"), c.get("code"), c.get("display")
    return None, None, concept.get("text")


def dt_or_period(resource: dict, dt_key: str, period_key: str):
    """Return a single timestamp string from a *DateTime or *Period field."""
    if resource.get(dt_key):
        return resource[dt_key]
    period = resource.get(period_key)
    if isinstance(period, dict):
        return period.get("start")
    return None


def extract_demographics_extension(patient: dict, url: str) -> str | None:
    """Pull the 'text' sub-extension (display) from a US-Core race/ethnicity ext."""
    for ext in patient.get("extension", []) or []:
        if ext.get("url") != url:
            continue
        for sub in ext.get("extension", []) or []:
            if sub.get("url") == "text":
                return sub.get("valueString")
        # fallback: ombCategory display
        for sub in ext.get("extension", []) or []:
            if sub.get("url") == "ombCategory":
                vc = sub.get("valueCoding", {})
                return vc.get("display")
    return None


# --------------------------------------------------------------------------- #
# Per-resource parsers -> append rows to buffers
# --------------------------------------------------------------------------- #
def parse_patient(r: dict, buf: dict[str, list]) -> None:
    deceased_dt = r.get("deceasedDateTime")
    deceased = bool(deceased_dt) or bool(r.get("deceasedBoolean"))
    buf["patients"].append({
        "patient_id": r.get("id"),
        "gender": r.get("gender"),
        "birth_date": r.get("birthDate"),
        "race": extract_demographics_extension(r, RACE_URL),
        "ethnicity": extract_demographics_extension(r, ETHNICITY_URL),
        "deceased": deceased,
        "deceased_date": deceased_dt,
    })


def parse_encounter(r: dict, resolver, buf) -> None:
    enc_class = r.get("class", {})
    type_concept = (r.get("type") or [{}])[0]
    _, type_code, type_display = get_coding(type_concept)
    reason = r.get("reasonCode") or []
    _, reason_code, _ = get_coding(reason[0]) if reason else (None, None, None)
    period = r.get("period", {}) or {}
    buf["encounters"].append({
        "encounter_id": r.get("id"),
        "patient_id": resolve_ref(r.get("subject"), resolver),
        "enc_class": enc_class.get("code") if isinstance(enc_class, dict) else None,
        "type_code": type_code,
        "type_display": type_display,
        "start_time": period.get("start"),
        "end_time": period.get("end"),
        "reason_code": reason_code,
    })


def parse_condition(r: dict, resolver, buf) -> None:
    _, code, display = get_coding(r.get("code"), SYSTEM_SNOMED)
    _, status, _ = get_coding(r.get("clinicalStatus"))
    buf["conditions"].append({
        "condition_id": r.get("id"),
        "patient_id": resolve_ref(r.get("subject"), resolver),
        "encounter_id": resolve_ref(r.get("encounter"), resolver),
        "snomed_code": code,
        "display": display,
        "clinical_status": status,
        "onset": dt_or_period(r, "onsetDateTime", "onsetPeriod"),
    })


def parse_observation(r: dict, resolver, buf) -> None:
    patient_id = resolve_ref(r.get("subject"), resolver)
    encounter_id = resolve_ref(r.get("encounter"), resolver)
    _, category, _ = get_coding((r.get("category") or [{}])[0])
    effective = dt_or_period(r, "effectiveDateTime", "effectivePeriod")
    oid = r.get("id")

    def row(obs_id, loinc, display, vnum, vunit, vstr):
        buf["observations"].append({
            "observation_id": obs_id,
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "category": category,
            "loinc_code": loinc,
            "display": display,
            "value_num": vnum,
            "value_unit": vunit,
            "value_string": vstr,
            "effective": effective,
        })

    components = r.get("component")
    if components:
        # Split each component into its own row; suffix id to keep it unique.
        for comp in components:
            _, loinc, display = get_coding(comp.get("code"), SYSTEM_LOINC)
            vq = comp.get("valueQuantity") or {}
            row(f"{oid}::{loinc}", loinc, display,
                vq.get("value"), vq.get("unit"), comp.get("valueString"))
        return

    _, loinc, display = get_coding(r.get("code"), SYSTEM_LOINC)
    if "valueQuantity" in r:
        vq = r["valueQuantity"]
        row(oid, loinc, display, vq.get("value"), vq.get("unit"), None)
    elif "valueString" in r:
        row(oid, loinc, display, None, None, r.get("valueString"))
    elif "valueCodeableConcept" in r:
        _, _, vdisplay = get_coding(r.get("valueCodeableConcept"))
        row(oid, loinc, display, None, None, vdisplay)
    else:
        row(oid, loinc, display, None, None, None)


def parse_medication(r: dict, resolver, buf) -> None:
    _, code, display = get_coding(r.get("medicationCodeableConcept"), SYSTEM_RXNORM)
    buf["medications"].append({
        "medication_id": r.get("id"),
        "patient_id": resolve_ref(r.get("subject"), resolver),
        "encounter_id": resolve_ref(r.get("encounter"), resolver),
        "rxnorm_code": code,
        "display": display,
        "status": r.get("status"),
        "authored_on": r.get("authoredOn"),
    })


def parse_procedure(r: dict, resolver, buf) -> None:
    _, code, display = get_coding(r.get("code"), SYSTEM_SNOMED)
    buf["procedures"].append({
        "procedure_id": r.get("id"),
        "patient_id": resolve_ref(r.get("subject"), resolver),
        "snomed_code": code,
        "display": display,
        "performed": dt_or_period(r, "performedDateTime", "performedPeriod"),
    })


DISPATCH = {
    "Patient": lambda r, res, buf: parse_patient(r, buf),
    "Encounter": parse_encounter,
    "Condition": parse_condition,
    "Observation": parse_observation,
    "MedicationRequest": parse_medication,
    "Procedure": parse_procedure,
}


# --------------------------------------------------------------------------- #
# DataFrame coercion + loading
# --------------------------------------------------------------------------- #
TIMESTAMP_COLS = {
    "encounters": ["start_time", "end_time"],
    "conditions": ["onset"],
    "observations": ["effective"],
    "medications": ["authored_on"],
    "procedures": ["performed"],
    "patients": ["deceased_date"],
}


def _to_naive_utc(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, utc=True, errors="coerce", format="ISO8601")
    return ts.dt.tz_localize(None)


def buffer_to_df(table: str, rows: list[dict]) -> pd.DataFrame:
    cols = schema.COLUMNS[table]
    df = pd.DataFrame(rows, columns=cols)
    for c in TIMESTAMP_COLS.get(table, []):
        df[c] = _to_naive_utc(df[c])
    if table == "patients":
        df["birth_date"] = pd.to_datetime(
            df["birth_date"], errors="coerce", format="ISO8601"
        ).dt.date
        df["deceased"] = df["deceased"].astype("boolean")
    if table == "observations":
        df["value_num"] = pd.to_numeric(df["value_num"], errors="coerce")
    return df


def flush(con, buffers: dict[str, list]) -> None:
    for table, rows in buffers.items():
        if not rows:
            continue
        df = buffer_to_df(table, rows)  # noqa: F841 (used via replacement scan)
        con.execute(f"INSERT INTO {table} SELECT * FROM df")
        rows.clear()


def create_tables(con) -> None:
    for table, ddl in schema.TABLES.items():
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(ddl)


def main() -> None:
    bundles = [
        p for p in sorted(RAW_DIR.glob("*.json"))
        if not p.name.startswith(INFO_PREFIXES)
    ]
    if not bundles:
        log.error("No patient bundles in %s. Run `make data` first.", RAW_DIR)
        raise SystemExit(1)

    log.info("Ingesting %d FHIR bundles into %s", len(bundles), DB_PATH)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    create_tables(con)

    buffers: dict[str, list] = {t: [] for t in schema.TABLES}
    for i, path in enumerate(bundles, 1):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Skipping unreadable bundle %s: %s", path.name, exc)
            continue
        entries = bundle.get("entry", []) or []
        resolver = build_resolver(entries)
        for entry in entries:
            resource = entry.get("resource", {})
            handler = DISPATCH.get(resource.get("resourceType"))
            if handler:
                handler(resource, resolver, buffers)
        if i % BATCH_SIZE == 0:
            flush(con, buffers)
            log.info("  ... processed %d/%d bundles", i, len(bundles))
    flush(con, buffers)

    log.info("Row counts:")
    for table in schema.TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        log.info("  %-13s %8d", table, n)
    con.close()
    log.info("Ingestion complete.")


if __name__ == "__main__":
    main()
