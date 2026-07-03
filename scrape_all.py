#!/usr/bin/env python3
"""
scrape_all.py
Scrape latest jobs from Internshala + Naukri + Indeed with NO role/location/salary
filters (any/any), merge all unique jobs, import into SyncUp.

Usage:
  export SYNCUP_IMPORT_API_KEY=local-dev-import-key
  python scrape_all.py

Environment:
  SYNCUP_IMPORT_URL       SyncUp import endpoint
  SYNCUP_IMPORT_API_KEY   required
  HEADLESS                default true
  SKIP_LOCAL_PUSH         default true
  PYTHON                  python3 or python (auto-detected)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from import_to_syncup import DEFAULT_IMPORT_URL, import_jobs

ROOT = Path(__file__).resolve().parent

SCRAPERS = [
    ("internshala_scraper.py", "internshala_jobs.json", "Internshala"),
    ("naukri_scraper.py", "naukri_jobs.json", "Naukri"),
    ("indeed_scraper.py", "indeed_jobs.json", "Indeed"),
]

SCRAPER_INPUT = "any\nany\nn\n"
OUTPUT_FILE = "merged_jobs_import.json"


def python_cmd() -> str:
    return os.environ.get("PYTHON", "python3" if sys.platform != "win32" else "python")


def run_scraper(script: str, label: str) -> None:
    path = ROOT / script
    if not path.exists():
        print(f"[WARN] Missing {script}, skipping {label}")
        return

    env = {
        **os.environ,
        "HEADLESS": os.environ.get("HEADLESS", "true"),
        "SKIP_LOCAL_PUSH": os.environ.get("SKIP_LOCAL_PUSH", "true"),
        "PYTHONIOENCODING": "utf-8",
    }
    print(f"\n{'=' * 60}\n[SCRAPE] {label} (any / any, no filters)\n{'=' * 60}")
    proc = subprocess.run(
        [python_cmd(), str(path)],
        input=SCRAPER_INPUT,
        text=True,
        cwd=str(ROOT),
        env=env,
    )
    if proc.returncode != 0:
        print(f"[WARN] {label} scraper exited with code {proc.returncode}")


def job_key(job: dict) -> str:
    return (job.get("apply_link") or "").strip() or (
        f"{job.get('title', '')}__{job.get('company', '')}".lower()
    )


def merge_jobs() -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    for _, outfile, label in SCRAPERS:
        path = ROOT / outfile
        if not path.exists():
            print(f"[WARN] No file {outfile} from {label}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            jobs = json.load(f)
        if not isinstance(jobs, list):
            continue
        added = 0
        for job in jobs:
            key = job_key(job)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(job)
            added += 1
        print(f"[MERGE] {label}: +{added} from {outfile} (total {len(merged)})")

    return merged


def main() -> int:
    api_key = os.environ.get("SYNCUP_IMPORT_API_KEY", "").strip()
    url = os.environ.get("SYNCUP_IMPORT_URL", DEFAULT_IMPORT_URL).strip()

    if not api_key:
        print("[ERROR] Set SYNCUP_IMPORT_API_KEY")
        return 1

    print("[START] Scraping all jobs (no filters) from all sources…")

    for script, _, label in SCRAPERS:
        run_scraper(script, label)

    jobs = merge_jobs()
    if not jobs:
        print("[ERROR] No jobs scraped. Check network / Playwright / site blocks.")
        return 1

    out_path = ROOT / OUTPUT_FILE
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)
    print(f"\n[SAVED] {len(jobs)} jobs -> {out_path.name}")

    print(f"\n[IMPORT] Sending {len(jobs)} jobs to SyncUp…")
    import_jobs(jobs, url, api_key, label="merged_jobs_import")
    print("\n[OK] Done. Search at /findjobs/search in SyncUp.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
