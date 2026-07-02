"""Shared pytest fixtures."""
import json
from pathlib import Path

import duckdb
import pytest

from clinicalflow import schema

FIXTURE = Path(__file__).parent / "fixtures" / "sample_bundle.json"


@pytest.fixture
def sample_bundle() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def mem_con():
    """Empty in-memory DuckDB connection."""
    con = duckdb.connect(":memory:")
    yield con
    con.close()


@pytest.fixture
def schema_con():
    """In-memory DuckDB with the six normalized tables created (empty)."""
    con = duckdb.connect(":memory:")
    for ddl in schema.TABLES.values():
        con.execute(ddl)
    yield con
    con.close()


@pytest.fixture
def status_of():
    """Helper: status of the result whose check matches and subject contains key."""
    def _lookup(results, check, key):
        for r in results:
            if r["check"] == check and key in r["subject"]:
                return r["status"]
        raise KeyError(f"no result for {check!r} containing {key!r}")
    return _lookup
