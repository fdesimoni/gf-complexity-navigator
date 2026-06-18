"""
GF BFS - Medallion: BRONZE -> SILVER
====================================
Reads typed bronze Parquet and writes cleaned, conformed silver Parquet plus a
data-quality log. Cleaning rules are the agreed demo defaults (see
approach/medallion_design.md); in a real engagement they are confirmed in the
Phase-1 data workshop. Every rule is applied explicitly and logged.

Chosen rules:
  * Suspect rows are KEPT and FLAGGED (is_negative_gp, is_zero_sales, ...).
  * Currency is kept NATIVE + EUR where available; no FX is fabricated.

Run:  python pipeline/build_silver.py
Exit codes:  0 = OK   2 = a bronze input is missing (run build_bronze.py first)
"""

import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BRONZE_DIR = os.path.join(REPO, "data", "bronze")
SILVER_DIR = os.path.join(REPO, "data", "silver")
CUSTOMER_DIM_FILE = os.path.join(HERE, "customer_dimension.csv")

STRING_SKIP = {"_source_file", "_loaded_at"}


def _trim_strings(df):
    for c in df.columns:
        if c in STRING_SKIP:
            continue
        if df[c].dtype == object or str(df[c].dtype) == "string":
            df[c] = df[c].astype("string").str.strip()
    return df


def _log(rows, table, check, value, note, rule):
    rows.append({"table": table, "check": check, "value": value,
                 "note": note, "rule_applied": rule})


def silver_customer(b, dq):
    t = "customer"
    n0 = len(b)
    b = _trim_strings(b.copy())

    if not os.path.exists(CUSTOMER_DIM_FILE):
        print(f"  [ERROR] missing customer dimension: {CUSTOMER_DIM_FILE}")
        print(f"          Run build_customer_dimension.py first")
        raise SystemExit(1)

    dim = pd.read_csv(CUSTOMER_DIM_FILE)
    cust_lookup = {}
    for _, row in dim.iterrows():
        cust_lookup[str(row['sales_location_id'])] = {
            'customer_id': row['customer_id'],
            'customer_name': row['customer_name'],
        }
    b['customer_number'] = b['customer_number'].astype(str)
    mapped = b['customer_number'].map(lambda x: cust_lookup.get(x, {}).get('customer_id'))
    not_found = mapped.isna().sum()
    if not_found > 0:
        print(f"  [WARN] {not_found} rows with unmapped customer_number (will be dropped)")

    b['customer_id'] = mapped
    b['customer_name'] = b['customer_number'].map(lambda x: cust_lookup.get(x, {}).get('customer_name'))
    b = b.dropna(subset=['customer_id', 'customer_name'])

    _log(dq, t, "customer_dimension_mapped", len(b),
         f"consolidated to {b['customer_id'].nunique()} unique customers", "customer_dim_map")
    b = b.drop_duplicates()
    _log(dq, t, "exact_duplicate_rows_dropped", len(b) - n0, "", "drop_exact_dupes")

    ns = b["net_sales_lc"]
    gp = b["consolidated_gross_profit_lc"]
    b["is_negative_gp"] = (gp < 0)
    b["is_zero_sales"] = (ns <= 0)
    b["is_cost_without_sales"] = (ns == 0) & (gp != 0)
    b["is_missing_currency"] = b["local_currency"].isna()
    b["is_missing_buying_group"] = b["buying_group_l6"].isna()

    _log(dq, t, "rows", len(b), "", "keep_all")
    _log(dq, t, "is_negative_gp", int(b["is_negative_gp"].sum()),
         f"{b['is_negative_gp'].mean()*100:.1f}% value-destroying lines", "flag_only")
    _log(dq, t, "is_zero_sales", int(b["is_zero_sales"].sum()),
         f"{b['is_zero_sales'].mean()*100:.1f}% returns/credits/rebates", "flag_only")
    _log(dq, t, "is_cost_without_sales", int(b["is_cost_without_sales"].sum()),
         "cost/credit booked without sales", "flag_only")
    _log(dq, t, "is_missing_currency", int(b["is_missing_currency"].sum()),
         "master-data gap", "flag_only")
    _log(dq, t, "is_missing_buying_group", int(b["is_missing_buying_group"].sum()),
         "breaks customer<->product bridge", "flag_only")
    _log(dq, t, "customer_groups_net_negative_gp",
         int(b.groupby("customer_group")["consolidated_gross_profit_lc"].sum().lt(0).sum()),
         "lose money overall", "flag_only")
    return b


def silver_product(b, dq):
    t = "product"
    n0 = len(b)
    b = _trim_strings(b.copy())

    b = b.drop_duplicates()
    _log(dq, t, "exact_duplicate_rows_dropped", n0 - len(b), "", "drop_exact_dupes")

    ns = b["net_sales_chf"]
    gp = b["gross_profit_chf"]

    b["is_negative_gp"] = (gp < 0)
    b["is_zero_sales"] = (ns == 0)
    b["is_cost_without_sales"] = (ns == 0) & (gp.fillna(0) != 0)
    b["is_missing_gp"] = gp.isna()
    b["is_missing_buying_group"] = b["buying_group_l6"].isna()

    _log(dq, t, "rows", len(b), "", "keep_all")
    _log(dq, t, "is_negative_gp", int(b["is_negative_gp"].sum()),
         f"{b['is_negative_gp'].mean()*100:.1f}% value-destroying lines", "flag_only")
    _log(dq, t, "is_zero_sales", int(b["is_zero_sales"].sum()),
         f"{b['is_zero_sales'].mean()*100:.1f}% slow/zero movers", "flag_only")
    _log(dq, t, "is_cost_without_sales", int(b["is_cost_without_sales"].sum()),
         "cost booked without sales", "flag_only")
    _log(dq, t, "is_missing_gp", int(b["is_missing_gp"].sum()),
         "incomplete costing", "flag_only")
    _log(dq, t, "is_missing_buying_group", int(b["is_missing_buying_group"].sum()),
         "breaks customer<->product bridge", "flag_only")
    return b


def build(name, fn, dq):
    src = os.path.join(BRONZE_DIR, name)
    if not os.path.exists(src):
        print(f"  [ERROR] missing bronze input: {src} (run build_bronze.py first)")
        return False
    df = fn(pd.read_parquet(src), dq)
    out = os.path.join(SILVER_DIR, name)
    df.to_parquet(out, index=False)
    # eyeball-friendly sample alongside the parquet (first 1000 rows)
    df.head(1000).to_csv(os.path.join(SILVER_DIR, name.replace(".parquet", "_sample.csv")),
                         index=False)
    print(f"  silver written: {name}  ({len(df):,} rows x {df.shape[1]} cols)")
    return True


def main():
    os.makedirs(SILVER_DIR, exist_ok=True)
    print("BRONZE -> SILVER")
    dq = []
    ok_c = build("customer.parquet", silver_customer, dq)
    ok_p = build("product.parquet", silver_product, dq)
    if not (ok_c and ok_p):
        print("FAILED: one or more bronze inputs missing.")
        sys.exit(2)
    dq_path = os.path.join(SILVER_DIR, "_dq_log.csv")
    pd.DataFrame(dq, columns=["table", "check", "value", "note", "rule_applied"]) \
        .to_csv(dq_path, index=False)
    print(f"  dq log written: _dq_log.csv  ({len(dq)} checks)")
    print("Done.")


if __name__ == "__main__":
    main()
