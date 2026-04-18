"""
clean.py
--------
Reads raw JSON snapshots, cleans and normalises them into a single
analysis-ready CSV: data/processed/bhopal_clean.csv

Run after scraper.py:
    python src/clean.py

What this does:
  - Parses messy price strings ("₹ 12,000/month", "12K", "1.2 Lac") → numeric
  - Parses area strings ("850 sq.ft", "850 Sq. Ft.") → numeric (sq ft)
  - Calculates price per sq ft
  - Adds calendar features: week_number, month, is_festival_season
  - Deduplicates by (locality, bhk, price, area, date)
"""

import os
import re
import json
import glob
import pandas as pd
from datetime import datetime, date

RAW_DIR       = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)

OUTPUT_CSV = os.path.join(PROCESSED_DIR, "bhopal_clean.csv")


# ── Price parser ──────────────────────────────────────────────────────────────

def parse_price(raw: str) -> float | None:
    """
    Converts messy Indian price strings to a float (₹ per month for rent).

    Examples handled:
        "₹ 12,000/month"  → 12000.0
        "12K"             → 12000.0
        "1.2 Lac"         → 120000.0
        "45,000"          → 45000.0
        "₹8500"           → 8500.0
    """
    if not raw or not isinstance(raw, str):
        return None

    raw = raw.upper().replace(",", "").replace("₹", "").replace("RS", "").strip()

    # Remove common suffixes that don't affect value
    raw = re.sub(r"(PER MONTH|/MONTH|MONTH|P\.M\.)", "", raw).strip()

    try:
        if "LAC" in raw or "LAKH" in raw:
            num = re.search(r"[\d.]+", raw)
            return float(num.group()) * 100_000 if num else None
        elif "K" in raw:
            num = re.search(r"[\d.]+", raw)
            return float(num.group()) * 1_000 if num else None
        elif "CR" in raw or "CRORE" in raw:
            num = re.search(r"[\d.]+", raw)
            return float(num.group()) * 10_000_000 if num else None
        else:
            num = re.search(r"[\d.]+", raw)
            return float(num.group()) if num else None
    except (ValueError, AttributeError):
        return None


# ── Area parser ───────────────────────────────────────────────────────────────

def parse_area_sqft(raw: str) -> float | None:
    """
    Converts area strings to float in sq ft.

    Examples:
        "850 sq.ft"   → 850.0
        "79 Sq. Mt."  → 850.3  (1 sqm = 10.764 sqft)
        "850"         → 850.0
    """
    if not raw or not isinstance(raw, str):
        return None

    raw_up = raw.upper()
    num = re.search(r"[\d.]+", raw.replace(",", ""))

    if not num:
        return None

    val = float(num.group())

    if "SQ. MT" in raw_up or "SQM" in raw_up or "SQ.M" in raw_up:
        val = val * 10.764  # convert sqm → sqft

    return round(val, 1)


# ── Festival season flags ─────────────────────────────────────────────────────

# Key Indian festivals and wedding season dates (2024-2025)
# These are the periods where we hypothesise demand spikes
FESTIVAL_WINDOWS = [
    # (label, start_mmdd, end_mmdd)
    ("Diwali",        "10-15", "11-05"),
    ("Navratri",      "10-01", "10-15"),
    ("Wedding Season","11-15", "12-31"),
    ("Wedding Season","01-01", "02-28"),
    ("Dussehra",      "10-10", "10-15"),
    ("Holi",          "03-20", "03-31"),
    ("Eid",           "04-05", "04-15"),  # approximate — adjust yearly
]

def get_festival_label(date_str: str) -> str | None:
    """Returns festival name if the date falls in a known festival window."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        mmdd = d.strftime("%m-%d")
        for label, start, end in FESTIVAL_WINDOWS:
            if start <= mmdd <= end:
                return label
    except Exception:
        pass
    return None


# ── Main cleaner ──────────────────────────────────────────────────────────────

def load_all_raw() -> list[dict]:
    """Loads all JSON snapshot files from data/raw/"""
    files = glob.glob(os.path.join(RAW_DIR, "bhopal_listings_*.json"))
    if not files:
        raise FileNotFoundError(
            f"No raw data files found in {RAW_DIR}.\n"
            "Run `python src/scraper.py` first."
        )

    all_rows = []
    for f in sorted(files):
        with open(f, encoding="utf-8") as fh:
            rows = json.load(fh)
            all_rows.extend(rows)

    print(f"Loaded {len(all_rows)} raw records from {len(files)} file(s).")
    return all_rows


def clean(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)

    # Parse numeric fields
    df["price"]   = df["price_raw"].apply(parse_price)
    df["area_sqft"] = df["area_raw"].apply(parse_area_sqft)

    # Drop rows where we couldn't parse price (unusable for analysis)
    before = len(df)
    df = df.dropna(subset=["price"])
    print(f"Dropped {before - len(df)} rows with unparseable price. {len(df)} remain.")

    # Sanity filter — Bhopal rents realistically between ₹3,000 and ₹1,00,000/month
    df = df[(df["price"] >= 3_000) & (df["price"] <= 1_00_000)]

    # Price per sq ft
    df["price_per_sqft"] = (df["price"] / df["area_sqft"]).round(2)

    # Date features
    df["scraped_date"] = pd.to_datetime(df["scraped_date"])
    df["year"]         = df["scraped_date"].dt.year
    df["month"]        = df["scraped_date"].dt.month
    df["month_name"]   = df["scraped_date"].dt.strftime("%b")
    df["week_number"]  = df["scraped_date"].dt.isocalendar().week.astype(int)

    # Festival flag
    df["festival"]     = df["scraped_date"].dt.strftime("%Y-%m-%d").apply(get_festival_label)
    df["is_festival"]  = df["festival"].notna()

    # Deduplicate
    before = len(df)
    df = df.drop_duplicates(subset=["locality", "bhk", "price", "area_sqft", "scraped_date"])
    print(f"Removed {before - len(df)} duplicate rows. {len(df)} unique records.")

    # Sort for readability
    df = df.sort_values(["scraped_date", "locality", "bhk"]).reset_index(drop=True)

    return df


def run_cleaner():
    rows = load_all_raw()
    df   = clean(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✓ Saved clean data → {OUTPUT_CSV}")
    print(f"\nShape: {df.shape}")
    print(f"\nSample:\n{df[['scraped_date','locality','bhk','price','area_sqft','price_per_sqft','festival']].head(10)}")
    return df


if __name__ == "__main__":
    run_cleaner()
