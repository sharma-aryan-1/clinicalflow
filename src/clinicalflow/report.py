"""Report writers: render QA and cohort results to Markdown.

Pure formatting — all computation lives in quality.py / cohort.py.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import ERROR_BUDGET, REPORTS_DIR, get_logger

log = get_logger()


def _fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.2f}%"


def write_quality_report(results: list[dict], path: Path | None = None) -> Path:
    """Render QA check results to a human-readable Markdown report."""
    path = path or (REPORTS_DIR / "data_quality_report.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    failed = [r for r in results if r["status"] == "fail"]
    overall = "PASS ✅" if not failed else f"FAIL ❌ ({len(failed)}/{total} checks)"

    lines: list[str] = []
    lines.append("# Data Quality Report")
    lines.append("")
    lines.append(
        "> Synthetic data (Synthea), no PHI. This report applies an "
        f"**error-budget contract**: a check fails when violations exceed "
        f"**{ERROR_BUDGET * 100:.0f}%** of the rows it inspects."
    )
    lines.append("")
    lines.append(f"- Generated: {datetime.now():%Y-%m-%d %H:%M}")
    lines.append(f"- Checks run: **{total}**")
    lines.append(f"- Overall: **{overall}**")
    lines.append("")

    # Group by check category, preserving first-seen order.
    categories: list[str] = []
    for r in results:
        if r["check"] not in categories:
            categories.append(r["check"])

    for cat in categories:
        rows = [r for r in results if r["check"] == cat]
        cat_fail = any(r["status"] == "fail" for r in rows)
        badge = "❌ FAIL" if cat_fail else "✅ PASS"
        lines.append(f"## {cat} — {badge}")
        lines.append("")
        lines.append("| Subject | Status | Violations | Inspected | Rate | Budget | Notes |")
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for r in rows:
            status = "✅ pass" if r["status"] == "pass" else "❌ fail"
            lines.append(
                f"| {r['subject']} | {status} | {r['violations']:,} | "
                f"{r['total']:,} | {_fmt_pct(r['observed'])} | "
                f"{_fmt_pct(r['threshold'])} | {r.get('note', '') or ''} |"
            )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Wrote QA report -> %s", path)
    return path


def _num(x, digits=1):
    return "—" if x is None else f"{x:.{digits}f}"


def write_cohort_report(m: dict, path: Path | None = None) -> Path:
    """Render cohort analysis metrics to a short population-health brief."""
    path = path or (REPORTS_DIR / "cohort_summary.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    L: list[str] = []
    L.append("# Cardiovascular Cohort Summary")
    L.append("")
    L.append("> Synthetic data (Synthea), no PHI. A population-health brief over "
             "patients with one or more cardiovascular conditions.")
    L.append("")
    L.append(f"- Generated: {datetime.now():%Y-%m-%d %H:%M}")
    L.append("")

    # Overview
    L.append("## Overview")
    L.append("")
    L.append(f"- **Total population:** {m['population']:,} patients")
    L.append(f"- **Cardiovascular cohort:** {m['cohort_size']:,} patients "
             f"(**{m['cohort_pct'] * 100:.1f}%** of the population)")
    L.append(f"- **Mean age:** {_num(m['age_mean'])} years")
    diab_n, diab_pct = m["diabetes"]
    L.append(f"- **Diabetes within cohort:** {diab_n:,} ({diab_pct * 100:.1f}%)")
    L.append("")

    # Sex
    L.append("### Sex distribution (cohort)")
    L.append("")
    L.append("| Sex | Patients | Share |")
    L.append("|---|---:|---:|")
    for gender, n in m["sex"]:
        L.append(f"| {gender} | {n:,} | {n / m['cohort_size'] * 100:.1f}% |")
    L.append("")

    # Age
    L.append("### Age distribution (cohort)")
    L.append("")
    L.append("| Age band | Patients | Share |")
    L.append("|---|---:|---:|")
    for label, n in m["age_buckets"]:
        L.append(f"| {label} | {n:,} | {n / m['cohort_size'] * 100:.1f}% |")
    L.append("")

    # Prevalence
    L.append("## Condition prevalence")
    L.append("")
    L.append("| Condition | Patients | % of cohort | % of population |")
    L.append("|---|---:|---:|---:|")
    for label, n, pct_c, pct_p in m["prevalence"]:
        L.append(f"| {label} | {n:,} | {pct_c * 100:.1f}% | {pct_p * 100:.1f}% |")
    L.append("")

    # Comorbidity matrix
    L.append("## Comorbidity co-occurrence")
    L.append("")
    L.append("Cell = patients having **both** the row and column condition "
             "(diagonal = total with that condition).")
    L.append("")
    labels = m["comorbidity_labels"]
    short = [lb.split("/")[0][:10] for lb in labels]
    L.append("| | " + " | ".join(short) + " |")
    L.append("|---|" + "---:|" * len(short))
    for i, row_label in enumerate(labels):
        cells = " | ".join(str(int(v)) for v in m["comorbidity_matrix"][i])
        L.append(f"| **{row_label}** | {cells} |")
    L.append("")

    # Medications
    L.append("## Medication patterns (cohort)")
    L.append("")
    L.append("| Drug class | Patients on ≥1 | % of cohort |")
    L.append("|---|---:|---:|")
    for cls, n, pct in m["med_classes"]:
        L.append(f"| {cls} | {n:,} | {pct * 100:.1f}% |")
    L.append("")

    # Vitals & labs
    bp, chol = m["bp"], m["chol"]
    L.append("## Vitals & labs (latest per cohort patient)")
    L.append("")
    L.append(f"- **Blood pressure** (n={bp['n']:,}): "
             f"systolic mean {_num(bp['sys_mean'])} / median {_num(bp['sys_median'])} mmHg; "
             f"diastolic mean {_num(bp['dia_mean'])} / median {_num(bp['dia_median'])} mmHg.")
    L.append(f"- **Population-health flag — latest BP ≥ 140/90:** "
             f"**{bp['flag_count']:,}** patients ({bp['flag_pct'] * 100:.1f}% of those with a BP).")
    L.append(f"- **Total cholesterol** (n={chol['n']:,}): "
             f"mean {_num(chol['mean'])}, median {_num(chol['median'])}, "
             f"IQR [{_num(chol['p25'])}, {_num(chol['p75'])}] mg/dL.")
    L.append("")

    path.write_text("\n".join(L), encoding="utf-8")
    log.info("Wrote cohort summary -> %s", path)
    return path
