"""
GF BFS - Chart Generation
=========================
Generates all Helbling-style charts from the gold layer data, using specs
from demos/charts/chart-*/spec.md files.

Each spec.md is parsed to create a render plan, which is then executed
deterministically using pandas and matplotlib. Chart structure is determined
by the LLM (if available), but all numbers are computed deterministically by
pandas from the source data.

Run:  python src/charts.py
Exit codes:
  0 = Success
  1 = Error during chart generation
  2 = Missing gold layer data (run pipeline.py first)
"""

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def check_gold_layer():
    gold_dir = os.path.join(REPO, "data", "gold")
    if not os.path.exists(gold_dir):
        return False
    return True


def main():
    print("\n" + "="*70)
    print("GF BFS - Chart Generation")
    print("="*70)
    if not check_gold_layer():
        print("\n[ERROR] Gold layer not found at data/gold/")
        print("Run the data pipeline first: python src/pipeline.py")
        sys.exit(2)
    analysis_script = os.path.join(HERE, "analysis.py")
    print("\nGenerating spec-driven charts...")
    try:
        result = subprocess.run(
            [sys.executable, analysis_script],
            cwd=REPO,
            check=False
        )
        if result.returncode != 0:
            print(f"\n[ERROR] Spec-driven chart generation failed with exit code {result.returncode}")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Spec-driven chart generation exception: {e}")
        sys.exit(1)
    matrix_script = os.path.join(HERE, "chart_customer_matrix.py")
    print("\nGenerating customer matrix chart...")
    try:
        result = subprocess.run(
            [sys.executable, matrix_script],
            cwd=REPO,
            check=False
        )
        if result.returncode != 0:
            print(f"\n[ERROR] Customer matrix chart generation failed with exit code {result.returncode}")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Customer matrix chart generation exception: {e}")
        sys.exit(1)
    print("\n" + "="*70)
    print("SUCCESS: All charts generated")
    print("="*70)
    print(f"\nOutputs:")
    print(f"  Spec-driven charts: demos/charts/chart-<name>/")
    print(f"  Customer matrix:    demos/charts/chart-customer_matrix/")
    print()


if __name__ == "__main__":
    main()
