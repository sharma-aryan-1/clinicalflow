# ClinicalFlow task runner for Windows PowerShell (drop-in for `make`).
# Usage:  .\make.ps1 <target>
# Targets: setup data ingest qa cohort dashboard test all clean help
param(
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$ErrorActionPreference = "Stop"
$PY = ".\.venv\Scripts\python.exe"

function Invoke-Setup {
    & $PY -m pip install --upgrade pip
    & $PY -m pip install -r requirements.txt
    & $PY -m pip install -e .
}

switch ($Target) {
    "setup"     { Invoke-Setup }
    "data"      { & $PY -m clinicalflow.acquire }
    "ingest"    { & $PY -m clinicalflow.pipeline ingest }
    "qa"        { & $PY -m clinicalflow.pipeline qa }
    "cohort"    { & $PY -m clinicalflow.pipeline cohort }
    "dashboard" { & $PY -m streamlit run app/dashboard.py }
    "test"      { & $PY -m pytest }
    "all"       { & $PY -m clinicalflow.pipeline all }
    "clean"     { Get-ChildItem -Path "data" -Filter "*.duckdb*" -ErrorAction SilentlyContinue | Remove-Item -Force }
    default {
        Write-Host "ClinicalFlow targets:"
        Write-Host "  setup      install pinned deps + editable package into .venv"
        Write-Host "  data       generate Synthea FHIR bundles into data/raw/ (seed 1234)"
        Write-Host "  ingest     parse FHIR bundles into DuckDB"
        Write-Host "  qa         run data-quality checks, write report"
        Write-Host "  cohort     build cardiovascular cohort, write summary"
        Write-Host "  dashboard  launch the Streamlit dashboard"
        Write-Host "  test       run pytest"
        Write-Host "  all        ingest -> qa -> cohort (regenerates reports)"
    }
}
