# GF BFS — Complexity & Profitability Proof-of-Concept

Deterministic Python pipeline that turns GF's data exports into the
complexity/profitability analyses and the Helbling-style charts.
Every number is computed with pandas — **no language model touches a figure**.

## Repository layout

```
gf-complexity-navigator/
├── README.md                      ← this file
├── requirements.txt               ← Python dependencies
├── .env.example                   ← LLM configuration template
│
├── input/                         ← source data (immutable)
│   ├── Customer View.xlsx
│   └── Product View.xlsx
│
├── src/                           ← pipeline scripts
│   ├── build_bronze.py            ← raw Excel → typed Parquet
│   ├── build_silver.py            ← bronze → cleaned Parquet + DQ log
│   ├── build_gold.py              ← silver → analysis-ready Parquet
│   ├── pipeline.py                ← complexity vs. value matrices, decision clusters
│   ├── analysis.py                ← Helbling-style charts
│   ├── build_audit.py             ← audit trail generation
│   ├── build_customer_dimension.py ← fuzzy-matched customer master
│   └── generate_customer_mapping.py ← name canonicalization
│
├── notebooks/                     ← explorative Jupyter notebooks
│   └── explorer.ipynb
│
├── data/                          ← medallion architecture (git-ignored)
│   ├── bronze/                    ← raw layer (typed, no cleanup)
│   ├── silver/                    ← cleaned layer + DQ log
│   └── gold/                      ← analysis-ready layer
│
├── demos/                         ← generated demo artifacts
│   ├── demo_results.xlsx
│   ├── customer_analysis.xlsx
│   ├── product_analysis.xlsx
│   ├── customer_matrix.png
│   ├── product_matrix.png
│   ├── buying_group_sustainability.png
│   ├── customer_product_complexity.png
│   └── charts/
│       ├── chart-customer_abc/
│       ├── chart-customer_profit_and_margin/
│       ├── chart-product_cagr_margin/
│       ├── chart-product_group_sales_margin/
│       └── chart-product_split_segment/
│
├── docs/                          ← engineering documentation
│   ├── architecture.md
│   └── data-and-insights-summary.md
│
└── approach/                      ← business & design documents
    ├── approach_v2.md             ← the business approach this PoC supports
    ├── audit.md                   ← generated audit trail
    ├── medallion_design.md        ← data layer architecture
    └── playbook.md                ← operating manual
```

Paths are anchored to each script's own location, so you can run them from any
working directory — the scripts always read from `input/` and write under
`demos/` and `data/`.

## Prerequisites

- Python 3.10+ (developed on 3.12)
- Dependencies listed in `requirements.txt`

```powershell
pip install -r requirements.txt
pip install jupyterlab ipykernel        # optional: only for notebooks/explorer.ipynb
```

**Data setup**: Copy GF's source Excel files (`Customer View.xlsx`, `Product View.xlsx`) into the `input/` folder.
Copy `.env.example` to `.env` and (optionally) fill in your Anthropic API credentials.

## Quickstart: Run the Pipeline

From the repository root, follow this sequence to regenerate all outputs:

```powershell
# Build the data medallion (bronze → silver → gold)
python src/build_bronze.py
python src/build_silver.py
python src/build_gold.py

# Generate analyses and charts
python src/pipeline.py        # → demos/*.xlsx + demos/*.png
python src/analysis.py        # → demos/charts/
```

Each script is idempotent and can be re-run independently. The pipeline always
reads from `input/`, writes to `data/` (medallion layers), and outputs final
artifacts to `demos/`.

---

## The Data Pipeline

### Medallion Architecture

The pipeline uses a **three-layer medallion** design:
- **Bronze** (`data/bronze/`): Raw data from Excel, typed but uncleaned
- **Silver** (`data/silver/`): Cleaned data with quality flags and deduplication
- **Gold** (`data/gold/`): Analysis-ready data with enriched columns for charting

### Scripts & Their Outputs

| Script | Input | Output | Purpose |
|--------|-------|--------|---------|
| `build_bronze.py` | `input/*.xlsx` | `data/bronze/*.parquet` | Type-coerce and load |
| `build_silver.py` | `data/bronze/*.parquet` | `data/silver/*.parquet` + `_dq_log.csv` | Clean, deduplicate, flag issues |
| `build_gold.py` | `data/silver/*.parquet` | `data/gold/*.parquet` + `_gold_manifest.csv` | Enrich for analysis |
| `pipeline.py` | `data/silver/*.parquet` | `demos/*.xlsx` + `demos/*.png` | Complexity vs. value matrices, decision clusters, fact sheets |
| `analysis.py` | `data/gold/*.parquet` | `demos/charts/` | Helbling-style rendered charts |
| `build_audit.py` | `data/silver/_dq_log.csv` + `data/gold/_gold_manifest.csv` | `approach/audit.md` | Generate audit trail |

### `src/pipeline.py` — Complexity vs. Value Analysis

Scores every **Customer Group** and every **Rep. Product Line** on two axes:
- **Value**: profit + size
- **Complexity**: order count, small-order burden, margin leakage, region/unit fragmentation

Assigns each to a decision cluster:

| Cluster | Meaning |
|---------|---------|
| **Grow** | high value, low complexity |
| **Protect / Serve differently** | valuable but costly to serve |
| **Selective deprioritization** | low value, high complexity |
| **Simplify / steer** | marginal, simplify handling |
| **Monitor** | mid-field |

**Outputs** (`demos/`)
- `demo_results.xlsx` — DQ scans, customer matrix, product matrix, cluster summaries
- `customer_matrix.png`, `product_matrix.png` — value vs. complexity bubble charts
- `customer_fact_sheets.txt` — auto 1-page summaries (top 10 + 10 worst)

---

### `src/analysis.py` — Generate Helbling-style Charts

Re-creates charts in Helbling style (chart + comment box). Each chart is written to its own folder under
`demos/charts/`, together with the exact numbers.

| Chart | Folder | Description |
|-------|--------|-------------|
| **A** | `chart-product_group_sales_margin/` | Sales × margin per product group |
| **B** | `chart-product_cagr_margin/` | Product growth (CAGR) × margin |
| **C** | `chart-customer_abc/` | Customer ABC (Pareto) |
| **D** | `chart-product_split_segment/` | Product split by buying group (Marimekko) |
| **E** | `chart-customer_profit_and_margin/` | Customer profit & margin scatter |

Each chart folder contains:
- `spec.md` — feature specification (governs rendering rules)
- `<X>_<name>.png` — rendered chart
- `data.csv` / `data.xlsx` — exact numbers behind the chart

**Honesty & Governance**
- All numbers are deterministic (pandas only); no LLM touches a figure
- Chart *structure* is decided by querying the Helbling LLM router with the spec
- Router is optional; charts render offline with sensible defaults if unreachable
- "Latest full year" = 2024 (2026 is partial); CAGR uses full years 2021→2025
- Margin = consolidated gross profit / net sales

---

## Notes

- **No-LLM governance**: every figure is deterministic and reproducible from the
  source files. The exact inputs per chart are persisted as `data.csv`/`data.xlsx`.
- **Empty / partial inputs are handled gracefully**: if a source file has no
  usable rows (e.g. `Customer View.xlsx` with only a header), the dependent
  customer analyses are skipped with a console note instead of crashing — the
  product-based outputs still run.

