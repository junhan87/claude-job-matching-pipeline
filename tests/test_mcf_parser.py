"""Tests for pure helper functions in parsers/mcf.py.

No API key or network access required — pure string/regex logic.
Run with:  python -m pytest tests/test_mcf_parser.py -v
"""

import pytest
from parsers.mcf import (
    _is_salary_text,
    _looks_like_company,
    _company_to_slug,
    _title_from_url,
)

# Fake 32-char hex UUID used throughout
_UUID = "abcdef1234567890abcdef1234567890"


# ---------------------------------------------------------------------------
# _is_salary_text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("$5,000 – $8,000",    True),
    ("$3000/mth",          True),
    ("$12,500 per month",  True),
    ("12,000 / mth",       True),
    # Not a salary
    ("Cloud Architect",    False),
    ("Pte Ltd",            False),
    ("Senior Engineer",    False),
])
def test_is_salary_text(text, expected):
    assert _is_salary_text(text) is expected


# ---------------------------------------------------------------------------
# _looks_like_company
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Acme Pte Ltd",           True),
    ("TechCorp Pte. Ltd.",     True),
    ("Global Solutions Inc.",  True),
    ("DataCorp Sdn Bhd",       True),
    ("Foo Co. Ltd.",           True),
    # Job titles — should NOT look like companies
    ("Cloud Architect",        False),
    ("Senior Engineer",        False),
    ("Principal Consultant",   False),
])
def test_looks_like_company(text, expected):
    assert _looks_like_company(text) is expected


# ---------------------------------------------------------------------------
# _company_to_slug
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Acme Pte Ltd",            "acme"),
    ("Tech Solutions Pte. Ltd.", "tech-solutions"),
    ("GovTech",                 "govtech"),
    ("Foo Bar Baz",             "foo-bar-baz"),
    ("OCBC Bank Ltd",           "ocbc-bank"),
])
def test_company_to_slug(name, expected):
    assert _company_to_slug(name) == expected


# ---------------------------------------------------------------------------
# _title_from_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,company,expected_title", [
    # Company slug is stripped from the end of the title segment
    (
        f"https://www.mycareersfuture.gov.sg/job/it/cloud-architect-govtech-{_UUID}",
        "GovTech",
        "Cloud Architect",
    ),
    # Multi-word company slug stripped
    (
        f"https://www.mycareersfuture.gov.sg/job/it/solution-architect-tech-solutions-{_UUID}",
        "Tech Solutions Pte. Ltd.",
        "Solution Architect",
    ),
    # Company slug not present in URL → entire base used as title
    (
        f"https://www.mycareersfuture.gov.sg/job/it/solution-architect-{_UUID}",
        "Unknown Corp",
        "Solution Architect",
    ),
    # URL without a valid 32-char UUID → empty string
    (
        "https://www.mycareersfuture.gov.sg/job/it/cloud-architect",
        "GovTech",
        "",
    ),
])
def test_title_from_url(url, company, expected_title):
    assert _title_from_url(url, company) == expected_title
