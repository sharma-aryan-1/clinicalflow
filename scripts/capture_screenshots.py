"""Capture dashboard screenshots into docs/ via Playwright.

Assumes a Streamlit server is already running (default http://localhost:8533).
Usage:
    # terminal 1
    streamlit run app/dashboard.py --server.headless true --server.port 8533
    # terminal 2
    python scripts/capture_screenshots.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8533"
DOCS = Path(__file__).resolve().parents[1] / "docs"
DOCS.mkdir(exist_ok=True)

SECTIONS = {
    "Overview": "overview",
    "Pipeline": "pipeline",
    "Condition prevalence": "condition_prevalence",
    "Comorbidities": "comorbidities",
    "Medications": "medications",
    "Vitals & labs": "vitals_labs",
    "Data quality": "data_quality",
}


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000},
                                device_scale_factor=2)
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(5000)
        sidebar = page.locator('[data-testid="stSidebar"]')
        for label, slug in SECTIONS.items():
            sidebar.get_by_text(label, exact=True).first.click()
            page.wait_for_timeout(3500)  # let plotly render
            out = DOCS / f"{slug}.png"
            page.screenshot(path=str(out), full_page=True)
            print(f"captured {out.name}")
        browser.close()


if __name__ == "__main__":
    main()
