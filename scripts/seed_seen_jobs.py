"""Seed seen_jobs.json from a previous run's plain-text output.

Parses the CONSOLIDATED RANKING section of main.py stdout (the same text
that is emailed after each run) and writes matching entries into seen_jobs.json
so those jobs are treated as already-analyzed on the next run.

Usage:
    # from a saved output file
    python seed_seen_jobs.py output.txt

    # from stdin (paste the email body)
    python seed_seen_jobs.py -

    # default: reads output.txt in current directory
    python seed_seen_jobs.py
"""

import json
import os
import re
import sys
from datetime import date
from typing import Optional

from core.seen_jobs import save_seen_jobs, MAX_AGE_DAYS, _id_from_url

# ── URL → dedup key (mirrors strategy ID extraction) ──────────────────────────

def _dedup_key_from_url(url: str) -> str:
    return _id_from_url(url)


# ── Output text parser ────────────────────────────────────────────────────────

# Matches the job header line — handles both formats:
#   current main.py:  "   1. [HIGH] Title"  or  "   2. [cached] [MEDIUM] Title"
#   legacy output:    "   1. HIGH Title"
_HEADER_RE = re.compile(
    r'^\s+\d+\.\s+(?:\[cached\]\s+)?\[?(?P<rank>HIGH|MEDIUM|LOW|SKIP)\]?\s+(?P<title>.+)$'
)

# Matches "Company | Score: 8/10 | Best Fit: principal_... | Platform: LinkedIn"
_META_RE = re.compile(
    r'^(?P<company>[^|]+)\|\s*Score:\s*(?P<score>[\d.]+)/10\s*\|\s*Best Fit:\s*(?P<best_fit>\S+)\s*\|\s*Platform:\s*(?P<platform>.+)$'
)

# Matches "Tech:... Exp:... Domain:... Role:..."
_TECH_RE = re.compile(
    r'Tech:(?P<tech>.*?)\s+Exp:(?P<exp>.*?)\s+Domain:(?P<domain>.*?)\s+Role:(?P<role>.+)'
)

# Matches "Gaps: a, b, c"
_GAPS_RE = re.compile(r'^Gaps:\s*(?P<gaps>.+)$')


def _parse_ranking(text: str) -> list[dict]:
    """Extract job result dicts from the CONSOLIDATED RANKING block."""
    # Locate the header line
    start = text.find('CONSOLIDATED RANKING')
    if start == -1:
        return []
    # Step past the 'CONSOLIDATED RANKING' line and its trailing === separator
    after_header = text.find('\n', start)          # end of header line
    if after_header == -1:
        return []
    sep_end = text.find('\n', after_header + 1)    # end of trailing === line
    section_start = sep_end + 1 if sep_end != -1 else after_header + 1
    # Content ends at next ===-style separator (JD NOT FOUND section) or EOF
    end_match = re.search(r'\n={3,}', text[section_start:])
    section = text[section_start: section_start + end_match.start()] if end_match else text[section_start:]

    jobs = []
    current: Optional[dict] = None

    for raw_line in section.splitlines():
        line = raw_line.strip()

        m = _HEADER_RE.match(raw_line)
        if m:
            if current and current.get('_url'):
                jobs.append(current)
            current = {
                'rank':    m.group('rank'),
                'title':   m.group('title').strip(),
                # fields filled in as we read subsequent lines
                'score': None, 'best_fit': '', 'tech': '', 'exp': '',
                'domain': '', 'role': '', 'technical_gaps': [], 'verdict': '',
                '_url': '', '_jd_url': '', '_company': '', '_platform': '',
            }
            continue

        if current is None:
            continue

        # Company / score / platform line
        m = _META_RE.match(line)
        if m:
            current['_company']  = m.group('company').strip()
            current['score']     = int(m.group('score')) if m.group('score').isdigit() else m.group('score')
            current['best_fit']  = m.group('best_fit').strip()
            current['_platform'] = m.group('platform').strip()
            continue

        # Tech / exp / domain / role line
        m = _TECH_RE.match(line)
        if m:
            current['tech']   = m.group('tech').strip()
            current['exp']    = m.group('exp').strip()
            current['domain'] = m.group('domain').strip()
            current['role']   = m.group('role').strip()
            continue

        # Gaps line
        m = _GAPS_RE.match(line)
        if m:
            current['technical_gaps'] = [g.strip() for g in m.group('gaps').split(',')]
            continue

        # URL line
        if line.startswith('http'):
            if not current['_url']:
                current['_url'] = line
            continue

        # JD URL line
        if line.startswith('JD: http'):
            current['_jd_url'] = line[4:].strip()
            continue

        # Anything left that is non-empty is the verdict
        if line and not line.startswith('='):
            if current['verdict']:
                current['verdict'] += ' ' + line
            else:
                current['verdict'] = line

    if current and current.get('_url'):
        jobs.append(current)

    return jobs


def _to_result_dict(job: dict) -> dict:
    """Shape the parsed job into the seen_jobs result format."""
    return {
        'rank':           job['rank'],
        'score':          job['score'],
        'best_fit':       job['best_fit'],
        'tech':           job['tech'],
        'exp':            job['exp'],
        'domain':         job['domain'],
        'role':           job['role'],
        'technical_gaps': job['technical_gaps'],
        'verdict':        job['verdict'],
        '_title':         job['title'],
        '_company':       job['_company'],
        '_url':           job['_url'],
        '_jd_url':        job['_jd_url'],
        '_platform':      job['_platform'],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

SEEN_PATH = 'data/seen_jobs.json'


def main():
    # Determine input source
    if len(sys.argv) > 1:
        src = sys.argv[1]
    else:
        src = 'output.txt'

    if src == '-':
        text = sys.stdin.read()
    else:
        if not os.path.exists(src):
            print(f"Error: file not found: {src}", file=sys.stderr)
            sys.exit(1)
        with open(src, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()

    jobs = _parse_ranking(text)
    if not jobs:
        print("No jobs found in CONSOLIDATED RANKING section.")
        sys.exit(0)

    # Load existing seen_jobs (to merge, not overwrite)
    if os.path.exists(SEEN_PATH):
        with open(SEEN_PATH, 'r', encoding='utf-8') as f:
            seen = json.load(f)
    else:
        seen = {}

    today = date.today().isoformat()
    added = 0
    skipped = 0

    for job in jobs:
        key = _dedup_key_from_url(job['_url'])
        if not key:
            print(f"  WARN: could not derive key for '{job['title']}' — skipped")
            continue
        if key in seen:
            print(f"  skip (already in cache): {job['title']}")
            skipped += 1
        else:
            seen[key] = {'seen_at': today, 'result': _to_result_dict(job)}
            print(f"  added [{job['rank']}] {job['title']} ({key})")
            added += 1

    save_seen_jobs(SEEN_PATH, seen)
    print(f"\nDone -- {added} added, {skipped} already cached -> {SEEN_PATH}")


if __name__ == '__main__':
    main()
