# SyncUp Job Scraper

Scrapes **Naukri**, **Indeed**, **Internshala** → imports into SyncUp `ExternalJob` → shows on `/findjobs/search`.

---

## Quick start (every run)

**Terminal 1**
```bash
cd SyncUp-App && make dev
```

**Terminal 2**
```bash
cd Job_Scrapper
./scrape_all.sh
```

Open: http://localhost:3000/findjobs/search

**Git Bash (Windows) — if Python not found:**
```bash
export PYTHON=py
./scrape_all.sh
```

---

## First time only

### 1. Python
```bash
cd Job_Scrapper
pip install playwright requests tf-playwright-stealth
playwright install chromium
chmod +x scrape_all.sh
```

### 2. SyncUp
```bash
cd SyncUp-App
make setup-local
cd packages/db && pnpm run migrate:all && pnpm run generate:all
cd ../..
```

### 3. API key (both must match)

`SyncUp-App/apps/job-service/.env`:
```env
EXTERNAL_JOB_IMPORT_API_KEY=local-dev-import-key
```

`scrape_all.sh` already uses `local-dev-import-key` — no `.env` file needed in Job_Scrapper.

---

## SyncUp connection

| What | Local |
|------|-------|
| Import URL | `http://localhost:6001/api/job-service/job/external/import` |
| API key (scraper) | `SYNCUP_IMPORT_API_KEY` → `local-dev-import-key` |
| API key (SyncUp) | `EXTERNAL_JOB_IMPORT_API_KEY` → `local-dev-import-key` |
| Gateway | `:6001` |
| Web UI | `http://localhost:3000/findjobs/search` |

**Flow:** `scrape_all.py` → `import_to_syncup.py` → `POST` with header `X-Import-Api-Key` → MongoDB `ExternalJob`.

Same `apply_url` = **update**, new URL = **insert**.

---

## What `scrape_all.sh` does

1. Scrape Internshala + Naukri + Indeed (`any` / `any`)
2. Merge → `merged_jobs_import.json`
3. Import to SyncUp

~80 jobs typical (one page per site).

---

## Other commands

**One source + filters**
```bash
printf "software\nbangalore\nn\n" | python internshala_scraper.py
export SYNCUP_IMPORT_API_KEY=local-dev-import-key
export SYNCUP_IMPORT_URL=http://localhost:6001/api/job-service/job/external/import
python import_to_syncup.py internshala_jobs.json
```

**One source + dedup (CI style)**
```bash
printf "any\nany\nn\n" | python naukri_scraper.py
python dedup_filter.py naukri
python import_to_syncup.py naukri_jobs_new.json
```

---

## Production (GitHub Actions)

- Cron: every 4 hours — `.github/workflows/scrape.yml`
- Secrets: `SYNCUP_IMPORT_URL`, `SYNCUP_IMPORT_API_KEY`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Python not found (Git Bash) | `export PYTHON=py` |
| `401 Invalid API key` | Keys must match on scraper + job-service |
| `401 No token provided` | Restart `make dev` |
| No jobs in UI | Log in, refresh `/findjobs/search` |

---

## Files

| File | Role |
|------|------|
| `scrape_all.sh` / `scrape_all.py` | Run all sources + import |
| `import_to_syncup.py` | POST jobs to SyncUp |
| `dedup_filter.py` | Skip already-seen jobs (CI) |
| `*_scraper.py` | Single source scrapers |
| `.env.example` | Reference only (not auto-loaded) |
