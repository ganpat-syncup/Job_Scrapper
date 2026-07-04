"""
linkedin_scraper.py
SyncUp — Project 02 / Job Scraper
LinkedIn public jobs search scraper (Playwright + stealth).

Note: LinkedIn often shows a login wall for unauthenticated sessions.
Set LINKEDIN_LI_AT (and optionally LINKEDIN_JSESSIONID) from a logged-in browser
cookie for more reliable results.
"""

import json
import logging
import os
import re
import requests
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import stealth_sync
    STEALTH_AVAILABLE = True
except ImportError:
    STEALTH_AVAILABLE = False

SOURCE_PLATFORM = "LinkedIn"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "linkedin_jobs.json")
SERVER_URL = os.environ.get("SYNCUP_SERVER_URL", "http://localhost:3000/api/jobs")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
HEADLESS = os.environ.get("HEADLESS", "false").lower() == "true"
LINKEDIN_LI_AT = os.environ.get("LINKEDIN_LI_AT", "").strip()
LINKEDIN_JSESSIONID = os.environ.get("LINKEDIN_JSESSIONID", "").strip()

logging.basicConfig(
    filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scraper.log"),
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


def alert_slack(message: str) -> None:
    if not SLACK_WEBHOOK_URL:
        return
    try:
        requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
    except Exception:
        pass


def build_url(role: str, location: str, is_remote: bool) -> str:
    role_slug = role.strip()
    location_slug = location.strip()
    is_any = role_slug.lower() in ("any", "all", "") and location_slug.lower() in ("any", "all", "")

    if is_any:
        return "https://www.linkedin.com/jobs/search/?location=India&f_TPR=r86400"
    if is_remote:
        keywords = quote_plus(role_slug) if role_slug else ""
        base = f"https://www.linkedin.com/jobs/search/?keywords={keywords}&location=India&f_WT=2"
        return base
    keywords = quote_plus(role_slug)
    loc = quote_plus(location_slug)
    return f"https://www.linkedin.com/jobs/search/?keywords={keywords}&location={loc}"


def parse_salary_amount(salary_text: str) -> Optional[int]:
    if not salary_text or salary_text.strip() in ("N/A", "Not disclosed", ""):
        return None
    numbers = re.findall(r"\d+", salary_text.replace(",", ""))
    try:
        return int(numbers[0]) if numbers else None
    except ValueError:
        return None


def passes_salary_filter(
    salary_text: str, min_salary: Optional[int], max_salary: Optional[int]
) -> bool:
    if min_salary is None and max_salary is None:
        return True
    amount = parse_salary_amount(salary_text)
    if amount is None:
        return False
    if min_salary is not None and amount < min_salary:
        return False
    if max_salary is not None and amount > max_salary:
        return False
    return True


def is_duplicate(seen: list, new_job: dict) -> bool:
    link = new_job.get("apply_link")
    if link and link != "N/A":
        return any(j.get("apply_link") == link for j in seen)
    return any(
        j.get("title") == new_job.get("title")
        and j.get("company") == new_job.get("company")
        for j in seen
    )


def normalize_apply_link(href: str) -> str:
    if not href or href == "N/A":
        return "N/A"
    href = href.strip()
    if href.startswith("/"):
        return f"https://www.linkedin.com{href.split('?')[0]}"
    return href.split("?")[0]


def text_from(card, selectors: list[str]) -> str:
    for sel in selectors:
        el = card.query_selector(sel)
        if el:
            t = el.inner_text().strip()
            if t:
                return t
    return "N/A"


def link_from(card, selectors: list[str]) -> str:
    for sel in selectors:
        el = card.query_selector(sel)
        if el:
            href = el.get_attribute("href")
            if href:
                return normalize_apply_link(href)
    return "N/A"


def dismiss_overlays(page) -> None:
    for sel in (
        'button[action-type="accept"]',
        'button[data-tracking-control-name="public_jobs_contextual-sign-in-modal_modal_dismiss"]',
        'button.artdeco-modal__dismiss',
    ):
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click(timeout=2000)
                page.wait_for_timeout(800)
                break
        except Exception:
            continue


def add_linkedin_cookies(context) -> None:
    if not LINKEDIN_LI_AT:
        return
    cookies = [
        {
            "name": "li_at",
            "value": LINKEDIN_LI_AT,
            "domain": ".linkedin.com",
            "path": "/",
        }
    ]
    if LINKEDIN_JSESSIONID:
        cookies.append(
            {
                "name": "JSESSIONID",
                "value": LINKEDIN_JSESSIONID,
                "domain": ".www.linkedin.com",
                "path": "/",
            }
        )
    context.add_cookies(cookies)
    print("[AUTH] LinkedIn session cookie applied")


def scrape_linkedin(
    role: str,
    location: str,
    min_salary: Optional[int] = None,
    max_salary: Optional[int] = None,
) -> list:
    is_remote = location.strip().lower() in ("remote", "work-from-home", "wfh")
    url = build_url(role, location, is_remote)
    print(f"\n[SEARCH] Opening: {url}")
    scraped = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en'] });
            window.chrome = { runtime: {} };
        """)
        add_linkedin_cookies(context)

        page = context.new_page()
        if STEALTH_AVAILABLE:
            stealth_sync(page)
            print("[STEALTH] Stealth mode active")

        try:
            page.goto(url, timeout=60_000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            dismiss_overlays(page)
            page.wait_for_timeout(2000)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(2000)
        except Exception as e:
            msg = f"[LinkedIn] Failed to load {url}: {e}"
            logging.error(msg)
            print(f"[ERROR] Could not load page: {e}")
            alert_slack(f"[ERROR] LinkedIn scraper failed\n{msg}")
            browser.close()
            return []

        if page.query_selector('form[action*="login"], input#session_key'):
            print(
                "[WARN] LinkedIn login wall detected. "
                "Set LINKEDIN_LI_AT in env for authenticated scraping."
            )

        cards = page.query_selector_all(
            "li.jobs-search-results__list-item, "
            "li.scaffold-layout__list-item, "
            "div.job-search-card, "
            "div.base-card"
        )
        print(f"[FOUND] Found {len(cards)} listings on page\n")

        if not cards:
            msg = f"[LinkedIn] No listings at {url} — login wall or layout change"
            logging.error(msg)
            alert_slack(f"[WARN] LinkedIn 0 listings\n{url}")
            browser.close()
            return scraped

        for card in cards:
            try:
                title = text_from(
                    card,
                    [
                        "h3.base-search-card__title",
                        "a.job-search-card__title-link",
                        "h3.job-search-card__title",
                    ],
                )
                company = text_from(
                    card,
                    [
                        "h4.base-search-card__subtitle",
                        "a.job-search-card__subtitle-link",
                        "h4.job-search-card__subtitle",
                    ],
                )
                location_t = text_from(
                    card,
                    [
                        "span.job-search-card__location",
                        ".artdeco-entity-lockup__caption",
                    ],
                ).lower()
                date_raw = text_from(
                    card,
                    ["time", "span.job-search-card__listdate", "time.job-search-card__listdate"],
                )
                apply_link = link_from(
                    card,
                    [
                        "a.base-card__full-link",
                        "a.job-search-card__title-link",
                        "a[href*='/jobs/view/']",
                    ],
                )
                salary = "Not disclosed"

                if apply_link == "N/A" or title == "N/A":
                    continue

                if not passes_salary_filter(salary, min_salary, max_salary):
                    continue

                record = {
                    "title": title,
                    "company": company,
                    "location": location_t,
                    "job_type": "N/A",
                    "salary": salary,
                    "salary_numeric": None,
                    "skills_required": [],
                    "posting_date": date_raw,
                    "apply_link": apply_link,
                    "source_platform": SOURCE_PLATFORM,
                    "scraped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }

                if is_duplicate(scraped, record):
                    print(f"  [SKIP]  Duplicate: {title} @ {company}")
                    continue

                scraped.append(record)
                print(f"  [OK] {title} — {company}")

            except Exception as e:
                logging.error(f"[LinkedIn] Card error: {e}")
                print(f"  [WARN]  Card error: {e}")
                continue

        browser.close()

    return scraped


def save_jobs(jobs: list, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)
    print(f"\n[SAVED] Saved {len(jobs)} jobs -> {filepath}")


def push_to_server(jobs: list, api_url: str = SERVER_URL) -> None:
    pushed = skipped = failed = 0
    for job in jobs:
        try:
            res = requests.post(api_url, json=job, timeout=10)
            data = res.json()
            if res.status_code == 200 and data.get("status") == "stored":
                pushed += 1
            elif data.get("status") == "duplicate":
                skipped += 1
            else:
                failed += 1
        except requests.exceptions.ConnectionError:
            print("\n[ERROR] Cannot connect to local server")
            break
        except Exception as e:
            failed += 1
            logging.error(f"Push error: {e}")
    print(f"\n[STATS] Server push: {pushed} stored, {skipped} duplicates, {failed} failed")


def prompt_salary_filter() -> Tuple[Optional[int], Optional[int]]:
    use_filter = input("Apply a salary filter? (y/n): ").strip().lower()
    if use_filter != "y":
        return None, None

    def parse_int(prompt: str):
        val = input(prompt).strip()
        if not val:
            return None
        try:
            return int(val.replace(",", ""))
        except ValueError:
            print("  Invalid — skipping this bound.")
            return None

    return (
        parse_int("  Min salary Rs/year (blank = no minimum): "),
        parse_int("  Max salary Rs/year (blank = no maximum): "),
    )


if __name__ == "__main__":
    role = input("Enter role (e.g. software developer, or any): ").strip()
    location = input("Enter location (e.g. pune, remote, or any): ").strip()
    min_s, max_s = prompt_salary_filter()

    jobs = scrape_linkedin(role, location, min_salary=min_s, max_salary=max_s)

    if jobs:
        save_jobs(jobs, OUTPUT_FILE)
        if os.environ.get("SKIP_LOCAL_PUSH", "").lower() not in ("1", "true", "yes"):
            push_to_server(jobs)
    else:
        print("\n[WARN]  No jobs found. Try LINKEDIN_LI_AT cookie if login wall appears.")
        alert_slack(f"[WARN] LinkedIn 0 results for '{role}' in '{location}'")
