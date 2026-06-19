# Data Quality Demo Guide

## Overview

A complete **data quality assessment notebook** (`notebooks/B_data_quality.ipynb`) has been created to systematically identify and visualize data quality issues in the input data for demo purposes.

---

## What's Included

### 1. Notebook: `B_data_quality.ipynb`

A Jupyter notebook that walks through data quality issues interactively:

**Structure:**
- **Section 1–2**: Setup & data loading from silver layer
- **Section 3**: **DQ Scorecard** — one-page overview of all issues (horizontal bar chart)
- **Section 4**: **Missing Data Deep Dives** (4 charts)
- **Section 5**: **Faulty/Implausible Data** (3 charts)
- **Section 6**: **Master Data Issues** (2 analyses)
- **Section 7**: **Combined Impact Summary**
- **Section 8**: Export to CSV/XLSX

### 2. Generated HTML Charts

Running the notebook produces 8 interactive Vega-Lite HTML charts:

| Chart | File | Content |
|-------|------|---------|
| DQ Scorecard | `dq_scorecard.html` | Overview of all issues, colored by severity |
| Missing Buying Group | `dq_missing_buying_group.html` | Pie chart: product rows with/without buying_group_l6 |
| Missing Gross Profit | `dq_missing_gp.html` | Stacked bar by business_unit showing GP completeness |
| Missing Booked Dates | `dq_missing_dates.html` | Temporal distribution of missing dates by year |
| Coverage Gap | `dq_coverage_gap.html` | Timeline showing product (2021–2026) vs customer (2025–2026) |
| Negative GP | `dq_negative_gp.html` | Side-by-side comparison of negative GP lines |
| Cost Without Sales | `dq_cost_without_sales.html` | Anomalous booking patterns per table |
| Zero/Negative Sales | `dq_zero_sales.html` | Returns/credits/rebates distribution by region |
| Customer ID Ambiguity | `dq_customer_id_ambiguity.html` | Cardinality check: how many distinct names/groups/numbers |

### 3. Export Files

The notebook produces:
- **dq_report.csv** — DQ summary table (Issue, Table, Rows Affected, %, Severity, Category)
- **dq_report.xlsx** — Same data in Excel format

---

## How to Run

### Prerequisites
```bash
# Ensure silver layer data is current
python src/pipeline.py
```

### Run the Notebook
```bash
# In Jupyter
jupyter notebook notebooks/B_data_quality.ipynb

# Or via command line
jupyter nbconvert --to notebook --execute notebooks/B_data_quality.ipynb
```

### Expected Execution Time
~2–3 minutes (reading 115k customer + 37k product rows, rendering 8 interactive charts).

---

## Demo Flow

**For a 10-minute demo, use this sequence:**

1. **Slide 0 — Title** (30 sec)
   - "Data Quality Assessment: What Issues Exist?"

2. **Slide 1 — Scorecard** (3 min)
   - Open `dq_scorecard.html`
   - Highlight severity: red (>10%), orange (5–10%), blue (<5%)
   - **Key message:** ~15 distinct DQ issues identified across customer & product data

3. **Slide 2 — Missing Data** (3 min)
   - Show `dq_missing_buying_group.html` + `dq_missing_gp.html`
   - **Insight:** ~5% of products missing buying_group_l6 (blocks customer-product linkage)
   - **Insight:** ~10% of products missing gross profit (incomplete costing)

4. **Slide 3 — Coverage Mismatch** (1 min)
   - Show `dq_coverage_gap.html`
   - **Key message:** Customer data is 2025–2026; Product data is 2021–2026 → only 2 years overlap

5. **Slide 4 — Faulty Data** (2 min)
   - Show `dq_negative_gp.html`
   - **Insight:** 12.3% of customer rows have negative GP (value-destroying transactions)
   - **Context:** These are flagged, not dropped — they reveal where to investigate

6. **Slide 5 — Master Data Mess** (1 min)
   - Show `dq_customer_id_ambiguity.html`
   - **Key message:** No unique customer ID; consolidation relies on fuzzy matching (risky)

7. **Wrap-up** (30 sec)
   - "Data is usable, not decision-grade. Phase-1 work: define proper master data keys & fix linkage."

---

## Key Metrics for the Demo

| Issue | Count | % Affected | Severity |
|-------|-------|-----------|----------|
| Negative GP (Customer) | 14,259 | 12.3% | HIGH |
| Zero/Negative Sales (Customer) | 26,629 | 23.0% | HIGH |
| Missing Booked Date (Customer) | 23,252 | 20.1% | HIGH |
| Cost Without Sales (Customer) | 3,844 | 3.3% | MEDIUM |
| Missing Buying Group (Product) | 2,009 | 5.4% | MEDIUM |
| Missing Gross Profit (Product) | 3,889 | 10.5% | MEDIUM |
| Cost Without Sales (Product) | 692 | 1.9% | MEDIUM |
| Negative GP (Product) | 3,235 | 8.8% | MEDIUM |
| Missing Currency (Customer) | 12 | 0.01% | LOW |
| Name Inconsistencies (Customer) | ~8 | <0.01% | LOW |

---

## Design Notes

### Chart Style
- Helbling color palette: BLUE, ORANGE, GREEN, RED, GREY
- Vega-Lite (declarative, interactive, exportable as PNG/SVG)
- Tooltips on hover for detailed exploration

### Data Source
- Silver layer (already cleaned & flagged by `src/build_silver.py`)
- No additional processing needed — flags are pre-computed
- DQ log (`_dq_log.csv`) used for scorecard baseline

### Demo Suitability
- **Beginner-friendly:** No statistical jargon, focus on counts and percentages
- **Executive-friendly:** Color-coded severity, clear "action items"
- **Technical-friendly:** Full transparency on where issues live (flag columns, row counts)

---

## Customization

To modify the demo:

1. **Change colors:** Edit `BLUE`, `ORANGE`, `GREEN`, `RED`, `GREY` at the top of the notebook
2. **Skip a chart:** Comment out the relevant cell (e.g., `Section 4c`)
3. **Add a new chart:** Copy any existing Vega-Lite spec and modify the data/encoding
4. **Export to PDF:** Use `vl_convert` to convert HTML to PDF:
   ```python
   import vl_convert as vlc
   vlc.vegalite_to_pdf(vl_spec=spec, output_path='chart.pdf')
   ```

---

## Troubleshooting

**Chart doesn't render in Jupyter:**
- Ensure `vl-convert-python>=1.3` is installed: `pip install vl-convert-python`

**Missing data files:**
- Run `python src/pipeline.py` to regenerate silver layer & DQ log

**UnicodeDecodeError when running:**
- Use UTF-8 encoding: `jupyter nbconvert --encoding utf-8 ...`

---

## Next Steps (Post-Demo)

**Phase-1 work (in order of priority):**
1. Define authoritative customer master (ID, name, legal entity, location)
2. Establish proper product hierarchy (L1–L6 buying groups, not reverse-engineered)
3. Create foreign-key constraints (customer_number → customer_group, product_id → buying_group_l6)
4. Backfill missing values (booked dates, gross profit) with rules, not nulls
5. Reconcile overlapping data ranges (make customer 2021–2026 if possible)

---

## Files Modified/Created

```
notebooks/
  B_data_quality.ipynb         [NEW - main notebook]
  dq_scorecard.html            [GENERATED]
  dq_missing_buying_group.html [GENERATED]
  dq_missing_gp.html           [GENERATED]
  dq_missing_dates.html        [GENERATED]
  dq_coverage_gap.html         [GENERATED]
  dq_negative_gp.html          [GENERATED]
  dq_cost_without_sales.html   [GENERATED]
  dq_zero_sales.html           [GENERATED]
  dq_customer_id_ambiguity.html[GENERATED]
  dq_report.csv                [GENERATED]
  dq_report.xlsx               [GENERATED]

DEMO_DATA_QUALITY_GUIDE.md     [THIS FILE - NEW]
```

---

**Author:** Claude Code  
**Date:** 2026-06-19  
**Status:** Ready for demo
