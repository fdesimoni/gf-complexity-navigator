# Feature Specification: Consolidated Profit & Margin per Customer

**Feature Branch**: `chart-customer_profit_and_margin`
**Created**: 2026-06-11
**Status**: Implemented (proof-of-concept)
**Artifact**: [`E_customer_profit_and_margin.png`](E_customer_profit_and_margin.png) · data in [`data.csv`](data.csv) / [`data.xlsx`](data.xlsx) · produced by [`analysis.py`](../../../analysis.py) → `chart_E()`
**Mirrors**: GF `Auswertung.pdf` — "Cons. profit & margin per customer {year}"
**Input**: "Cons. profit & margin per customer, {year}" — dual-axis profit curve + per-customer margin scatter, low-margin highlight

## Execution Flow (main)

```
1. Load customer data (Customer View.xlsx); restrict to a single full year {year}
2. Group by Customer (grain = Customer Name / Customer Group); sum Consolidated
   Gross Profit (= "consolidated profit") and Net Sales; margin = profit / sales
3. Keep customers with Net Sales > 0; sort by consolidated profit DESCENDING
4. X-axis = customer rank (1 = largest profit) — customers stay in profit order
5. Left Y-axis  = Consolidated Profit (CHF), drawn as a descending filled area/bars
   Right Y-axis = Consolidated Margin (%) per customer, drawn as diamond markers
   on thin stems down to 0 (0..100%), giving the GF PDF's dense "rain" look
6. Draw a highlight box over the LOW-MARGIN region (margin below a cut-off, default 30%)
   to flag profitable-looking-but-thin-margin customers
7. Derive counts (customers below cut-off, share of profit they carry, median margin)
   into the comment box
8. Run review checklist → mark any [NEEDS CLARIFICATION]
```

---

## ⚡ Quick Guidelines

- ✅ Focus on WHAT the chart must communicate to GF management and WHY
- ✅ Written for a business + analytics audience (a GF steering committee)
- ❌ Avoid prescribing plotting-library internals; the engine is interchangeable
- 🔒 Every figure is deterministic and traceable to source; no language model touches a number

---

## User Scenarios & Testing

### Primary User Story
As a **GF decision-maker**, I want to see, for a given year, **how much profit each customer contributes** (a steeply descending curve) overlaid with **each customer's margin %**, so that I can spot customers that carry meaningful volume but earn a **thin or near-zero margin** — the prime cost-to-serve / pricing-review candidates.

### Acceptance Scenarios
1. **Given** customers ranked by consolidated profit, **When** the chart renders, **Then** the **left Y-axis** shows consolidated profit (CHF) as a curve/area that falls steeply from the largest customer to a long flat tail.
2. **Given** the same customers in the same rank order, **When** rendered, **Then** each customer's **consolidated margin %** is plotted against the **right Y-axis** (0–100%) as a point marker at that customer's X position.
3. **Given** the two series share one X-axis, **Then** profit (left axis, CHF) and margin (right axis, %) are visibly distinguished (different mark style / colour) and the right axis is labelled in percent.
4. **Given** a configurable margin cut-off (default 30%), **When** rendered, **Then** a **highlight box** spans the low-margin region so customers **below** the cut-off are visually flagged.
5. **Given** the rendered chart, **When** a reviewer reads the comment box, **Then** the total customer count, the count (and profit share) **below the margin cut-off**, and the **median margin** are all derivable.

### Edge Cases
- Customers with Net Sales ≤ 0 in the year → **excluded** (margin undefined).
- Customers with negative consolidated profit → **plotted** (the curve may dip below zero at the tail); margin may be negative and is **clipped/annotated** rather than dropped.
- A very long customer tail (thousands of customers) → the curve must stay readable (X ticks thinned; markers kept visible via size/transparency).
- 2026 is a partial year → **excluded** unless explicitly selected.

---

## Requirements

### Functional Requirements

**Data & scope**
- **FR-001**: The chart MUST represent **one customer per X position**, for a single configurable full year **{year}**, at a configurable grain (default **Customer Name**; **Customer Group** selectable).
- **FR-002**: A customer MUST be **included only if** it has **Net Sales > 0** in the year; otherwise excluded (margin undefined).
- **FR-003**: Customers MUST be **sorted by Consolidated Gross Profit descending**, and this rank defines the X-axis order for **both** series.

**Axes & encodings**
- **FR-004**: The **X-axis** MUST encode the **customer rank** (1 = largest consolidated profit). Individual customer labels are NOT required (the population is large).
- **FR-005**: The **left Y-axis** MUST encode **Consolidated Profit (CHF)**, rendered as a **filled area / bar series** in descending order. Currency: all charts report **CHF**. The customer source carries only local-currency money (EUR, ~100% of rows; GF supplies no native customer CHF), so gold normalizes EUR→CHF with a **single disclosed rate** (`build_gold.EUR_CHF_RATE`, demo `0.93`) and the chart **discloses the rate** in the subtitle / comment box. The flat rate is asserted valid only while the source is single-currency EUR; a mixed-currency extract fails loud and requires a dated FX table.
- **FR-006**: The **right Y-axis** MUST encode **Consolidated Margin % = Consolidated Gross Profit / Net Sales**, rendered as **per-customer diamond markers on thin stems to 0**, scaled **0–100%** (margins outside the range pinned to the axis edge for readability, kept in the data).
- **FR-007**: The two series MUST be visually distinguishable and a **legend** MUST name them ("Consolidated Profit", "Consolidated Margin").

**Low-margin highlight**
- **FR-008**: The chart MUST draw a **highlight box** over the **low-margin region** (margin **below** a configurable cut-off, default **30%**), to flag profitable-looking but thin-margin customers.

**Narrative**
- **FR-009**: The comment box MUST state, all deterministic: total customers in scope; **count below the margin cut-off** and the **share of total profit** they represent; the **median margin**; and the **largest customer's** profit and margin.

**Honesty / governance**
- **FR-010**: Margin MUST be labelled a **gross** margin (Consolidated Gross Profit / Net Sales); **true cost-to-serve is not yet included** (proxy note).
- **FR-011**: Every figure MUST be reproducible from source; **no language model may produce any number**. Exact inputs MUST be persisted (`data.csv` / `data.xlsx`).

### Key Entities
- **Customer**: the unit of analysis (grain = Customer Name, configurable to Customer Group); carries Net Sales, Consolidated Gross Profit (consolidated profit), derived margin %, profit rank, and a below-/above-cut-off flag.
- **Margin cut-off**: the threshold (default 30%) defining the low-margin highlight region.

---

## Render plan (new kind: `profit_margin_dual`)

This chart introduces a fifth chart **kind** (the four prior kinds do not cover a
dual-axis profit/margin overlay), implemented in `analysis.py` → `chart_E()`:

```
"profit_margin_dual"  (consolidated profit & margin per customer)
{ "kind": "profit_margin_dual",
  "group_field": <column, e.g. "Customer Name" | "Customer Group">,
  "year": <int, e.g. 2025>,
  "margin_cutoff_pct": <float, e.g. 30>,  // low-margin highlight threshold
  "title": <str>, "subtitle": <str> }
```

The profit/sales columns (`Consolidated Gross Profit CHF`, `Net Sales CHF`) and the
descending profit sort are fixed in `chart_E()` (not LLM-selectable), so the model
can never redirect the metric. Defaults (built-in fallback `PLAN_E`):
`group_field = "Customer Name"`, `year = 2025` (the sample's only full year;
2026 is partial), `margin_cutoff_pct = 30`,
`title = "Consolidated profit & margin per customer, {year}"`,
`subtitle = "Customers ranked by consolidated profit; margin overlaid (gross)"`.

---

## Review & Acceptance Checklist

### Content Quality
- [x] No prescribed plotting-library internals (engine interchangeable)
- [x] Focused on decision value to GF and why
- [x] Written for a business + analytics audience
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable against the rendered chart + `data.csv`
- [x] Dual axes (profit CHF / margin %), rank ordering and low-margin highlight are unambiguous
- [x] Inclusion rule (Net Sales > 0), grain and single-year scope are explicit
- [x] "No-LLM-numbers" governance stated

---

## Notes / Dependencies
- Source: Gold customer data (columns: `Customer Name` / `Customer Group`, `Net Sales CHF`, `Consolidated Gross Profit CHF`). Renderer: `analysis.py` → `chart_E()` (`profit_margin_dual` kind).
- Complements [`chart-customer_abc`](../chart-customer_abc/spec.md): ABC shows *concentration* of profit; this chart shows *margin quality* per customer and flags the thin-margin tail.
- Supports the Phase 2a customer-profitability / cost-to-serve narrative in [`approach_v2.md`](../../../approach_v2.md) (net-negative and thin-margin customers).
- Fine-tune: edit [`data.csv`](data.csv) in this folder.
