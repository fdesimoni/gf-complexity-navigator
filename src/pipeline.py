"""
GF BFS - Data Processing Pipeline Orchestrator
===============================================
Runs the complete medallion data pipeline in sequence:
  1. BRONZE: Raw Excel → Typed, standardized Parquet
  2. SILVER: Bronze → Cleaned, conformed Parquet + quality log
  3. GOLD:   Silver → Star schema (dimensions + facts)

Exit codes:
  0 = Success
  1 = Build failed
  2 = Missing input file (run with data in input/ directory)
"""

import os
import sys
import subprocess
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def run_stage(script_name, stage_name, stage_num):
    """Run a build stage and return True on success."""
    script_path = os.path.join(HERE, script_name)
    print(f"\n{'='*70}")
    print(f"STAGE {stage_num}: {stage_name}")
    print(f"{'='*70}")

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=REPO,
            check=False
        )
        if result.returncode != 0:
            print(f"\n[ERROR] {stage_name} failed with exit code {result.returncode}")
            return False
        return True
    except Exception as e:
        print(f"\n[ERROR] {stage_name} exception: {e}")
        return False


def check_inputs():
    """Verify input files exist."""
    input_dir = os.path.join(REPO, "input")
    required_files = [
        "Customer View.xlsx",
        "Product View.xlsx"
    ]
    missing = []
    for fname in required_files:
        fpath = os.path.join(input_dir, fname)
        if not os.path.exists(fpath):
            missing.append(fpath)
    return missing


def main():
    print("\n" + "="*70)
    print("GF BFS - Data Processing Pipeline")
    print("="*70)

    missing = check_inputs()
    if missing:
        print("\n[ERROR] Missing input files:")
        for fpath in missing:
            print(f"  {fpath}")
        print("\nCopy 'Customer View.xlsx' and 'Product View.xlsx' to input/")
        sys.exit(2)
    stages = [
        ("build_bronze.py", "BRONZE (Raw → Typed)"),
        ("build_silver.py", "SILVER (Cleaned + Conformed)"),
        ("build_gold.py", "GOLD (Star Schema)"),
    ]

    for i, (script, name) in enumerate(stages, 1):
        if not run_stage(script, name, i):
            sys.exit(1)
    print("\n" + "="*70)
    print("SUCCESS: Pipeline complete")
    print("="*70)
    print("\nOutputs:")
    print(f"  Bronze:     data/bronze/*.parquet")
    print(f"  Silver:     data/silver/*.parquet + _dq_log.csv")
    print(f"  Gold:       data/gold/dimensions/*.parquet + data/gold/fact/*.parquet")
    print()


if __name__ == "__main__":
    main()
