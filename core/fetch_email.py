import warnings
import os
import sys
import json
import argparse
import httpx
from collections import defaultdict
warnings.filterwarnings("ignore", category=FutureWarning)

# Ensure stdout handles Unicode (e.g. CJK chars in job titles) on Windows consoles
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os.path
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from parsers import STRATEGIES
from core.http_utils import build_ssl_context
from core.stats import stats

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r', encoding='utf-8') as f:
                token_data = json.load(f)
        except (UnicodeDecodeError, ValueError):
            with open('token.json', 'r', encoding='latin-1') as f:
                token_data = json.load(f)
        creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w', encoding='utf-8') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)

def _iter_html_parts(part):
    """Recursively yield base64-encoded HTML parts from a Gmail message payload."""
    if part.get('mimeType') == 'text/html':
        data = part.get('body', {}).get('data')
        if data:
            yield data
    for sub in part.get('parts', []):
        yield from _iter_html_parts(sub)


def collect_jobs(platforms, days, verbose=False):
    """Fetch job alerts and return them as a dict keyed by strategy name.

    Returns:
        dict[str, list[dict]]: {strategy_name: [job_dict, ...]}
    """
    service = get_gmail_service()
    http_client = httpx.Client(verify=build_ssl_context())

    all_messages = []
    for platform_id in platforms:
        strategy = STRATEGIES[platform_id]
        query = f'{strategy.email_query} newer_than:{days}d'
        if verbose:
            print(f'[verbose] {strategy.name}: querying Gmail: {query!r}')
        stats.start(f'{strategy.name}_email_fetch')
        results = service.users().messages().list(userId='me', q=query, maxResults=strategy.max_results).execute()
        stats.stop(f'{strategy.name}_email_fetch')
        msgs = results.get('messages', [])
        if verbose:
            print(f'[verbose] {strategy.name}: {len(msgs)} message(s) returned')
        for msg in msgs:
            all_messages.append((strategy, msg['id']))

    if not all_messages:
        return {}

    platform_messages = defaultdict(list)
    for strategy, msg_id in all_messages:
        platform_messages[strategy].append(msg_id)

    all_jobs = {}
    for strategy, msg_ids in platform_messages.items():
        seen_jobs = {}  # dedup_key -> job dict, deduplicated across emails
        for msg_id in msg_ids:
            stats.start(f'{strategy.name}_email_fetch')
            message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            stats.stop(f'{strategy.name}_email_fetch')
            payload = message['payload']

            # Skip emails whose subject doesn't match the strategy's subject filter
            if strategy.subject_pattern is not None:
                headers = payload.get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
                if not strategy.subject_pattern.search(subject):
                    if verbose:
                        print(f'[verbose] {strategy.name}: SKIP msg {msg_id} — subject filter mismatch: {subject!r}')
                    continue
                if verbose:
                    print(f'[verbose] {strategy.name}: PASS msg {msg_id} — subject: {subject!r}')
            elif verbose:
                print(f'[verbose] {strategy.name}: processing msg {msg_id} (no subject filter)')

            for data in _iter_html_parts(payload):
                html_content = base64.urlsafe_b64decode(data).decode('utf-8')
                stats.start(f'{strategy.name}_parse')
                result = strategy.extract_jobs(html_content, http_client=http_client)
                stats.stop(f'{strategy.name}_parse')
                if verbose:
                    print(f'[verbose] {strategy.name}: extracted {len(result["job_urls"])} job(s) from msg {msg_id}')
                for job in result['job_urls']:
                    # Prefer content-based _id (survives cross-email dedup when
                    # canonical URLs are not resolvable), then fall back to url.
                    dedup_key = job.get('_id') or job.get('url', '')
                    if dedup_key and dedup_key not in seen_jobs:
                        seen_jobs[dedup_key] = job
        all_jobs[strategy.name] = list(seen_jobs.values())

    return all_jobs


def fetch_latest_job_alerts(platforms, days):
    all_jobs = collect_jobs(platforms, days)

    if not all_jobs:
        print("No new job alerts found.")
        return

    for strategy_name, jobs in all_jobs.items():
        print(f"\n=== {strategy_name} — {len(jobs)} unique jobs ===")
        if jobs:
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
                print(f"       {url}")
        else:
            print("  (no jobs extracted)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch job alert emails.')
    parser.add_argument(
        '--platform', '-p',
        type=int,
        nargs='+',
        choices=list(STRATEGIES.keys()),
        default=list(STRATEGIES.keys()),
        metavar='PLATFORM',
        help='Platforms to fetch: 0=LinkedIn, 1=MyCareersFuture, 2=Jobstreet (default: all)',
    )
    parser.add_argument(
        '--days', '-d',
        type=int,
        default=5,
        help='How many days back to fetch (default: 5)',
    )
    args = parser.parse_args()
    fetch_latest_job_alerts(platforms=args.platform, days=args.days)