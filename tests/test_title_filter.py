"""Tests for the title pre-filter logic in utils.py.

No Anthropic API key or network access required — pure regex logic only.
Run with:  python -m pytest tests/test_title_filter.py -v
"""

import pytest

from core.config import should_analyze


# ---------------------------------------------------------------------------
# Should PASS (analyze = True) — real titles from LinkedIn feed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Principal - Software Engineering",                                          # principal
    "Principal Platform Architect",                                              # principal + architect
    "Solution Architect - A26011",                                               # architect
    "Software Engineering Lead",                                                 # lead
    "Cloud Solution Architect (Manager)",                                        # architect
    "Senior Solutions Integration Architect, DxD Hub",                          # architect
    "Principal Architect",                                                       # principal + architect
    "Solution Architect / Implementation Manager",                               # architect
    "Solution Architect",                                                        # architect
    "Aviation Cloud Solutions Architect (AVS Innovation Lab)",                   # architect
    "Principal Enterprise Architect",                                            # principal + architect
    "Solution Architect, Broadcom Software",                                     # architect
    "Infrastructure Architect (AWS)",                                            # architect
    "Cloud Infrastructure Architect / Solutions Architect / Enterprise Architect", # architect
    "System Architect and Engineering Lead",                                     # architect + lead
    "Vice President, Cloud Architect",                                           # architect
    "Cloud Architect",                                                           # architect
])
def test_should_analyze_pass(title):
    assert should_analyze(title) is True, f"Expected PASS for: {title!r}"


# ---------------------------------------------------------------------------
# Should SKIP — no include pattern matches — real titles from LinkedIn feed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    # Real feed titles with no matching include pattern
    "Senior / Systems Engineer (Open Digital Platform)",
    "Senior System Engineer",
    "Software Engineering - C++, Systematic Trading, Equities",
    # NOTE: \bvp\b and solutions? engineer were removed from TITLE_INCLUDE;
    # these real titles are currently skipped by the filter.
    "VP of Engineering",
    "Assistant VP, Cloud Infrastructure Engineer (AWS / Azure / OpenShift)",
    "Solutions Engineer",
    "Solution Engineer",
    "Senior Solution Engineer - Cloud & AI Apps",
    # Generic no-match titles
    "Senior Software Engineer",
    "Backend Developer",
    "DevOps Engineer",
    "Data Engineer",
    "Engineering Manager",
])
def test_should_analyze_no_include(title):
    assert should_analyze(title) is False, f"Expected SKIP (no include) for: {title!r}"


# ---------------------------------------------------------------------------
# Should SKIP — include matched but exclude fired
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    "Lead Frontend Engineer",          # lead + frontend
    "Principal QA Engineer",           # principal + \bqa\b
    "Staff Mobile Developer",          # staff + mobile
    "Lead Android Developer",          # lead + android
    "Lead iOS Developer",              # lead + ios
    "Principal Java Developer",        # principal + java developer
    "Lead .NET Developer",             # lead + .net developer
    "Principal Data Analyst",          # principal + data analyst
    "Staff Product Manager",           # staff + product manager
    "VP of Marketing",                 # vp + marketing
    "VP of Sales",                     # vp + sales
    "Lead Mobile Architect",           # lead + mobile
])
def test_should_analyze_excluded(title):
    assert should_analyze(title) is False, f"Expected SKIP (excluded) for: {title!r}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title", [
    None,
    "",
    "(Unknown Title)",
])
def test_should_analyze_edge_cases(title):
    assert should_analyze(title) is False, f"Expected SKIP (edge case) for: {title!r}"


def test_vp_boundary():
    """'mvp' should NOT match the \\bvp\\b include pattern."""
    assert should_analyze("MVP Product Owner") is False


def test_case_insensitive():
    """Matching must be case-insensitive."""
    assert should_analyze("PRINCIPAL ENGINEER") is True
    assert should_analyze("lead FRONTEND engineer") is False
