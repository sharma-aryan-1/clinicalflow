"""Phase 1: Synthea data acquisition.

Generates synthetic FHIR R4 bundles with a fixed seed for reproducibility and
copies them into ``data/raw/``. Idempotent: if patient bundles already exist it
does nothing unless ``--force`` is passed.

Usage:
    python -m clinicalflow.acquire          # generate if data/raw is empty
    python -m clinicalflow.acquire --force  # always regenerate
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .config import (
    RAW_DIR,
    ROOT_DIR,
    SYNTHEA_POPULATION,
    SYNTHEA_SEED,
    SYNTHEA_STATE,
    get_logger,
)

log = get_logger()

SYNTHEA_DIR = ROOT_DIR / "synthea"
SYNTHEA_REPO = "https://github.com/synthetichealth/synthea.git"
INFO_PREFIXES = ("hospitalInformation", "practitionerInformation")


def _patient_bundles(directory):
    """JSON files that are per-patient bundles (excludes org/practitioner info)."""
    return [
        p
        for p in directory.glob("*.json")
        if not p.name.startswith(INFO_PREFIXES)
    ]


def clone_synthea() -> None:
    if SYNTHEA_DIR.exists():
        log.info("Synthea clone already present at %s", SYNTHEA_DIR)
        return
    log.info("Cloning Synthea (shallow) into %s ...", SYNTHEA_DIR)
    subprocess.run(
        ["git", "clone", "--depth", "1", SYNTHEA_REPO, str(SYNTHEA_DIR)],
        check=True,
    )


def run_generator() -> None:
    """Invoke Synthea's Gradle launcher with the configured seed/population."""
    out_fhir = SYNTHEA_DIR / "output" / "fhir"
    if out_fhir.exists():
        log.info("Clearing previous Synthea output at %s", out_fhir)
        shutil.rmtree(out_fhir)

    gradlew = SYNTHEA_DIR / ("gradlew.bat" if os.name == "nt" else "gradlew")
    args = [
        "-p", str(SYNTHEA_POPULATION),
        "-s", str(SYNTHEA_SEED),
        "-cs", str(SYNTHEA_SEED),  # clinician seed, also fixed for reproducibility
        SYNTHEA_STATE,
    ]
    params = "-Params=[" + ",".join(f"'{a}'" for a in args) + "]"
    log.info(
        "Generating %d patients (seed=%d, state=%s). This can take several minutes...",
        SYNTHEA_POPULATION,
        SYNTHEA_SEED,
        SYNTHEA_STATE,
    )
    cmd = [str(gradlew), "run", params]
    if os.name == "nt":
        cmd = ["cmd", "/c", *cmd]
    subprocess.run(cmd, cwd=str(SYNTHEA_DIR), check=True)


def copy_bundles() -> None:
    out_fhir = SYNTHEA_DIR / "output" / "fhir"
    bundles = list(out_fhir.glob("*.json"))
    if not bundles:
        raise RuntimeError(f"No FHIR bundles found in {out_fhir} after generation.")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    # Wipe stale bundles so re-runs are clean.
    for old in RAW_DIR.glob("*.json"):
        old.unlink()

    for b in bundles:
        shutil.copy2(b, RAW_DIR / b.name)

    patients = _patient_bundles(RAW_DIR)
    log.info(
        "Copied %d files to %s (%d patient bundles + %d info bundles).",
        len(bundles),
        RAW_DIR,
        len(patients),
        len(bundles) - len(patients),
    )


def main(force: bool | None = None) -> None:
    if force is None:
        force = "--force" in sys.argv

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    existing = _patient_bundles(RAW_DIR)
    if existing and not force:
        log.info(
            "data/raw already has %d patient bundles; skipping generation "
            "(use --force to regenerate).",
            len(existing),
        )
        return

    clone_synthea()
    run_generator()
    copy_bundles()


if __name__ == "__main__":
    main()
