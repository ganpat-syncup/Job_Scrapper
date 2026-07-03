#!/usr/bin/env python3
"""
import_to_syncup.py
Push scraped jobs JSON into SyncUp job-service ExternalJob collection.

Usage:
  python import_to_syncup.py internshala_jobs_new.json
  python import_to_syncup.py naukri_jobs_new.json indeed_jobs_new.json

Environment:
  SYNCUP_IMPORT_URL   e.g. http://localhost:6001/api/job-service/job/external/import
  SYNCUP_IMPORT_API_KEY  must match EXTERNAL_JOB_IMPORT_API_KEY in job-service
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

DEFAULT_IMPORT_URL = "http://localhost:6001/api/job-service/job/external/import"
BATCH_SIZE = 100


def load_jobs(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON array of jobs")
    return data


def post_batch(url: str, api_key: str, jobs: list[dict[str, Any]]) -> dict[str, Any]:
    res = requests.post(
        url,
        json={"jobs": jobs},
        headers={
            "Content-Type": "application/json",
            "X-Import-Api-Key": api_key,
        },
        timeout=120,
    )
    try:
        body = res.json()
    except Exception:
        body = {"raw": res.text}
    if not res.ok:
        msg = str(body)
        if res.status_code == 401 and "No token provided" in msg:
            raise RuntimeError(
                f"HTTP {res.status_code}: {body}\n"
                "Hint: job-service is likely running old code. Restart SyncUp "
                "(make dev) so /job/external/import is registered before JWT auth."
            )
        raise RuntimeError(f"HTTP {res.status_code}: {body}")
    return body


def import_jobs(
    jobs: list[dict[str, Any]], url: str, api_key: str, label: str = "batch"
) -> dict[str, int]:
    if not jobs:
        print(f"[SKIP] {label}: no jobs to import")
        return {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

    totals = {"inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

    for i in range(0, len(jobs), BATCH_SIZE):
        batch = jobs[i : i + BATCH_SIZE]
        result = post_batch(url, api_key, batch)
        data = result.get("data") or result
        for key in totals:
            totals[key] += int(data.get(key, 0))
        print(
            f"[BATCH] {label} rows {i + 1}-{i + len(batch)}: "
            f"+{data.get('inserted', 0)} inserted, "
            f"{data.get('updated', 0)} updated, "
            f"{data.get('skipped', 0)} skipped, "
            f"{data.get('failed', 0)} failed"
        )

    print(
        f"[DONE] {label}: {len(jobs)} jobs sent — "
        f"inserted={totals['inserted']}, updated={totals['updated']}, "
        f"skipped={totals['skipped']}, failed={totals['failed']}"
    )
    return totals


def import_file(path: str, url: str, api_key: str) -> None:
    jobs = load_jobs(path)
    import_jobs(jobs, url, api_key, label=path)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python import_to_syncup.py <jobs.json> [more.json ...]")
        return 1

    url = os.environ.get("SYNCUP_IMPORT_URL", DEFAULT_IMPORT_URL).strip()
    api_key = os.environ.get("SYNCUP_IMPORT_API_KEY", "").strip()
    if not api_key:
        print("[ERROR] Set SYNCUP_IMPORT_API_KEY (matches SyncUp EXTERNAL_JOB_IMPORT_API_KEY)")
        return 1

    exit_code = 0
    for path in sys.argv[1:]:
        if not os.path.exists(path):
            print(f"[ERROR] File not found: {path}")
            exit_code = 1
            continue
        try:
            import_file(path, url, api_key)
        except Exception as e:
            print(f"[ERROR] Failed to import {path}: {e}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
