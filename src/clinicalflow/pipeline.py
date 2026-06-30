"""Orchestrates ingest -> qa -> cohort -> report.

Usage:
    python -m clinicalflow.pipeline all
    python -m clinicalflow.pipeline ingest
"""
from __future__ import annotations

import sys

from .config import get_logger

log = get_logger()

STAGES = ("ingest", "qa", "cohort", "report", "all")


def run(stage: str) -> None:
    if stage not in STAGES:
        log.error("Unknown stage %r. Choose from: %s", stage, ", ".join(STAGES))
        sys.exit(2)
    log.info("[pipeline] requested stage: %s", stage)

    if stage in ("ingest", "all"):
        from . import ingest

        ingest.main()
    if stage in ("qa", "all"):
        from . import quality

        quality.main()
    if stage in ("cohort", "all"):
        from . import cohort

        cohort.main()


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    run(stage)


if __name__ == "__main__":
    main()
