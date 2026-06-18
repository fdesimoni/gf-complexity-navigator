# Feature Specification: Sales × Margin per Rep. Product Line (Mekko)

**Feature Branch**: `chart-product_group_sales_margin`
**Created**: 2026-06-11
**Status**: Spec updated → Mekko (Marimekko) chart
**Artifact**: [`A_product_group_sales_margin.png`](A_product_group_sales_margin.png) · data in [`data.csv`](data.csv) / [`data.xlsx`](data.xlsx) · produced by [`analysis.py`](../../../analysis.py) → `chart_A()`
**Input**: "A few representative product lines account for the bulk of margin in {year}" — a **Mekko chart** where bar **width = sales**, bar **height = margin %**, so each bar's **area ≈ gross profit**, one column per Rep. Product Line

## Execution Flow (main)

```
1. Load product data (Product View.xlsx), derive Year from Quarter
2. Filter to the latest full year (default 2024)
3. Group by Rep. Product Line (column S, "Rep. Product Line"); sum Net Sales and Gross Profit
4. Compute margin % = Gross Profit / Net Sales; sort lines by Gross Profit descending
5. Render a MEKKO: each column's WIDTH ∝ Net Sales (CHF m), HEIGHT = margin % (left axis).
   Columns sit side by side with no gaps; cumulative width = total sales.
   Each column therefore has AREA ≈ Gross Profit. Inside each column place value
   boxes: Total Sales (CHF m, blue) and Gross Profit (CHF m, grey)
6. Draw an average-margin reference line (Ø, sales-weighted) across the plot
7. Derive headline numbers (largest gross-profit line, best/worst margin, average) into comment box
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
As a **GF decision-maker**, I want to see, for the latest full year, a **Mekko (Marimekko) chart** of the representative product lines where each column's **width is proportional to its sales** and its **height is its profit margin %** — so each column's **area approximates its gross profit** — ranked by gross-profit contribution, with the **company average margin** as a reference line, so that I can see at a glance both *how big* each line is (width) and *how profitable* it is (height), and which lines sit above or below the average margin.

### Acceptance Scenarios
1. **Given** product data for the target year, **When** the chart renders, **Then** **one column per Rep. Product Line** appears, **sorted by Gross Profit descending** (largest profit contributor leftmost), with **no horizontal gaps** between columns.
2. **Given** each Rep. Product Line, **When** rendered, **Then** its **column width is proportional to its Net Sales (CHF m)** and its **column height equals its margin %** (left axis, %); consequently the column **area ≈ Gross Profit**.
3. **Given** the X-axis, **When** rendered, **Then** the **cumulative column width equals total Net Sales** (the X-axis measures sales, not a categorical index), so widest columns are the biggest sellers.
4. **Given** each column, **When** rendered, **Then** it contains two labelled value boxes: **Total Sales (CHF m, blue)** and **Gross Profit (CHF m, grey)**.
5. **Given** the full set of product lines, **When** rendered, **Then** a horizontal **average-margin reference line (Ø)** spans the plot and is labelled with the average margin %.
6. **Given** a line whose margin is above (below) the average, **When** rendered, **Then** the top of its column sits above (below) the Ø line.
7. **Given** the rendered chart, **When** a reviewer reads the comment box, **Then** the largest gross-profit line, the highest- and lowest-margin lines, and the average margin are all derivable from the plotted data.

### Edge Cases
- A line with Net Sales = 0 → column width 0 (effectively not visible); margin defined as 0% (no divide-by-zero).
- A line with negative gross profit → column height shown below 0% (not hidden); width still ∝ |sales|.
- Very small lines (below `others_max_share`) → pooled into a single **"Others"** column; its margin is recomputed from pooled sales/profit (not an average of margins).
- Rows with a missing / `#N/A` Rep. Product Line → grouped under an explicit "#N/A" (or "Unassigned") column rather than dropped, so all sales reconcile to the total width.

---

## Requirements

### Functional Requirements

**Data & scope**
- **FR-001**: The chart MUST represent **one column per Rep. Product Line** (`Rep. Product Line`, column S in `Product View.xlsx`), for a single configurable **full year** (default 2024). Lines whose **sales share falls below a small threshold** (`others_max_share`, default 1.5% of total sales) MUST be **rolled up into a single "Others" column** rather than truncated, so all sales and gross profit still reconcile to the total. No line may be silently dropped.
- **FR-002**: Columns MUST be **sorted by Gross Profit descending** (largest profit contributor leftmost).

**Axes & encodings (Mekko)**
- **FR-003**: The **X-axis MUST encode Net Sales** (CHF m), not a categorical index: each column's **width MUST be proportional to its Net Sales**, columns MUST be drawn **edge-to-edge (no gaps)**, and the **total width MUST equal total Net Sales**.
- **FR-004**: The **left Y-axis** MUST encode **margin % = Gross Profit / Net Sales × 100**; each column's **height MUST equal its margin %**.
- **FR-005**: Because width ∝ sales and height = margin, each column's **area MUST approximate its Gross Profit** (sales × margin) — this area-encodes-profit property is the defining feature of the Mekko and MUST hold.
- **FR-006**: Each column MUST contain **two embedded, individually labelled value boxes**: **Total Sales in CHF millions** (blue) and **Gross Profit in CHF millions** (grey).
- **FR-007**: The chart MUST draw a horizontal **average-margin reference line (Ø)**, computed as the **sales-weighted average margin** (= Σ Gross Profit / Σ Net Sales × 100), labelled with its value.
- **FR-008**: Column height (margin), column width (sales), the two value boxes and the Ø line MUST be visually distinguishable (distinct colours) and the value boxes individually legended.
- **FR-009**: Each column MUST be **labelled with its Rep. Product Line name** (e.g. below/along the X-axis). With ~25 distinct lines of widely varying width, the layout MUST remain legible (e.g. rotated/abbreviated/leader-lined labels for narrow columns, adequate figure width); no column may be dropped to fit.

**Derived narrative**
- **FR-010**: The comment box MUST state: the largest **gross-profit** line with its figure, the highest- and lowest-margin lines with their margins, and the **average margin** — all computed deterministically.

**Honesty / governance**
- **FR-011**: Margin MUST be labelled as a **proxy** (gross profit / net sales); the chart MUST note that **true cost-to-serve is not yet included**.
- **FR-012**: Every figure MUST be reproducible from source; **no language model may produce any number**. The chart's exact inputs MUST be persisted alongside it (`data.csv` / `data.xlsx`) for fine-tuning.

### Key Entities
- **Rep. Product Line** (`Rep. Product Line`, column S): the unit of analysis; carries Net Sales (→ column width), Gross Profit (→ column area), derived margin % (→ column height), sales & gross profit in CHF m. ~25 distinct values (incl. `#N/A`/`Other`).
- **Year**: the single reporting period (latest full year; 2026 is partial and excluded).

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
- [x] Mekko encoding (width = sales, height = margin %, area ≈ gross profit, edge-to-edge columns, Ø line), sorting are unambiguous
- [x] Scope (one year, by Rep. Product Line — all values, no truncation) is bounded
- [x] Proxy-margin and "no-LLM-numbers" governance stated

---

## Notes / Dependencies
- Source: `Product View.xlsx`. Renderer: `analysis.py` → `chart_A()`.
- **Implementation**: `chart_A()` renders the Mekko by positioning columns at cumulative-sales edges with per-column `width` ∝ sales, and rolls up sub-`others_max_share` lines into an "Others" column. Title is aligned to the GF original ("Products: Sales x Margin {year}").