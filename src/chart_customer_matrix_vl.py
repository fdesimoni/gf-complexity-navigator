"""
GF BFS - Customer Matrix Chart (Vega-Lite Renderer)
====================================================
Vega-Lite declarative rendering for the customer complexity × profitability matrix.

Reads a computed customer matrix DataFrame and hydrates a Vega-Lite spec with data,
then exports to PNG and interactive HTML.

Spec can be:
- Static (vega_spec.json, default, offline-safe)
- LLM-generated (via Helbling router, if USE_LLM_SPEC=1 env var set)

Spec: demos/charts/chart-customer_matrix/vega_spec.json (fallback)
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

# LLM router (same env vars as analysis.py)
LLM_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api-chat.helbling.ch/llm").rstrip("/")
LLM_API_KEY = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY") or "not-used"
LLM_MODEL = os.environ.get("ANALYSIS_LLM_MODEL", "claude-sonnet-4-6")

VEGA_SCHEMA_DOC = """
You convert CHART CONTEXT into a valid Vega-Lite 5 JSON specification.
You control only visual structure: layers, mark types, encodings, colors, interactions.
You MUST NOT compute, invent, or output any data value or statistic.

Requirements for the spec you produce:
- "$schema": "https://vega.github.io/schema/vega-lite/v5.json"
- "layer" array with exactly 4 entries in this order:
    0: rect marks for quadrant background shading (data injected at runtime)
    1: rule marks for vertical reference lines at 40th/60th percentile
    2: rule marks for horizontal reference lines at 40th/60th percentile
    3: circle marks for scatter points (data injected at runtime)
- Layer 3 encoding MUST include:
    x: field "complexity_pct" (quantitative, domain [-5,105])
    y: field "profitability_pct" (quantitative, domain [-5,105])
    size: field "net_sales" (quantitative, range [50,650], no legend)
    color: field "quadrant" (nominal, domain/range left as empty arrays [])
    tooltip: Customer Group, profitability_pct (.1f), complexity_pct (.1f), net_sales (,.0f), quadrant
- Layer 0 encoding MUST use fields: x/x2 from "x1"/"x2", y/y2 from "y1"/"y2", color from "color" (identity scale)
- You MAY adjust: title text, axis titles, mark opacity/stroke, width/height, legend placement

Return ONLY the JSON object. No prose, no code fences.
"""


def _llm_messages(prompt, max_tokens=2000, timeout=60):
    """POST to Helbling router; raises on transport/HTTP error (caller handles fallback)."""
    import urllib.request
    import urllib.error

    body = json.dumps({
        "model": LLM_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        LLM_BASE_URL + "/v1/messages", data=body, method="POST",
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": LLM_API_KEY,
        })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")


def _extract_json(text):
    """Extract first {...} JSON object from text (tolerates stray prose or fences)."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in LLM reply")
    return json.loads(text[start:end + 1])


def _load_static_spec():
    """Load the hand-authored Vega-Lite skeleton from vega_spec.json (fallback)."""
    try:
        with open(SPEC_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise SystemExit(
            f"[ERROR] Failed to load fallback spec from {SPEC_PATH}\n        {e}"
        )


def generate_vega_spec_from_llm(chart_context):
    """
    Call the Helbling LLM router to produce a Vega-Lite 5 spec for the customer matrix.

    The LLM controls only visual structure (layers, encodings, mark types, colors).
    It never sees or emits data values — those are injected by render_customer_matrix_vl().

    Args:
        chart_context (dict): {
            "title":               str   — chart title
            "subtitle":            str   — one-line description
            "n_groups":            int   — number of customer groups
            "quadrant_thresholds": str   — e.g. "40th/60th percentile thresholds"
            "quadrant_names":      list  — 5 quadrant label strings
        }

    Returns:
        dict: Vega-Lite 5 spec with layer structure matching VEGA_SCHEMA_DOC.
              Falls back to _load_static_spec() on any error.
    """
    import urllib.error

    prompt = (
        VEGA_SCHEMA_DOC
        + "\n\n=== CHART CONTEXT ===\n"
        + f"Title: {chart_context.get('title', 'Customer Matrix')}\n"
        + f"Subtitle: {chart_context.get('subtitle', '')}\n"
        + f"Customer groups: {chart_context.get('n_groups', 'N')}\n"
        + f"Quadrant thresholds: {chart_context.get('quadrant_thresholds', '40th/60th percentile')}\n"
        + f"Quadrant names: {', '.join(chart_context.get('quadrant_names', []))}\n"
        + "=== END CONTEXT ===\nGenerate the Vega-Lite spec now."
    )

    try:
        raw = _llm_messages(prompt)
        spec = _extract_json(raw)
        # Validate required structure
        if spec.get("$schema", "").find("vega-lite") == -1:
            raise ValueError("spec missing valid $schema")
        if not isinstance(spec.get("layer"), list) or len(spec["layer"]) != 4:
            raise ValueError(f"expected 4 layers, got {len(spec.get('layer', []))}")
        print("  [customer_matrix] Vega-Lite spec generated by LLM router")
        return spec
    except (urllib.error.URLError, ValueError, json.JSONDecodeError, TimeoutError, OSError) as e:
        print(f"  [customer_matrix] LLM router unavailable ({e}); using static spec")
        return _load_static_spec()


def render_customer_matrix_vl(cm, use_llm=False):
    """
    Render customer matrix as Vega-Lite chart, export PNG + HTML.

    Args:
        cm (pd.DataFrame): computed customer matrix with columns:
            Customer Group, complexity_pct, profitability_pct, net_sales, quadrant, ...
        use_llm (bool): if True, generate spec via LLM router; else use static spec

    Outputs:
        - demos/charts/chart-customer_matrix/customer_matrix.png
        - demos/charts/chart-customer_matrix/customer_matrix.html
        - demos/charts/chart-customer_matrix/vega_spec.json (final hydrated spec)
    """
    # Step 1: Get Vega-Lite spec (LLM-generated or static)
    if use_llm:
        chart_context = {
            "title":               "Customer Groups: Complexity & Profitability Analysis",
            "subtitle":            "Each point = a customer group. Size ∝ net sales.",
            "n_groups":            len(cm),
            "quadrant_thresholds": "40th and 60th percentile on both axes",
            "quadrant_names":      list(QUAD_COLORS.keys()),
        }
        spec = generate_vega_spec_from_llm(chart_context)
    else:
        spec = _load_static_spec()

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
