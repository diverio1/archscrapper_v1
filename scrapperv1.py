#!/usr/bin/env python3
"""
Small-Town Architecture Job Scraper
----------------------------------
This script gathers job ads posted by architecture firms in small U.S. towns
(population ≤ 50 000). It outputs an Excel file with:

  • firm_name  
  • role_title  
  • phone  
  • website  

Free dependencies:
  requests
  beautifulsoup4
  pandas
  openpyxl
  playwright

Quick start:
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install requests beautifulsoup4 pandas openpyxl playwright
  playwright install
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

# ─────────────── Config ───────────────
TIMEOUT = 30
MAX_POPULATION = 50_000
OUTPUT_FILE = Path("architecture_jobs.xlsx")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}
# Optional: set your own key if you hit limits
CENSUS_KEY: Optional[str] = None

PHONE_RE = re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[\-.\s])\d{3}[\-.\s]\d{4}\b")

STATE_LOOKUP = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI",
    "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO",
    "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH",
    "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


@dataclass
class JobRow:
    firm_name: str
    role_title: str
    phone: Optional[str]
    website: Optional[str]

    def to_dict(self):
        return asdict(self)


def get_small_towns() -> List[Tuple[str, str]]:
    """Return (city, state) for places with pop ≤ MAX_POPULATION."""
    raw = None
    for year in (2023, 2022, 2017):
        url = f"https://api.census.gov/data/{year}/pep/population"
        params = {"get": "NAME,POP", "for": "place:*"}
        if CENSUS_KEY:
            params["key"] = CENSUS_KEY
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            raw = r.json()
            break
        except Exception as e:
            print(f"census {year} failed: {e}", file=sys.stderr)
    if raw is None:
        sys.exit("No working census data.")
    towns = []
    for name, pop, *_ in raw[1:]:
        try:
            if int(pop) > MAX_POPULATION:
                continue
        except:
            continue
        city, _, state = name.partition(",")
        abbr = STATE_LOOKUP.get(state.strip())
        if abbr:
            towns.append((city.strip(), abbr))
    return towns


def get_contact_info(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Fetch a phone and site link from the job page or firm site."""
    phone = None
    site = None
    try:
        text = requests.get(url, headers=HEADERS, timeout=TIMEOUT).text
        soup = BeautifulSoup(text, "html.parser")
        m = PHONE_RE.search(soup.get_text(" ", strip=True))
        if m:
            phone = m.group()
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if h.startswith("http") and "@" not in h and not h.startswith("mailto"):
                site = h
                break
        if site and not phone:
            extra = requests.get(site, headers=HEADERS, timeout=TIMEOUT).text
            m2 = PHONE_RE.search(extra)
            if m2:
                phone = m2.group()
    except Exception as e:
        print(f"contact error {url}: {e}", file=sys.stderr)
    return phone, site


def scrape_archinect(city: str, state: str) -> List[JobRow]:
    rows = []
    url = f"https://archinect.com/jobs/{state}/{city.replace(' ', '-')}"
    try:
        html = requests.get(url, headers=HEADERS, timeout=TIMEOUT).text
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(".job-listing"):
            t1 = card.select_one(".job-listing-title")
            t2 = card.select_one(".job-position")
            if not (t1 and t2):
                continue
            link = "https://archinect.com" + card.a["href"]
            ph, site = get_contact_info(link)
            rows.append(JobRow(t1.get_text(strip=True), t2.get_text(strip=True), ph, site))
    except Exception as e:
        print(f"archinect {city}, {state} error: {e}", file=sys.stderr)
    return rows


def scrape_aia(city: str, state: str) -> List[JobRow]:
    rows = []
    url = "https://careercenter.aia.org/jobs/"
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            params={"keywords": "", "location": f"{city}, {state}"},
        )
        r.raise_for_status()
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
        print(f"aia {city}, {state} error: {e}", file=sys.stderr)
    return rows


def main():
    all_jobs: List[JobRow] = []
    towns = get_small_towns()
    print(f"Checking {len(towns)} towns…", file=sys.stderr)
    for i, (city, state) in enumerate(towns, 1):
        print(f"[{i}/{len(towns)}] {city}, {state}", file=sys.stderr)
        all_jobs.extend(scrape_archinect(city, state))
        all_jobs.extend(scrape_aia(city, state))
    if not all_jobs:
        print("No data found.", file=sys.stderr)
        return
    df = pd.DataFrame([j.to_dict() for j in all_jobs])
    df.drop_duplicates(subset=["firm_name", "role_title"], inplace=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Saved {len(df)} rows to {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
