"""
scraper.py
----------
Scrapes rental and property listings for Bhopal from 99acres and MagicBricks.
Saves raw JSON snapshots to data/raw/ with a timestamp in the filename.

Run daily via cron:
    0 9 * * * cd /path/to/project && python src/scraper.py

Requirements:
    pip install requests beautifulsoup4 pandas
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import random
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
os.makedirs(RAW_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

# Bhopal localities to track — add/remove as needed
LOCALITIES = [
    "Arera Colony",
    "MP Nagar",
    "Shivaji Nagar",
    "Kolar Road",
    "Ayodhya Nagar",
    "Hoshangabad Road",
    "Bairagarh",
    "Misrod",
]

# Property types
PROPERTY_TYPES = ["1 BHK", "2 BHK", "3 BHK"]

TODAY = datetime.now().strftime("%Y-%m-%d")

# ── 99acres scraper ───────────────────────────────────────────────────────────

def scrape_99acres_bhopal(locality: str, bhk: str) -> list[dict]:
    """
    Scrapes rental listings from 99acres for a given Bhopal locality and BHK type.
    Returns a list of listing dicts.

    NOTE: Web scraping can break when sites update their HTML.
    If this function returns empty results, inspect the page source and
    update the CSS selectors below.
    """
    slug = locality.lower().replace(" ", "-")
    bhk_num = bhk.split()[0]  # "2 BHK" → "2"

    url = (
        f"https://www.99acres.com/property-for-rent-in-{slug}-bhopal-ffid"
        f"?preference=S&area_unit=1&res_com=R"
        f"&bedroom_num={bhk_num}"
    )

    listings = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 99acres listing cards (selector accurate as of 2024 — update if broken)
        cards = soup.select("div[class*='projectTuple__']")

        for card in cards[:20]:  # cap at 20 per page
            try:
                price_el = card.select_one("span[class*='price__']")
                area_el  = card.select_one("span[class*='area__']")
                title_el = card.select_one("div[class*='title__']")

                price_text = price_el.get_text(strip=True) if price_el else None
                area_text  = area_el.get_text(strip=True)  if area_el  else None
                title_text = title_el.get_text(strip=True) if title_el else None

                listings.append({
                    "source":    "99acres",
                    "locality":  locality,
                    "bhk":       bhk,
                    "price_raw": price_text,
                    "area_raw":  area_text,
                    "title":     title_text,
                    "url":       url,
                    "scraped_date": TODAY,
                })

            except Exception as e:
                print(f"  [warn] Skipping card: {e}")
                continue

    except requests.RequestException as e:
        print(f"  [error] Failed to fetch 99acres ({locality}, {bhk}): {e}")

    return listings


# ── MagicBricks scraper ───────────────────────────────────────────────────────

def scrape_magicbricks_bhopal(locality: str, bhk: str) -> list[dict]:
    """
    Scrapes rental listings from MagicBricks for a given Bhopal locality and BHK type.

    MagicBricks uses a JSON API — more stable than HTML scraping.
    """
    bhk_map = {"1 BHK": 1, "2 BHK": 2, "3 BHK": 3}
    bhk_num = bhk_map.get(bhk, 2)

    # MagicBricks search API (public, no auth required)
    api_url = (
        "https://www.magicbricks.com/mbsearch/property-details/propertyList"
        f"?editSearch=Y&category=R&proptype=Multistorey-Apartment,Builder-Floor-Apartment,"
        f"Penthouse,Studio-Apartment&Locality={locality.replace(' ', '%20')},"
        f"Bhopal&bedroom={bhk_num}&page=1"
    )

    listings = []

    try:
        api_headers = {**HEADERS, "Accept": "application/json, text/javascript, */*; q=0.01",
                       "X-Requested-With": "XMLHttpRequest"}
        resp = requests.get(api_url, headers=api_headers, timeout=15)
        data = resp.json()

        props = data.get("propertyList", {}).get("property", [])

        for prop in props[:20]:
            listings.append({
                "source":      "magicbricks",
                "locality":    locality,
                "bhk":         bhk,
                "price_raw":   str(prop.get("amount", "")),
                "area_raw":    str(prop.get("builtUpArea", "")),
                "title":       prop.get("heading", ""),
                "url":         "https://www.magicbricks.com" + prop.get("propertyUrl", ""),
                "scraped_date": TODAY,
            })

    except Exception as e:
        print(f"  [error] MagicBricks ({locality}, {bhk}): {e}")

    return listings


# ── Main runner ───────────────────────────────────────────────────────────────

def run_scraper():
    all_listings = []

    for locality in LOCALITIES:
        for bhk in PROPERTY_TYPES:
            print(f"  Scraping → {locality} | {bhk}")

            listings = scrape_99acres_bhopal(locality, bhk)
            all_listings.extend(listings)

            # Be polite — random delay between 2-5 seconds
            time.sleep(random.uniform(2, 5))

            listings = scrape_magicbricks_bhopal(locality, bhk)
            all_listings.extend(listings)

            time.sleep(random.uniform(2, 4))

    # Save raw JSON snapshot
    filename = os.path.join(RAW_DIR, f"bhopal_listings_{TODAY}.json")
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_listings, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved {len(all_listings)} listings → {filename}")
    return all_listings


if __name__ == "__main__":
    print(f"Starting Bhopal Price Intelligence scraper — {TODAY}\n")
    run_scraper()
