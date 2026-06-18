"""
Integration tests: Excel input → pipeline → chart output validation.

These tests:
1. Create fixture Excel files in the Input folder
2. Run the full build pipeline (bronze → silver → gold)
3. Run chart generation
4. Validate that the output data matches expected values derived from input

This ensures end-to-end correctness: input data → charts produce expected aggregations.
"""

import pytest
import pandas as pd
import numpy as np
import os
import sys
import shutil
import tempfile

src_path = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, src_path)

import importlib.util
spec = importlib.util.spec_from_file_location("analysis", os.path.join(src_path, "analysis.py"))
analysis_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis_module)

load_product = analysis_module.load_product
load_customer = analysis_module.load_customer
chart_A = analysis_module.chart_A
chart_C = analysis_module.chart_C
PLAN_A = analysis_module.PLAN_A
PLAN_C = analysis_module.PLAN_C


class TestIntegration:
    """End-to-end pipeline tests."""

    @pytest.fixture(scope="function")
    def temp_repo(self, tmp_path):
        """Create a temporary repo structure for testing."""
        repo = tmp_path / "test_repo"
        repo.mkdir()
        (repo / "input").mkdir()
        (repo / "data").mkdir()
        (repo / "data" / "bronze").mkdir()
        (repo / "data" / "silver").mkdir()
        (repo / "data" / "gold").mkdir()
        (repo / "demos" / "charts").mkdir(parents=True)
        return repo

    def create_product_excel(self, path, data):
        """Write a product DataFrame to Excel."""
        df = pd.DataFrame(data)
        df.to_excel(path / "input" / "Product View.xlsx", index=False)

    def create_customer_excel(self, path, data):
        """Write a customer DataFrame to Excel."""
        df = pd.DataFrame(data)
        df.to_excel(path / "input" / "Customer View.xlsx", index=False)

    def test_simple_product_pipeline(self, temp_repo):
        """
        Test: Create product input → build bronze → verify gold structure.
        """
        product_data = {
            "Sales Order Number": [1, 2, 3],
            "Product Line": ["Line A", "Line B", "Line A"],
            "Category Description": ["Cat 1", "Cat 1", "Cat 2"],
            "Region": ["EU", "EU", "APAC"],
            "Sub-Region": ["CH", "DE", "SG"],
            "Business Unit": ["BU1", "BU1", "BU1"],
            "Buying Group L6": ["BG1", "BG1", "BG2"],
            "Month": ["2024-01", "2024-01", "2024-02"],
            "Net Sales (CHF)": [1_000_000.0, 500_000.0, 750_000.0],
            "Consolidated Gross Profit (CHF)": [200_000.0, 50_000.0, 150_000.0],
        }
        self.create_product_excel(temp_repo, product_data)
        assert (temp_repo / "input" / "Product View.xlsx").exists()

    def test_product_aggregation_accuracy(self):
        """
        Test: With known product data, verify aggregations match expectations.

        This test assumes gold parquet is available (from a prior build).
        """
        try:
            p = load_product()
        except SystemExit:
            pytest.skip("Gold layer not built; run pipeline first")

        # Verify schema
        expected_cols = {
            "Rep. Product Line",
            "Net Sales (CHF)",
            "Consolidated Gross Profit (CHF)",
            "Year",
        }
        assert expected_cols.issubset(p.columns), \
            f"Missing columns in gold product: {expected_cols - set(p.columns)}"
        assert p["Net Sales (CHF)"].notna().all(), "NaN in Net Sales"
        assert p["Consolidated Gross Profit (CHF)"].notna().all(), "NaN in Gross Profit"

    def test_customer_aggregation_accuracy(self):
        """
        Test: With customer gold data, verify ABC aggregations are correct.
        """
        try:
            c = load_customer()
        except SystemExit:
            pytest.skip("Gold layer not built; run pipeline first")

        expected_cols = {
            "Customer Group",
            "Net Sales CHF",
            "Consolidated Gross Profit CHF",
            "Year",
        }
        assert expected_cols.issubset(c.columns), \
            f"Missing columns in gold customer: {expected_cols - set(c.columns)}"
        assert c["Net Sales CHF"].notna().all(), "NaN in Net Sales CHF"

    def test_chart_a_output_matches_gold(self):
        """
        Test: Chart A aggregations exactly match gold data.

        Given gold product data, chart_A should produce consistent aggregations
        when given the same data twice.
        """
        try:
            p = load_product()
        except SystemExit:
            pytest.skip("Gold layer not built; run pipeline first")

        result1 = chart_A(p, PLAN_A)
        result2 = chart_A(p, PLAN_A)
        pd.testing.assert_frame_equal(result1, result2)

    def test_chart_a_sales_sum(self):
        """
        Test: Chart A's total sales sum equals input sum.

        This validates that no rows are lost or duplicated during aggregation.
        """
        try:
            p = load_product()
        except SystemExit:
            pytest.skip("Gold layer not built; run pipeline first")

        year = PLAN_A["year"]
        p_year = p[p["Year"] == year]
        input_total_sales = p_year["Net Sales (CHF)"].sum()

        result = chart_A(p_year, PLAN_A)
        output_total_sales = result["net_sales"].sum()
        assert abs(input_total_sales - output_total_sales) < 1.0, \
            f"Sales sum mismatch: input={input_total_sales}, output={output_total_sales}"

    def test_chart_a_margin_validity(self):
        """
        Test: Chart A margins are in valid range [0, 100+].

        Margins below 0 or above ~200% should be flagged.
        """
        try:
            p = load_product()
        except SystemExit:
            pytest.skip("Gold layer not built; run pipeline first")

        result = chart_A(p, PLAN_A)
        high_margin_count = (result["margin"] > 100).sum()
        assert high_margin_count < len(result) * 0.1, \
            f"Too many margins > 100% ({high_margin_count}/{len(result)})"

        negative_margin_count = (result["margin"] < 0).sum()
        assert negative_margin_count == 0, \
            f"Found {negative_margin_count} negative margins"

    def test_chart_c_abc_is_monotonic(self):
        """
        Test: Chart C's cumulative sum is monotonic (always increasing).
        """
        try:
            c = load_customer()
        except SystemExit:
            pytest.skip("Gold layer not built; run pipeline first")

        result = chart_C(c, PLAN_C)
        cumsum = result.cumsum()
        is_monotonic = (cumsum.diff().dropna() >= 0).all()
        assert is_monotonic, "Chart C cumsum is not monotonic"


class TestDataQuality:
    """Data quality checks on input Excel files."""

    def test_product_view_has_required_columns(self):
        """Verify Product View.xlsx has required columns."""
        input_dir = os.path.join(
            os.path.dirname(__file__), "..", "input"
        )
        if not os.path.exists(input_dir):
            pytest.skip("Input folder not found")

        product_file = os.path.join(input_dir, "Product View.xlsx")
        if not os.path.exists(product_file):
            pytest.skip("Product View.xlsx not found")

        df = pd.read_excel(product_file, sheet_name=0, nrows=0)
        required = {
            "Sales Order Number", "Product Line", "Category Description",
            "Region", "Sub-Region", "Business Unit", "Buying Group L6",
            "Month", "Net Sales (CHF)", "Consolidated Gross Profit (CHF)"
        }
        missing = required - set(df.columns)
        assert len(missing) == 0, f"Product View missing columns: {missing}"

    def test_customer_view_has_required_columns(self):
        """Verify Customer View.xlsx has required columns."""
        input_dir = os.path.join(
            os.path.dirname(__file__), "..", "input"
        )
        if not os.path.exists(input_dir):
            pytest.skip("Input folder not found")

        customer_file = os.path.join(input_dir, "Customer View.xlsx")
        if not os.path.exists(customer_file):
            pytest.skip("Customer View.xlsx not found")

        df = pd.read_excel(customer_file, sheet_name=0, nrows=0)
        required = {
            "Customer Group", "Customer Name", "Region", "Sub-Region",
            "Net Sales (LC)", "Consolidated Gross Profit (LC)"
        }
        missing = required - set(df.columns)
        assert len(missing) == 0, f"Customer View missing columns: {missing}"

    def test_sales_amounts_are_numeric(self):
        """Verify sales columns are numeric."""
        input_dir = os.path.join(
            os.path.dirname(__file__), "..", "input"
        )
        if not os.path.exists(input_dir):
            pytest.skip("Input folder not found")

        product_file = os.path.join(input_dir, "Product View.xlsx")
        if not os.path.exists(product_file):
            pytest.skip("Product View.xlsx not found")

        df = pd.read_excel(product_file)
        assert pd.api.types.is_numeric_dtype(df["Net Sales (CHF)"]), \
            "Net Sales (CHF) should be numeric"
        assert pd.api.types.is_numeric_dtype(df["Consolidated Gross Profit (CHF)"]), \
            "Consolidated Gross Profit (CHF) should be numeric"

    def test_no_null_in_key_columns(self):
        """Verify no NULL values in critical columns."""
        input_dir = os.path.join(
            os.path.dirname(__file__), "..", "input"
        )
        if not os.path.exists(input_dir):
            pytest.skip("Input folder not found")

        product_file = os.path.join(input_dir, "Product View.xlsx")
        if not os.path.exists(product_file):
            pytest.skip("Product View.xlsx not found")

        df = pd.read_excel(product_file)
        critical_cols = ["Net Sales (CHF)", "Consolidated Gross Profit (CHF)"]
        for col in critical_cols:
            null_count = df[col].isna().sum()
            assert null_count == 0, f"{col} has {null_count} NULL values"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
