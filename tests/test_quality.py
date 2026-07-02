"""Quality-check tests: feed known-bad rows and assert the right checks fail."""
from clinicalflow.quality import run_checks


def _load_bad_data(con):
    # Patients: p1 clean; p2 missing gender and an impossible future birth_date.
    con.execute(
        "INSERT INTO patients VALUES "
        "('p1','male',DATE '1970-01-01','White','Not Hispanic',false,NULL),"
        "('p2',NULL,   DATE '2999-01-01',NULL,   NULL,          false,NULL)"
    )
    # Conditions: duplicate id (c1 twice) and one with a null SNOMED code.
    con.execute(
        "INSERT INTO conditions VALUES "
        "('c1','p1','e1','59621000','Essential hypertension','active',NULL),"
        "('c1','p1','e1','59621000','Essential hypertension','active',NULL),"
        "('c3','p1','e1',NULL,      'no code',              'active',NULL)"
    )
    # Observations: one orphan (patient 'ghost') and one out-of-range systolic (400).
    con.execute(
        "INSERT INTO observations VALUES "
        "('o1','ghost','e1','vital-signs','8480-6','Systolic',400,'mm[Hg]',NULL,NULL),"
        "('o2','p1',   'e1','vital-signs','8480-6','Systolic',120,'mm[Hg]',NULL,NULL)"
    )


def test_known_bad_rows_fail_the_right_checks(schema_con, status_of):
    _load_bad_data(schema_con)
    results = run_checks(schema_con)

    assert status_of(results, "Referential integrity", "observations") == "fail"  # orphan obs
    assert status_of(results, "Duplicates", "conditions") == "fail"               # dup c1
    assert status_of(results, "Code-system validation", "conditions") == "fail"   # null SNOMED
    assert status_of(results, "Value-range", "8480-6") == "fail"                  # systolic 400
    assert status_of(results, "Completeness", "gender") == "fail"                 # p2 null gender
    assert status_of(results, "Temporal sanity", "birth_date not in future") == "fail"


def test_clean_dimensions_pass(schema_con, status_of):
    _load_bad_data(schema_con)
    results = run_checks(schema_con)
    # patient ids are unique even though condition ids are not.
    assert status_of(results, "Duplicates", "patients") == "pass"
    # birth_date is present for every patient (completeness of birth_date passes).
    assert status_of(results, "Completeness", "birth_date") == "pass"
