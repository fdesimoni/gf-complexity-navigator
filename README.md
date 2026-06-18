# GF Complexity Navigator

Deterministic Python pipeline for complexity & profitability analysis. All figures computed with pandas — no LLM involved.

## Repository layout

```
gf-complexity-navigator/
├── README.md
├── requirements.txt
├── .env.example
├── input/                 ← source Excel files (git-ignored)
├── src/                   ← pipeline scripts
│   ├── build_bronze.py
│   ├── build_silver.py
│   ├── build_gold.py
│   ├── pipeline.py
│   ├── analysis.py
│   └── build_audit.py
├── data/                  ← medallion layers (git-ignored)
│   ├── bronze/
│   ├── silver/
│   └── gold/
├── demos/                 ← outputs
└── approach/              ← documentation
```


## Setup

```powershell
pip install -r requirements.txt
# optional: pip install jupyterlab ipykernel
```

Copy GF source files to `input/` and `.env.example` to `.env`.

## Quickstart

```powershell
python src/build_bronze.py
python src/build_silver.py
python src/build_gold.py
python src/pipeline.py
python src/analysis.py
```

## Pipeline

| Script | Purpose |
|--------|---------|
| `build_bronze.py` | Load & type-coerce Excel data |
| `build_silver.py` | Clean & deduplicate |
| `build_gold.py` | Enrich for analysis |
| `pipeline.py` | Complexity vs. value analysis, clusters, fact sheets |
| `analysis.py` | Generate Helbling-style charts |
| `build_audit.py` | Audit trail |

