"""Tests for parse_salary_min and salary_meets_threshold in core/config.py.

No API key or network access required — pure regex logic only.
Run with:  python -m pytest tests/test_salary_filter.py -v
"""

import pytest
from core.config import parse_salary_min, salary_meets_threshold


# ---------------------------------------------------------------------------
# parse_salary_min
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("salary,expected", [
    ("$5,000 – $8,000",   5000),
    ("$5,000/mth",        5000),
    ("$5,000 per month",  5000),
    ("$12,500",           12500),
    ("$3,000-$4,500",     3000),
    ("",                  None),
    (None,                None),
    ("To be discussed",   None),
    ("Competitive",       None),
])
def test_parse_salary_min(salary, expected):
    assert parse_salary_min(salary) == expected


# ---------------------------------------------------------------------------
# salary_meets_threshold
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("salary,min_salary,expected", [
    # No salary info → always kept (unknown ≠ below threshold)
    ("",                  5000, True),
    (None,                5000, True),
    ("To be discussed",   5000, True),
    ("Competitive",       5000, True),
    # Meets threshold
    ("$5,000 – $8,000",   5000, True),
    ("$6,000/mth",        5000, True),
    ("$10,000",           5000, True),
    # Exactly at threshold
    ("$5,000",            5000, True),
    # Below threshold
    ("$3,000 – $5,000",   5000, False),
    ("$4,999",            5000, False),
    ("$1,500",            5000, False),
    # min_salary = 0 → everything passes
    ("$1,000",               0, True),
])
def test_salary_meets_threshold(salary, min_salary, expected):
    assert salary_meets_threshold(salary, min_salary) is expected
