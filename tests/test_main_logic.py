"""Tests for main.py logic functions: print_ranking and print_jobs.

No API key or network access required.
A dummy ANTHROPIC_API_KEY is set before importing main to prevent the Anthropic
SDK from raising AuthenticationError at module-import time.

Run with:  python -m pytest tests/test_main_logic.py -v
"""

import os
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy-key")  # noqa: E402

import pytest
from main import print_ranking, print_jobs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(title, rank, score, company="Acme", platform="LinkedIn"):
    return {
        "_title":    title,
        "_company":  company,
        "_url":      "https://example.com",
        "_platform": platform,
        "rank":      rank,
        "score":     score,
    }


# ---------------------------------------------------------------------------
# print_ranking — sort order
# ---------------------------------------------------------------------------

def test_print_ranking_order_high_before_medium_before_low_before_skip(capsys):
    results = [
        _make_result("Job LOW",    "LOW",    7),
        _make_result("Job HIGH",   "HIGH",   9),
        _make_result("Job MEDIUM", "MEDIUM", 8),
        _make_result("Job SKIP",   "SKIP",   1),
    ]
    print_ranking(results)
    titles = [r["_title"] for r in results]
    assert titles == ["Job HIGH", "Job MEDIUM", "Job LOW", "Job SKIP"]


def test_print_ranking_same_rank_sorted_by_score_desc(capsys):
    results = [
        _make_result("Score 6", "HIGH", 6),
        _make_result("Score 9", "HIGH", 9),
        _make_result("Score 7", "HIGH", 7),
    ]
    print_ranking(results)
    titles = [r["_title"] for r in results]
    assert titles == ["Score 9", "Score 7", "Score 6"]


def test_print_ranking_unknown_rank_treated_as_skip(capsys):
    results = [
        _make_result("Unknown Rank", "UNKNOWN", 5),
        _make_result("High Rank",    "HIGH",    5),
    ]
    print_ranking(results)
    assert results[0]["_title"] == "High Rank"
    assert results[1]["_title"] == "Unknown Rank"


def test_print_ranking_none_score_does_not_crash(capsys):
    results = [_make_result("No Score", "HIGH", None)]
    print_ranking(results)  # should not raise


def test_print_ranking_cached_tag_shown(capsys):
    results = [_make_result("Cached Job", "HIGH", 9)]
    results[0]["_cached"] = True
    print_ranking(results)
    out = capsys.readouterr().out
    assert "[cached]" in out


# ---------------------------------------------------------------------------
# print_jobs — salary filter
# ---------------------------------------------------------------------------

def _make_job(title, salary="", url="https://www.linkedin.com/jobs/view/1"):
    return {"title": title, "company": "Acme", "location": "SG", "salary": salary, "url": url}


def test_print_jobs_salary_below_threshold_skipped(capsys):
    jobs = {"LinkedIn": [_make_job("Cloud Architect", salary="$2,000")]}
    to_analyze, cached = print_jobs(jobs, do_analyze=True, min_salary=5000, seen={})
    out = capsys.readouterr().out
    assert "skipped — salary" in out
    assert to_analyze == []
    assert cached == []


def test_print_jobs_no_salary_always_kept(capsys):
    jobs = {"LinkedIn": [_make_job("Cloud Architect", salary="")]}
    to_analyze, cached = print_jobs(jobs, do_analyze=True, min_salary=5000, seen={})
    # Job without salary must NOT be flagged as below-threshold
    out = capsys.readouterr().out
    assert "skipped — salary" not in out


# ---------------------------------------------------------------------------
# print_jobs — title filter
# ---------------------------------------------------------------------------

def test_print_jobs_title_filter_skips_non_matching(capsys):
    jobs = {"LinkedIn": [_make_job("Senior Software Engineer", salary="$8,000", url="https://www.linkedin.com/jobs/view/2")]}
    to_analyze, cached = print_jobs(jobs, do_analyze=True, min_salary=0, seen={})
    out = capsys.readouterr().out
    assert "skipped — title filter" in out
    assert to_analyze == []


def test_print_jobs_matching_title_queued_for_analysis(capsys):
    jobs = {"LinkedIn": [_make_job("Cloud Architect", salary="$8,000", url="https://www.linkedin.com/jobs/view/3")]}
    to_analyze, cached = print_jobs(jobs, do_analyze=True, min_salary=0, seen={})
    assert len(to_analyze) == 1
    assert to_analyze[0]["_title"] == "Cloud Architect"


# ---------------------------------------------------------------------------
# print_jobs — seen / cache path
# ---------------------------------------------------------------------------

def test_print_jobs_cached_job_not_re_queued(capsys):
    from datetime import date
    seen = {
        "3": {
            "seen_at": date.today().isoformat(),
            "result":  {"_title": "Cloud Architect", "_company": "Acme",
                        "_url": "u", "_platform": "LinkedIn", "rank": "HIGH", "score": 9},
        }
    }
    jobs = {"LinkedIn": [_make_job("Cloud Architect", salary="$8,000", url="https://www.linkedin.com/jobs/view/3")]}
    to_analyze, cached = print_jobs(jobs, do_analyze=True, min_salary=0, seen=seen)
    out = capsys.readouterr().out
    assert "cached result" in out
    assert to_analyze == []
    assert len(cached) == 1


# ---------------------------------------------------------------------------
# print_jobs — analyze=False means no title filtering
# ---------------------------------------------------------------------------

def test_print_jobs_no_analyze_skips_title_filter(capsys):
    """Without --analyze, title filter is never applied."""
    jobs = {"LinkedIn": [_make_job("Senior Software Engineer", salary="$8,000", url="https://www.linkedin.com/jobs/view/4")]}
    to_analyze, cached = print_jobs(jobs, do_analyze=False, min_salary=0, seen={})
    out = capsys.readouterr().out
    assert "skipped — title filter" not in out
    assert to_analyze == []  # no AI job when analyze=False
