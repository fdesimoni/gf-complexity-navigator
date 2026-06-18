# Feature Specification: Product-Line Growth vs. Margin Change (CAGR × Δ Margin)

**Feature Branch**: `chart-product_cagr_margin`
**Created**: 2026-06-11
**Status**: Implemented (proof-of-concept)
**Artifact**: [`B_product_cagr_margin.png`](B_product_cagr_margin.png) · data in [`data.csv`](data.csv) / [`data.xlsx`](data.xlsx) · produced by [`analysis.py`](../../../analysis.py) → `chart_B()`
**Input**: "Product-line growth vs. margin change, {y0}-{y1}" — bubble / four-quadrant chart

## Execution Flow (main)

```
1. Load product data, derive Year from Quarter
2. Restrict to full years y0..y1 (default 2021..2025); pivot Net Sales by line × year
3. Keep lines with positive sales in both the first and last year
4. Compute CAGR = (sales[y1] / sales[y0])^(1/n) − 1 (Y);
   Δ margin = margin[y1] − margin[y0] in percentage points (X);
   total period sales = bubble size
5. Plot Δ margin (X) vs CAGR% (Y); bubble area = period sales;
   reference lines at 0% growth (horizontal) and 0 pp margin change (vertical)
   split the plane into four shaded, named quadrants. Both axes are capped at
   ±20 (Y in %, X in pp); outliers clamp to the edge with their true value shown
6. Label every line; derive margin-improved/declined and
   sales-decline counts into the comment box
7. Run review checklist → mark any [NEEDS CLARIFICATION]
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
As a **GF decision-maker**, I want each product line placed by its **5-year sales growth** against the **change in its profit margin** over the same window, with bubble size showing how much revenue it carries, so that I can separate lines to grow/protect from lines that need a pricing, cost-structure or innovation response.

### Acceptance Scenarios
1. **Given** a line with positive sales in both 2021 and 2025, **When** the chart renders, **Then** it appears at (Δ margin, CAGR%) with bubble area proportional to its 2021–2025 sales.
2. **Given** a line in sales decline, **When** rendered, **Then** it sits **below the 0%-growth line**.
3. **Given** a line whose margin fell over the window, **When** rendered, **Then** it sits **left of the 0-pp vertical line**; a line whose margin rose sits to the right.
4. **Given** the full set, **When** rendered, **Then** a vertical reference line marks **0 pp margin change** and a horizontal line marks **0% growth**, splitting the plane into **four named, shaded quadrants**: top-left *Review cost structure*, top-right *Assess potential*, bottom-left *Warning sign – need for innovation*, bottom-right *Review pricing*.
5. **Given** the rendered chart, **When** a reviewer reads the comment box, **Then** the count of lines whose **margin improved vs. declined**, the count in **sales decline (CAGR < 0)**, the **best margin mover**, and any **>10% CAGR grower (or its absence)** are all derivable.
6. **Given** the rendered chart, **When** rendered, **Then** every line is text-labelled: large bubbles carry a white label centred inside, smaller bubbles an offset dark label just outside.
7. **Given** a line whose CAGR or Δ margin falls outside the ±20 axis caps, **When** rendered, **Then** its bubble is clamped to the axis edge and its label is suffixed with the true off-axis value (e.g. `Silenta (+42 pp)`) so no number is hidden.

### Edge Cases
- A line lacking positive sales in the first OR last year → **excluded** from the chart (CAGR / margin-delta undefined).
- 2026 is a partial year → **excluded** from the CAGR window.
- Two lines overlapping in position → bubble transparency must keep both visible.
- A line beyond the ±20 axis caps (CAGR % or Δ margin pp) → its bubble is clamped to the axis edge and its label carries the true value, so the cap tightens the view without hiding any line.
- "Other revenue" / residual buckets may be excluded from the chart (as in the PDF) to keep the product picture clean.

---

## Requirements

### Functional Requirements

**Data & scope**
- **FR-001**: The chart MUST represent one bubble per **Rep. Product Line**, over a configurable full-year window **y0..y1** (default 2021–2025).
- **FR-002**: A line MUST be **included only if** it has Net Sales > 0 in both y0 and y1; otherwise excluded (CAGR / margin-delta undefined).
- **FR-003**: The CAGR window MUST use **full years only** (2026 partial year excluded).

**Axes & encodings**
- **FR-004**: The **X-axis** MUST encode the **change in margin over the window, Δ margin = margin[y1] − margin[y0]**, in **percentage points**, where margin[t] = Gross Profit[t] / Net Sales[t]. (A `margin_delta` vs. absolute-`margin` X mode is selectable in the render plan; default is `margin_delta` to mirror the PDF.)
- **FR-005**: The **Y-axis** MUST encode **Sales CAGR % = (NS[y1]/NS[y0])^(1/n) − 1**, where n = y1 − y0.
- **FR-005a**: Both axes MUST be capped symmetrically at a configurable limit (`y_clip_pct` for CAGR %, default ±20%; `x_clip_pp` for Δ margin pp, default ±20 pp) so a single far outlier cannot stretch an axis and leave the plot mostly empty. A line outside a cap MUST be clamped to the axis edge and its true off-axis value MUST be shown in its label.
- **FR-006**: **Bubble area** MUST encode the line's **total Net Sales over the window**, scaled relative to the largest line.
- **FR-007**: The chart MUST draw a **0%-growth horizontal line** and a **0-pp-margin-change vertical line** to split the plane into **four shaded quadrants**, each carrying its action label (FR-008).

**Quadrant meaning (documented, as in the PDF)**
- **FR-008**: The four quadrants MUST be named on the chart: **top-left = Review cost structure** (margin fell, sales grew); **top-right = Assess potential** (margin and sales both up); **bottom-left = Warning sign – need for innovation** (margin and sales both down); **bottom-right = Review pricing** (margin up, sales down).

**Labelling & narrative**
- **FR-009**: Every line MUST be text-labelled and plotted. Above-median lines carry a white label centred inside the bubble; smaller lines (and any clamped to an axis edge) carry an offset dark label just outside the bubble.
- **FR-010**: The comment box MUST state, all deterministic: count of lines whose **margin improved** vs. **declined** and the **best margin mover** (name + Δpp); count in **sales decline (CAGR < 0)**; and either the count growing **>10% CAGR** (with the fastest line) or, if none, an explicit broad-decline statement.

**Honesty / governance**
- **FR-011**: Every figure MUST be reproducible from source; **no language model may produce any number**. Exact inputs MUST be persisted (`data.csv` / `data.xlsx`).

### Key Entities
- **Rep. Product Line**: the unit of analysis; carries per-year Net Sales and Gross Profit, total Net Sales, derived CAGR, start/end margin %, **Δ margin (pp)**, average margin %, period sales (CHF m).
- **CAGR / Δ-margin window (y0..y1)**: the full-year span over which growth and margin change are computed.

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
- [x] Axes (Δ margin / CAGR), their ±20 caps with edge-clamping, bubble size and four-quadrant lines/labels are unambiguous
- [x] Inclusion rule and full-year-only window are explicit
- [x] "No-LLM-numbers" governance stated