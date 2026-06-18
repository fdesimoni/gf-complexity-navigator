"""
GF BFS - Customer Matrix Chart (Complexity & Profitability Analysis)
=====================================================================
Dedicated pipeline to create the customer_matrix.png chart.

Reads gold-layer customer data, computes profitability and complexity scores
(per spec.md), renders a 2D scatter plot with quadrant shading, and exports
the underlying data.

Spec: demos/charts/chart-customer_matrix/spec.md
Run:  python src/chart_customer_matrix.py
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Paths anchored to this script
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GOLD_DIR = os.path.join(REPO, "data", "gold")
CUST_GOLD = os.path.join(GOLD_DIR, "customer.parquet")
FACT_DENORM = os.path.join(GOLD_DIR, "fact", "fact_sales_denormalized.parquet")
OUT_DIR = os.path.join(REPO, "demos", "charts", "chart-customer_matrix")

# Ensure output directory exists
os.makedirs(OUT_DIR, exist_ok=True)

# Helbling-ish palette
BLUE = "#1f4e79"
LBLUE = "#5b9bd5"
ORANGE = "#ed7d31"
GREY = "#a6a6a6"
GREEN = "#2e7d32"
RED = "#c0392b"
LIGHT_GREEN = "#e2efda"
LIGHT_RED = "#f8dcdb"
LIGHT_YELLOW = "#fff2cc"
LIGHT_GREY = "#f2f2f2"

plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#888888"})

CUSTOMER_RENAME = {
    "customer_group": "Customer Group",
    "customer_name": "Customer Name",
    "customer_number": "Customer Number",
    "region": "Region",
    "sales_unit": "Sales Unit",
    "sub_region": "Sub-Region",
    "buying_group_l6": "Buying Group L6",
    "local_currency": "Local Currency",
    "net_sales_lc": "Net Sales LC",
    "consolidated_gross_profit_lc": "Consolidated Gross Profit LC",
    "booked_date": "Booked Date",
    "sales_order_number": "Sales Order Number",
    "month": "Month",
}


def load_customer():
    """Load customer data from denormalized fact table or fallback to customer.parquet."""
    # Try star schema denormalized fact first
    if os.path.exists(FACT_DENORM):
        df = pd.read_parquet(FACT_DENORM)
        # Filter to customer-source facts
        df = df[df.get("_source_view", "") == "customer"].copy()
        if len(df) == 0:
            raise SystemExit(f"[ERROR] denormalized fact table empty or missing _source_view='customer'")
        return df.rename(columns=CUSTOMER_RENAME)
    # Fallback to legacy customer.parquet
    elif os.path.exists(CUST_GOLD):
        return pd.read_parquet(CUST_GOLD).rename(columns=CUSTOMER_RENAME)
    else:
        raise SystemExit(
            f"[ERROR] missing gold layer: {FACT_DENORM} or {CUST_GOLD}\n"
            f"        build it first: python src/build_bronze.py && "
            f"python src/build_silver.py && python src/build_gold_star.py")


def pct_rank(s):
    """Percentile rank 0-100; NaNs ignored. Deterministic (rank method='average' for ties)."""
    return s.rank(pct=True, method="average") * 100.0


def compute_customer_matrix(c):
    """
    Compute profitability and complexity scores per Customer Group.

    PROFITABILITY (Y-axis):
      VALUE = pct_rank(gross_profit) × 0.6 + pct_rank(net_sales) × 0.4
      profitability_pct = pct_rank(VALUE_raw)  [0-100]

    COMPLEXITY (X-axis):
      proxy_1 = pct_rank(order_count)           [30% weight]
      proxy_2 = pct_rank(−avg_order_value)      [30% weight]
      proxy_3 = pct_rank(neg_line_share)        [20% weight]
      proxy_4 = pct_rank(regions + sales_units) [20% weight]
      COMPLEXITY_raw = 0.30×p1 + 0.30×p2 + 0.20×p3 + 0.20×p4
      complexity_pct = pct_rank(COMPLEXITY_raw)  [0-100]

    Quadrants (defined by 60/40 thresholds):
      - Top-left:    profitability_pct ≥ 60, complexity_pct < 40
      - Top-right:   profitability_pct ≥ 60, complexity_pct ≥ 60
      - Bottom-left: profitability_pct < 40, complexity_pct < 40
      - Bottom-right: profitability_pct < 40, complexity_pct ≥ 60
      - Center:      all other (mid-range on at least one axis)
    """
    c = c.copy()
    c["neg_line"] = (c["Consolidated Gross Profit LC"] < 0).astype(int)

    # Aggregate per Customer Group
    g = c.groupby("Customer Group")
    out = pd.DataFrame({
        # Profitability drivers
        "net_sales": g["Net Sales LC"].sum(),
        "gross_profit": g["Consolidated Gross Profit LC"].sum(),
        # Complexity drivers
        "orders": g["Sales Order Number"].nunique(),
        "lines": g.size(),
        "neg_line_share": g["neg_line"].mean(),
        "regions": g["Region"].nunique(),
        "sales_units": g["Sales Unit"].nunique(),
    }).reset_index()

    # Derived metrics
    out["avg_order_value"] = np.where(
        out["orders"] != 0,
        out["net_sales"] / out["orders"],
        0
    )
    out["gp_pct"] = np.where(
        out["net_sales"] != 0,
        out["gross_profit"] / out["net_sales"] * 100,
        0
    )
    out["fragmentation"] = out["regions"] + out["sales_units"]

    # Profitability Score (Y-axis)
    # VALUE_raw = pct_rank(gross_profit) × 0.6 + pct_rank(net_sales) × 0.4
    out["value_raw"] = (
        pct_rank(out["gross_profit"]) * 0.6
        + pct_rank(out["net_sales"]) * 0.4
    )
    out["profitability_pct"] = pct_rank(out["value_raw"])

    # Complexity Score (X-axis)
    # Four independent proxies, each percentile-ranked and weighted
    proxy_order_freq = pct_rank(out["orders"])
    proxy_small_order = pct_rank(-out["avg_order_value"])  # negative: small AOV = high complexity
    proxy_margin_leak = pct_rank(out["neg_line_share"])
    proxy_fragmentation = pct_rank(out["fragmentation"])

    out["complexity_raw"] = (
        proxy_order_freq * 0.30
        + proxy_small_order * 0.30
        + proxy_margin_leak * 0.20
        + proxy_fragmentation * 0.20
    )
    out["complexity_pct"] = pct_rank(out["complexity_raw"])

    # Quadrant classification (60/40 thresholds on percentile axes)
    def assign_quadrant(prof_pct, cplx_pct):
        if prof_pct >= 60 and cplx_pct < 40:
            return "Top-left (High Profit, Low Complexity)"
        elif prof_pct >= 60 and cplx_pct >= 60:
            return "Top-right (High Profit, High Complexity)"
        elif prof_pct < 40 and cplx_pct < 40:
            return "Bottom-left (Low Profit, Low Complexity)"
        elif prof_pct < 40 and cplx_pct >= 60:
            return "Bottom-right (Low Profit, High Complexity)"
        else:
            return "Center (Mid-range)"

    out["quadrant"] = [
        assign_quadrant(p, k)
        for p, k in zip(out["profitability_pct"], out["complexity_pct"])
    ]

    # Sort by net_sales descending (for reference)
    return out.sort_values("net_sales", ascending=False).reset_index(drop=True)


def render_customer_matrix(cm):
    """
    Render the 2D scatter plot with quadrant shading, gridlines at 40/60 percentiles,
    and labeled customer groups.
    """
    fig = plt.figure(figsize=(13.33, 7.5))
    ax = fig.add_axes([0.08, 0.12, 0.54, 0.72])

    # Quadrant background shading (per spec FR-016)
    # Four corners + center region
    Q_TL = LIGHT_GREEN      # top-left: high profit, low complexity
    Q_TR = "#e7f0f7"        # top-right: high profit, high complexity
    Q_BL = LIGHT_YELLOW     # bottom-left: low profit, low complexity
    Q_BR = LIGHT_RED        # bottom-right: low profit, high complexity

    # Shading: fill the four quadrants
    ax.axvspan(0, 40, ymin=0.6, ymax=1.0, color=Q_TL, alpha=0.8, lw=0, zorder=0)
    ax.axvspan(60, 100, ymin=0.6, ymax=1.0, color=Q_TR, alpha=0.8, lw=0, zorder=0)
    ax.axvspan(0, 40, ymin=0.0, ymax=0.4, color=Q_BL, alpha=0.8, lw=0, zorder=0)
    ax.axvspan(60, 100, ymin=0.0, ymax=0.4, color=Q_BR, alpha=0.8, lw=0, zorder=0)

    # Gridlines at 40th and 60th percentiles (per spec FR-014)
    ax.axvline(40, color="#cccccc", lw=0.8, ls="--", alpha=0.6, zorder=1)
    ax.axvline(60, color="#cccccc", lw=0.8, ls="--", alpha=0.6, zorder=1)
    ax.axhline(40, color="#cccccc", lw=0.8, ls="--", alpha=0.6, zorder=1)
    ax.axhline(60, color="#cccccc", lw=0.8, ls="--", alpha=0.6, zorder=1)

    # Color map for quadrants (for points)
    quad_colors = {
        "Top-left (High Profit, Low Complexity)": GREEN,
        "Top-right (High Profit, High Complexity)": BLUE,
        "Bottom-left (Low Profit, Low Complexity)": ORANGE,
        "Bottom-right (Low Profit, High Complexity)": RED,
        "Center (Mid-range)": GREY,
    }

    colors = cm["quadrant"].map(quad_colors)
    # Point size proportional to net_sales (per spec FR-017)
    sizes = (cm["net_sales"] / cm["net_sales"].max() * 600) + 50

    ax.scatter(cm["complexity_pct"], cm["profitability_pct"],
              s=sizes, c=colors, alpha=0.7, edgecolors="white", lw=1.2, zorder=3)

    # Labeling: top-10 by net_sales + top-3 per quadrant + statistical outliers
    # (per spec FR-018)
    labeled_idx = set()

    # Top 10 by net_sales
    top_10_idx = cm.nlargest(10, "net_sales").index
    labeled_idx.update(top_10_idx)

    # Top 3 per quadrant
    for quad in cm["quadrant"].unique():
        quad_top3 = cm[cm["quadrant"] == quad].nlargest(3, "net_sales").index
        labeled_idx.update(quad_top3)

    # Outliers: highest/lowest profitability and complexity
    labeled_idx.add(cm["profitability_pct"].idxmax())
    labeled_idx.add(cm["profitability_pct"].idxmin())
    labeled_idx.add(cm["complexity_pct"].idxmax())
    labeled_idx.add(cm["complexity_pct"].idxmin())

    # Plot labels for selected points
    for idx in labeled_idx:
        row = cm.iloc[idx]
        label = row["Customer Group"][:20]  # truncate long names
        # Offset label slightly from point
        ax.annotate(label, (row["complexity_pct"], row["profitability_pct"]),
                   xytext=(5, 5), textcoords="offset points",
                   fontsize=7, ha="left", va="bottom",
                   bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="none",
                            alpha=0.8, linewidth=0),
                   zorder=5)

    # Axes
    ax.set_xlabel("Complexity Percentile (0–100)\n→ Low Complexity | High Complexity →",
                 color=BLUE, fontweight="bold")
    ax.set_ylabel("Profitability Percentile (0–100)\n→ Low Profit | High Profit →",
                 color=BLUE, fontweight="bold")
    ax.set_xlim(-5, 105)
    ax.set_ylim(-5, 105)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_yticks([0, 20, 40, 60, 80, 100])

    # Quadrant labels in each corner
    qkw = dict(fontsize=9, fontweight="bold", color="#333333", zorder=5)
    ax.text(20, 80, "Grow\n(Valuable,\nEasy)", ha="center", va="center", **qkw)
    ax.text(80, 80, "Protect /\nServe Differently\n(Valuable,\nCostly)", ha="center", va="center", **qkw)
    ax.text(20, 20, "Simplify / Steer\n(Marginal,\nEasy)", ha="center", va="center", **qkw)
    ax.text(80, 20, "Selective\nDeprioritization\n(Marginal,\nCostly)", ha="center", va="center", **qkw)

    # Slide chrome (Helbling style)
    fig.text(0.012, 0.965, "2 Approach", fontsize=8, color="#555555")
    fig.text(0.98, 0.965, "confidential", fontsize=8, color="#555555", ha="right")
    fig.text(0.012, 0.93, "Customer Groups: Complexity & Profitability Analysis",
            fontsize=13, fontweight="bold", color=BLUE)
    fig.text(0.012, 0.895,
            "Each point = a customer group. Position indicates profitability (Y) and complexity (X).",
            fontsize=9.5, color="#333333")

    # Comment box (right side of chart)
    quad_dist = cm["quadrant"].value_counts().to_dict()
    lines = [
        f"• {len(cm)} customer groups analyzed.",
        "",
        f"• Distribution across quadrants:",
        f"  - High profit, low complexity: {quad_dist.get('Top-left (High Profit, Low Complexity)', 0)}",
        f"  - High profit, high complexity: {quad_dist.get('Top-right (High Profit, High Complexity)', 0)}",
        f"  - Low profit, low complexity: {quad_dist.get('Bottom-left (Low Profit, Low Complexity)', 0)}",
        f"  - Low profit, high complexity: {quad_dist.get('Bottom-right (Low Profit, High Complexity)', 0)}",
        f"  - Mid-range: {quad_dist.get('Center (Mid-range)', 0)}",
        "",
    ]

    # Top customer groups per quadrant (by net_sales)
    for quad in ["Top-left (High Profit, Low Complexity)",
                 "Top-right (High Profit, High Complexity)",
                 "Bottom-right (Low Profit, High Complexity)"]:
        quad_cg = cm[cm["quadrant"] == quad].nlargest(2, "net_sales")
        if not quad_cg.empty:
            short_quad = quad.split("(")[0].strip()
            lines.append(f"• {short_quad}: {quad_cg.iloc[0]['Customer Group']}")

    lines += [
        "",
        "Profitability = 60% gross profit + 40% sales volume.",
        "Complexity = order frequency (30%) + small-order",
        "burden (30%) + margin leakage (20%) +",
        "fragmentation (20%); each is percentile-ranked.",
    ]

    fig.text(0.67, 0.84, "Comments", fontsize=9.5, fontweight="bold", color=BLUE)
    fig.text(0.67, 0.82, "\n".join(lines), fontsize=7.5, color="#222222", va="top")

    # Footer
    fig.text(0.012, 0.015,
            "Source: GF BFS gold layer (customer.parquet) | "
            "Helbling proof-of-concept | numbers deterministic",
            fontsize=6.5, color="#888888")
    fig.text(0.98, 0.015, "GF_BFS_CustomerMatrix", fontsize=6.5, color="#888888", ha="right")

    # Save chart
    chart_path = os.path.join(OUT_DIR, "customer_matrix.png")
    fig.savefig(chart_path, dpi=140)
    plt.close(fig)
    print(f"  chart saved: {chart_path}")


def export_data(cm):
    """Export computed matrix data to CSV and XLSX."""
    # Columns to export (all input components + derived scores)
    export_cols = [
        "Customer Group",
        "net_sales",
        "gross_profit",
        "orders",
        "avg_order_value",
        "neg_line_share",
        "regions",
        "sales_units",
        "fragmentation",
        "gp_pct",
        "value_raw",
        "profitability_pct",
        "complexity_raw",
        "complexity_pct",
        "quadrant",
    ]
    export_data = cm[export_cols].copy()

    csv_path = os.path.join(OUT_DIR, "data.csv")
    xlsx_path = os.path.join(OUT_DIR, "data.xlsx")

    export_data.to_csv(csv_path, index=False)
    export_data.to_excel(xlsx_path, index=False, sheet_name="Customer Matrix")

    print(f"  data exported: {csv_path}")
    print(f"  data exported: {xlsx_path}")


def main():
    print("=" * 70)
    print("Customer Matrix Chart - Complexity & Profitability Analysis")
    print("=" * 70)

    print("\nStep 1: Load customer data...")
    c = load_customer()
    print(f"  loaded {len(c)} transaction rows")

    print("\nStep 2: Compute profitability & complexity scores...")
    cm = compute_customer_matrix(c)
    print(f"  computed scores for {len(cm)} customer groups")
    print(f"  quadrant distribution:")
    for quad, count in cm["quadrant"].value_counts().items():
        print(f"    - {quad}: {count}")

    print("\nStep 3: Render chart (Vega-Lite)...")
    try:
        from chart_customer_matrix_vl import render_customer_matrix_vl
        render_customer_matrix_vl(cm)
    except ImportError:
        print("  [WARNING] chart_customer_matrix_vl not found; falling back to matplotlib")
        render_customer_matrix(cm)

    print("\nStep 4: Export data...")
    export_data(cm)

    print("\n" + "=" * 70)
    print("[OK] Customer matrix chart complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
