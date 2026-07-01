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
