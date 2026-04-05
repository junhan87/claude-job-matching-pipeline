"""Tests for core/seen_jobs.py.

No API key or network access required — file I/O uses pytest's tmp_path.
Run with:  python -m pytest tests/test_seen_jobs.py -v
"""

import json
import pytest
from datetime import date, timedelta

from core.seen_jobs import (
    get_dedup_key,
    load_seen_jobs,
    save_seen_jobs,
    is_seen,
    get_cached_result,
    mark_seen,
)


# ---------------------------------------------------------------------------
# get_dedup_key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("job,expected", [
    # LinkedIn job ID extracted from URL
    (
        {"url": "https://www.linkedin.com/jobs/view/1234567890"},
        "1234567890",
    ),
    # MCF job — 32-char hex UUID extracted from URL
    (
        {"url": "https://www.mycareersfuture.gov.sg/job/it/cloud-architect-acme-pte-ltd-abcdef1234567890abcdef1234567890"},
        "abcdef1234567890abcdef1234567890",
    ),
    # Jobstreet job ID extracted from URL (canonical format: {cc}.jobstreet.com)
    (
        {"url": "https://sg.jobstreet.com/job/9876543"},
        "9876543",
    ),
    # Explicit _id that is not a u_ hash takes precedence over URL
    (
        {"_id": "JS-999", "url": "https://www.jobstreet.com.sg/job/111"},
        "JS-999",
    ),
    # u_ prefix → fall back to URL-extracted ID
    (
        {"_id": "u_abc", "url": "https://www.linkedin.com/jobs/view/555"},
        "555",
    ),
    # No URL, no _id → empty string
    (
        {"url": ""},
        "",
    ),
])
def test_get_dedup_key(job, expected):
    assert get_dedup_key(job) == expected


# ---------------------------------------------------------------------------
# load_seen_jobs
# ---------------------------------------------------------------------------

def test_load_seen_jobs_missing_file(tmp_path):
    result = load_seen_jobs(str(tmp_path / "nonexistent.json"))
    assert result == {}


def test_load_seen_jobs_corrupt_json(tmp_path):
    p = tmp_path / "corrupt.json"
    p.write_text("not-valid-json")
    assert load_seen_jobs(str(p)) == {}


def test_load_seen_jobs_empty_object(tmp_path):
    p = tmp_path / "empty.json"
    p.write_text("{}")
    assert load_seen_jobs(str(p)) == {}


def test_load_prunes_entries_older_than_30_days(tmp_path):
    path = str(tmp_path / "seen.json")
    old_date   = (date.today() - timedelta(days=31)).isoformat()
    today_str  = date.today().isoformat()
    data = {
        "old_job": {"seen_at": old_date,  "result": {"_title": "Old"}},
        "new_job": {"seen_at": today_str, "result": {"_title": "New"}},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    loaded = load_seen_jobs(path)
    assert "old_job" not in loaded
    assert "new_job" in loaded


def test_load_keeps_entry_exactly_at_boundary(tmp_path):
    """An entry from exactly MAX_AGE_DAYS ago should still be kept (>= cutoff)."""
    path = str(tmp_path / "seen.json")
    boundary = (date.today() - timedelta(days=30)).isoformat()
    data = {"boundary_job": {"seen_at": boundary, "result": {}}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

    loaded = load_seen_jobs(path)
    assert "boundary_job" in loaded


# ---------------------------------------------------------------------------
# save_seen_jobs / roundtrip
# ---------------------------------------------------------------------------

def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "seen.json")
    data = {
        "12345": {
            "seen_at": date.today().isoformat(),
            "result":  {"_title": "Cloud Architect", "rank": "HIGH"},
        },
    }
    save_seen_jobs(path, data)
    loaded = load_seen_jobs(path)
    assert loaded == data


def test_save_is_atomic_tmp_file_removed(tmp_path):
    """save_seen_jobs must not leave a .tmp file behind."""
    path = str(tmp_path / "seen.json")
    save_seen_jobs(path, {})
    assert not (tmp_path / "seen.json.tmp").exists()


# ---------------------------------------------------------------------------
# is_seen
# ---------------------------------------------------------------------------

def test_is_seen_true():
    seen = {"12345": {"seen_at": date.today().isoformat(), "result": {}}}
    job = {"url": "https://www.linkedin.com/jobs/view/12345"}
    assert is_seen(job, seen) is True


def test_is_seen_false():
    job = {"url": "https://www.linkedin.com/jobs/view/99999"}
    assert is_seen(job, {}) is False


def test_is_seen_empty_key_returns_false():
    """A job with no URL and no _id produces an empty dedup key — never 'seen'."""
    assert is_seen({"url": ""}, {"": {}}) is False


# ---------------------------------------------------------------------------
# get_cached_result
# ---------------------------------------------------------------------------

def test_get_cached_result_returns_copy():
    original = {"_title": "Cloud Architect", "rank": "HIGH"}
    seen = {"12345": {"seen_at": date.today().isoformat(), "result": original}}
    job = {"url": "https://www.linkedin.com/jobs/view/12345"}

    cached = get_cached_result(job, seen)
    assert cached == original
    assert cached is not original  # must be a copy, not the same object


def test_get_cached_result_missing_key():
    assert get_cached_result({"url": "https://www.linkedin.com/jobs/view/99"}, {}) is None


def test_get_cached_result_entry_has_no_result_key():
    seen = {"12345": {"seen_at": date.today().isoformat()}}
    job = {"url": "https://www.linkedin.com/jobs/view/12345"}
    assert get_cached_result(job, seen) is None


# ---------------------------------------------------------------------------
# mark_seen
# ---------------------------------------------------------------------------

def test_mark_seen_records_key_and_date():
    seen = {}
    job = {"url": "https://www.linkedin.com/jobs/view/7777"}
    result = {"_title": "Architect", "rank": "HIGH"}

    mark_seen(job, seen, result)

    assert "7777" in seen
    assert seen["7777"]["result"] == result
    assert seen["7777"]["seen_at"] == date.today().isoformat()


def test_mark_seen_no_op_for_empty_key():
    """Jobs that produce an empty dedup key must not pollute the seen dict."""
    seen = {}
    mark_seen({"url": ""}, seen, {"_title": "X"})
    assert seen == {}
