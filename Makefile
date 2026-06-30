# ClinicalFlow pipeline targets.
# On Windows without `make`, use the equivalent: .\make.ps1 <target>
#
# Assumes a virtualenv at .venv. Override PY for a different interpreter.

ifeq ($(OS),Windows_NT)
	PY ?= .venv/Scripts/python
else
	PY ?= .venv/bin/python
endif

.PHONY: setup data ingest qa cohort dashboard test all clean help

help:
	@echo "ClinicalFlow targets:"
	@echo "  setup      install pinned deps + editable package into .venv"
	@echo "  data       generate Synthea FHIR bundles into data/raw/ (seed 1234)"
	@echo "  ingest     parse FHIR bundles into DuckDB"
	@echo "  qa         run data-quality checks, write report"
	@echo "  cohort     build cardiovascular cohort, write summary"
	@echo "  dashboard  launch the Streamlit dashboard"
	@echo "  test       run pytest"
	@echo "  all        ingest -> qa -> cohort (regenerates reports)"

setup:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e .

data:
	$(PY) -m clinicalflow.acquire

ingest:
	$(PY) -m clinicalflow.pipeline ingest

qa:
	$(PY) -m clinicalflow.pipeline qa

cohort:
	$(PY) -m clinicalflow.pipeline cohort

dashboard:
	$(PY) -m streamlit run app/dashboard.py

test:
	$(PY) -m pytest

all:
	$(PY) -m clinicalflow.pipeline all

clean:
	$(PY) -c "import pathlib,glob; [pathlib.Path(p).unlink() for p in glob.glob('data/*.duckdb*')]"
