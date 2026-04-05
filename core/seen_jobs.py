"""Persistent cross-run job deduplication with cached analysis results.

seen_jobs.json format:
{
  "<dedup_key>": {
    "seen_at": "YYYY-MM-DD",
    "result": { ...full parsed analysis dict including _title, _company, _url, _platform... }
  }
}

Entries older than MAX_AGE_DAYS are pruned on load.
"""

import json
import os
import re
from datetime import date, timedelta
from typing import Optional

MAX_AGE_DAYS = 30

# Platform-specific ID extraction from URLs (same patterns used by strategy parsers)
_LI_RE  = re.compile(r'/jobs/view/(\d+)')
_MCF_RE = re.compile(r'-([0-9a-f]{32})(?:[/?#]|$)')
_JS_RE  = re.compile(r'jobstreet\.com/job/(\d+)')


def _id_from_url(url: str) -> str:
    """Extract the platform-specific numeric/UUID job ID from a URL, or return the full URL."""
    m = _LI_RE.search(url)
    if m:
        return m.group(1)
    m = _MCF_RE.search(url)
    if m:
        return m.group(1)
    m = _JS_RE.search(url)
    if m:
        return m.group(1)
    return url


def get_dedup_key(job: dict) -> str:
    """Return the canonical dedup key for a job.

    Prefers the strategy-set _id when it is a real platform ID (not a pseudo
    u_ hash). Falls back to extracting the ID from the job URL so that
    LinkedIn/MCF jobs (which don't set _id) still match correctly.
    """
    _id = job.get('_id', '')
    if _id and not _id.startswith('u_'):
        return _id
    url = job.get('url', '')
    if url:
        return _id_from_url(url)
    return _id


def load_seen_jobs(path: str) -> dict:
    """Load seen_jobs.json, prune stale entries, and return the dict.

    Returns an empty dict if the file is missing or unreadable.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    cutoff = (date.today() - timedelta(days=MAX_AGE_DAYS)).isoformat()
    pruned = {k: v for k, v in data.items() if v.get('seen_at', '') >= cutoff}
    return pruned


def save_seen_jobs(path: str, seen: dict) -> None:
    """Atomically write seen dict to path (write to .tmp then os.replace)."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def is_seen(job: dict, seen: dict) -> bool:
    """Return True if this job's dedup key exists in seen."""
    key = get_dedup_key(job)
    return bool(key) and key in seen


def get_cached_result(job: dict, seen: dict) -> Optional[dict]:
    """Return a copy of the stored analysis result dict, or None if not found."""
    key = get_dedup_key(job)
    entry = seen.get(key)
    if entry and 'result' in entry:
        return dict(entry['result'])
    return None


def mark_seen(job: dict, seen: dict, result: dict) -> None:
    """Record a successfully analyzed job with its full result dict."""
    key = get_dedup_key(job)
    if not key:
        return
    seen[key] = {
        'seen_at': date.today().isoformat(),
        'result': result,
    }
