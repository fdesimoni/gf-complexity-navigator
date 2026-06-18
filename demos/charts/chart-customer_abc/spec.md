# Feature Specification: Customer ABC / Pareto Analysis

**Feature Branch**: `chart-customer_abc`
**Created**: 2026-06-11
**Status**: Implemented (proof-of-concept)
**Artifact**: [`C_customer_abc.png`](C_customer_abc.png) · data in [`data.csv`](data.csv) / [`data.xlsx`](data.xlsx) · produced by [`analysis.py`](../../../analysis.py) → `chart_C()`
**Mirrors**: GF `Auswertung.pdf` chart 8
**Input**: "80% of margin is generated with {N} of {total} customers" — cumulative margin Pareto curve

## Execution Flow (main)

```
1. Load customer data (Customer View.xlsx)
2. Group by Customer Group; sum Consolidated Gross Profit (margin); keep groups with margin > 0; sort descending
3. Compute cumulative margin share (%) over customers ranked by margin
4. Determine A/B/C cut-offs: A = up to 80% cum, B = up to 95% cum, C = remainder
5. Plot cumulative-margin curve; shade A/B/C bands; mark 80% and 95% reference lines
6. Derive A/B/C counts and top-customer margin shares into comment box
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
As a **GF decision-maker**, I want to see how concentrated **margin** is across customer groups — how few customers make up 80% and 95% of gross profit — so that I can size the dependency on a handful of large distributors and target account strategy accordingly.

### Acceptance Scenarios
1. **Given** customer groups ranked by margin, **When** the chart renders, **Then** the Y-axis shows **cumulative margin %** rising from the largest customer to 100%.
2. **Given** the cumulative curve, **When** it crosses 80% and 95%, **Then** **A** (≤80%) and **B** (≤95%) cut-offs are marked and the A / B / C bands are shaded distinctly.
3. **Given** the rendered chart, **When** a reviewer reads the comment box, **Then** the A-count and its % of customers, B-count, C-count and top-customer margin shares are all derivable.
4. **Given** the curve's steep early rise, **Then** the chart visibly communicates **extreme concentration** (few customers, most of the margin).

### Edge Cases
- Customer groups with Gross Profit ≤ 0 (loss-making / credits) → **excluded** before ranking.
- Ties in margin → stable rank order, cut-offs computed on cumulative share.
- A very long C tail (1,500+ groups) → must remain readable (curve flat near 100%).

---

## Requirements

### Functional Requirements

**Data & scope**
- **FR-001**: The chart MUST rank **Customer Groups** by Consolidated Gross Profit (margin) descending, including only groups with **margin > 0**.
- **FR-002**: Each customer's cumulative contribution MUST be expressed as a **percentage of total margin**.

**Axes & encodings**
- **FR-003**: The **X-axis** MUST encode the **number of customers, ranked by margin** (1 = largest).
- **FR-004**: The **Y-axis** MUST encode **cumulative margin %** (0–100).
- **FR-005**: The curve MUST be monotonically non-decreasing and reach 100% at the last customer.

**ABC segmentation**
- **FR-006**: The chart MUST derive cut-offs: **A** = customers up to 80% cumulative margin, **B** = up to 95% cumulative margin, **C** = the remainder, and MUST shade these three bands distinctly.
- **FR-007**: Reference lines at **80%** and **95%** cumulative margin, and vertical markers at the A and B cut-offs, MUST be drawn.

**Narrative**
- **FR-008**: The comment box MUST state: total customer groups; A-count and its % of customers; B-count; C-count; and the top customers by margin share — all deterministic.

**Honesty / governance**
- **FR-009**: Grain MUST be stated as **Customer Group** (configurable to finer/coarser grain).
- **FR-010**: Every figure MUST be reproducible from source; **no language model may produce any number**. Exact inputs MUST be persisted (`data.csv` / `data.xlsx`).

### Key Entities
- **Customer Group**: the unit of analysis; carries total Consolidated Gross Profit (margin), margin rank, cumulative share, and an A/B/C class.
- **ABC class**: A (≤80% cum margin), B (≤95% cum margin), C (remainder).

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
- [x] Axes (customer rank / cumulative margin %), cut-offs and bands are unambiguous
- [x] Exclusion of margin ≤ 0 and grain are explicit
- [x] "No-LLM-numbers" governance stated