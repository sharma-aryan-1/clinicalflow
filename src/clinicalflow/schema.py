"""DuckDB table DDL for the normalized FHIR store.

`patient_id` (the Patient resource id) is the stable join key across all tables.
Constraints are intentionally NOT declared as PRIMARY KEY / NOT NULL: the QA
layer (Phase 3) is responsible for detecting duplicates, orphans, and missing
values and reporting them rather than failing ingestion.

Column-order in each DDL must match the order produced by ingest.py.
"""
from __future__ import annotations

# Ordered column lists are the contract between schema and ingest.
COLUMNS: dict[str, list[str]] = {
    "patients": [
        "patient_id", "gender", "birth_date", "race", "ethnicity",
        "deceased", "deceased_date",
    ],
    "encounters": [
        "encounter_id", "patient_id", "enc_class", "type_code", "type_display",
        "start_time", "end_time", "reason_code",
    ],
    "conditions": [
        "condition_id", "patient_id", "encounter_id", "snomed_code", "display",
        "clinical_status", "onset",
    ],
    "observations": [
        "observation_id", "patient_id", "encounter_id", "category",
        "loinc_code", "display", "value_num", "value_unit", "value_string",
        "effective",
    ],
    "medications": [
        "medication_id", "patient_id", "encounter_id", "rxnorm_code", "display",
        "status", "authored_on",
    ],
    "procedures": [
        "procedure_id", "patient_id", "snomed_code", "display", "performed",
    ],
}

TABLES: dict[str, str] = {
    "patients": """
        CREATE TABLE patients (
            patient_id    VARCHAR,
            gender        VARCHAR,
            birth_date    DATE,
            race          VARCHAR,
            ethnicity     VARCHAR,
            deceased      BOOLEAN,
            deceased_date TIMESTAMP
        )
    """,
    "encounters": """
        CREATE TABLE encounters (
            encounter_id VARCHAR,
            patient_id   VARCHAR,
            enc_class    VARCHAR,
            type_code    VARCHAR,
            type_display VARCHAR,
            start_time   TIMESTAMP,
            end_time     TIMESTAMP,
            reason_code  VARCHAR
        )
    """,
    "conditions": """
        CREATE TABLE conditions (
            condition_id    VARCHAR,
            patient_id      VARCHAR,
            encounter_id    VARCHAR,
            snomed_code     VARCHAR,
            display         VARCHAR,
            clinical_status VARCHAR,
            onset           TIMESTAMP
        )
    """,
    "observations": """
        CREATE TABLE observations (
            observation_id VARCHAR,
            patient_id     VARCHAR,
            encounter_id   VARCHAR,
            category       VARCHAR,
            loinc_code     VARCHAR,
            display        VARCHAR,
            value_num      DOUBLE,
            value_unit     VARCHAR,
            value_string   VARCHAR,
            effective      TIMESTAMP
        )
    """,
    "medications": """
        CREATE TABLE medications (
            medication_id VARCHAR,
            patient_id    VARCHAR,
            encounter_id  VARCHAR,
            rxnorm_code   VARCHAR,
            display       VARCHAR,
            status        VARCHAR,
            authored_on   TIMESTAMP
        )
    """,
    "procedures": """
        CREATE TABLE procedures (
            procedure_id VARCHAR,
            patient_id   VARCHAR,
            snomed_code  VARCHAR,
            display      VARCHAR,
            performed    TIMESTAMP
        )
    """,
}
