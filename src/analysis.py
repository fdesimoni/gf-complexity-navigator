"""
GF BFS - "Auswertung" charts, driven by each chart's spec.md
============================================================

SPEC-DRIVEN RENDERING 
  Every chart reads its own spec.md and asks the Helbling LLM router to turn
  that prose specification into a small, *structured* render plan (chart kind,
  fields, sort order, year, encodings, labels). The plan is then executed
  deterministically in pandas/matplotlib.

  Governance (honesty, see every spec's FR "no language model may produce any
  number"): the LLM decides only the chart *structure* - it never computes or
  emits a single figure. All numbers are produced by pandas from the source
  Excel files. If the router is unreachable, each chart falls back to a built-in
  default plan, so the pipeline stays runnable offline.

Scope:
  A) Sales x margin per product group           (chart-product_group_sales_margin)
  B) Product growth (CAGR) x margin             (chart-product_cagr_margin)
  C) Customer ABC / Pareto                      (chart-customer_abc)
  D) Product split by buying group (Marimekko)  (chart-product_split_segment)

Run:  python analysis.py   ->  outputs in output/charts/chart-<name>/
"""
import os
import re
import json
import urllib.request
import urllib.error

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------------
# Paths are anchored to this script's location so the analysis runs from any
# working directory. Repo layout:
#   <repo>/data/gold/                      - analysis-ready Parquet (medallion)
#   <repo>/src/analysis.py                 - this script
#   <repo>/demos/charts/                   - one chart-<name>/ folder per chart
#
# This script reads the GOLD layer (data/gold/*.parquet), produced by
# build_gold.py from silver. Build the chain first if gold is missing:
#   python src/build_bronze.py && python src/build_silver.py
#   && python src/build_gold.py
# ----------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GOLD_DIR = os.path.join(REPO, "data", "gold")

# Star schema paths (Phase 1: denormalized compatibility layer)
FACT_DENORM_CUST = os.path.join(GOLD_DIR, "fact", "fact_sales_denormalized.parquet")
FACT_DENORM_PROD = os.path.join(GOLD_DIR, "fact", "fact_sales_denormalized.parquet")

# Legacy flat gold tables (fallback for backward compatibility)
CUST_GOLD = os.path.join(GOLD_DIR, "customer.parquet")
PROD_GOLD = os.path.join(GOLD_DIR, "product.parquet")
OUT = os.path.join(REPO, "demos", "charts")

# Helbling LLM router (Anthropic-compatible Messages API). Overridable via env.
LLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api-chat.helbling.ch/llm").rstrip("/")
LLM_API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY") \
    or "not-used-but-required"
LLM_MODEL = os.environ.get("ANALYSIS_LLM_MODEL", "claude-sonnet-4-6")

# Helbling-ish palette
BLUE = "#1f4e79"
LBLUE = "#5b9bd5"
ORANGE = "#ed7d31"
GREY = "#a6a6a6"
GREEN = "#2e7d32"
RED = "#c0392b"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": "#888888"})


# Gold is stored in snake_case (medallion convention). The chart functions and
# the spec-driven plan defaults (group_field, value_field, ...) were written
# against the original Excel display names, so on load we rename gold's columns
# back to those display names. Types are already enforced and 'year' is already
# materialized in gold -- no coercion or Year-derivation needed here.
PRODUCT_RENAME = {
    "rep_product_line": "Rep. Product Line",
    "category_description": "2 - Category Description",
    "sub_region": "Sub-Region",
    "region": "Region",
    "business_unit": "Business Unit",
    "buying_group_l6": "Buying Group L6",
    "net_sales_chf": "Net Sales (CHF)",
    "gross_profit_chf": "Consolidated Gross Profit (CHF)",
    "quarter": "Quarter",
    "year": "Year",
    # Star schema compatibility (denormalized fact table)
    "product_portfolio": "Product Portfolio",
    "legacy_data": "Legacy Data",
}
CUSTOMER_RENAME = {
    "customer_group": "Customer Group",
    "customer_name": "Customer Name",
    "region": "Region",
    "sub_region": "Sub-Region",
    "buying_group_l6": "Buying Group L6",
    "local_currency": "Local Currency",
    "net_sales_lc": "Net Sales LC",
    "consolidated_gross_profit_lc": "Consolidated Gross Profit LC",
    "net_sales_chf": "Net Sales CHF",
    "gross_profit_chf": "Consolidated Gross Profit CHF",
    "eur_chf_rate": "EUR/CHF Rate",
    "year": "Year",
    # Star schema compatibility (denormalized fact table)
    "customer_number": "Customer Number",
    "booked_date": "Booked Date",
    "sales_order_number": "Sales Order Number",
}


def _load_gold(path, rename, label):
    if not os.path.exists(path):
        raise SystemExit(
            f"[ERROR] missing gold layer: {path}\n"
            f"        build it first: python src/build_bronze.py && "
            f"python src/build_silver.py && python src/build_gold_star.py")
    df = pd.read_parquet(path).rename(columns=rename)
    return df


def load_product():
    # Try star schema denormalized fact first; fall back to legacy gold
    if os.path.exists(FACT_DENORM_PROD):
        df = pd.read_parquet(FACT_DENORM_PROD)
        # Filter to product-source facts and project needed columns
        df = df[df["_source_view"] == "product"].copy()
        return df.rename(columns=PRODUCT_RENAME)
    else:
        return _load_gold(PROD_GOLD, PRODUCT_RENAME, "product")


def load_customer():
    # Try star schema denormalized fact first; fall back to legacy gold
    if os.path.exists(FACT_DENORM_CUST):
        df = pd.read_parquet(FACT_DENORM_CUST)
        # Filter to customer-source facts and project needed columns
        df = df[df["_source_view"] == "customer"].copy()
        return df.rename(columns=CUSTOMER_RENAME)
    else:
        return _load_gold(CUST_GOLD, CUSTOMER_RENAME, "customer")


# ============================================================================
# SPEC -> PLAN (the only place the LLM is involved; it never emits a number)
# ============================================================================
# Each chart kind has a small, fixed set of plan parameters. We hand the LLM the
# full spec.md plus the menu of allowed kinds/params and ask it to fill in the
# plan as JSON. We then validate every field against a built-in default; any
# missing/invalid field silently falls back to the default value, so a vague or
# malformed answer can never break rendering and can never inject a number.

PLAN_SCHEMA_DOC = """
You convert a chart SPECIFICATION (markdown) into a STRUCTURED RENDER PLAN as
strict JSON. You choose ONLY the chart's structure (kind, fields, sort, year,
labels). You MUST NOT compute, invent, or output any data value / statistic -
all numbers are computed separately from the source data. Output JSON only.

Allowed "kind" values and their parameters:

1) "bar_margin_with_boxes"  (sales & margin per product group)
   { "kind": "bar_margin_with_boxes",
     "group_field": <column name, e.g. "2 - Category Description">,
     "year": <int, e.g. 2025>,
     "sort_by": "gross_profit" | "net_sales",   // descending
     "bar_height": "margin" | "net_sales",
     "value_boxes": ["net_sales", "gross_profit"],  // any subset, in order
     "avg_line": "weighted_margin" | "mean_margin" | "none",
     "title": <str>, "subtitle": <str> }

2) "bubble_quadrant"  (CAGR x margin)
   { "kind": "bubble_quadrant",
     "group_field": <column, e.g. "Rep. Product Line">,
     "year_start": <int>, "year_end": <int>,
     "x": "margin" | "margin_delta",   // absolute avg margin %, or change in
                                       // margin (margin[y1]-margin[y0], pp)
     "y": "cagr", "bubble": "net_sales",
     "vline": "median_margin" | "mean_margin" | "zero_delta" | "none",
     "hline": "zero_growth" | "none",
     "title": <str>, "subtitle": <str> }

3) "pareto_abc"  (customer ABC)
   { "kind": "pareto_abc",
     "group_field": <column, e.g. "Customer Group">,
     "value_field": <column, e.g. "Consolidated Gross Profit LC" for margin,
                      or "Net Sales LC" for sales>,
     "value_label": <short noun for the axis/comments, e.g. "margin" | "sales">,
     "a_cut": <float, cumulative %, e.g. 80>,
     "b_cut": <float, cumulative %, e.g. 95>,
     "top_n_listed": <int>,
     "title": <str>, "subtitle": <str> }

4) "stacked_segment"  (product split by segment)
   { "kind": "stacked_segment",
     "segment_field": <column, e.g. "Sub-Region">,
     "stack_field": <column, e.g. "2 - Category Description">,
     "year": <int>,
     "label_threshold_pct": <float, e.g. 6>,
     "title": <str>, "subtitle": <str> }

5) "profit_margin_dual"  (consolidated profit & margin per customer)
   { "kind": "profit_margin_dual",
     "group_field": <column, e.g. "Customer Number" | "Customer Group">,
     "year": <int, e.g. 2024>,
     "margin_cutoff_pct": <float, e.g. 30>,  // low-margin highlight threshold
     "title": <str>, "subtitle": <str> }

Rules:
- Pick the kind that matches the spec's "Input" line / acceptance scenarios.
- Honour explicit instructions in the spec (e.g. "sorted by Gross Profit
  descending", "bar height = margin %", default year, A/B cut-offs).
- title/subtitle: short business-readable strings; you MAY use the literal
  token {year} / {y0} / {y1} and they will be filled with the real years.
- Return ONLY the JSON object, no prose, no code fences.
"""


def _llm_messages(prompt, max_tokens=900, timeout=60):
    """POST a single user message to the Anthropic-compatible router and return
    the concatenated text. Raises on any transport/HTTP error so the caller can
    fall back to the built-in default plan."""
    body = json.dumps({
        "model": LLM_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        LLM_BASE_URL + "/v1/messages", data=body, method="POST",
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": LLM_API_KEY,
        })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    parts = payload.get("content", [])
    return "".join(b.get("text", "") for b in parts if b.get("type") == "text")


def _extract_json(text):
    """Pull the first {...} JSON object out of an LLM reply (tolerates stray
    prose or ```json fences)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in LLM reply")
    return json.loads(text[start:end + 1])


def plan_chart_from_spec(spec_path, default_plan):
    """Read the chart's spec.md, ask the router to turn it into a render plan,
    and return a plan dict. Every field is validated against `default_plan`;
    unknown 'kind' or transport failure -> the default plan is returned intact.
    This is the ONLY model call, and it can only influence structure, never a
    number."""
    name = os.path.basename(os.path.dirname(spec_path))
    try:
        with open(spec_path, "r", encoding="utf-8") as f:
            spec_text = f.read()
    except OSError as e:
        print(f"  [{name}] spec.md unreadable ({e}); using built-in default plan")
        return dict(default_plan)

    prompt = (PLAN_SCHEMA_DOC + "\n\n=== SPECIFICATION (spec.md) ===\n" + spec_text
              + "\n\n=== END SPECIFICATION ===\nReturn the JSON render plan now.")
    try:
        raw = _llm_messages(prompt)
        plan = _extract_json(raw)
    except (urllib.error.URLError, ValueError, json.JSONDecodeError, TimeoutError,
            OSError) as e:
        print(f"  [{name}] router/plan unavailable ({e}); using built-in default plan")
        return dict(default_plan)

    if plan.get("kind") != default_plan["kind"]:
        print(f"  [{name}] LLM returned kind={plan.get('kind')!r} != "
              f"{default_plan['kind']!r}; using built-in default plan")
        return dict(default_plan)

    merged = _merge_plan(default_plan, plan)
    print(f"  [{name}] plan from spec.md -> {merged['kind']}")
    return merged


def _merge_plan(default_plan, plan):
    """Keep only keys present in the default plan; type-check each against the
    default's type. Anything missing/mismatched falls back to the default."""
    out = dict(default_plan)
    for key, dval in default_plan.items():
        if key not in plan:
            continue
        val = plan[key]
        if isinstance(dval, bool):
            if isinstance(val, bool):
                out[key] = val
        elif isinstance(dval, int) and not isinstance(dval, bool):
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[key] = int(val)
        elif isinstance(dval, float):
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[key] = float(val)
        elif isinstance(dval, list):
            if isinstance(val, list):
                out[key] = val
        elif isinstance(dval, str):
            if isinstance(val, str) and val.strip():
                out[key] = val
    return out


def _fmt(s, **kw):
    """Fill {year}/{y0}/{y1} tokens in LLM-provided titles. Tokens the model
    emitted that we don't supply (e.g. {year} on the year-less ABC chart) are
    stripped rather than left as literal braces."""
    for key, val in kw.items():
        s = s.replace("{" + key + "}", str(val))
    # drop any remaining "{token}" the model invented and tidy stray separators
    s = re.sub(r"\s*\(\{[^}]*\}\)", "", s)   # " ({year})" -> ""
    s = re.sub(r"\{[^}]*\}", "", s)          # bare "{token}" -> ""
    s = re.sub(r"\s{2,}", " ", s).strip()
    return re.sub(r"[\s,;:–-]+$", "", s)     # drop a separator left dangling by a stripped token


# ----------------------------------------------------------------------------
# Slide chrome (Helbling pitch style: header band + comment box + footer)
# ----------------------------------------------------------------------------
def _slide(fig, title, subtitle):
    fig.text(0.012, 0.965, "2 Approach", fontsize=8, color="#555555")
    fig.text(0.98, 0.965, "confidential", fontsize=8, color="#555555", ha="right")
    fig.text(0.012, 0.93, title, fontsize=13, fontweight="bold", color=BLUE)
    fig.text(0.012, 0.895, subtitle, fontsize=9.5, color="#333333")
    fig.text(0.012, 0.015, "Source: GF BFS sample data (Customer View / Product View) | "
             "Helbling proof-of-concept | numbers deterministic",
             fontsize=6.5, color="#888888")
    fig.text(0.98, 0.015, "GF_BFS_Demo", fontsize=6.5, color="#888888", ha="right")


def _comment_box(fig, lines, x=0.70, y0=0.84):
    fig.text(x, y0 + 0.02, "Comments", fontsize=9.5, fontweight="bold", color=BLUE)
    fig.text(x, y0 - 0.02, "\n".join(lines), fontsize=8, color="#222222",
             va="top", wrap=True)


# ============================================================================
# A) Sales & margin per rep. product line  ->  kind "bar_margin_with_boxes"
# ============================================================================
PLAN_A = {
    "kind": "bar_margin_with_boxes",
    "group_field": "Rep. Product Line",
    "group_label": "rep. product lines",
    "year": 2025,
    "sort_by": "gross_profit",
    "bar_height": "margin",
    "value_boxes": ["net_sales", "gross_profit"],
    "avg_line": "weighted_margin",
    "others_max_share": 0.015,
    "title": "Products: Sales x Margin {year}",
    "subtitle": "Mekko: bar width = sales (CHF m), height = margin %, area ≈ gross profit",
}


def chart_A(p, plan):
    year = int(plan["year"])
    gfield = plan["group_field"]
    d = p[p["Year"] == year]
    g = d.groupby(gfield).agg(
        ns=("Net Sales (CHF)", "sum"),
        gp=("Consolidated Gross Profit (CHF)", "sum")).reset_index()
    sort_col = "gp" if plan["sort_by"] == "gross_profit" else "ns"
    g = g.sort_values(sort_col, ascending=False).reset_index(drop=True)
    total_ns = g.ns.sum()

    # Roll up small lines (sales share < others_max_share of total) into a single
    # "Others" column, mirroring the GF PDF. Done on raw CHF so totals reconcile;
    # margin is recomputed from the pooled sales/profit. See spec.md FR-001.
    others_share = float(plan.get("others_max_share", 0.0) or 0.0)
    if others_share > 0 and total_ns > 0:
        small = g.ns / total_ns < others_share
        if small.sum() > 1:
            keep = g[~small].copy()
            pooled = g[small]
            others = pd.DataFrame([{
                gfield: "Others",
                "ns": pooled.ns.sum(),
                "gp": pooled.gp.sum(),
            }])
            g = pd.concat([keep, others], ignore_index=True)

    g["margin"] = np.where(g.ns != 0, g.gp / g.ns * 100, 0)
    g["ns_m"] = g.ns / 1e6
    g["gp_m"] = g.gp / 1e6
    total_ns = g.ns.sum()

    fig = plt.figure(figsize=(13.33, 7.5))
    ax = fig.add_axes([0.06, 0.12, 0.58, 0.70])

    # --- Mekko (Marimekko) geometry -------------------------------------------
    # Column HEIGHT = margin %; column WIDTH ∝ Net Sales; columns are drawn
    # edge-to-edge so total width = total sales and each column's AREA ≈ gross
    # profit (sales × margin). See spec.md FR-003..FR-005.
    if plan["bar_height"] == "net_sales":
        heights = g["ns_m"].values
        ax.set_ylabel("Total Sales %d [CHF m]" % year, color=BLUE)
    else:
        heights = g["margin"].values
        ax.set_ylabel("Margin %d [in %%]" % year, color=BLUE)

    widths = g["ns_m"].values.astype(float)            # column width ∝ sales (CHF m)
    edges = np.concatenate([[0.0], np.cumsum(widths)])  # left edge of each column
    centers = edges[:-1] + widths / 2.0                 # column centre (for labels/boxes)
    gap = max(widths.sum() * 0.004, 0.02)               # thin separator between columns

    bars = ax.bar(centers, heights, width=np.maximum(widths - gap, 0.0),
                  color=LBLUE, align="center")

    # embedded value boxes inside each column (sales, gross profit), per the spec
    box_styles = {
        "net_sales": (g["ns_m"], "Sales [CHF m]", BLUE),
        "gross_profit": (g["gp_m"], "Gross profit [CHF m]", GREY),
    }
    boxes = [b for b in plan["value_boxes"] if b in box_styles]
    handles = []
    # only label columns wide enough to hold a box without overlap
    min_w = widths.sum() * 0.020
    for slot, key in enumerate(boxes):
        series, label, color = box_styles[key]
        for xi, w, h, v in zip(centers, widths, heights, series):
            if w < min_w:
                continue
            yb = h * (0.62 - 0.30 * slot) if h > 0 else h * (0.30 + 0.30 * slot)
            ax.text(xi, yb, f"{v:.0f}", ha="center", va="center", fontsize=8,
                    color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.18", fc=color, ec="none", alpha=0.92))
        handles.append(plt.Line2D([0], [0], marker="s", color="none",
                                  markerfacecolor=color, markersize=8, label=label))

    if plan["avg_line"] != "none" and plan["bar_height"] == "margin":
        if plan["avg_line"] == "mean_margin":
            avg = g["margin"].mean()
            avg_lbl = "mean"
        else:
            avg = g.gp.sum() / total_ns * 100 if total_ns else 0.0
            avg_lbl = "sales-weighted"
        ax.axhline(avg, color=ORANGE, lw=1.8, ls="--")
        ax.text(edges[-1], avg + 1.2, f"Ø margin {avg:.0f}% ({avg_lbl})",
                ha="right", color=ORANGE, fontsize=8, fontweight="bold")
    ax.set_xlim(0, edges[-1])
    # x ticks at column centres; suppress labels for columns too narrow to read
    ax.set_xticks(centers)
    ax.set_xticklabels([n if w >= min_w else "" for n, w in zip(g[gfield], widths)],
                       rotation=30, ha="right", fontsize=8.5)
    ax.set_xlabel("Net Sales %d [CHF m] — column width ∝ sales" % year, color=BLUE)
    ax.set_ylim(min(0, float(np.min(heights)) * 1.15), float(np.max(heights)) * 1.2)
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8)

    best = g.loc[g.margin.idxmax()]
    worst = g.loc[g.margin.idxmin()]
    avg_margin = g.gp.sum() / total_ns * 100 if total_ns else 0.0
    _slide(fig, _fmt(plan["title"], year=year), _fmt(plan["subtitle"], year=year))
    glabel = plan.get("group_label", "groups")
    gsing = glabel.rstrip("s")
    _comment_box(fig, [
        f"• GF BFS sells across {len(g)} {glabel} in {year}.",
        f"• Largest gross-profit {gsing}: '{g.iloc[0][gfield]}'",
        f"  (CHF {g.iloc[0]['gp_m']:.0f} m profit, {g.iloc[0]['margin']:.0f}% margin).",
        f"• Highest margin: '{best[gfield]}' ({best['margin']:.0f}%);",
        f"  lowest: '{worst[gfield]}' ({worst['margin']:.0f}%).",
        f"• Average margin (sales-weighted): {avg_margin:.0f}%.",
        "",
        "Proxy note: margin = consolidated gross profit / net",
        "sales; true cost-to-serve not yet included.",
    ])
    fig.savefig(os.path.join(OUT, "A_product_group_sales_margin.png"), dpi=140)
    plt.close(fig)
    return g.rename(columns={"ns": "net_sales", "gp": "gross_profit"})


# ============================================================================
# B) Product growth (CAGR) x margin  ->  kind "bubble_quadrant"
# ============================================================================
PLAN_B = {
    "kind": "bubble_quadrant",
    "group_field": "Rep. Product Line",
    "year_start": 2021,
    "year_end": 2025,
    "x": "margin_delta",
    "y": "cagr",
    "bubble": "net_sales",
    "vline": "zero_delta",
    "hline": "zero_growth",
    "y_clip_pct": 20.0,   # cap the symmetric CAGR axis at ±20% (tighten the
                          # mostly-empty span); outliers clamp to the edge
    "x_clip_pp": 20.0,    # cap the symmetric Δ-margin axis at ±20 pp likewise
    "title": "Product-line growth vs. margin change, {y0}-{y1}",
    "subtitle": "Products: Sales growth '{y0}-'{y1} x Δ Margin '{y0}-'{y1}",
}


def chart_B(p, plan):
    y0, y1 = int(plan["year_start"]), int(plan["year_end"])
    gfield = plan["group_field"]
    d = p[p["Year"].between(y0, y1)]
    piv = d.pivot_table(index=gfield, columns="Year",
                        values="Net Sales (CHF)", aggfunc="sum")
    gp = d.groupby(gfield).agg(
        ns=("Net Sales (CHF)", "sum"),
        gp=("Consolidated Gross Profit (CHF)", "sum"))
    df = piv.join(gp)
    df = df[(df.get(y0, 0) > 0) & (df.get(y1, 0) > 0)].copy()
    n = y1 - y0
    df["cagr"] = (df[y1] / df[y0]) ** (1 / n) - 1
    df["margin"] = df.gp / df.ns * 100
    df["sales_m"] = df.ns / 1e6

    # Per-year margins for the start/end of the window, so we can encode the
    # CHANGE in margin (Δ margin, in percentage points) on the X axis — mirrors
    # the GF PDF's "Δ Margin" bubble chart. gp_y/ns_y by line × year.
    gpy = d.pivot_table(index=gfield, columns="Year",
                        values="Consolidated Gross Profit (CHF)", aggfunc="sum")
    df["margin_y0"] = gpy.get(y0) / df[y0] * 100
    df["margin_y1"] = gpy.get(y1) / df[y1] * 100
    df["margin_delta"] = df["margin_y1"] - df["margin_y0"]

    xfield = "margin_delta" if plan["x"] == "margin_delta" else "margin"
    xvals = df[xfield]

    fig = plt.figure(figsize=(13.33, 7.5))
    ax = fig.add_axes([0.06, 0.12, 0.58, 0.70])
    if plan["vline"] == "zero_delta":
        vx = 0.0
    elif plan["vline"] == "mean_margin":
        vx = df["margin"].mean()
    else:
        vx = df["margin"].median()

    # Four-quadrant background shading (top band lighter, right band darker —
    # as in the GF PDF), formed by the 0%-growth line and the vertical ref line.
    xlo, xhi = float(xvals.min()), float(xvals.max())
    xpad = (xhi - xlo) * 0.12 or 1.0
    # Keep the symmetric CAGR axis as short as possible: hard-cap it at the
    # configured ±y_clip_pct (default ±20%) so a single far outlier (e.g. a tiny
    # line at −36% CAGR) can't stretch the axis and leave the plot mostly empty.
    # Bubbles beyond the cap are clamped to the boundary (see below) so none are
    # hidden — their true CAGR is shown in the label.
    data_ymax = max(abs(df["cagr"].min()), abs(df["cagr"].max())) * 100
    y_clip = float(plan.get("y_clip_pct", 0) or 0)
    ymax = y_clip if y_clip else (data_ymax * 1.18 or 10)
    df["cagr_plot"] = (df["cagr"] * 100).clip(-ymax * 0.97, ymax * 0.97)
    df["y_clipped"] = (df["cagr"] * 100).abs() > ymax

    # Same treatment for the Δ-margin X axis: hard-cap at the configured ±x_clip_pp
    # (default ±20 pp) and clamp far outliers (e.g. Silenta at +42 pp) to the edge
    # so the bulk of the lines aren't squeezed into a narrow central column.
    x_clip = float(plan.get("x_clip_pp", 0) or 0)
    if x_clip:
        xmax = x_clip
        df["x_plot"] = xvals.clip(-xmax * 0.97, xmax * 0.97)
        df["x_clipped"] = xvals.abs() > xmax
        ax.set_xlim(-xmax, xmax)
    else:
        df["x_plot"] = xvals
        df["x_clipped"] = False
        ax.set_xlim(xlo - xpad, xhi + xpad)
    ax.set_ylim(-ymax, ymax)
    Q_TL, Q_TR = "#bcd6ef", "#7fb3e0"   # top-left / top-right
    Q_BL, Q_BR = "#dce9f6", "#9cc4e6"   # bottom-left / bottom-right
    x_lim = ax.get_xlim()
    ax.axvspan(x_lim[0], vx, ymin=0.5, ymax=1.0, color=Q_TL, lw=0, zorder=0)
    ax.axvspan(vx, x_lim[1], ymin=0.5, ymax=1.0, color=Q_TR, lw=0, zorder=0)
    ax.axvspan(x_lim[0], vx, ymin=0.0, ymax=0.5, color=Q_BL, lw=0, zorder=0)
    ax.axvspan(vx, x_lim[1], ymin=0.0, ymax=0.5, color=Q_BR, lw=0, zorder=0)

    sizes = (df["sales_m"].clip(lower=0) / df["sales_m"].max() * 1800) + 40
    ax.scatter(df["x_plot"], df["cagr_plot"], s=sizes, c=BLUE, alpha=0.85,
               edgecolors="white", zorder=3)
    # Label every bubble. Large bubbles get a white label centred inside; small
    # bubbles can't hold readable text, so their label is offset just outside in
    # dark ink so no line goes unnamed. A bubble clamped to an axis edge gets its
    # true (off-axis) value appended so the cap never hides a real number.
    big = df["sales_m"].quantile(0.5)
    for name, r in df.iterrows():
        label = str(name)[:18]
        if r["y_clipped"]:
            label += " (%+.0f%%)" % (r["cagr"] * 100)
        if r["x_clipped"]:
            label += " (%+.0f pp)" % r[xfield]
        clipped = r["y_clipped"] or r["x_clipped"]
        x, y = r["x_plot"], r["cagr_plot"]
        if r["sales_m"] > big and not clipped:
            ax.annotate(label, (x, y), fontsize=8.5, ha="center", va="center",
                        color="white", fontweight="bold", zorder=4)
        else:
            ax.annotate(label, (x, y), xytext=(4, 4),
                        textcoords="offset points", fontsize=7.5,
                        ha="left", va="bottom", color="#1f2d3d", zorder=4)
    if plan["hline"] != "none":
        ax.axhline(0, color="#9aa7b4", lw=1, zorder=2)
    if plan["vline"] != "none":
        ax.axvline(vx, color="#9aa7b4", lw=1, ls="--", zorder=2)

    if xfield == "margin_delta":
        ax.set_xlabel("Δ Margin %d-%d [in pp]" % (y0, y1))
    else:
        ax.set_xlabel("Margin (avg %d-%d) [in %%]" % (y0, y1))
    ax.set_ylabel("Sales CAGR %d-%d [in %%]" % (y0, y1), color=BLUE)

    # Four named quadrants (as in the GF PDF): the action label for each corner.
    qkw = dict(fontsize=8, fontweight="bold", color=BLUE, zorder=5)
    ax.text(0.03, 0.95, "Review cost structure", transform=ax.transAxes,
            va="top", ha="left", **qkw)
    ax.text(0.97, 0.95, "Assess potential", transform=ax.transAxes,
            va="top", ha="right", **qkw)
    ax.text(0.03, 0.05, "Warning sign –\nneed for innovation", transform=ax.transAxes,
            va="bottom", ha="left", **qkw)
    ax.text(0.97, 0.05, "Review pricing", transform=ax.transAxes,
            va="bottom", ha="right", **qkw)
    ax.text(0.98, 0.86, "Bubble = sales %d-%d" % (y0, y1), transform=ax.transAxes,
            fontsize=6.5, ha="right", color="#666666", zorder=5)

    growers = df[df.cagr > 0.10].sort_values("cagr", ascending=False)
    sales_decliners = df[df.cagr < 0]   # CAGR<0 == net-sales decline over window
    margin_down = df[df["margin_delta"] < 0]
    margin_up = df[df["margin_delta"] > 0]
    best_m = df["margin_delta"].idxmax()
    lines = [
        f"• {len(margin_up)} of {len(df)} product lines improved their",
        f"  margin over {y0}-{y1}; best: '{best_m}'",
        f"  ({df.loc[best_m, 'margin_delta']:+.0f} pp).",
        f"• Sales declined in {len(sales_decliners)} of {len(df)} lines",
        f"  (CAGR < 0); margins fell in {len(margin_down)} of {len(df)}.",
    ]
    if len(growers):
        lines += [f"• {len(growers)} lines still grew > 10% CAGR; fastest:",
                  f"  '{growers.index[0]}' ({growers['cagr'].iloc[0]*100:+.0f}%)."]
    else:
        lines += ["• No line grew > 10% CAGR — a worrying,",
                  "  broad-based decline signal."]
    lines += [
        "",
        "Quadrant logic: top-right = assess potential;",
        "bottom-right = review pricing; top-left = review",
        "cost structure; bottom-left = need for innovation.",
    ]
    _slide(fig, _fmt(plan["title"], y0=y0, y1=y1),
           _fmt(plan["subtitle"], y0=y0 % 100, y1=y1 % 100))
    _comment_box(fig, lines)
    fig.savefig(os.path.join(OUT, "B_product_cagr_margin.png"), dpi=140)
    plt.close(fig)
    # Drop render-only helper columns so the persisted data.csv/xlsx stay clean.
    return df.drop(columns=["cagr_plot", "y_clipped", "x_plot", "x_clipped"])


# ============================================================================
# C) Customer ABC / Pareto  ->  kind "pareto_abc"
# ============================================================================
PLAN_C = {
    "kind": "pareto_abc",
    "group_field": "Customer Group",
    # CHF (normalized from EUR in gold). ABC is share-based, so the bins are
    # identical to EUR; using CHF keeps every customer chart in one currency.
    "value_field": "Consolidated Gross Profit CHF",
    "value_label": "margin",
    "a_cut": 80.0,
    "b_cut": 95.0,
    "top_n_listed": 6,
    "title": "80% of margin is generated with {a_cut} of {total} customers",
    "subtitle": "Customers: ABC analysis by cumulative {value_label} (by {group_field})",
}


def chart_C(c, plan):
    gfield, vfield = plan["group_field"], plan["value_field"]
    vlabel = plan.get("value_label", "value")
    g = c.groupby(gfield)[vfield].sum().sort_values(ascending=False)
    g = g[g > 0]
    if g.empty:
        print(f"  [skip] chart_C: no customer rows with {vlabel} > 0 "
              "(Customer View.xlsx is empty?)")
        return None
    total = g.sum()
    cum = g.cumsum() / total * 100
    nn = np.arange(1, len(g) + 1)

    a_pct, b_pct = float(plan["a_cut"]), float(plan["b_cut"])
    a_cut = int((cum <= a_pct).sum()) + 1
    b_cut = int((cum <= b_pct).sum()) + 1

    n = len(g)
    fig = plt.figure(figsize=(13.33, 7.5))
    ax = fig.add_axes([0.06, 0.12, 0.58, 0.70])

    # Full-height A / B / C bands in three shades of blue (mirrors the GF PDF):
    # A = darkest, B = mid, C = lightest. Bands span the whole plot height so
    # the ABC segmentation reads even where the curve hugs the top-left.
    # Log x-axis: the GF sample is extremely concentrated (A/B are a handful of
    # customers out of ~1,500), so on a linear axis the A/B bands collapse to
    # invisible slivers. A log scale spreads the early ranks so the three ABC
    # bands stay readable while the long C tail stays compact.
    x0 = 0.7  # left edge just below rank 1 (log scale can't start at 0)
    A_BAND, B_BAND, C_BAND = "#2e8be0", "#9cc9ee", "#e3eff8"
    ax.axvspan(x0, a_cut, color=A_BAND, alpha=0.9, lw=0, zorder=0)
    ax.axvspan(a_cut, b_cut, color=B_BAND, alpha=0.9, lw=0, zorder=0)
    ax.axvspan(b_cut, n, color=C_BAND, alpha=0.9, lw=0, zorder=0)

    ax.plot(nn, cum.values, color=BLUE, lw=2.4, zorder=3)
    ax.axhline(a_pct, color="white", lw=1.0, zorder=2)
    ax.axhline(b_pct, color="white", lw=1.0, zorder=2)
    ax.set_xscale("log")
    ax.set_xlabel(f"Number of customers (ranked by {vlabel}, log scale)")
    ax.set_ylabel(f"Cumulative {vlabel} [%]", color=BLUE)
    ax.set_xlim(x0, n)
    ax.set_ylim(0, 102)

    # Y axis as percentages; tick the A/B cut counts on the x axis like the PDF.
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    xticks = sorted({1, a_cut, b_cut, n})
    ax.set_xticks(xticks)
    ax.set_xticklabels([str(t) for t in xticks])
    ax.tick_params(axis="x", which="minor", length=0)
    ax.xaxis.set_minor_formatter(plt.NullFormatter())

    # A / B / C labels centred in each band (geometric centre on the log axis).
    def _gmid(lo, hi):
        return float(np.sqrt(max(lo, x0) * hi))
    ax.text(_gmid(x0, a_cut), 30, "A", ha="center", va="center",
            color="white", fontsize=15, fontweight="bold", zorder=4)
    ax.text(_gmid(a_cut, b_cut), 30, "B", ha="center", va="center",
            color="#0b3d6b", fontsize=15, fontweight="bold", zorder=4)
    ax.text(_gmid(b_cut, n), 30, "C", ha="center", va="center",
            color="#0b3d6b", fontsize=15, fontweight="bold", zorder=4)

    _slide(fig,
           _fmt(plan["title"], a_cut=a_cut, total=len(g)),
           _fmt(plan["subtitle"], group_field=gfield, value_label=vlabel))
    top = g.head(int(plan["top_n_listed"]))
    lines = [f"• {vlabel.capitalize()} generated with {len(g)} customer groups:",
             f"• {a_pct:.0f}% of {vlabel} → {a_cut} customers ({a_cut/len(g)*100:.1f}%) = 'A'",
             f"• {b_pct:.0f}% of {vlabel} → {b_cut} customers (→ {b_cut-a_cut} 'B')",
             f"• remaining {100-b_pct:.0f}% → {len(g)-b_cut} 'C' customers",
             "• → extreme concentration on a few large",
             "  distributor groups.",
             "",
             f"Top customers by {vlabel}:"]
    for name, v in top.items():
        lines.append(f"  - {str(name)[:22]}: {v/total*100:.0f}%")
    _comment_box(fig, lines)
    fig.savefig(os.path.join(OUT, "C_customer_abc.png"), dpi=140)
    plt.close(fig)
    return g


# ============================================================================
# D) Product split by segment  ->  kind "stacked_segment"
# ============================================================================
PLAN_D = {
    "kind": "stacked_segment",
    "segment_field": "Buying Group L6",
    "stack_field": "Rep. Product Line",
    "year": 2025,
    "label_threshold_pct": 6.0,
    "sort_segments": True,        # order columns by descending segment sales
    "others_max_share": 0.0,      # roll up segments below this sales share into "Others" (0 = off)
    "title": "Product mix differs markedly across buying groups ({year})",
    "subtitle": "Marimekko: column width = buying-group sales (CHF m); split by {seg} in {year}",
}


def chart_D(p, plan):
    year = int(plan["year"])
    seg, stack = plan["segment_field"], plan["stack_field"]
    thr = float(plan["label_threshold_pct"])
    d = p[p["Year"] == year]
    piv = d.pivot_table(index=stack, columns=seg,
                        values="Net Sales (CHF)", aggfunc="sum", fill_value=0)

    # --- segment totals drive column WIDTH (Marimekko) ------------------------
    seg_tot = piv.sum(axis=0)                       # CHF per segment (column)
    if plan.get("sort_segments", True):
        seg_tot = seg_tot.sort_values(ascending=False)
        piv = piv[seg_tot.index]

    # Roll up small segments (sales share < others_max_share of total) into one
    # "Others" column, mirroring chart_A(). Done on raw CHF so totals reconcile.
    others_share = float(plan.get("others_max_share", 0.0) or 0.0)
    total_all = float(seg_tot.sum())
    if others_share > 0 and total_all > 0:
        small = seg_tot / total_all < others_share
        if small.sum() > 1:
            keep_cols = seg_tot.index[~small]
            others = piv[seg_tot.index[small]].sum(axis=1)
            piv = piv[keep_cols].copy()
            piv["Others"] = others
            seg_tot = piv.sum(axis=0)

    share = piv / piv.sum(axis=0) * 100             # within-segment % (column height)
    seg_tot_m = seg_tot / 1e6                        # CHF m for labels
    cats = share.index.tolist()
    segs = share.columns.tolist()
    colors = plt.cm.tab20(np.linspace(0, 1, len(cats)))

    fig = plt.figure(figsize=(13.33, 7.5))
    # Taller bottom margin to host the staggered (multi-tier) x-axis labels.
    ax = fig.add_axes([0.08, 0.24, 0.55, 0.60])

    # --- Mekko (Marimekko) geometry -------------------------------------------
    # Column HEIGHT = within-segment product-line share (sums to 100%); column
    # WIDTH ∝ segment Net Sales; columns drawn edge-to-edge so total width = total
    # sales. Same pattern as chart_A(). See spec.md FR-003..FR-005.
    widths = seg_tot_m.values.astype(float)
    edges = np.concatenate([[0.0], np.cumsum(widths)])   # left edge of each column
    centers = edges[:-1] + widths / 2.0                  # column centre (ticks/labels)
    gap = max(widths.sum() * 0.004, 0.02)                # thin separator
    bar_w = np.maximum(widths - gap, 0.0)
    min_w = widths.sum() * 0.020                         # columns too narrow to label

    bottom = np.zeros(len(segs))
    for ci, cat in enumerate(cats):
        vals = share.loc[cat].values
        ax.bar(centers, vals, bottom=bottom, width=bar_w,
               color=colors[ci], align="center", label=str(cat)[:22])
        for xi, w, v, b in zip(centers, widths, vals, bottom):
            if v >= thr and w >= min_w:
                ax.text(xi, b + v / 2, f"{v:.0f}%", ha="center", va="center",
                        fontsize=7.5, color="white")
        bottom += vals

    ax.set_xlim(0, edges[-1])
    # Staggered x-axis labels: every column is labelled (even narrow ones), but
    # consecutive labels alternate across stacked tiers below the axis so adjacent
    # narrow columns never overlap. A thin leader connects each column centre to
    # its label. Mirrors the GF PDF example. See spec.md FR-006.
    ax.set_xticks(centers)
    ax.set_xticklabels([])                 # suppress default (overlapping) tick text
    ax.tick_params(axis="x", length=0)
    tiers = [-0.06, -0.115, -0.17, -0.225]   # axes-fraction y per tier (below the axis)
    # Use as many tiers as needed: 2 when every column is wide, up to 4 for a
    # long tail of narrow columns (keeps every group rather than rolling up).
    n_tiers = 2 if (widths >= min_w).all() else len(tiers)
    for i, (xi, s, t) in enumerate(zip(centers, segs, seg_tot_m.values)):
        y = tiers[i % n_tiers]
        ax.annotate(f"{s}\n(CHF {t:.0f} m)",
                    xy=(xi, 0), xycoords=("data", "axes fraction"),
                    xytext=(xi, y), textcoords=("data", "axes fraction"),
                    ha="center", va="top", fontsize=7.5,
                    arrowprops=dict(arrowstyle="-", color="#999999", lw=0.5,
                                    shrinkA=0, shrinkB=2))
    ax.set_xlabel("Buying-group sales %d [CHF m] — column width ∝ sales" % year,
                  color=BLUE, labelpad=78)
    ax.set_ylabel("Product sales (in %% of buying-group sales %d)" % year)
    ax.set_ylim(0, 100)
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=7.5, frameon=False)

    _slide(fig, _fmt(plan["title"], year=year),
           _fmt(plan["subtitle"], seg=seg, year=year))
    biggest, smallest = seg_tot_m.index[0], seg_tot_m.index[-1]
    lines = [f"• Basis: column = {seg};", f"  slice = {stack}.",
             f"• Width ∝ buying-group sales (CHF m).", ""]
    for s in segs[:5]:
        topcat = share[s].idxmax()
        lines.append(f"• {str(s)[:18]}: led by '{str(topcat)[:16]}'")
        lines.append(f"  ({share[s].max():.0f}%, CHF {seg_tot_m[s]:.0f} m total).")
    lines += ["",
              f"Largest: '{str(biggest)[:18]}' (CHF {seg_tot_m.iloc[0]:.0f} m);",
              f"smallest: '{str(smallest)[:18]}' (CHF {seg_tot_m.iloc[-1]:.0f} m).",
              "Helps rank the portfolio relatively + absolutely."]
    _comment_box(fig, lines, x=0.80)
    fig.savefig(os.path.join(OUT, "D_product_split_segment.png"), dpi=140)
    plt.close(fig)
    return share


# ============================================================================
# E) Consolidated profit & margin per customer  ->  kind "profit_margin_dual"
# ============================================================================
PLAN_E = {
    "kind": "profit_margin_dual",
    "group_field": "Customer Name",
    "year": 2025,
    "margin_cutoff_pct": 30.0,
    "title": "Consolidated profit & margin per customer, {year}",
    "subtitle": "Customers ranked by consolidated profit; margin overlaid (gross)",
}


def _assert_source_currency(d, expected="EUR", field="Local Currency"):
    """Assert the customer source is single-currency `expected`, or raise.

    Customer amounts are local-currency ("LC"): an LC figure is meaningless
    without its currency. The CHF values in gold are a flat-rate normalization of
    these EUR amounts (build_gold.EUR_CHF_RATE), which is only valid while the
    source is single-currency EUR. So we FAIL LOUD if the column is absent, null,
    or carries any other/mixed currency -- a future multi-currency extract needs
    a dated FX table, not a flat rate. (We assert the source here even though the
    chart plots the pre-converted CHF columns, so the conversion's precondition
    is checked at render time too, not only at gold-build time.)"""
    if field not in d.columns:
        raise ValueError(
            f"chart_E: '{field}' column absent -- cannot verify source currency. "
            "Carry local_currency through to gold (build_gold.CUSTOMER_COLS).")
    codes = sorted(d[field].dropna().unique().tolist())
    if not codes:
        raise ValueError(f"chart_E: '{field}' is all-null -- currency unknown.")
    if codes != [expected]:
        raise ValueError(
            f"chart_E: source currency {codes}, expected ['{expected}']; the "
            "flat EUR->CHF rate is invalid for this data. Add a dated FX table "
            "before normalizing to CHF.")
    return expected


def chart_E(c, plan):
    """Dual-axis: customers ranked by consolidated profit (left axis, money area)
    with per-customer gross margin % overlaid (right axis, 0-100%), plus a
    low-margin highlight box. Mirrors the GF PDF "Cons. profit & margin per
    customer" chart.

    Currency: ALL charts report CHF. The customer source is EUR (local currency);
    gold normalizes it to CHF with a single disclosed rate (build_gold), so this
    chart plots the `*_chf` columns and labels CHF. The EUR source is still
    asserted single-currency before render -- see `_assert_source_currency` --
    because the flat rate is only valid for single-currency EUR data. The rate is
    disclosed on the chart (subtitle / comment box)."""
    year = int(plan["year"])
    gfield = plan["group_field"]
    cutoff = float(plan["margin_cutoff_pct"])
    pfield, sfield = "Consolidated Gross Profit CHF", "Net Sales CHF"
    cur = "CHF"                                           # reporting currency (all charts)

    d = c[c["Year"] == year] if "Year" in c.columns else c
    _assert_source_currency(d, expected="EUR")           # flat-rate precondition
    # Disclosure: the EUR->CHF rate used to normalize (carried in gold).
    rate = (float(d["EUR/CHF Rate"].dropna().iloc[0])
            if "EUR/CHF Rate" in d.columns and d["EUR/CHF Rate"].notna().any()
            else None)
    fx_note = f"EUR→CHF @ {rate:g}" if rate is not None else "EUR→CHF (rate n/a)"
    g = d.groupby(gfield).agg(profit=(pfield, "sum"), sales=(sfield, "sum"))
    g = g[g["sales"] > 0].copy()
    if g.empty:
        print(f"  [skip] chart_E: no customer rows with sales > 0 in {year}")
        return None
    g["margin"] = g["profit"] / g["sales"] * 100
    g = g.sort_values("profit", ascending=False).reset_index()
    g["rank"] = np.arange(1, len(g) + 1)

    n = len(g)
    total_profit = g["profit"].sum()
    rank = g["rank"].values

    fig = plt.figure(figsize=(13.33, 7.5))
    ax = fig.add_axes([0.07, 0.12, 0.57, 0.70])          # left axis: profit (money)
    axm = ax.twinx()                                     # right axis: margin (%)

    # Left: consolidated profit as a descending filled area (in {cur} '000s).
    profit_k = g["profit"].values / 1e3
    ax.fill_between(rank, 0, profit_k, color="#222222", lw=0, zorder=2)
    ax.set_ylabel(f"Consolidated Profit [{cur} '000]", color=BLUE)
    ax.set_xlabel("Customers (ranked by consolidated profit, 1 = largest)")
    ax.set_xlim(0.5, n + 0.5)
    pmax = float(np.nanmax(profit_k))
    pmin = min(0.0, float(np.nanmin(profit_k)))
    ax.set_ylim(pmin * 1.05 if pmin < 0 else 0, pmax * 1.08)

    # Right: per-customer gross margin %, as diamond markers on thin stems down
    # to 0 (the GF PDF's stem/"rain" look), clipped to 0..100 for readability;
    # values outside the range are pinned to the axis edge and stay in the data.
    margin_plot = g["margin"].clip(lower=0, upper=100).values
    axm.vlines(rank, 0, margin_plot, color=BLUE, lw=0.3, alpha=0.35, zorder=2)
    axm.scatter(rank, margin_plot, s=10, marker="D", color=BLUE, alpha=0.6,
                edgecolors="none", zorder=3)
    axm.set_ylabel("Consolidated Margin [%]", color=BLUE)
    axm.set_ylim(0, 100)
    axm.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))

    # Low-margin highlight box: customers whose margin sits BELOW the cut-off.
    # Drawn on the margin (right) axis so the band height = 0..cutoff.
    axm.axhspan(0, cutoff, xmin=0, xmax=1, facecolor="none", edgecolor=RED,
                lw=1.6, zorder=4)
    axm.text(n * 0.995, cutoff + 1.5, f"margin < {cutoff:.0f}%", ha="right",
             va="bottom", color=RED, fontsize=7.5, fontweight="bold", zorder=5)

    # Legend naming both series (proxy markers, not the real axes objects).
    handles = [
        plt.Line2D([0], [0], marker="s", color="none", markerfacecolor="#222222",
                   markersize=9, label="Consolidated Profit"),
        plt.Line2D([0], [0], marker="D", color="none", markerfacecolor=BLUE,
                   markersize=8, label="Consolidated Margin"),
    ]
    ax.legend(handles=handles, loc="upper right", fontsize=7.5, frameon=False)

    below = g[g["margin"] < cutoff]
    below_profit = below["profit"].sum()
    med_margin = float(g["margin"].median())
    top = g.iloc[0]
    subtitle = f"{_fmt(plan['subtitle'], year=year)} · {fx_note}"
    _slide(fig, _fmt(plan["title"], year=year), subtitle)
    _comment_box(fig, [
        f"• {n} customers with sales in {year}, ranked by",
        "  consolidated (gross) profit.",
        f"• {len(below)} of {n} customers ({len(below)/n*100:.0f}%) sit",
        f"  below a {cutoff:.0f}% margin (red box) — they carry",
        f"  {cur} {below_profit/1e6:.1f} m profit ({below_profit/total_profit*100:.0f}% of total).",
        f"• Median customer margin: {med_margin:.0f}%.",
        f"• Largest: '{str(top[gfield])[:22]}' — {cur} {top['profit']/1e6:.1f} m",
        f"  profit at {top['margin']:.0f}% margin.",
        "",
        "Proxy note: margin = consolidated gross profit /",
        "net sales; true cost-to-serve not yet included.",
        f"FX note: source EUR normalized to CHF ({fx_note}).",
    ])
    fig.savefig(os.path.join(OUT, "E_customer_profit_and_margin.png"), dpi=140)
    plt.close(fig)
    return g


def store_chart(name, data, png_filename):
    """Store one chart's data + image in its own ./<OUT>/chart-<name>/ folder,
    so each chart can be fine-tuned independently.

    Writes:  data.csv  (the exact numbers behind the chart, fine-tune here)
             data.xlsx (same, Excel)
    and moves the already-saved PNG into the folder.
    """
    folder = os.path.join(OUT, f"chart-{name}")
    os.makedirs(folder, exist_ok=True)
    df = data.reset_index() if data.index.name or isinstance(data.index, pd.MultiIndex) \
        else data.copy()
    df.to_csv(os.path.join(folder, "data.csv"), index=False)
    with pd.ExcelWriter(os.path.join(folder, "data.xlsx"), engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name=name[:31], index=False)
    src = os.path.join(OUT, png_filename)
    if os.path.exists(src):
        os.replace(src, os.path.join(folder, png_filename))
    print(f"  stored chart-{name}/  ({len(df)} rows)")
    return folder


def _spec(name):
    return os.path.join(OUT, f"chart-{name}", "spec.md")


def main():
    os.makedirs(OUT, exist_ok=True)
    p = load_product()
    c = load_customer()

    print("Resolving render plans from each chart's spec.md ...")
    plan_a = plan_chart_from_spec(_spec("product_group_sales_margin"), PLAN_A)
    plan_b = plan_chart_from_spec(_spec("product_cagr_margin"), PLAN_B)
    plan_c = plan_chart_from_spec(_spec("customer_abc"), PLAN_C)
    plan_d = plan_chart_from_spec(_spec("product_split_segment"), PLAN_D)
    plan_e = plan_chart_from_spec(_spec("customer_profit_and_margin"), PLAN_E)

    print("A) product-group sales & margin ...")
    A = chart_A(p, plan_a)
    print("B) product CAGR x margin ...")
    B = chart_B(p, plan_b)
    print("C) customer ABC / Pareto ...")
    C = chart_C(c, plan_c)
    print("D) product split by segment ...")
    D = chart_D(p, plan_d)
    print("E) customer profit & margin ...")
    E = chart_E(c, plan_e)

    # ---- store each chart's data in its own chart-<name> folder ----
    print("\nStoring per-chart data folders:")
    store_chart("product_group_sales_margin", A, "A_product_group_sales_margin.png")
    store_chart("product_cagr_margin", B, "B_product_cagr_margin.png")
    if C is not None:
        store_chart("customer_abc", C.rename(plan_c.get("value_label", "value")),
                    "C_customer_abc.png")
    store_chart("product_split_segment", D, "D_product_split_segment.png")
    if E is not None:
        E_renamed = E.rename(columns={
            "profit": "Consolidated Gross Profit CHF",
            "sales": "Net Sales CHF",
            "margin": "Consolidated Margin %",
        })
        store_chart("customer_profit_and_margin", E_renamed, "E_customer_profit_and_margin.png")

    print("\nDone. Each chart now lives in ./%s/chart-<name>/" % OUT)
    for d in sorted(os.listdir(OUT)):
        full = os.path.join(OUT, d)
        if os.path.isdir(full):
            print("  -", d, "->", sorted(os.listdir(full)))


if __name__ == "__main__":
    main()
