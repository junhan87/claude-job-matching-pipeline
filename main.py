import warnings
import os
import sys
import argparse
import json
import re
import functools
import concurrent.futures
import certifi
import httpx
from anthropic import Anthropic
from dotenv import load_dotenv
from typing import NamedTuple, Optional

warnings.filterwarnings("ignore", category=FutureWarning)

# Ensure stdout handles Unicode (e.g. CJK chars in job titles) on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from core.fetch_email import collect_jobs
from parsers import STRATEGIES
from core.http_utils import build_ssl_context
from core.config import LINKEDIN, MCF, JOBSTREET, RESUME_PATH, should_analyze, salary_meets_threshold, parse_salary_min
from analyzers import ANALYZERS
from core.stats import stats
from core.seen_jobs import load_seen_jobs, save_seen_jobs, is_seen, get_cached_result, mark_seen

load_dotenv()


client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    http_client=httpx.Client(verify=build_ssl_context()),
)

http_client = httpx.Client(verify=build_ssl_context(), follow_redirects=True, timeout=15)


class AnalysisResult(NamedTuple):
    job: dict
    parsed: Optional[dict]
    error: Optional[str]


def load_file(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: {path} not found."


@functools.lru_cache(maxsize=1)
def _build_system_text() -> str:
    resume = load_file(RESUME_PATH)
    instruction = load_file("prompts/matching_instructions.md")
    return (
        "You are a Career Architect. Compare the Job Description (JD) against the provided resume "
        "and follow the matching instructions exactly.\n\n"
        f"<resume>\n{resume}\n</resume>\n\n"
        f"<instructions>\n{instruction}\n</instructions>\n\n"
        "OUTPUT: Return ONLY a JSON object matching the output format in the instructions."
    )



def analyze_job(job: dict) -> str:
    """Dispatch job analysis to the first matching AnalysisStrategy."""
    system_text = _build_system_text()
    stats.start('ai_analysis')
    try:
        for strategy in ANALYZERS:
            if strategy.matches(job):
                result = strategy.analyze(job, system_text, client, http_client)
                stats.stop('ai_analysis')
                return result
        stats.stop('ai_analysis')
        return ""
    except Exception:
        stats.stop('ai_analysis')
        raise



def run_analysis(
    jobs_to_analyze: list,
    seen: dict,
    limit: Optional[int],
) -> 'tuple[list[dict], list[dict]]':
    """Run parallel AI analysis; returns (analyzed_results, jd_not_found)."""
    if limit is not None:
        jobs_to_analyze = jobs_to_analyze[:limit]

    # Warm the lru_cache once on the main thread before workers start
    _build_system_text()

    def _analyze_one(job: dict) -> AnalysisResult:
        """Worker: analyze one job and return an AnalysisResult."""
        try:
            raw = analyze_job(job)
            clean = raw.strip()
            if clean.startswith('```'):
                clean = re.sub(r'^```[a-zA-Z]*\n?', '', clean)
                clean = re.sub(r'\n?```$', '', clean).strip()
            parsed = json.loads(clean)
            parsed.update({
                '_title':    job['_title'],
                '_company':  job['_company'],
                '_url':      job['_url'],
                '_jd_url':   job.get('_jd_url', ''),
                '_platform': job['_platform'],
            })
            mark_seen(job, seen, parsed)
            return AnalysisResult(job=job, parsed=parsed, error=None)
        except Exception as exc:
            return AnalysisResult(job=job, parsed=None, error=str(exc))

    analyzed_results: list = []
    jd_not_found: list = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for result in executor.map(_analyze_one, jobs_to_analyze):
            if result.parsed is None:
                print(f"       AI error ({result.job.get('_title', '')}): {(result.error or 'unknown error')[:200]}")
                continue
            analyzed_results.append(result.parsed)
            if result.job.get('_jd_missing'):
                jd_not_found.append({
                    'title':    result.job['_title'],
                    'company':  result.job['_company'],
                    'url':      result.job['_url'],
                    'platform': result.job['_platform'],
                })

    save_seen_jobs('data/seen_jobs.json', seen)
    return analyzed_results, jd_not_found


def print_jobs(
    all_jobs: dict,
    do_analyze: bool,
    min_salary: int,
    seen: dict,
) -> 'tuple[list[dict], list[dict]]':
    """Print Pass 1 job listings; return (jobs_to_analyze, cached_results)."""
    jobs_to_analyze: list = []
    cached_results: list = []

    for strategy_name, jobs in all_jobs.items():
        print(f"\n=== {strategy_name} — {len(jobs)} unique jobs ===")
        for i, job in enumerate(jobs, 1):
            title = job.get('title') or '(Unknown Title)'
            company = job.get('company', '')
            location = job.get('location', '')
            salary = job.get('salary', '')
            url = job.get('url') or '(URL not resolved)'

            meta_parts = [p for p in [company, location, salary] if p]
            meta = ' | '.join(meta_parts)

            print(f"  {i:2}. {title}")
            if meta:
                print(f"       {meta}")

            if not salary_meets_threshold(salary, min_salary):
                parsed_sal = parse_salary_min(salary)
                print(f"       (skipped — salary ${parsed_sal:,}/mth < ${min_salary:,}/mth threshold)")
                continue
            print(f"       {url}")

            if do_analyze:
                if not should_analyze(title):
                    print("       (skipped — title filter)")
                    continue
                # Store display metadata on the job dict for use after parallel analysis
                job['_title']    = title
                job['_company']  = company
                job['_url']      = url
                job['_platform'] = strategy_name
                if is_seen(job, seen):
                    cached = get_cached_result(job, seen)
                    if cached is not None:
                        cached['_cached'] = True
                        cached_results.append(cached)
                        print("       (cached result — skipping AI)")
                        continue
                jobs_to_analyze.append(job)

    return jobs_to_analyze, cached_results


def print_ranking(results: list) -> None:
    """Sort by rank/score and print the consolidated ranking table."""
    rank_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "SKIP": 3}
    results.sort(key=lambda x: (rank_order.get(x.get('rank', 'SKIP'), 3), -(float(x.get('score') or 0))))

    print("\n" + "=" * 60)
    print("  CONSOLIDATED RANKING")
    print("=" * 60)
    for i, r in enumerate(results, 1):
        score = r.get('score', 'N/A')
        try:
            score = float(score)
        except (TypeError, ValueError):
            pass
        rank = r.get('rank', 'N/A')
        tech = r.get('tech', '')
        exp = r.get('exp', '')
        domain = r.get('domain', '')
        role = r.get('role', '')
        gaps = r.get('technical_gaps', [])
        verdict = r.get('verdict', '')
        cached_tag = '[cached] ' if r.get('_cached') else ''
        print(f"\n  {i:2}. {cached_tag}[{rank}] {r['_title']}")
        print(f"       {r['_company']} | Score: {score}/10 | Platform: {r['_platform']}")
        if tech or exp or domain or role:
            print(f"       Tech:{tech} Exp:{exp} Domain:{domain} Role:{role}")
        if gaps:
            print(f"       Gaps: {', '.join(gaps[:3])}")
        if verdict:
            print(f"       {verdict}")
        print(f"       {r['_url']}")
        if r.get('_jd_url'):
            print(f"       JD: {r['_jd_url']}")


def main():
    parser = argparse.ArgumentParser(description='Fetch and analyze job alert emails.')
    parser.add_argument(
        '--platform', '-p',
        type=int,
        nargs='+',
        choices=list(STRATEGIES.keys()),
        default=list(STRATEGIES.keys()),
        metavar='PLATFORM',
        help=f'Platforms to fetch: {LINKEDIN}=LinkedIn, {MCF}=MyCareersFuture, {JOBSTREET}=Jobstreet (default: all)',
    )
    parser.add_argument(
        '--days', '-d',
        type=int,
        default=1,
        help='How many days back to fetch (default: 1)',
    )
    parser.add_argument(
        '--analyze', '-a',
        action='store_true',
        help='Score each job with Claude AI (default: list only)',
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        metavar='N',
        help='Debug: cap the number of jobs sent to the AI per platform (default: no limit)',
    )
    parser.add_argument(
        '--min-salary', '-s',
        type=int,
        default=0,
        metavar='SGD',
        help='Hide jobs whose listed salary minimum is below this monthly SGD amount (default: no filter)',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Print debug info: email counts, subject filter results, job counts per message',
    )
    args = parser.parse_args()

    stats.start('total')
    stats.start('email_collection')
    all_jobs = collect_jobs(platforms=args.platform, days=args.days, verbose=args.verbose)
    stats.stop('email_collection')

    if not all_jobs:
        print("No new job alerts found.")
        stats.stop('total')
        stats.summary()
        return

    seen = load_seen_jobs('data/seen_jobs.json') if args.analyze else {}

    jobs_to_analyze, analyzed_results = print_jobs(
        all_jobs, args.analyze, args.min_salary, seen
    )

    if args.analyze and jobs_to_analyze:
        new_results, jd_not_found = run_analysis(jobs_to_analyze, seen, args.limit)
        analyzed_results.extend(new_results)
    else:
        jd_not_found = []

    if args.analyze and analyzed_results:
        print_ranking(analyzed_results)

    stats.stop('total')
    stats.summary()

    if args.analyze and jd_not_found:
        print("\n" + "=" * 60)
        print("  JD NOT FOUND — manual check required")
        print("=" * 60)
        for i, j in enumerate(jd_not_found, 1):
            print(f"\n  {i:2}. {j['title']}")
            print(f"       {j['company']} | {j['platform']}")
            print(f"       {j['url']}")


if __name__ == "__main__":
    main()