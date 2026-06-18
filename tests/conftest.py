"""
Shared pytest fixtures and configuration.

Provides common fixtures for product/customer DataFrames that multiple
tests can use.
"""

import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def product_fixture_simple():
    """Simple product dataset for basic tests."""
    return pd.DataFrame({
        "Rep. Product Line": ["Line A", "Line B", "Line C"],
        "Year": [2024, 2024, 2024],
        "Net Sales (CHF)": [1_000_000.0, 2_000_000.0, 500_000.0],
        "Consolidated Gross Profit (CHF)": [200_000.0, 300_000.0, 50_000.0],
    })


@pytest.fixture
def product_fixture_multiear():
    """Product dataset spanning multiple years for CAGR tests."""
    return pd.DataFrame({
        "Rep. Product Line": (
            ["Line A"] * 5 + ["Line B"] * 5 + ["Line C"] * 5
        ),
        "Year": [2021, 2022, 2023, 2024, 2025] * 3,
        "Net Sales (CHF)": [
            1_000_000, 1_100_000, 1_150_000, 1_200_000, 1_500_000,
            2_000_000, 1_900_000, 1_800_000, 1_600_000, 1_500_000,
            500_000, 600_000, 500_000, 700_000, 900_000,
        ],
        "Consolidated Gross Profit (CHF)": [
            200_000, 220_000, 230_000, 240_000, 300_000,
            300_000, 285_000, 270_000, 240_000, 225_000,
            75_000, 90_000, 75_000, 105_000, 180_000,
        ],
    })


@pytest.fixture
def customer_fixture_simple():
    """Simple customer dataset for basic tests."""
    return pd.DataFrame({
        "Customer Group": [
            "Big Corp", "Mid Corp", "Small Corp"
        ],
        "Year": [2025, 2025, 2025],
        "Local Currency": ["EUR", "EUR", "EUR"],
        "Net Sales CHF": [1_000_000.0, 500_000.0, 100_000.0],
        "Consolidated Gross Profit CHF": [300_000.0, 100_000.0, 5_000.0],
        "EUR/CHF Rate": [0.93, 0.93, 0.93],
    })


@pytest.fixture
def customer_fixture_abc():
    """Customer dataset designed to test ABC segmentation."""
    return pd.DataFrame({
        "Customer Group": [
            "A1", "A2", "A3",  # Top tier (A customers)
            "B1", "B2",         # Mid tier (B customers)
            "C1", "C2", "C3", "C4", "C5",  # Long tail (C customers)
        ],
        "Consolidated Gross Profit CHF": [
            300_000, 300_000, 300_000,
            100_000, 100_000,
            50_000, 40_000, 30_000, 20_000, 10_000,
        ],
    })


@pytest.fixture
def segment_fixture_simple():
    """Product x segment data for stacked chart tests."""
    return pd.DataFrame({
        "Rep. Product Line": ["P1", "P1", "P2", "P2", "P3", "P3"],
        "Buying Group L6": ["BG A", "BG B", "BG A", "BG B", "BG A", "BG B"],
        "Year": [2024] * 6,
        "Net Sales (CHF)": [
            500_000, 300_000,
            200_000, 1_000_000,
            100_000, 200_000,
        ],
    })


def pytest_configure(config):
    """Setup for all tests: configure matplotlib to not display."""
    import matplotlib
    matplotlib.use("Agg")


class AssertDataFrame:
    """Helper for robust DataFrame assertions."""

    @staticmethod
    def sum_matches(result_df, expected_total, column_name, tolerance=1.0):
        """Assert that sum of a column matches expected total."""
        actual = result_df[column_name].sum()
        assert abs(actual - expected_total) <= tolerance, \
            f"Sum mismatch in {column_name}: expected {expected_total}, got {actual}"

    @staticmethod
    def is_sorted(result_df, column_name, ascending=False):
        """Assert that a DataFrame is sorted by a column."""
        expected = result_df.sort_values(column_name, ascending=ascending)
        pd.testing.assert_frame_equal(result_df, expected)

    @staticmethod
    def no_nulls(result_df, column_name=None):
        """Assert that a column (or all) has no NaN values."""
        if column_name:
            assert result_df[column_name].notna().all(), \
                f"Found NaN values in {column_name}"
        else:
            assert result_df.notna().all().all(), \
                "Found NaN values in DataFrame"

    @staticmethod
    def column_in_range(result_df, column_name, min_val, max_val):
        """Assert that a column's values fall within [min, max]."""
        assert (result_df[column_name] >= min_val).all() and \
               (result_df[column_name] <= max_val).all(), \
            f"{column_name} has values outside [{min_val}, {max_val}]"


@pytest.fixture
def assert_df():
    """Provide DataFrame assertion helpers."""
    return AssertDataFrame()
