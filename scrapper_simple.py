#!/usr/bin/env python3
"""
Simple Architecture Job Scraper
--------------------------------
This script gathers job ads posted by architecture firms in specified U.S. towns.
It outputs an Excel file with:

  • firm_name
  • role_title
  • phone
  • website

Dependencies (all free):
  requests
  beautifulsoup4
  pandas
  openpyxl

Quick start:
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install requests beautifulsoup4 pandas openpyxl
  python scrapperv1.py
"""

import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Tuple, Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

# -----------------------------------------------
# Configuration
# -----------------------------------------------
# List the towns you want to check (City, State)
LOCATIONS: List[Tuple[str, str]] = [
    ("Fort Worth", "TX"),
    ("Bozeman", "MT"),
    ("Asheville", "NC"),
    # add more entries here
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

# -----------------------------------------------
# Data class
# -----------------------------------------------
@dataclass
class JobRow:
    firm_name: str
    role_title: str
    phone: Optional[str]
    website: Optional[str]

    def to_dict(self):
        return asdict(self)

# -----------------------------------------------
# Helper function to extract phone & site
# -----------------------------------------------
def get_contact_info(url: str) -> Tuple[Optional[str], Optional[str]]:
    phone = None
    site = None
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        m = PHONE_RE.search(text)
        if m:
            phone = m.group()
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and "@" not in h and not h.startswith("mailto"):
                site = h
                break
    except Exception as e:
        print(f"Contact fetch error {url}: {e}", file=sys.stderr)
    return phone, site

# -----------------------------------------------
# Scraper functions
# -----------------------------------------------
def scrape_archinect(city: str, state: str) -> List[JobRow]:
    rows: List[JobRow] = []
    url = f"https://archinect.com/jobs/{state}/{city.replace(' ', '-') }"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select(".job-listing"):
            t1 = card.select_one(".job-listing-title")
            t2 = card.select_one(".job-position")
            if not (t1 and t2):
                continue
            link = "https://archinect.com" + card.a["href"]
            ph, site = get_contact_info(link)
            rows.append(JobRow(t1.get_text(strip=True), t2.get_text(strip=True), ph, site))
    except Exception as e:
        print(f"Archinect error {city}, {state}: {e}", file=sys.stderr)
    return rows


def scrape_aia(city: str, state: str) -> List[JobRow]:
    rows: List[JobRow] = []
    url = "https://careercenter.aia.org/jobs/"
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            params={"keywords": "", "location": f"{city}, {state}"},
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("article.job-listing"):
            n = card.select_one(".job-listing__info--name")
            r2 = card.select_one(".job-listing__info--title")
            if not (n and r2):
                continue
            link = card.select_one("a")["href"]
            ph, site = get_contact_info(link)
            rows.append(JobRow(n.get_text(strip=True), r2.get_text(strip=True), ph, site))
    except Exception as e:
        print(f"AIA error {city}, {state}: {e}", file=sys.stderr)
    return rows

# -----------------------------------------------
# Main
# -----------------------------------------------
def main():
    all_jobs: List[JobRow] = []
    for city, state in LOCATIONS:
        print(f"Scraping {city}, {state}…", file=sys.stderr)
        all_jobs.extend(scrape_archinect(city, state))
        all_jobs.extend(scrape_aia(city, state))
    if not all_jobs:
        print("No jobs found.", file=sys.stderr)
        return
    df = pd.DataFrame([j.to_dict() for j in all_jobs])
    df.drop_duplicates(subset=["firm_name", "role_title"], inplace=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Saved {len(df)} jobs to {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
