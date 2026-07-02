"""Cohort tests: assert membership and a prevalence number on a tiny fixture."""
from clinicalflow.cohort import analyze, build_cohort


def _load_mini_cohort(con):
    # p1 hypertension (CV) -> in cohort; p2 diabetes only (risk factor, not CV);
    # p3 no conditions -> not in cohort.
    con.execute(
        "INSERT INTO patients VALUES "
        "('p1','male',  DATE '1955-01-01',NULL,NULL,false,NULL),"
        "('p2','female',DATE '1960-01-01',NULL,NULL,false,NULL),"
        "('p3','male',  DATE '1980-01-01',NULL,NULL,false,NULL)"
    )
    con.execute(
        "INSERT INTO conditions VALUES "
        "('c1','p1','e1','59621000','Essential hypertension','active',NULL),"
        "('c2','p2','e2','44054006','Diabetes mellitus type 2','active',NULL)"
    )


def test_membership(schema_con):
    _load_mini_cohort(schema_con)
    build_cohort(schema_con)
    flags = dict(schema_con.execute(
        "SELECT patient_id, has_cv FROM cv_cohort ORDER BY patient_id"
    ).fetchall())
    assert flags == {"p1": 1, "p2": 0, "p3": 0}
    # diabetes is tracked but does not confer cohort membership.
    assert schema_con.execute(
        "SELECT diabetes FROM cv_cohort WHERE patient_id='p2'"
    ).fetchone()[0] == 1


def test_prevalence_and_size(schema_con):
    _load_mini_cohort(schema_con)
    build_cohort(schema_con)
    m = analyze(schema_con)
    assert m["cohort_size"] == 1
    assert m["population"] == 3
    prevalence = {label: n for label, n, _pc, _pp in m["prevalence"]}
    assert prevalence["Hypertension"] == 1
    assert prevalence["Heart failure"] == 0
