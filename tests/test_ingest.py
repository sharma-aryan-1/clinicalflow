"""Ingestion tests against the hand-checked fixture bundle."""
from clinicalflow.ingest import ingest_bundles, resolve_ref


def _counts(con):
    tables = ["patients", "encounters", "conditions", "observations",
              "medications", "procedures"]
    return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def test_row_counts(mem_con, sample_bundle):
    ingest_bundles(mem_con, [sample_bundle])
    assert _counts(mem_con) == {
        "patients": 1, "encounters": 1, "conditions": 2,
        "observations": 3,  # 2 BP components + 1 cholesterol
        "medications": 2, "procedures": 1,
    }


def test_patient_fields(mem_con, sample_bundle):
    ingest_bundles(mem_con, [sample_bundle])
    row = mem_con.execute(
        "SELECT gender, race, ethnicity, deceased FROM patients WHERE patient_id='p1'"
    ).fetchone()
    assert row == ("male", "White", "Not Hispanic or Latino", False)


def test_reference_resolution(mem_con, sample_bundle):
    ingest_bundles(mem_con, [sample_bundle])
    # urn:uuid references resolve to bare ids across resources.
    assert mem_con.execute("SELECT DISTINCT patient_id FROM encounters").fetchall() == [("p1",)]
    assert mem_con.execute(
        "SELECT patient_id, encounter_id FROM conditions WHERE condition_id='c1'"
    ).fetchone() == ("p1", "e1")


def test_bp_components_split(mem_con, sample_bundle):
    ingest_bundles(mem_con, [sample_bundle])
    rows = dict(mem_con.execute(
        "SELECT loinc_code, value_num FROM observations WHERE observation_id LIKE 'o1::%'"
    ).fetchall())
    assert rows["8480-6"] == 145
    assert rows["8462-4"] == 92
    # component rows carry unique ids -> no duplicate observation_ids
    distinct_ids = mem_con.execute(
        "SELECT COUNT(DISTINCT observation_id) FROM observations"
    ).fetchone()[0]
    assert distinct_ids == 3


def test_value_quantity(mem_con, sample_bundle):
    ingest_bundles(mem_con, [sample_bundle])
    assert mem_con.execute(
        "SELECT value_num, value_unit FROM observations WHERE loinc_code='2093-3'"
    ).fetchone() == (210, "mg/dL")


def test_medication_reference_recovered(mem_con, sample_bundle):
    ingest_bundles(mem_con, [sample_bundle])
    meds = dict(mem_con.execute(
        "SELECT medication_id, rxnorm_code FROM medications"
    ).fetchall())
    assert meds["m1"] == "312961"           # inline medicationCodeableConcept
    assert meds["m2"] == "314076"           # recovered via medicationReference -> Medication


def test_resolve_ref_forms():
    resolver = {"urn:uuid:abc": "abc"}
    assert resolve_ref({"reference": "urn:uuid:abc"}, resolver) == "abc"
    assert resolve_ref({"reference": "urn:uuid:zzz"}, {}) == "zzz"   # strip prefix
    assert resolve_ref({"reference": "Patient/xyz"}, {}) == "xyz"    # Type/id form
    assert resolve_ref(None, {}) is None
