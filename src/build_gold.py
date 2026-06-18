"""
GF BFS - Star Schema: SILVER -> GOLD (Dimensional)
===================================================
Converts medallion silver layer into a star schema with dimensions and facts.

Builds:
  1. Dimension tables (Dim_Customer, Dim_Product, Dim_Geography, Dim_Time, Dim_BuyingGroup)
     - SCD Type 2 tracking (when dimensions change, old version is closed, new is opened)
  2. Unified Fact_Sales table with FK keys to all dimensions
  3. Denormalized compatibility layer (fact + current dimensions pre-joined)
     - For backward compatibility with analysis.py (zero chart code changes)

See approach/medallion_design.md and STAR_SCHEMA_CHART_IMPACT.md for design details.

Run:  python src/build_gold_star.py
Exit codes:  0 = OK   2 = missing silver input
"""

import os
import sys
import hashlib
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SILVER_DIR = os.path.join(REPO, "data", "silver")
GOLD_DIR = os.path.join(REPO, "data", "gold")
GOLD_DIM_DIR = os.path.join(GOLD_DIR, "dimensions")
GOLD_FACT_DIR = os.path.join(GOLD_DIR, "fact")

# FX rate for EUR -> CHF conversion (same as build_gold.py for consistency)
EUR_CHF_RATE = 0.93

# Extract date: treat today as the extract date for SCD tracking
EXTRACT_DATE = datetime.now().date()


def ensure_dirs():
    """Create gold layer directories."""
    os.makedirs(GOLD_DIM_DIR, exist_ok=True)
    os.makedirs(GOLD_FACT_DIR, exist_ok=True)


def _hash_row(row, cols):
    """Compute hash of row values for SCD change detection."""
    values = tuple(str(row.get(c, "")) for c in cols)
    return hashlib.md5(str(values).encode()).hexdigest()


# ============================================================================
# DIMENSION BUILDERS
# ============================================================================

def build_dim_time(customer_silver, product_silver):
    """
    Extract unique time periods from both views and create time dimension.

    Customer view: monthly grain (year, month)
    Product view: quarterly grain (year, quarter)
    """
    times = []
    if "year" in customer_silver.columns and "month" in customer_silver.columns:
        c_times = customer_silver[["year", "month"]].dropna().drop_duplicates()
        for _, row in c_times.iterrows():
            year = int(row["year"])
            month = int(row["month"])
            time_id = f"{year}{month:02d}"
            times.append({
                "time_id": time_id,
                "year": year,
                "month": month,
                "month_name": pd.Timestamp(year=year, month=month, day=1).strftime("%B"),
                "quarter": f"{year} Q{(month - 1) // 3 + 1}",
                "grain": "monthly",
            })
    if "quarter" in product_silver.columns:
        p_times = product_silver[["quarter"]].dropna().drop_duplicates()
        for _, row in p_times.iterrows():
            qtr = str(row["quarter"]).strip()
            parts = qtr.replace("Q", "").replace("-", " ").split()
            if len(parts) >= 2:
                year = int(parts[0])
                qnum = int(parts[1])
                time_id = f"{year}Q{qnum}"
                times.append({
                    "time_id": time_id,
                    "year": year,
                    "month": None,
                    "month_name": None,
                    "quarter": qtr,
                    "grain": "quarterly",
                })

    df = pd.DataFrame(times).drop_duplicates(subset=["time_id"])
    df = df.sort_values("time_id").reset_index(drop=True)
    print(f"  Dim_Time: {len(df)} rows")
    return df


def build_dim_geography(customer_silver, product_silver):
    """
    Extract unique geographies from both views (region + sub_region + business_unit).
    Sales_unit is extracted separately to Dim_SalesUnit.
    """
    geogs = []

    for source, data in [("customer", customer_silver), ("product", product_silver)]:
        if "region" in data.columns:
            cols = ["region"]
            if "sub_region" in data.columns:
                cols.append("sub_region")
            if "business_unit" in data.columns:
                cols.append("business_unit")

            geo_data = data[cols].dropna(how="all").drop_duplicates()
            for _, row in geo_data.iterrows():
                region = str(row.get("region", "")).strip()
                sub_region = str(row.get("sub_region", "")).strip() if "sub_region" in cols else None
                business_unit = str(row.get("business_unit", "")).strip() if "business_unit" in cols else None

                # Create geography key (WITHOUT sales_unit)
                geo_key = f"{region}|{sub_region}|{business_unit}"
                geogs.append({
                    "geography_id": geo_key,
                    "region": region if region else None,
                    "sub_region": sub_region if sub_region else None,
                    "business_unit": business_unit if business_unit else None,
                })

    df = pd.DataFrame(geogs).drop_duplicates(subset=["geography_id"])
    df = df.reset_index(drop=True)
    print(f"  Dim_Geography: {len(df)} rows")
    return df


def build_dim_sales_unit(customer_silver, product_silver):
    """
    Extract unique sales units from both views.
    Sales_unit is a distinct operational dimension (e.g., Germany vs Germany BT).
    """
    units = []

    for source, data in [("customer", customer_silver), ("product", product_silver)]:
        if "sales_unit" in data.columns:
            su_data = data[["sales_unit"]].dropna().drop_duplicates()
            for _, row in su_data.iterrows():
                sales_unit = str(row["sales_unit"]).strip()
                units.append({
                    "sales_unit_id": sales_unit,
                    "sales_unit": sales_unit,
                })

    df = pd.DataFrame(units).drop_duplicates(subset=["sales_unit_id"])
    df = df.reset_index(drop=True)
    print(f"  Dim_SalesUnit: {len(df)} rows")
    return df


def build_dim_buying_group(customer_silver, product_silver):
    """
    Extract unique buying groups from both views.
    """
    groups = []

    for source, data in [("customer", customer_silver), ("product", product_silver)]:
        if "buying_group_l6" in data.columns:
            bg_data = data[["buying_group_l6"]].dropna().drop_duplicates()
            for _, row in bg_data.iterrows():
                bg = str(row["buying_group_l6"]).strip()
                groups.append({
                    "buying_group_id": bg,
                    "buying_group_l6": bg,
                    "is_missing": False,
                })

    # Add a special "UNCLASSIFIED" row for missing values
    groups.append({
        "buying_group_id": "[UNCLASSIFIED]",
        "buying_group_l6": "[UNCLASSIFIED]",
        "is_missing": True,
    })

    df = pd.DataFrame(groups).drop_duplicates(subset=["buying_group_id"])
    df = df.reset_index(drop=True)
    print(f"  Dim_BuyingGroup: {len(df)} rows")
    return df


def build_dim_customer(customer_silver):
    """
    Extract unique customers from customer silver.
    Uses the consolidation mapping from customer_dimension.csv to apply canonical names.
    SCD Type 2: track when customer name/group changed.

    For now (Phase 1), just create current versions (no historical tracking).
    """
    if "customer_id" not in customer_silver.columns:
        raise ValueError("customer_id column not found in silver")

    # Load consolidation mapping (same as build_silver.py)
    import os
    dim_file = os.path.join(HERE, "customer_dimension.csv")
    if not os.path.exists(dim_file):
        raise ValueError(f"customer_dimension.csv not found at {dim_file}")

    dim_mapping = pd.read_csv(dim_file)
    # Columns: customer_id, customer_name (original), sales_location_id, customer_name (consolidated), is_missing
    canonical_names = {}
    for _, row in dim_mapping.iterrows():
        cid = row['customer_id']
        canonical_name = row.iloc[3]  # 4th column = consolidated customer_name
        canonical_names[cid] = canonical_name

    # Unique customers: keep first occurrence per customer_id, but use canonical names
    cust_data = customer_silver[[
        "customer_id", "customer_name", "customer_group", "customer_number"
    ]].drop_duplicates(subset=["customer_id"], keep="first").copy()

    # Apply canonical names from consolidation mapping
    cust_data["customer_name"] = cust_data["customer_id"].map(
        lambda cid: canonical_names.get(cid, cust_data[cust_data["customer_id"] == cid]["customer_name"].iloc[0] if len(cust_data[cust_data["customer_id"] == cid]) > 0 else None)
    )

    cust_data = cust_data.reset_index(drop=True)
    cust_data["_scd_effective_date"] = EXTRACT_DATE
    cust_data["_scd_end_date"] = None
    cust_data["_scd_is_current"] = True
    cust_data["_scd_version"] = 1
    cust_data["_source"] = "customer"

    print(f"  Dim_Customer: {len(cust_data)} rows (with canonical consolidation)")
    return cust_data


def build_dim_product(product_silver):
    """
    Extract unique products from product silver.
    SCD Type 2: track when product line/category changed.

    For now (Phase 1), just create current versions.
    Aggregates by product_id to avoid duplicates.
    """
    # Create product_id from product_me (product code)
    product_silver = product_silver.copy()
    product_silver["product_id"] = product_silver.get("product_me", "UNKNOWN").fillna("UNKNOWN")

    cols_to_use = ["product_id"]
    for col in ["rep_product_line", "category_description",
                "product_portfolio", "legacy_data", "buying_group_l6", "product_me"]:
        if col in product_silver.columns:
            cols_to_use.append(col)

    # Group by product_id and take first value of each attribute
    # (in Phase 1, assuming each product_id has consistent attributes)
    prod_data = product_silver[cols_to_use].groupby("product_id", as_index=False).first()

    prod_data["_scd_effective_date"] = EXTRACT_DATE
    prod_data["_scd_end_date"] = None
    prod_data["_scd_is_current"] = True
    prod_data["_scd_version"] = 1
    prod_data["_source"] = "product"

    print(f"  Dim_Product: {len(prod_data)} rows (grouped from {len(product_silver)} original rows)")
    return prod_data


# ============================================================================
# FACT TABLE BUILDER
# ============================================================================

def build_fact_sales(customer_silver, product_silver, dim_time, dim_geography,
                     dim_buying_group, dim_customer, dim_product, dim_sales_unit):
    """
    Build unified fact table from customer + product silver views.
    Adds FK keys to all dimensions (including sales_unit_id).
    """
    facts = []

    # --- CUSTOMER FACTS ---
    print("  Building customer facts...")
    c = customer_silver.copy()

    # Add dimension keys
    if "year" in c.columns and "month" in c.columns:
        c["time_id"] = c["year"].astype(str).str.zfill(4) + c["month"].astype(str).str.zfill(2)

    # Geography ID: composite (WITHOUT sales_unit)
    c["geography_id"] = (
        c.get("region", "").fillna("") + "|" +
        c.get("sub_region", "").fillna("") + "|" +
        c.get("business_unit", "").fillna("")
    )

    # Sales Unit ID: separate dimension key
    c["sales_unit_id"] = c.get("sales_unit", "").fillna("")

    # Buying group: use value or UNCLASSIFIED
    c["buying_group_id"] = c.get("buying_group_l6", "").fillna("[UNCLASSIFIED]")
    c["buying_group_id"] = c["buying_group_id"].apply(lambda x: x if str(x).strip() else "[UNCLASSIFIED]")

    # Measures
    c["net_sales_chf"] = c.get("net_sales_lc", 0) * EUR_CHF_RATE
    c["gross_profit_chf"] = c.get("consolidated_gross_profit_lc", 0) * EUR_CHF_RATE
    c["gross_profit_chf_incl_freight"] = c.get("consolidated_gross_profit_lc_incl_freight", 0) * EUR_CHF_RATE

    # Select columns for fact
    fact_cols = [
        "customer_id", "product_id", "geography_id", "time_id", "sales_unit_id",
        "buying_group_id", "sales_order_number", "booked_date", "local_currency",
        "net_sales_lc", "net_sales_chf",
        "consolidated_gross_profit_lc", "gross_profit_chf", "gross_profit_chf_incl_freight",
        "is_negative_gp", "is_zero_sales",
    ]

    # Add missing product_id column (NaN for customer facts)
    if "product_id" not in c.columns:
        c["product_id"] = None

    c_fact = c[[col for col in fact_cols if col in c.columns]].copy()
    c_fact["_source_view"] = "customer"
    c_fact["_scd_effective_date"] = EXTRACT_DATE

    facts.append(c_fact)
    print(f"    Customer facts: {len(c_fact)} rows")

    # --- PRODUCT FACTS ---
    print("  Building product facts...")
    p = product_silver.copy()

    # Time ID from quarter
    if "quarter" in p.columns:
        p["time_id"] = (
            p["quarter"].astype(str).str.extract(r"(\d{4})", expand=False) +
            "Q" + p["quarter"].astype(str).str.extract(r"Q\s*(\d)", expand=False)
        )

    # Geography ID: composite (WITHOUT sales_unit)
    p["geography_id"] = (
        p.get("region", "").fillna("") + "|" +
        p.get("sub_region", "").fillna("") + "|" +
        p.get("business_unit", "").fillna("")
    )

    # Sales Unit ID: separate dimension key
    p["sales_unit_id"] = p.get("sales_unit", "").fillna("")

    # Buying group
    p["buying_group_id"] = p.get("buying_group_l6", "").fillna("[UNCLASSIFIED]")
    p["buying_group_id"] = p["buying_group_id"].apply(lambda x: x if str(x).strip() else "[UNCLASSIFIED]")

    # Product ID from product_me
    p["product_id"] = p.get("product_me", "UNKNOWN").fillna("UNKNOWN")

    # Measures
    p["net_sales_chf"] = p.get("net_sales_chf", 0)
    p["gross_profit_chf"] = p.get("gross_profit_chf", 0)
    p["gross_profit_chf_incl_freight"] = p.get("gross_profit_chf_incl_freight", 0)

    # No LC equivalents for product view
    p["net_sales_lc"] = None
    p["consolidated_gross_profit_lc"] = None
    p["local_currency"] = None

    # Select fact columns
    p_fact_cols = [
        "customer_id", "product_id", "geography_id", "time_id", "buying_group_id",
        "sales_order_number", "booked_date", "local_currency",
        "net_sales_lc", "net_sales_chf",
        "consolidated_gross_profit_lc", "gross_profit_chf", "gross_profit_chf_incl_freight",
        "is_negative_gp", "is_zero_sales",
    ]

    # Add missing columns
    if "customer_id" not in p.columns:
        p["customer_id"] = None
    if "sales_order_number" not in p.columns:
        p["sales_order_number"] = None
    if "booked_date" not in p.columns:
        p["booked_date"] = None

    p_fact = p[[col for col in p_fact_cols if col in p.columns or col in ["customer_id", "sales_order_number", "booked_date"]]].copy()
    p_fact["_source_view"] = "product"
    p_fact["_scd_effective_date"] = EXTRACT_DATE

    facts.append(p_fact)
    print(f"    Product facts: {len(p_fact)} rows")

    # --- UNION ---
    fact = pd.concat(facts, ignore_index=True)
    fact = fact.reset_index(drop=True)
    print(f"  Fact_Sales (unified): {len(fact)} rows")

    return fact


def build_denormalized_fact(fact, dim_customer, dim_product, dim_geography,
                            dim_time, dim_buying_group, dim_sales_unit):
    """
    Create denormalized fact table (pre-joined, current dimensions only).

    For backward compatibility with analysis.py: charts read this single table
    without needing to join dimensions themselves.

    IMPORTANT: Joins are done with proper deduplication to avoid Cartesian products.
    Dimensions must have unique keys.
    """
    print("  Building denormalized fact (pre-joined)...")

    denorm = fact.copy()

    # Clean up dimension keys to ensure uniqueness (drop duplicates, keep first)
    dim_c = dim_customer[dim_customer["_scd_is_current"]].copy()
    if len(dim_c) > 0:
        dim_c = dim_c.drop_duplicates(subset=["customer_id"], keep="first")
        denorm = denorm.merge(
            dim_c[["customer_id", "customer_name", "customer_group", "customer_number"]],
            on="customer_id", how="left", suffixes=("", "_from_dim")
        )

    # Join product dimension (current only)
    dim_p = dim_product[dim_product["_scd_is_current"]].copy()
    if len(dim_p) > 0:
        dim_p = dim_p.drop_duplicates(subset=["product_id"], keep="first")
        denorm = denorm.merge(
            dim_p[[
                "product_id", "product_me", "rep_product_line", "category_description",
                "product_portfolio"
            ]],
            on="product_id", how="left", suffixes=("", "_from_product")
        )

    # Join geography dimension (ensure no duplicates on geography_id)
    dim_g = dim_geography.copy()
    if len(dim_g) > 0:
        dim_g = dim_g.drop_duplicates(subset=["geography_id"], keep="first")
        denorm = denorm.merge(
            dim_g[["geography_id", "region", "sub_region", "business_unit"]],
            on="geography_id", how="left", suffixes=("", "_from_geo")
        )

    # Join sales_unit dimension (ensure no duplicates on sales_unit_id)
    dim_s = dim_sales_unit.copy()
    if len(dim_s) > 0:
        dim_s = dim_s.drop_duplicates(subset=["sales_unit_id"], keep="first")
        denorm = denorm.merge(
            dim_s[["sales_unit_id", "sales_unit"]],
            on="sales_unit_id", how="left", suffixes=("", "_from_su")
        )

    # Join time dimension (ensure no duplicates on time_id)
    dim_t = dim_time.copy()
    if len(dim_t) > 0:
        dim_t = dim_t.drop_duplicates(subset=["time_id"], keep="first")
        denorm = denorm.merge(
            dim_t[["time_id", "year", "month", "quarter"]],
            on="time_id", how="left", suffixes=("", "_from_time")
        )

    # Join buying group dimension (ensure no duplicates on buying_group_id)
    dim_b = dim_buying_group.copy()
    if len(dim_b) > 0:
        dim_b = dim_b.drop_duplicates(subset=["buying_group_id"], keep="first")
        denorm = denorm.merge(
            dim_b[["buying_group_id", "buying_group_l6"]],
            on="buying_group_id", how="left", suffixes=("", "_from_bg")
        )

    # Drop SCD/lineage columns not needed for charts
    cols_to_drop = ["_scd_effective_date", "_scd_end_date"]
    cols_to_drop.extend([col for col in denorm.columns if col.startswith("_scd_")])
    denorm = denorm.drop(columns=cols_to_drop, errors="ignore")

    print(f"  Denormalized fact: {len(denorm)} rows x {denorm.shape[1]} cols")
    return denorm


# ============================================================================
# MAIN
# ============================================================================

def main():
    ensure_dirs()

    # Load silver
    cust_path = os.path.join(SILVER_DIR, "customer.parquet")
    prod_path = os.path.join(SILVER_DIR, "product.parquet")

    if not os.path.exists(cust_path) or not os.path.exists(prod_path):
        print(f"[ERROR] missing silver input")
        print(f"  customer: {cust_path} {'✓' if os.path.exists(cust_path) else '✗'}")
        print(f"  product:  {prod_path} {'✓' if os.path.exists(prod_path) else '✗'}")
        sys.exit(2)

    print("Loading silver...")
    customer_silver = pd.read_parquet(cust_path)
    product_silver = pd.read_parquet(prod_path)

    # Build dimensions
    print("\nBuilding dimensions...")
    dim_time = build_dim_time(customer_silver, product_silver)
    dim_geography = build_dim_geography(customer_silver, product_silver)
    dim_sales_unit = build_dim_sales_unit(customer_silver, product_silver)
    dim_buying_group = build_dim_buying_group(customer_silver, product_silver)
    dim_customer = build_dim_customer(customer_silver)
    dim_product = build_dim_product(product_silver)

    # Build fact table
    print("\nBuilding fact table...")
    fact_sales = build_fact_sales(
        customer_silver, product_silver,
        dim_time, dim_geography, dim_buying_group, dim_customer, dim_product, dim_sales_unit
    )

    # Build denormalized compatibility layer
    print("\nBuilding denormalized fact (compatibility layer)...")
    fact_denorm = build_denormalized_fact(
        fact_sales, dim_customer, dim_product, dim_geography, dim_time, dim_buying_group, dim_sales_unit
    )

    # Write to parquet
    print("\nWriting to parquet...")

    # Ensure directories are writable
    import shutil
    shutil.rmtree(GOLD_DIM_DIR, ignore_errors=True)
    shutil.rmtree(GOLD_FACT_DIR, ignore_errors=True)
    os.makedirs(GOLD_DIM_DIR, exist_ok=True)
    os.makedirs(GOLD_FACT_DIR, exist_ok=True)

    dim_time.to_parquet(os.path.join(GOLD_DIM_DIR, "dim_time.parquet"), index=False)
    dim_geography.to_parquet(os.path.join(GOLD_DIM_DIR, "dim_geography.parquet"), index=False)
    dim_sales_unit.to_parquet(os.path.join(GOLD_DIM_DIR, "dim_sales_unit.parquet"), index=False)
    dim_buying_group.to_parquet(os.path.join(GOLD_DIM_DIR, "dim_buying_group.parquet"), index=False)
    dim_customer.to_parquet(os.path.join(GOLD_DIM_DIR, "dim_customer.parquet"), index=False)
    dim_product.to_parquet(os.path.join(GOLD_DIM_DIR, "dim_product.parquet"), index=False)

    fact_sales.to_parquet(os.path.join(GOLD_FACT_DIR, "fact_sales.parquet"), index=False)
    fact_denorm.to_parquet(os.path.join(GOLD_FACT_DIR, "fact_sales_denormalized.parquet"), index=False)

    print("\nStar schema built successfully (OK)")
    print(f"  Dimensions: {GOLD_DIM_DIR}")
    print(f"  Fact tables: {GOLD_FACT_DIR}")
    print(f"  Compatibility layer: fact_sales_denormalized.parquet")


if __name__ == "__main__":
    main()
