"""Tests for parsers/linkedin.py — email HTML parsing.

No API key or network access required — all parsing is done on inline HTML fixtures.
Run with:  python -m pytest tests/test_linkedin_parser.py -v
"""

import pytest
from bs4 import BeautifulSoup

from parsers.linkedin import _clean_job_url, LinkedInStrategy


# ---------------------------------------------------------------------------
# _clean_job_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (
        "https://www.linkedin.com/jobs/view/1234567890?trk=guest_job_details",
        "https://www.linkedin.com/jobs/view/1234567890",
    ),
    (
        "https://www.linkedin.com/jobs/view/9876543210?refId=abc&trackingId=xyz",
        "https://www.linkedin.com/jobs/view/9876543210",
    ),
    # Already clean — no change
    (
        "https://www.linkedin.com/jobs/view/111",
        "https://www.linkedin.com/jobs/view/111",
    ),
    # /comm/ prefix — normalised to canonical /jobs/view/
    (
        "https://www.linkedin.com/comm/jobs/view/4387995274/?trackingId=abc",
        "https://www.linkedin.com/jobs/view/4387995274",
    ),
    (
        "https://www.linkedin.com/comm/jobs/view/9999/?refId=xyz&trackingId=xyz",
        "https://www.linkedin.com/jobs/view/9999",
    ),
])
def test_clean_job_url(raw, expected):
    assert _clean_job_url(raw) == expected


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Minimal LinkedIn alert email with two structured job cards and a preheader.
_TWO_CARD_HTML = """
<html><body>
  <div data-email-preheader="true">Acme Corp: Looking for a cloud architect to lead\u2026</div>
  <td data-test-id="job-card">
    <a class="font-bold" href="https://www.linkedin.com/jobs/view/111?trk=abc">Cloud Architect</a>
    <p class="text-system-gray-100">Acme Corp\u00b7Singapore</p>
  </td>
  <td data-test-id="job-card">
    <a class="font-bold" href="https://www.linkedin.com/jobs/view/222?trk=xyz">Solution Architect</a>
    <p class="text-system-gray-100">Beta Ltd\u00b7Remote</p>
  </td>
</body></html>
"""

# Same structure but using the newer /comm/jobs/view/ URL format LinkedIn emails now send.
_TWO_CARD_COMM_HTML = """
<html><body>
  <div data-email-preheader="true">Acme Corp: Looking for a cloud architect to lead\u2026</div>
  <td data-test-id="job-card">
    <a class="font-bold" href="https://www.linkedin.com/comm/jobs/view/111/?trackingId=abc">Cloud Architect</a>
    <p class="text-system-gray-100">Acme Corp\u00b7Singapore</p>
  </td>
  <td data-test-id="job-card">
    <a class="font-bold" href="https://www.linkedin.com/comm/jobs/view/222/?trackingId=xyz">Solution Architect</a>
    <p class="text-system-gray-100">Beta Ltd\u00b7Remote</p>
  </td>
</body></html>
"""

# Email with no structured cards — only plain <a> links (fallback path).
_FALLBACK_LINK_HTML = """
<html><body>
  <a href="https://www.linkedin.com/jobs/view/333?trk=foo">Principal Architect</a>
  <a href="https://www.linkedin.com/jobs/view/444?trk=bar">Staff Engineer</a>
  <a href="https://www.example.com/not-a-job">Unrelated link</a>
</body></html>
"""

# Email with no job URLs at all.
_EMPTY_HTML = "<html><body><p>No jobs today.</p></body></html>"


# ---------------------------------------------------------------------------
# _extract_job_urls — structured card path
# ---------------------------------------------------------------------------

def test_extracts_two_job_cards():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_TWO_CARD_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert "111" in result
    assert "222" in result


def test_card_title_and_company_parsed():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_TWO_CARD_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert result["111"]["title"] == "Cloud Architect"
    assert result["111"]["company"] == "Acme Corp"
    assert result["111"]["location"] == "Singapore"


def test_card_url_is_cleaned():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_TWO_CARD_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert "trk=" not in result["111"]["url"]
    assert result["111"]["url"] == "https://www.linkedin.com/jobs/view/111"


# ---------------------------------------------------------------------------
# /comm/jobs/view/ URL format (new LinkedIn email format)
# ---------------------------------------------------------------------------

def test_comm_url_cards_extracted():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_TWO_CARD_COMM_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert "111" in result
    assert "222" in result


def test_comm_url_normalised_to_canonical():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_TWO_CARD_COMM_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert result["111"]["url"] == "https://www.linkedin.com/jobs/view/111"
    assert "trackingId" not in result["111"]["url"]
    assert "/comm/" not in result["111"]["url"]


def test_preheader_snippet_attached_to_first_job_only():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_TWO_CARD_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    # First job should have description from preheader
    assert "description" in result["111"]
    assert "cloud architect" in result["111"]["description"].lower()
    # Second job should NOT have a description
    assert "description" not in result["222"]


# ---------------------------------------------------------------------------
# _extract_job_urls — fallback link-scan path
# ---------------------------------------------------------------------------

def test_fallback_extracts_linkedin_links():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_FALLBACK_LINK_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert "333" in result
    assert "444" in result


def test_fallback_ignores_non_linkedin_links():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_FALLBACK_LINK_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    # Only LinkedIn job URLs should appear
    for key in result:
        assert key in ("333", "444")


def test_empty_email_returns_empty_dict():
    strategy = LinkedInStrategy()
    soup = BeautifulSoup(_EMPTY_HTML, "html.parser")
    result = strategy._extract_job_urls(soup, None)
    assert result == {}
