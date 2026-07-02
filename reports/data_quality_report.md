# Data Quality Report

> Synthetic data (Synthea), no PHI. This report applies an **error-budget contract**: a check fails when violations exceed **1%** of the rows it inspects.

- Generated: 2026-07-02 13:10
- Checks run: **28**
- Overall: **PASS ✅**

## Referential integrity — ✅ PASS

| Subject | Status | Violations | Inspected | Rate | Budget | Notes |
|---|---|---:|---:|---:|---:|---|
| encounters.patient_id → patients | ✅ pass | 0 | 205,566 | 0.00% | 1.00% | orphan rows with no matching patient |
| conditions.patient_id → patients | ✅ pass | 0 | 129,716 | 0.00% | 1.00% | orphan rows with no matching patient |
| observations.patient_id → patients | ✅ pass | 0 | 2,674,521 | 0.00% | 1.00% | orphan rows with no matching patient |
| medications.patient_id → patients | ✅ pass | 0 | 180,891 | 0.00% | 1.00% | orphan rows with no matching patient |
| procedures.patient_id → patients | ✅ pass | 0 | 579,074 | 0.00% | 1.00% | orphan rows with no matching patient |

## Code-system validation — ✅ PASS

| Subject | Status | Violations | Inspected | Rate | Budget | Notes |
|---|---|---:|---:|---:|---:|---|
| conditions.snomed_code (SNOMED) | ✅ pass | 0 | 129,716 | 0.00% | 1.00% | null or malformed codes |
| procedures.snomed_code (SNOMED) | ✅ pass | 0 | 579,074 | 0.00% | 1.00% | null or malformed codes |
| observations.loinc_code (LOINC) | ✅ pass | 606 | 2,674,521 | 0.02% | 1.00% | null or malformed codes |
| medications.rxnorm_code (RxNorm) | ✅ pass | 0 | 180,891 | 0.00% | 1.00% | null or malformed codes |

## Value-range — ✅ PASS

| Subject | Status | Violations | Inspected | Rate | Budget | Notes |
|---|---|---:|---:|---:|---:|---|
| Systolic BP (8480-6) | ✅ pass | 8 | 51,826 | 0.02% | 1.00% | bounds [50, 300]; e.g. 45.155, 43.027, 40.819 |
| Diastolic BP (8462-4) | ✅ pass | 11 | 51,826 | 0.02% | 1.00% | bounds [30, 200]; e.g. 29.0, 28.0, 29.0 |
| Heart rate (8867-4) | ✅ pass | 0 | 48,432 | 0.00% | 1.00% | bounds [20, 250] |
| BMI (39156-5) | ✅ pass | 0 | 44,072 | 0.00% | 1.00% | bounds [10, 100] |
| Total cholesterol (2093-3) | ✅ pass | 0 | 18,107 | 0.00% | 1.00% | bounds [50, 500] |

## Completeness — ✅ PASS

| Subject | Status | Violations | Inspected | Rate | Budget | Notes |
|---|---|---:|---:|---:|---:|---|
| patients.birth_date | ✅ pass | 0 | 3,450 | 0.00% | 1.00% | null / missing |
| patients.gender | ✅ pass | 0 | 3,450 | 0.00% | 1.00% | null / missing |
| observations.value | ✅ pass | 0 | 2,674,521 | 0.00% | 1.00% | null / missing |
| conditions.snomed_code | ✅ pass | 0 | 129,716 | 0.00% | 1.00% | null / missing |

## Temporal sanity — ✅ PASS

| Subject | Status | Violations | Inspected | Rate | Budget | Notes |
|---|---|---:|---:|---:|---:|---|
| birth_date not in future | ✅ pass | 0 | 3,450 | 0.00% | 1.00% |  |
| death after birth | ✅ pass | 0 | 3,450 | 0.00% | 1.00% |  |
| encounter not future-dated | ✅ pass | 1 | 205,566 | 0.00% | 1.00% | encounters with start after run time |
| encounter after birth | ✅ pass | 0 | 205,566 | 0.00% | 1.00% | encounters dated before the patient's birth |

## Duplicates — ✅ PASS

| Subject | Status | Violations | Inspected | Rate | Budget | Notes |
|---|---|---:|---:|---:|---:|---|
| patients.patient_id | ✅ pass | 0 | 3,450 | 0.00% | 1.00% | duplicate resource ids |
| encounters.encounter_id | ✅ pass | 0 | 205,566 | 0.00% | 1.00% | duplicate resource ids |
| conditions.condition_id | ✅ pass | 0 | 129,716 | 0.00% | 1.00% | duplicate resource ids |
| observations.observation_id | ✅ pass | 0 | 2,674,521 | 0.00% | 1.00% | duplicate resource ids |
| medications.medication_id | ✅ pass | 0 | 180,891 | 0.00% | 1.00% | duplicate resource ids |
| procedures.procedure_id | ✅ pass | 0 | 579,074 | 0.00% | 1.00% | duplicate resource ids |
