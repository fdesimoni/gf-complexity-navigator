"""
GF BFS - Customer Matrix Chart (Vega-Lite Renderer)
====================================================
Vega-Lite declarative rendering for the customer complexity × profitability matrix.

Reads a computed customer matrix DataFrame and hydrates a Vega-Lite spec with data,
then exports to PNG and interactive HTML.

Spec: demos/charts/chart-customer_matrix/vega_spec.json
Run:  python src/chart_customer_matrix.py (via main() in chart_customer_matrix.py)
"""
import os
import json

try:
    import vl_convert as vlc
except ImportError:
    vlc = None

# Paths anchored to this script
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SPEC_PATH = os.path.join(REPO, "demos", "charts", "chart-customer_matrix", "vega_spec.json")
OUT_DIR = os.path.join(REPO, "demos", "charts", "chart-customer_matrix")

# Helbling palette
QUAD_COLORS = {
    "Top-left (High Profit, Low Complexity)": "#2e7d32",     # GREEN
    "Top-right (High Profit, High Complexity)": "#1f4e79",   # BLUE
    "Bottom-left (Low Profit, Low Complexity)": "#ed7d31",   # ORANGE
    "Bottom-right (Low Profit, High Complexity)": "#c0392b", # RED
    "Center (Mid-range)": "#a6a6a6",                         # GREY
}

# Quadrant background shading (x1, x2, y1, y2 bounds + color)
QUAD_BG = [
    {"x1": 0, "x2": 40, "y1": 60, "y2": 100, "color": "#e2efda"},    # Top-left (green bg)
    {"x1": 60, "x2": 100, "y1": 60, "y2": 100, "color": "#e7f0f7"},  # Top-right (blue bg)
    {"x1": 0, "x2": 40, "y1": 0, "y2": 40, "color": "#fff2cc"},      # Bottom-left (yellow bg)
    {"x1": 60, "x2": 100, "y1": 0, "y2": 40, "color": "#f8dcdb"},    # Bottom-right (red bg)
]


def render_customer_matrix_vl(cm):
    """
    Render customer matrix as Vega-Lite chart, export PNG + HTML.

    Args:
        cm (pd.DataFrame): computed customer matrix with columns:
            Customer Group, complexity_pct, profitability_pct, net_sales, quadrant, ...

    Outputs:
        - demos/charts/chart-customer_matrix/customer_matrix.png
        - demos/charts/chart-customer_matrix/customer_matrix.html
        - demos/charts/chart-customer_matrix/vega_spec.json (final hydrated spec)
    """
    # Step 1: Load Vega-Lite spec skeleton
    try:
        with open(SPEC_PATH, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise SystemExit(
            f"[ERROR] Failed to load Vega-Lite spec from {SPEC_PATH}\n"
            f"        {e}\n"
            f"        Ensure demos/charts/chart-customer_matrix/vega_spec.json exists."
        )

    # Step 2: Inject data into spec layers
    # Layer 0: quadrant background shading (rect marks)
    spec["layer"][0]["data"]["values"] = QUAD_BG

    # Layer 1: reference gridlines (vertical rules at 40/60)
    # Already has correct data structure, keep it

    # Layer 2: reference gridlines (horizontal rules at 40/60)
    # Already has correct data structure, keep it

    # Layer 3: scatter points (customer groups)
    spec["layer"][3]["data"]["values"] = cm.to_dict(orient="records")

    # Step 3: Set color domain/range for quadrants
    quad_domain = list(QUAD_COLORS.keys())
    quad_range = list(QUAD_COLORS.values())
    spec["layer"][3]["encoding"]["color"]["scale"]["domain"] = quad_domain
    spec["layer"][3]["encoding"]["color"]["scale"]["range"] = quad_range

    # Step 4: Export PNG via vl-convert
    if vlc is None:
        raise SystemExit(
            "[ERROR] vl-convert-python is not installed.\n"
            "        Run: pip install vl-convert-python>=1.3"
        )

    try:
        png_bytes = vlc.vegalite_to_png(vl_spec=json.dumps(spec), scale=2)
        chart_path = os.path.join(OUT_DIR, "customer_matrix.png")
        with open(chart_path, "wb") as f:
            f.write(png_bytes)
        print(f"  chart saved: {chart_path}")
    except Exception as e:
        print(f"  [WARNING] PNG export failed ({e}); skipping PNG output")

    # Step 5: Export interactive HTML
    try:
        html = vlc.vegalite_to_html(vl_spec=json.dumps(spec))
        html_path = os.path.join(OUT_DIR, "customer_matrix.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  interactive HTML: {html_path}")
    except Exception as e:
        print(f"  [WARNING] HTML export failed ({e}); skipping HTML output")

    # Step 6: Export final hydrated spec (for auditing + debugging)
    try:
        spec_path = os.path.join(OUT_DIR, "vega_spec.json")
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
        print(f"  spec exported: {spec_path}")
    except Exception as e:
        print(f"  [WARNING] spec export failed ({e})")


if __name__ == "__main__":
    # Quick test: load sample data and render
    import sys
    import pandas as pd

    # This is mainly for debugging; normal usage is via chart_customer_matrix.py
    print("[DEBUG] chart_customer_matrix_vl.py loaded but not meant to run standalone.")
    print("        Use: python src/chart_customer_matrix.py")
    sys.exit(0)
