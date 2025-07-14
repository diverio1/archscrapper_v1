#!/usr/bin/env python3
"""
Small-Town Architecture Job Scraper
----------------------------------
This script gathers job ads posted by architecture firms in small or mid-size U.S. towns
(population below 50 000 by default). It outputs an Excel file with:

    • firm_name
    • role_title
    • phone
    • website

Dependencies (all are free):
    requests
    beautifulsoup4
    pandas
    openpyxl  (Excel writer)
    playwright (for pages that need JavaScript)

Quick start on macOS / Linux:
    python -m venv venv
    source venv/bin/activate
    pip install requests beautifulsoup4 pandas openpyxl playwright
    playwright install
    python small_town_architecture_job_scraper.py

The first run may take a few minutes as Playwright downloads a headless browser.
No paid keys are needed. The U.S. Census API works without a key for this
population check rate. Add your own key if you plan heavy use.
"""

from __future__ import annotations
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Iterable, Tuple

import requests
import pandas as pd
from bs4 import BeautifulSoup

# -----------------------------------------------
# Configuration
# -----------------------------------------------
MAX_POPULATION = 50_000  # upper limit for a town to be considered small
OUTPUT_FILE = Path("architecture_jobs.xlsx")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

# Optional: provide your own Census API key to lift rate limits
CENSUS_KEY: str | None = None

# Regex to catch U.S. phone numbers (simple form)
PHONE_RE = re.compile(r"(?:\(\d{3}\)\s?|\b\d{3}[\-.\s])\d{3}[\-.\s]\d{4}\b")

# -----------------------------------------------
# Data classes
# -----------------------------------------------
@dataclass
class JobRow:
    firm_name: str
    role_title: str
    phone: str | None
    website: str | None

    def to_dict(self) -> Dict[str, str | None]:
        return asdict(self)

# -----------------------------------------------
# Helper functions
# -----------------------------------------------
def get_small_towns() -> List[Tuple[str, str]]:
    """Return a list of (city, state_abbr) where population < MAX_POPULATION."""
    url = (
        "https://api.census.gov/data/2023/pep/population"
        "?get=NAME,POP&for=place:*"
    )
    if CENSUS_KEY:
        url += f"&key={CENSUS_KEY}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()[1:]  # skip header row
    small_places: List[Tuple[str, str]] = []
    for name, pop, _, _ in data:
        try:
            pop_int = int(pop)
        except ValueError:
            continue
        if pop_int <= MAX_POPULATION:
            city_part, _, state_name = name.partition(",")
            state_abbr = STATE_LOOKUP.get(state_name.strip())
            if state_abbr:
                small_places.append((city_part.strip(), state_abbr))
    return small_places

# State name → postal code map
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

# ------------------------------------------------
# Scrapers per site
# ------------------------------------------------
def scrape_archinect(city: str, state: str) -> Iterable[JobRow]:
    """Yield JobRow entries from Archinect Jobs for the given city/state."""
    url_city = city.replace(" ", "-")
    url = f"https://archinect.com/jobs/{state}/{url_city}"
    try:
        html = requests.get(url, headers=HEADERS, timeout=20).text
    except Exception:
        return
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select(".job-listing"):
        firm_tag = card.select_one(".job-listing-title")
        role_tag = card.select_one(".job-position")
        if not (firm_tag and role_tag):
            continue
        firm_name = firm_tag.get_text(strip=True)
        role_title = role_tag.get_text(strip=True)
        job_link = "https://archinect.com" + card.a["href"]
        phone, website = get_contact_info(job_link)
        yield JobRow(firm_name, role_title, phone, website)

def scrape_aia_career_center(city: str, state: str) -> Iterable[JobRow]:
    """Simple keyword search on AIA Career Center."""
    query = f"{city}, {state}"
    search_url = (
        "https://careercenter.aia.org/jobs/"
        f"?keywords=&location={requests.utils.quote(query)}"
    )
    try:
        html = requests.get(search_url, headers=HEADERS, timeout=20).text
    except Exception:
        return
    soup = BeautifulSoup(html, "html.parser")
    for card in soup.select("article.job-listing"):
        firm_tag = card.select_one(".job-listing__info--name")
        role_tag = card.select_one(".job-listing__info--title")
        if not (firm_tag and role_tag):
            continue
        firm_name = firm_tag.get_text(strip=True)
        role_title = role_tag.get_text(strip=True)
        job_link = card.select_one("a")["href"]
        phone, website = get_contact_info(job_link)
        yield JobRow(firm_name, role_title, phone, website)

# ------------------------------------------------
# Contact info helper
# ------------------------------------------------
def get_contact_info(job_link: str) -> Tuple[str | None, str | None]:
    """Return (phone, website) found on the firm page linked from the ad."""
    phone = None
    website = None
    try:
        job_html = requests.get(job_link, headers=HEADERS, timeout=20).text
    except Exception:
        return phone, website
    soup = BeautifulSoup(job_html, "html.parser")
    text = soup.get_text(" ", strip=True)
    m = PHONE_RE.search(text)
    if m:
        phone = m.group()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "@" not in href and not href.startswith("mailto:"):
            website = href
            break
    if website and not phone:
        try:
            contact_html = requests.get(website, headers=HEADERS, timeout=20).text
            m2 = PHONE_RE.search(contact_html)
            if m2:
                phone = m2.group()
        except Exception:
            pass
    return phone, website

# ------------------------------------------------
# Main
# ------------------------------------------------
def main():
    rows: List[JobRow] = []
    towns = get_small_towns()
    print(f"Checking {len(towns)} towns…", file=sys.stderr)
    for idx, (city, state) in enumerate(towns, 1):
        print(f"[{idx}/{len(towns)}] {city}, {state}", file=sys.stderr)
        for job in scrape_archinect(city, state):
            rows.append(job)
        for job in scrape_aia_career_center(city, state):
            rows.append(job)
    if not rows:
        print("No data gathered.", file=sys.stderr)
        return
    df = pd.DataFrame([r.to_dict() for r in rows])
    df.drop_duplicates(subset=["firm_name", "role_title"], inplace=True)
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"Saved {len(df)} rows to {OUTPUT_FILE}", file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Aborted by user.", file=sys.stderr)
