# Feature Specification: Product Split by Segment — Marimekko

**Feature Branch**: `chart-product_split_segment`
**Created**: 2026-06-11
**Updated**: 2026-06-14 (reframed as a Marimekko; column width ∝ segment sales; basis = Buying Group L6 × Rep. Product Line)
**Status**: Spec updated — renderer change pending
**Artifact**: [`D_product_split_segment.png`](D_product_split_segment.png) · data in [`data.csv`](data.csv) / [`data.xlsx`](data.xlsx) · produced by [`analysis.py`](../../../analysis.py) → `chart_D()`
**Basis**: segment (column) = **Buying Group L6**; stack slice (product) = **Rep. Product Line**
**Input**: "Product mix differs markedly across buying groups ({year})" — **Marimekko**: one 100%-stacked bar per buying group, **column width ∝ that buying group's total sales**

## Purpose (why this chart exists)

This chart supports **Lever A1 — Segment analysis: rank the business portfolio**. The
basis is **Buying Group L6** (the segment / column dimension) split by **Rep. Product
Line** (the product / stack dimension). A plain equal-width stacked bar shows
*relative* product mix per buying group but hides *how big each buying group is*. By
making **column width proportional to buying-group sales**, a Marimekko lets a reader
judge **relative and absolute importance in one view**: a product line can be a large
*share* of a small buying group (relatively important, absolutely minor) or a modest
share of a large buying group (absolutely large). This is the read the GF steering
committee needs to target product rationalization buying-group by buying-group without
over-weighting small ones.

## Execution Flow (main)

```
1. Load product data, derive Year from Quarter
2. Filter to the target full year (default 2025)
3. Pivot Net Sales by Rep. Product Line × Buying Group L6
4. Per buying group: total sales (CHF m) → column WIDTH; product-line shares → 100% stack HEIGHT
5. Render columns edge-to-edge, widths ∝ buying-group sales, each a 100% stack; label slices ≥ threshold
6. Label each column with the buying-group name and its absolute sales (CHF m) on the X-axis
7. Derive, per buying group, the dominant product line + its share, and the largest/smallest
   buying groups by absolute sales, into the comment box
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
As a **GF decision-maker**, I want to see the product-line mix per **buying group**
**with each buying group's bar scaled to its sales size**, so that I can rank the
portfolio on *relative and absolute* importance together and target rationalization
where it moves the most money — not just where a share looks large.

### Acceptance Scenarios
1. **Given** product data for the target year, **When** the chart renders, **Then** each **Buying Group L6** is one **100%-stacked column**, and the **column's width is proportional to that buying group's total sales (CHF m)**, columns drawn edge-to-edge.
2. **Given** two buying groups, **When** rendered, **Then** the **ratio of their column widths equals the ratio of their total sales** (a buying group with 2× the sales is 2× as wide).
3. **Given** a buying-group column, **When** rendered, **Then** each stacked slice's height equals that **Rep. Product Line's % of the buying group's sales**, slices sum to 100%, and slices ≥ the label threshold are labelled.
4. **Given** each column, **When** rendered, **Then** the buying group's **name and absolute sales (CHF m)** are shown on the X-axis (sales doubles as the width legend).
5. **Given** the rendered chart, **When** a reviewer reads the comment box, **Then** the dominant product line per buying group **and** the largest/smallest buying groups by absolute sales are derivable.

### Edge Cases
- A product line absent from a buying group → contributes a 0% (no visible slice).
- A negative within-group share (e.g. credits/returns, −0.01%) → handled without breaking the 100% stack. *[NEEDS CLARIFICATION: floor-to-0, drop, or show as-is?]*
- A slice below the label threshold → drawn but **not** labelled (readability).
- A buying group too narrow to hold its X-axis label → label may be suppressed or rotated, but the column is still drawn and still contributes its full width.
- Many small buying groups → small ones MAY be rolled into an "Others" column (configurable share threshold, mirroring `chart_A()`) to keep the Mekko readable. *[default off]*

---

## Requirements

### Functional Requirements

**Data & scope**
- **FR-001**: The chart MUST show one **100%-stacked column per buying group** (`Buying Group L6`) for a configurable **full year** (default 2025).
- **FR-002**: Stack slices MUST be **Rep. Product Line**.

**Marimekko geometry (the key change)**
- **FR-003**: Each buying-group column's **width MUST be proportional to that buying group's total Net Sales (CHF m)**; columns MUST be drawn **edge-to-edge** so total chart width ≈ total sales (a thin separator between columns is permitted).
- **FR-004**: The **height axis** MUST encode **% of buying-group sales (0–100)**; each column's slices MUST sum to 100%.
- **FR-005**: Each Rep. Product Line MUST have a **consistent colour across all buying groups**, with a legend; slices **≥ the label threshold** MUST carry a value label.

**Axes & labelling**
- **FR-006**: The **X-axis** MUST list buying groups, each column labelled with the **buying-group name and its absolute sales (CHF m)**; the absolute sales value doubles as the explanation of the column width.
- **FR-007**: Buying groups SHOULD be ordered by **descending absolute sales** (largest first) so the portfolio reads left-to-right by size. *[default; configurable]*

**Narrative**
- **FR-008**: The comment box MUST state, per buying group, the **dominant Rep. Product Line and its share**, and MUST identify the **largest and smallest buying groups by absolute sales** — all deterministic.
- **FR-009**: The chart MUST support the message **"the product-line mix differs markedly across buying groups, and buying groups differ markedly in size"** (purpose: rank the portfolio on relative *and* absolute importance — Lever A1).

**Honesty / governance**
- **FR-010**: The basis MUST be stated explicitly on the chart/comment: segment = **Buying Group L6**, slice = **Rep. Product Line**. *(Both are real source fields — no proxy substitution.)*
- **FR-011**: Handling of negative within-group shares MUST be defined. *[NEEDS CLARIFICATION: floor-to-0, drop, or show as-is?]*
- **FR-012**: Every figure MUST be reproducible from source; **no language model may produce any number**. Exact inputs MUST be persisted (`data.csv` / `data.xlsx`).

### Key Entities
- **Buying Group** (`Buying Group L6`): a column; carries **total sales (CHF m) → column width** and a within-group product-line distribution summing to 100% → column height.
- **Rep. Product Line**: a stack slice; its height is its % share of a given buying group's sales, its colour is consistent across buying groups.

---

## Review & Acceptance Checklist

### Content Quality
- [x] No prescribed plotting-library internals (engine interchangeable)
- [x] Focused on decision value to GF and why
- [x] Written for a business + analytics audience
- [x] All mandatory sections completed

### Requirement Completeness
- [ ] One `[NEEDS CLARIFICATION]` remains (FR-011: negative within-segment share handling)
- [x] Requirements are testable against the rendered chart + `data.csv`
- [x] **Marimekko geometry (width ∝ buying-group sales) is explicit and testable** (FR-003, scenario 2)
- [x] Height axis (% of buying group), 100%-stack and labelling rule are unambiguous
- [x] Basis (Buying Group L6 × Rep. Product Line) is stated and uses real source fields
- [x] "No-LLM-numbers" governance stated

---

## Notes / Dependencies
- **Plan change required** (`PLAN_D`): `segment_field` → `"Buying Group L6"`, `stack_field` → `"Rep. Product Line"`
  (both present in `PRODUCT_RENAME`). Update the title/subtitle to "buying group" wording.
- **Renderer change required**: the current `chart_D()` draws **equal-width** bars (`width=0.55`).
  To meet FR-003 it MUST scale column widths to `buying-group total sales (CHF m)` and draw them
  edge-to-edge — the same Marimekko geometry already used by `chart_A()` (`edges = cumsum(widths)`,
  `centers`, thin `gap`). Reuse that pattern: widths from `piv.sum(axis=0)/1e6`, X ticks at column
  centres labelled `"{buying_group}\n(CHF {total:.0f} m)"`. Optionally roll up small buying groups
  into "Others" (cf. `others_max_share` in `chart_A()`).