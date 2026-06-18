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
python src/pipeline.py
python src/charts.py
```

## Pipeline

| Script | Purpose |
|--------|---------|
| `pipeline.py` | Run the data processing pipeline |
| `analysis.py` | Generate Helbling-style charts |