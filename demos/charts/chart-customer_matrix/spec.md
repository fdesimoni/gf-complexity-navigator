# Feature Specification: Customer Matrix — Complexity & Profitability Analysis

**Feature Branch**: `chart-customer_matrix`
**Created**: 2026-06-18
**Status**: Spec (ready for implementation)
**Artifact**: [`customer_matrix.png`](customer_matrix.png) · data in [`data.csv`](data.csv) / [`data.xlsx`](data.xlsx) · produced by [`pipeline.py`](../../../src/pipeline.py) → `customer_matrix()`
**Input**: "What is the complexity-vs-profitability profile of our customer base? Which customers are simple and profitable versus complex and unprofitable?"

## Purpose (Why This Chart Exists)

This chart enables **analysis of customer-group complexity and profitability as a 2D problem**. Each customer group is positioned on two independently-scored axes:
- **Profitability (Y)**: a blend of margin (gross profit) and volume (net sales)
- **Complexity (X)**: a weighted proxy capturing transaction load, order size, margin leakage, and geographic/organizational fragmentation

The simultaneous visualization answers: **Which customer groups are worth our operational effort?** Are high-profit customers also expensive to serve? Are low-profit customers dragging down margins with complexity overhead? This 2D view is fundamental to portfolio decisions: customer segmentation, pricing models, account management resource allocation, and operational design (e.g., "should this customer be on self-service or dedicated support?").

---

## ⚡ Quick Guidelines

- ✅ Focus on WHAT the chart must communicate to GF management and WHY
- ✅ Written for a business + analytics audience (a GF steering committee)
- ❌ Avoid prescribing plotting-library internals; the engine is interchangeable
- 🔒 Every figure is deterministic and traceable to source; no language model touches a number

---

## User Scenarios & Testing

### Primary User Story
As a **GF decision-maker**, I want to see the **profitability and complexity profile of each customer group simultaneously** — plotted as a 2D matrix where each customer is a point — so that I can identify which customers are strategically attractive (high profit, low complexity), which are valuable but operationally costly (high profit, high complexity), and which are candidates for portfolio rationalization (low profit, high complexity).

### Acceptance Scenarios
1. **Given** customer groups and their profitability/complexity scores, **When** the chart renders, **Then** each customer group is plotted as a **point on a 2D grid** where **X = complexity percentile (0–100)** and **Y = profitability percentile (0–100)**.
2. **Given** two customer groups with different profitability but same complexity, **When** rendered, **Then** they appear **vertically aligned** with the higher-profitability customer **above** the lower-profitability one.
3. **Given** the 2D scatter, **When** a reviewer reads the comment box, **Then** the **count of customer groups in each quadrant** (high-profit/low-complexity, high-profit/high-complexity, low-profit/low-complexity, low-profit/high-complexity, and center) are derivable.
4. **Given** the rendered chart, **When** a reviewer examines a labeled customer group, **Then** the **profitability components (gross profit, net sales)** and **complexity drivers (order frequency, average order value, margin leakage, fragmentation)** are all traceable in the exported `data.csv` / `data.xlsx`.
5. **Given** outlier customer groups (e.g., a single huge order, or a geographically fragmented customer with high margin leakage), **When** plotted, **Then** they remain **readable and clearly positioned** in their respective quadrants.

### Edge Cases
- Customer groups with zero or negative gross profit → included in analysis (they rank low on profitability but may be valuable for volume or strategic reasons; complexity score is still computed).
- Ties in profitability or complexity → stable rank order (pandas `rank()` uses "average" method by default; ties share the same percentile).
- A customer group with very high order frequency but only one large order → both drivers are captured (frequency contributes separately from order-value proxy).
- Geographic spread (regions + sales units) as a fragmentation proxy → a customer spread across 5 regions + 3 sales units counts as "8 fragments"; this is a simplifying proxy and may be refined in Phase 2.

---

## Requirements

### Functional Requirements

**Data & Scope**
- **FR-001**: The chart MUST analyze **Customer Groups** (aggregation grain), computing profitability and complexity scores deterministically from raw transaction data (`customer.parquet` silver layer).
- **FR-002**: Analysis MUST include all customer groups in the source data (no pre-filter on profitability; negative-GP groups are included).
- **FR-003**: Each customer group's scores MUST be **reproducible and traceable** — input components (`gross_profit`, `net_sales`, `orders`, `avg_order_value`, `neg_line_share`, `regions`, `sales_units`) MUST be exported in `data.csv` / `data.xlsx`.

**Profitability Score (Value Axis)**
- **FR-004**: Profitability MUST be computed as: `profitability_raw = percentile_rank(gross_profit) × 0.6 + percentile_rank(net_sales) × 0.4`, where `percentile_rank()` is the 0–100 percentile rank of each component.
- **FR-005**: The final **profitability percentile** (0–100) MUST be `percentile_rank(profitability_raw)`, placing each customer on a comparable 0–100 scale.
- **FR-006**: Gross profit (60% weight) reflects **margin generation**; net sales (40% weight) reflects **business volume**. Both are in local currency aggregated per customer group.

**Complexity Score (Complexity Axis)**
- **FR-007**: Complexity MUST be computed as a weighted blend of four independent proxy metrics:
  - **Order Frequency (30%)**: `percentile_rank(count of distinct sales orders per customer group)` — transaction load and order-processing overhead.
  - **Small-Order Burden (30%)**: `percentile_rank(−average order value per customer group)` — inverse AOV so that small-order customers rank high on complexity; high AOV customers rank low.
  - **Margin Leakage (20%)**: `percentile_rank(share of transaction lines with negative gross profit per customer group)` — signals miscosted products, bundled losses, or poor margin management.
  - **Fragmentation (20%)**: `percentile_rank(count of distinct regions + count of distinct sales units per customer group)` — geographic and organizational spread = logistics and coordination complexity.
- **FR-008**: `complexity_raw = (order_freq_pct × 0.30) + (small_order_burden_pct × 0.30) + (margin_leakage_pct × 0.20) + (fragmentation_pct × 0.20)`.
- **FR-009**: The final **complexity percentile** (0–100) MUST be `percentile_rank(complexity_raw)`.
- **FR-010**: Each proxy MUST be documented in the comment box (rationale for 4-proxy blend, not just a black-box score).

**Axes & Plot Geometry**
- **FR-011**: The **X-axis** MUST encode **complexity percentile (0–100)**, with 0 = least complex, 100 = most complex.
- **FR-012**: The **Y-axis** MUST encode **profitability percentile (0–100)**, with 0 = least profitable, 100 = most profitable.
- **FR-013**: Each customer group MUST be plotted as a **point** at coordinates `(complexity_pct, profitability_pct)`.
- **FR-014**: The plot area MUST include **gridlines or visual markers at the 40th and 60th percentiles** on both axes to make quadrant boundaries clear (FR-016).

**Quadrant Classification**
- **FR-015**: Quadrants MUST be defined by the **60th and 40th percentile thresholds** on both axes:
  - **Top-left (High Profit, Low Complexity)**: `profitability_pct ≥ 60` AND `complexity_pct < 40`.
  - **Top-right (High Profit, High Complexity)**: `profitability_pct ≥ 60` AND `complexity_pct ≥ 60`.
  - **Bottom-left (Low Profit, Low Complexity)**: `profitability_pct < 40` AND `complexity_pct < 40`.
  - **Bottom-right (Low Profit, High Complexity)**: `profitability_pct < 40` AND `complexity_pct ≥ 60`.
  - **Center (Mid-range)**: All others — neither clearly high nor low on both axes.
- **FR-016**: Quadrants MUST be **visually distinguished** (shading, color coding, or border markers) so a reviewer can instantly identify which customer group falls where.

**Point Encoding & Labeling**
- **FR-017**: Each point's **size or opacity MAY encode net sales** (larger/brighter = higher sales) to provide a third dimension of business volume without cluttering the primary 2D analysis.
- **FR-018**: **Labeling rule**: customer groups MUST be labeled if they are **(a) in the top-N by net sales (default: top 10), or (b) in top-3 per quadrant, or (c) statistical outliers** (e.g., highest complexity, lowest profitability). Smaller/mid-range customer groups MAY be left unlabeled for readability.
- **FR-019**: Labels MUST show the **customer group name** and, optionally, net sales or profitability/complexity values (trade-off: readability vs. information density).

**Narrative & Comment Box**
- **FR-020**: The comment box MUST state:
  - **Total customer groups** analyzed.
  - **Count of customer groups in each quadrant** (top-left, top-right, bottom-left, bottom-right, center).
  - **Top 3 customer groups per quadrant** (by net sales) — so the reader knows which customer groups exemplify each profile.
  - **Extreme cases**: highest profitability, lowest profitability, highest complexity, lowest complexity (by customer group name and value).
  - **Brief rationale** for the 4-proxy complexity blend (order frequency, small-order burden, margin leakage, fragmentation) so the reader understands what "complexity" means in this context.
- **FR-021**: All figures in the comment box MUST be deterministic and derived directly from `data.csv` / `data.xlsx`; no language model generates any number.

**Honesty & Governance**
- **FR-022**: The chart MUST clearly state the **analysis grain is Customer Group** (configurable to finer grain, e.g., Customer ID, if desired, but must be declared).
- **FR-023**: The **profitability formula (60% margin, 40% volume)** and **complexity formula (4-proxy blend)** MUST be stated on the chart or in a legend/subtitle so a reviewer understands the scoring approach.
- **FR-024**: Every figure — gross profit, net sales, order counts, avg order value, margin leakage, fragmentation — MUST be **reproducible from source**; exact inputs MUST be persisted in `data.csv` / `data.xlsx`.
- **FR-025**: No language model may produce any number on the chart. All values are deterministic SQL/pandas aggregations from `customer.parquet` (silver layer).

### Key Entities
- **Customer Group**: the unit of analysis; carries gross profit, net sales, order frequency, avg order value, margin leakage, fragmentation, profitability percentile, complexity percentile, and quadrant assignment.
- **Quadrant**: defined by 40th/60th percentile thresholds; classifies customer groups into 5 regions (4 corners + center).
- **Profitability Score**: blend of gross profit (60%) and net sales (40%), then percentile-ranked.
- **Complexity Score**: weighted blend of 4 proxies (order frequency 30%, small-order burden 30%, margin leakage 20%, fragmentation 20%), then percentile-ranked.

---

## Execution Flow (main)

```
1. Load customer data (customer.parquet silver layer, rename to Excel display names)
2. Group by Customer Group; aggregate:
   - gross_profit = sum(Consolidated Gross Profit LC)
   - net_sales = sum(Net Sales LC)
   - orders = count(distinct Sales Order Number)
   - avg_order_value = net_sales / orders
   - neg_line_share = mean(Consolidated Gross Profit LC < 0)
   - regions = count(distinct Region)
   - sales_units = count(distinct Sales Unit)
3. Compute profitability score:
   - profitability_raw = pct_rank(gross_profit) × 0.6 + pct_rank(net_sales) × 0.4
   - profitability_pct = pct_rank(profitability_raw)  [0–100]
4. Compute complexity score:
   - order_freq_pct = pct_rank(orders)
   - small_order_burden_pct = pct_rank(−avg_order_value)
   - margin_leakage_pct = pct_rank(neg_line_share)
   - fragmentation_pct = pct_rank(regions + sales_units)
   - complexity_raw = (order_freq_pct × 0.30) + (small_order_burden_pct × 0.30) 
                    + (margin_leakage_pct × 0.20) + (fragmentation_pct × 0.20)
   - complexity_pct = pct_rank(complexity_raw)  [0–100]
5. Classify quadrant: per customer group, assign to one of 5 regions based on thresholds (60/40) on profitability_pct and complexity_pct
6. Render 2D scatter plot:
   - X-axis = complexity_pct (0–100)
   - Y-axis = profitability_pct (0–100)
   - Points = customer groups (color by quadrant, size ∝ net_sales)
   - Gridlines / reference at 40th/60th percentiles on both axes
7. Label customer groups per FR-018 (top-N by sales, top-3 per quadrant, outliers)
8. Derive comment-box insights per FR-020:
   - Quadrant distribution
   - Top customer groups per quadrant (by net sales)
   - Extreme cases (highest/lowest profitability & complexity)
   - Rationale for complexity blend
9. Export data:
   - `data.csv` / `data.xlsx`: one row per customer group with all components
     (gross_profit, net_sales, orders, avg_order_value, neg_line_share, regions, sales_units, 
      profitability_raw, profitability_pct, complexity_raw, complexity_pct, quadrant)
10. Run review checklist → mark any [NEEDS CLARIFICATION]
```

---

## Review & Acceptance Checklist

### Content Quality
- [x] No prescribed plotting-library internals (engine interchangeable)
- [x] Focused on decision value to GF and why (portfolio analysis: profitability + complexity)
- [x] Written for a business + analytics audience
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No `[NEEDS CLARIFICATION]` markers remain
- [x] Requirements are testable against the rendered chart + `data.csv`
- [x] Both axes (profitability & complexity percentiles), quadrant thresholds (60/40), and labeling rule are unambiguous
- [x] Profitability formula (60% gross profit, 40% net sales) is explicit
- [x] Complexity formula (4-proxy blend: 30% order frequency, 30% small-order burden, 20% margin leakage, 20% fragmentation) is explicit and justified
- [x] Quadrant boundaries and classification are deterministic
- [x] Analysis grain (Customer Group) is stated
- [x] "No-LLM-numbers" governance stated and enforced

### Dependencies & Notes
- **Data source**: `src/pipeline.py` → `customer_matrix()` function (lines 181–239).
- **Silver layer input**: `customer.parquet` (pre-aggregated by transformation pipeline `build_silver.py`).
- **Output format**: Export to `data.csv` and `data.xlsx` with all input components and derived scores.
- **Future refinement (Phase 2)**: Replace fragmentation proxy (regions + sales units count) with actual order fulfillment cost or customer service cost data if available.
