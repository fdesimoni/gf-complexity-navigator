"""
GF BFS - Medallion: RAW -> BRONZE
=================================
Reads the two raw Excel exports from input/ and writes typed, standardized
Parquet to data/bronze/. This stage does NOT drop rows or apply business logic
-- it only standardizes column names, enforces dtypes, and stamps lineage.

See approach/medallion_design.md for the full design and column mappings.

Run:  python pipeline/build_bronze.py
Exit codes:  0 = OK   2 = a raw input file is missing
"""

import os
import sys
import datetime as dt
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
INPUT_DIR = os.path.join(REPO, "input")
BRONZE_DIR = os.path.join(REPO, "data", "bronze")

CUST_FILE = os.path.join(INPUT_DIR, "Customer View.xlsx")
PROD_FILE = os.path.join(INPUT_DIR, "Product View.xlsx")

# ----------------------------------------------------------------------------
# Raw -> bronze column maps. Keys are the raw Excel headers (after strip());
# values are the snake_case bronze names. Any raw column NOT in the map is
# still carried through with an auto-snake_cased name, but a warning is printed
# so a schema change (renamed/added column) is loud, not silent.
# ----------------------------------------------------------------------------
CUSTOMER_MAP = {
    "Year": "year",
    "Month": "month",
    "Buying Group L6": "buying_group_l6",
    "Customer Group": "customer_group",
    "Customer Number": "customer_number",
    "Customer Name": "customer_name",
    "Booked Date": "booked_date",
    "Sales Order Number": "sales_order_number",
    "Net Ordered Amount LC": "net_ordered_amount_lc",
    "NS Ordered Amount LC": "ns_ordered_amount_lc",
    "Business Unit": "business_unit",
    "Region": "region",
    "Sub-Region": "sub_region",
    "Sales Unit": "sales_unit",
    "Local Currency": "local_currency",
    "Net Sales LC": "net_sales_lc",
    "Consolidated Gross Profit LC incl. Outbound Freight":
        "consolidated_gross_profit_lc_incl_freight",
    "Consolidated Gross Profit LC": "consolidated_gross_profit_lc",
}

PRODUCT_MAP = {
    "Month Name": "month_name",
    "Quarter": "quarter",
    "Division": "division",
    "Business Unit": "business_unit",
    "Region": "region",
    "Sub-Region": "sub_region",
    "Sales Unit": "sales_unit",
    "Legacy Data": "legacy_data",
    "2 - Category Description": "category_description",
    "me": "product_me",
    "Buying Group L6": "buying_group_l6",
    "Net Sales (CHF)": "net_sales_chf",
    "Consolidated Gross Profit (CHF)": "gross_profit_chf",
    "Consolidated Gross Profit (CHF) incl. Outbound Freight":
        "gross_profit_chf_incl_freight",
    "Net Sales EUR": "net_sales_eur",
    "Consolidated Gross Profit EUR": "gross_profit_eur",
    "Consolidated Gross Profit (EUR) incl. Outbound Freight":
        "gross_profit_eur_incl_freight",
    "Product Portfolio": "product_portfolio",
    "Rep. Product Line": "rep_product_line",
}

# Bronze columns to force numeric (everything else stays string/datetime as read).
CUSTOMER_NUMERIC = [
    "net_ordered_amount_lc", "ns_ordered_amount_lc", "net_sales_lc",
    "consolidated_gross_profit_lc", "consolidated_gross_profit_lc_incl_freight",
]
PRODUCT_NUMERIC = [
    "net_sales_chf", "gross_profit_chf", "gross_profit_chf_incl_freight",
    "net_sales_eur", "gross_profit_eur", "gross_profit_eur_incl_freight",
]


def _auto_snake(name):
    return (name.strip().lower()
            .replace(" ", "_").replace("-", "_").replace(".", "")
            .replace("(", "").replace(")", "").replace("__", "_"))


def _standardize(df, colmap, label):
    """Rename via map; auto-snake unmapped columns with a loud warning."""
    df.columns = [c.strip() for c in df.columns]
    rename, unmapped = {}, []
    for c in df.columns:
        if c in colmap:
            rename[c] = colmap[c]
        else:
            rename[c] = _auto_snake(c)
            unmapped.append(c)
    if unmapped:
        print(f"  [WARN] {label}: {len(unmapped)} unmapped column(s) "
              f"(schema change?): {unmapped}")
    return df.rename(columns=rename)


def _coerce(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build(src, colmap, numeric, out_name):
    if not os.path.exists(src):
        print(f"  [ERROR] missing raw input: {src}")
        return None
    df = pd.read_excel(src)
    df = _standardize(df, colmap, os.path.basename(src))
    df = _coerce(df, numeric)
    df["_source_file"] = os.path.basename(src)
    df["_loaded_at"] = dt.datetime.now().isoformat(timespec="seconds")
    out_path = os.path.join(BRONZE_DIR, out_name)
    df.to_parquet(out_path, index=False)
    print(f"  bronze written: {out_name}  ({len(df):,} rows x {df.shape[1]} cols)")
    return df


def main():
    os.makedirs(BRONZE_DIR, exist_ok=True)
    print("RAW -> BRONZE")
    c = build(CUST_FILE, CUSTOMER_MAP, CUSTOMER_NUMERIC, "customer.parquet")
    p = build(PROD_FILE, PRODUCT_MAP, PRODUCT_NUMERIC, "product.parquet")
    if c is None or p is None:
        print("FAILED: one or more raw inputs missing.")
        sys.exit(2)
    print("Done.")


if __name__ == "__main__":
    main()
