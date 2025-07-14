#!/usr/bin/env python3
"""
Archinect Job Scraper (Debug Mode)
---------------------------------
This script fetches architecture job listings from Archinect for a given set of U.S. towns.
It logs debug info and saves results to an Excel file with columns:

  • firm_name
  • role_title
  • phone
  • website

Dependencies:
  requests
  beautifulsoup4
  pandas
  openpyxl

Usage:
  python3 -m venv venv
  source venv/bin/activate
  pip install requests beautifulsoup4 pandas openpyxl
  python scrapper_simple.py
"""

import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

# ---------------- Configuration ----------------
# Specify the city,state pairs you want to scrape
LOCATIONS: List[Tuple[str, str]] = [
    ("Fort Worth", "TX"),
    ("Bozeman", "MT"),
    ("Asheville", "NC"),
    # add more towns here
]

OUTPUT_FILE = Path("architecture_jobs.xlsx")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
PHONE_RE = re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[\-\.\s])\d{3}[\-\.\s]\d{4}\b")
TIMEOUT = 10  # seconds for HTTP requests

@dataclass
class JobRow:
    firm_name: str
    role_title: str
    phone: Optional[str]
    website: Optional[str]

    def to_dict(self):
        return asdict(self)

# -------------- Helper Functions --------------
def get_contact_info(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch phone and website from a job page."""
    phone = None
    site = None
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        m = PHONE_RE.search(text)
        if m:
            phone = m.group()
        # find first external link
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "@" not in href and not href.startswith("mailto"):
                site = href
                break
    except Exception as e:
        print(f"Contact fetch error for {url}: {e}", file=sys.stderr)
    return phone, site

# ------------- Scraper Function -------------
def scrape_archinect(city: str, state: str) -> List[JobRow]:
    rows: List[JobRow] = []
    url = f"https://archinect.com/jobs/{state}/{city.replace(' ', '-') }"
    print(f"Fetching Archinect URL: {url}", file=sys.stderr)
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        print(f"Status code: {r.status_code}", file=sys.stderr)
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".job-listing")
        print(f"Found {len(cards)} listings on Archinect for {city}, {state}", file=sys.stderr)
        for card in cards:
            title_tag = card.select_one(".job-listing-title")
            role_tag = card.select_one(".job-position")
            if not (title_tag and role_tag):
                continue
            firm = title_tag.get_text(strip=True)
            role = role_tag.get_text(strip=True)
            link = "https://archinect.com" + card.a["href"]
            phone, site = get_contact_info(link)
            print(f"  - {firm}: {role} (contacted)", file=sys.stderr)
            rows.append(JobRow(firm, role, phone, site))
    except Exception as e:
        print(f"Error scraping Archinect for {city}, {state}: {e}", file=sys.stderr)
    return rows

# ------------------ Main ------------------
def main():
    all_jobs: List[JobRow] = []
    for city, state in LOCATIONS:
        print(f"\nScraping {city}, {state}" + "="*20, file=sys.stderr)
        jobs = scrape_archinect(city, state)
        all_jobs.extend(jobs)
    if not all_jobs:
        print("No jobs collected.", file=sys.stderr)
        return
    df = pd.DataFrame([job.to_dict() for job in all_jobs])
    df.drop_duplicates(subset=["firm_name", "role_title"], inplace=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"\nSaved {len(df)} job rows to {OUTPUT_FILE}", file=sys.stderr)

if __name__ == "__main__":
    main()
