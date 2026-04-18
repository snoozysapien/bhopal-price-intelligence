"""
analyse.py
----------
Runs all analyses and generates charts saved to outputs/.

What this finds:
  1. Median rent by locality and BHK — which areas are cheapest?
  2. Price trend over time — is Bhopal getting more expensive?
  3. Festival effect — do prices spike around Diwali / Navratri?
  4. Price per sq ft inequality — are some localities wildly overpriced per sqft?
  5. Week-of-year heatmap — when is the worst time to rent?
  6. Pareto analysis — top localities generate the most price variance

Run:
    python src/analyse.py
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import warnings
warnings.filterwarnings("ignore")

PROCESSED_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "bhopal_clean.csv")
OUT_DIR       = os.path.join(os.path.dirname(__file__), "..", "outputs")
os.makedirs(OUT_DIR, exist_ok=True)

# ── Matplotlib style ──────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.family":       "DejaVu Sans",
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "axes.labelsize":    11,
    "axes.titlesize":    13,
    "axes.titleweight":  "bold",
    "figure.dpi":        150,
    "savefig.bbox":      "tight",
    "savefig.dpi":       150,
})

PALETTE = ["#2E4057", "#048A81", "#54C6EB", "#EF798A", "#F7A072", "#8B5CF6", "#F59E0B", "#10B981"]


# ── Loader ────────────────────────────────────────────────────────────────────

def load() -> pd.DataFrame:
    if not os.path.exists(PROCESSED_CSV):
        raise FileNotFoundError(
            f"Processed CSV not found: {PROCESSED_CSV}\n"
            "Run: python src/scraper.py && python src/clean.py"
        )
    df = pd.read_csv(PROCESSED_CSV, parse_dates=["scraped_date"])
    print(f"Loaded {len(df)} records for analysis.\n")
    return df


# ── Chart 1: Median rent by locality ─────────────────────────────────────────

def chart_locality_rents(df: pd.DataFrame):
    """
    Business question: Which Bhopal localities give best value for renters?
    """
    summary = (
        df.groupby(["locality", "bhk"])["price"]
        .median()
        .unstack("bhk")
        .sort_values("2 BHK", ascending=True)
    )

    fig, ax = plt.subplots(figsize=(10, 6))
    x = np.arange(len(summary))
    width = 0.25

    for i, bhk in enumerate(["1 BHK", "2 BHK", "3 BHK"]):
        if bhk in summary.columns:
            bars = ax.barh(x + i * width, summary[bhk] / 1000, width, label=bhk, color=PALETTE[i], alpha=0.88)

    ax.set_yticks(x + width)
    ax.set_yticklabels(summary.index)
    ax.set_xlabel("Median Monthly Rent (₹ thousands)")
    ax.set_title("Median Rent by Locality & BHK — Bhopal")
    ax.legend(title="BHK", frameon=False)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"₹{v:.0f}K"))

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "01_locality_rents.png"))
    plt.close()
    print("✓ Chart 1 saved: 01_locality_rents.png")

    # Print insight
    cheapest = summary["2 BHK"].idxmin()
    priciest = summary["2 BHK"].idxmax()
    diff = summary.loc[priciest, "2 BHK"] - summary.loc[cheapest, "2 BHK"]
    print(f"  INSIGHT: For a 2 BHK, {priciest} costs ₹{diff:,.0f}/month more than {cheapest}.")


# ── Chart 2: Price trend over time ────────────────────────────────────────────

def chart_price_trend(df: pd.DataFrame):
    """
    Business question: Is Bhopal rent inflation accelerating?
    """
    monthly = (
        df.groupby(["year", "month"])["price"]
        .agg(median="median", q25=lambda x: x.quantile(0.25), q75=lambda x: x.quantile(0.75))
        .reset_index()
    )
    monthly["period"] = pd.to_datetime(monthly[["year", "month"]].assign(day=1))

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.fill_between(monthly["period"], monthly["q25"] / 1000, monthly["q75"] / 1000,
                    alpha=0.18, color=PALETTE[1], label="IQR (25th–75th percentile)")
    ax.plot(monthly["period"], monthly["median"] / 1000, color=PALETTE[0],
            linewidth=2.5, marker="o", markersize=4, label="Median rent")

    ax.set_ylabel("Monthly Rent (₹ thousands)")
    ax.set_title("Bhopal Rental Price Trend Over Time")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"₹{v:.0f}K"))
    ax.legend(frameon=False)
    ax.grid(axis="y", linestyle="--", alpha=0.4)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "02_price_trend.png"))
    plt.close()
    print("✓ Chart 2 saved: 02_price_trend.png")


# ── Chart 3: Festival price premium ──────────────────────────────────────────

def chart_festival_effect(df: pd.DataFrame):
    """
    THE KEY INSIGHT: Do rents spike before/during Diwali and Navratri?

    This chart compares median rent during festival vs non-festival weeks.
    """
    festival_median     = df[df["is_festival"]]["price"].median()
    non_festival_median = df[~df["is_festival"]]["price"].median()

    if pd.isna(festival_median) or pd.isna(non_festival_median):
        print("  [skip] Not enough festival-period data yet. Collect more weeks.")
        return

    premium_pct = ((festival_median - non_festival_median) / non_festival_median) * 100

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: Bar comparison
    ax = axes[0]
    bars = ax.bar(["Non-Festival Weeks", "Festival Weeks"],
                  [non_festival_median / 1000, festival_median / 1000],
                  color=[PALETTE[2], PALETTE[3]], alpha=0.9, width=0.5)
    ax.bar_label(bars, labels=[f"₹{non_festival_median/1000:.1f}K", f"₹{festival_median/1000:.1f}K"],
                 padding=4, fontsize=11, fontweight="bold")
    ax.set_ylabel("Median Monthly Rent (₹)")
    ax.set_title(f"Festival Price Premium: +{premium_pct:.1f}%")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"₹{v:.0f}K"))
    ax.set_ylim(0, festival_median / 1000 * 1.25)

    # Right: By festival type
    ax2 = axes[1]
    by_festival = (
        df.groupby(df["festival"].fillna("Non-Festival"))["price"]
        .median()
        .sort_values(ascending=True)
    )
    by_festival.plot(kind="barh", ax=ax2, color=PALETTE[4], alpha=0.88)
    ax2.set_xlabel("Median Rent (₹)")
    ax2.set_title("Median Rent by Festival Period")
    ax2.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"₹{v/1000:.0f}K"))

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "03_festival_effect.png"))
    plt.close()
    print(f"✓ Chart 3 saved: 03_festival_effect.png")
    print(f"  INSIGHT: Rents are {premium_pct:.1f}% higher during festival weeks.")


# ── Chart 4: Price per sq ft by locality ─────────────────────────────────────

def chart_price_per_sqft(df: pd.DataFrame):
    """
    The non-obvious insight: Which locality is expensive *per sq ft*?
    A big cheap flat and a tiny expensive flat both show up similarly
    in raw rent — price/sqft reveals the truth.
    """
    ppsf = df.dropna(subset=["price_per_sqft"])

    if ppsf.empty:
        print("  [skip] No area data available for price-per-sqft chart.")
        return

    locality_ppsf = (
        ppsf.groupby("locality")["price_per_sqft"]
        .median()
        .sort_values(ascending=False)
    )

    fig, ax = plt.subplots(figsize=(9, 6))
    colors = [PALETTE[3] if v == locality_ppsf.max() else PALETTE[1] for v in locality_ppsf]
    locality_ppsf.plot(kind="barh", ax=ax, color=colors[::-1], alpha=0.9)

    ax.set_xlabel("Median Price per Sq Ft (₹/sqft/month)")
    ax.set_title("Which Bhopal Locality Is Most Expensive per Sq Ft?")
    ax.axvline(locality_ppsf.median(), linestyle="--", color=PALETTE[0], alpha=0.6, label=f"City median: ₹{locality_ppsf.median():.0f}/sqft")
    ax.legend(frameon=False)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "04_price_per_sqft.png"))
    plt.close()
    print("✓ Chart 4 saved: 04_price_per_sqft.png")


# ── Chart 5: Weekly heatmap ───────────────────────────────────────────────────

def chart_weekly_heatmap(df: pd.DataFrame):
    """
    Heatmap of median rent by week-of-year and BHK type.
    Reveals the worst weeks to start house hunting.
    """
    pivot = (
        df.groupby(["week_number", "bhk"])["price"]
        .median()
        .unstack("bhk")
    )

    if pivot.empty:
        print("  [skip] Not enough weekly data for heatmap.")
        return

    fig, ax = plt.subplots(figsize=(14, 4))
    im = ax.imshow(pivot.T / 1000, aspect="auto", cmap="RdYlGn_r", interpolation="nearest")

    ax.set_yticks(range(len(pivot.columns)))
    ax.set_yticklabels(pivot.columns)
    ax.set_xlabel("Week of Year")
    ax.set_title("Bhopal Rent Heatmap: Which Weeks Are Most Expensive?")

    # Festival week annotations
    festival_weeks = {
        "Navratri": 41, "Diwali": 44, "Wedding\nSeason": 48,
        "Holi": 12, "Eid": 15
    }
    for label, wk in festival_weeks.items():
        if wk in pivot.index:
            idx = list(pivot.index).index(wk)
            ax.axvline(idx, color="white", linewidth=1.5, alpha=0.7)
            ax.text(idx, -0.6, label, ha="center", va="bottom", fontsize=7, color="white",
                    transform=ax.transData)

    cbar = fig.colorbar(im, ax=ax, orientation="vertical", pad=0.01)
    cbar.set_label("Median Rent (₹K)", fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "05_weekly_heatmap.png"))
    plt.close()
    print("✓ Chart 5 saved: 05_weekly_heatmap.png")


# ── Chart 6: Supply concentration ────────────────────────────────────────────

def chart_listing_concentration(df: pd.DataFrame):
    """
    How many localities dominate the Bhopal rental market?
    A Pareto-style analysis — 80/20 rule applied to listing supply.
    """
    by_loc = df.groupby("locality").size().sort_values(ascending=False)
    cumulative = (by_loc.cumsum() / by_loc.sum() * 100)

    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax2 = ax1.twinx()

    ax1.bar(by_loc.index, by_loc.values, color=PALETTE[1], alpha=0.8)
    ax2.plot(by_loc.index, cumulative.values, color=PALETTE[3], marker="o",
             markersize=5, linewidth=2, label="Cumulative %")
    ax2.axhline(80, linestyle="--", color=PALETTE[0], alpha=0.5, linewidth=1)
    ax2.text(len(by_loc) - 1, 81, "80%", color=PALETTE[0], fontsize=9)

    ax1.set_ylabel("Number of Listings")
    ax2.set_ylabel("Cumulative % of Listings")
    ax1.set_title("Rental Listing Concentration by Locality (Bhopal)")
    plt.xticks(rotation=35, ha="right")
    ax2.set_ylim(0, 110)

    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "06_listing_concentration.png"))
    plt.close()
    print("✓ Chart 6 saved: 06_listing_concentration.png")


# ── Summary stats ─────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame):
    print("\n" + "═" * 55)
    print("  BHOPAL PRICE INTELLIGENCE — KEY STATS")
    print("═" * 55)
    print(f"  Total listings analysed : {len(df):,}")
    print(f"  Date range              : {df['scraped_date'].min().date()} → {df['scraped_date'].max().date()}")
    print(f"  Localities tracked      : {df['locality'].nunique()}")
    print()
    print("  Median rents:")
    for bhk in ["1 BHK", "2 BHK", "3 BHK"]:
        subset = df[df["bhk"] == bhk]
        if not subset.empty:
            print(f"    {bhk}: ₹{subset['price'].median():,.0f}/month")
    print()

    # Festival premium
    fest_med     = df[df["is_festival"]]["price"].median()
    nonfest_med  = df[~df["is_festival"]]["price"].median()
    if not (pd.isna(fest_med) or pd.isna(nonfest_med)):
        prem = ((fest_med - nonfest_med) / nonfest_med) * 100
        print(f"  Festival price premium  : +{prem:.1f}%")

    # Cheapest/priciest locality (2 BHK)
    loc_med = df[df["bhk"] == "2 BHK"].groupby("locality")["price"].median()
    if not loc_med.empty:
        print(f"  Cheapest 2BHK locality  : {loc_med.idxmin()} (₹{loc_med.min():,.0f})")
        print(f"  Priciest 2BHK locality  : {loc_med.idxmax()} (₹{loc_med.max():,.0f})")

    print("═" * 55 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_analysis():
    df = load()
    print_summary(df)

    chart_locality_rents(df)
    chart_price_trend(df)
    chart_festival_effect(df)
    chart_price_per_sqft(df)
    chart_weekly_heatmap(df)
    chart_listing_concentration(df)

    print(f"\n✓ All charts saved to: {OUT_DIR}/")


if __name__ == "__main__":
    run_analysis()
