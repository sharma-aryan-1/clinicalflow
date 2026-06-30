"""ClinicalFlow: FHIR-based EHR pipeline and cardiovascular cohort analysis.

Pipeline stages:
    ingest  -> FHIR R4 bundles into DuckDB
    quality -> data governance and QA checks
    cohort  -> cardiovascular cohort definition and analysis
    report  -> human-readable QA and cohort reports
"""

__version__ = "0.1.0"
