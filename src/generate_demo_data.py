"""
generate_demo_data.py
---------------------
Generates realistic synthetic Bhopal rental data for demonstration.
Use this if you haven't run the live scraper yet — it produces a CSV
that the analysis scripts can consume directly.

Run:
    python src/generate_demo_data.py
"""

import os
import json
import random
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

PROCESSED_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
RAW_DIR       = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
os.makedirs(PROCESSED_DIR, exist_ok=True)
os.makedirs(RAW_DIR, exist_ok=True)

random.seed(42)
np.random.seed(42)

# ── Ground-truth price ranges for Bhopal (based on 2024 market research) ──────
# Source: MagicBricks / 99acres public data, Jan–Dec 2024
# Format: locality → {bhk → (median_rent, std_dev)}

BHOPAL_MARKET = {
    "Arera Colony":       {"1 BHK": (9500, 1200),  "2 BHK": (16000, 2200), "3 BHK": (24000, 3500)},
    "MP Nagar":           {"1 BHK": (11000, 1500), "2 BHK": (19500, 2800), "3 BHK": (30000, 4000)},
    "Shivaji Nagar":      {"1 BHK": (7500, 900),   "2 BHK": (12500, 1800), "3 BHK": (18000, 2500)},
    "Kolar Road":         {"1 BHK": (6500, 800),   "2 BHK": (10500, 1400), "3 BHK": (16000, 2200)},
    "Ayodhya Nagar":      {"1 BHK": (7000, 850),   "2 BHK": (11500, 1600), "3 BHK": (17500, 2400)},
    "Hoshangabad Road":   {"1 BHK": (8000, 1000),  "2 BHK": (14000, 2000), "3 BHK": (21000, 3000)},
    "Bairagarh":          {"1 BHK": (5500, 700),   "2 BHK": (9000, 1200),  "3 BHK": (14000, 2000)},
    "Misrod":             {"1 BHK": (5000, 600),   "2 BHK": (8500, 1100),  "3 BHK": (13000, 1800)},
}

# Typical sq ft ranges per BHK in Bhopal
AREA_RANGES = {
    "1 BHK": (400, 650),
    "2 BHK": (700, 1050),
    "3 BHK": (1100, 1500),
}

# Festival calendar 2024-2025 (approx)
FESTIVAL_PERIODS = [
    ("Navratri",        "2024-10-03", "2024-10-12"),
    ("Dussehra",        "2024-10-12", "2024-10-14"),
    ("Diwali",          "2024-10-28", "2024-11-05"),
    ("Wedding Season",  "2024-11-15", "2024-12-31"),
    ("Wedding Season",  "2025-01-01", "2025-02-15"),
    ("Holi",            "2025-03-14", "2025-03-16"),
]

def festival_multiplier(date: pd.Timestamp) -> float:
    """Returns a price multiplier for festival periods."""
    for _, start, end in FESTIVAL_PERIODS:
        if pd.Timestamp(start) <= date <= pd.Timestamp(end):
            return random.uniform(1.07, 1.15)  # 7–15% premium
    # General seasonal effects
    month = date.month
    if month in [6, 7, 8]:   # Monsoon — mild dip
        return random.uniform(0.96, 1.00)
    if month in [4, 5]:       # Summer heat — slight dip
        return random.uniform(0.97, 1.02)
    return random.uniform(0.99, 1.03)  # baseline noise


def generate_demo_csv():
    rows = []
    start_date = pd.Timestamp("2024-01-15")
    end_date   = pd.Timestamp("2025-03-31")
    sources    = ["99acres", "magicbricks"]

    date_range = pd.date_range(start=start_date, end=end_date, freq="7D")  # weekly snapshots

    for snap_date in date_range:
        mult = festival_multiplier(snap_date)

        for locality, bhk_data in BHOPAL_MARKET.items():
            n_listings = random.randint(3, 12)  # variable supply
            for bhk, (median, std) in bhk_data.items():
                for _ in range(n_listings):
                    base_price = max(3000, int(np.random.normal(median, std) * mult))
                    # Round to nearest 500 (like real listings)
                    price = int(round(base_price / 500) * 500)

                    area_min, area_max = AREA_RANGES[bhk]
                    area = round(random.uniform(area_min, area_max), 0)

                    # Determine festival label
                    festival_label = None
                    for label, start, end in FESTIVAL_PERIODS:
                        if pd.Timestamp(start) <= snap_date <= pd.Timestamp(end):
                            festival_label = label
                            break

                    rows.append({
                        "source":          random.choice(sources),
                        "locality":        locality,
                        "bhk":             bhk,
                        "price_raw":       f"₹ {price:,}/month",
                        "area_raw":        f"{int(area)} sq.ft",
                        "title":           f"{bhk} Flat in {locality}",
                        "url":             f"https://example.com/{locality.lower().replace(' ', '-')}/{bhk.lower().replace(' ', '-')}",
                        "scraped_date":    snap_date.strftime("%Y-%m-%d"),
                        "price":           price,
                        "area_sqft":       area,
                        "price_per_sqft":  round(price / area, 2),
                        "year":            snap_date.year,
                        "month":           snap_date.month,
                        "month_name":      snap_date.strftime("%b"),
                        "week_number":     snap_date.isocalendar()[1],
                        "festival":        festival_label,
                        "is_festival":     festival_label is not None,
                    })

    df = pd.DataFrame(rows)
    out = os.path.join(PROCESSED_DIR, "bhopal_clean.csv")
    df.to_csv(out, index=False)
    print(f"✓ Generated {len(df):,} demo records → {out}")
    print(f"  Date range: {df['scraped_date'].min()} to {df['scraped_date'].max()}")
    print(f"  Localities: {df['locality'].nunique()}")
    print(f"\n  Sample:\n{df[['scraped_date','locality','bhk','price','area_sqft','festival']].head(8).to_string(index=False)}")
    return df


if __name__ == "__main__":
    generate_demo_csv()
