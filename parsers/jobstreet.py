import re
import hashlib
from bs4 import BeautifulSoup
from .base import JobAlertStrategy
from core.stats import stats

try:
    from curl_cffi import requests as cffi_requests
    _CURL_CFFI_AVAILABLE = True
except ImportError:
    _CURL_CFFI_AVAILABLE = False


def fetch_jd(url: str):
    """Fetch a Jobstreet job page using curl_cffi Chrome impersonation.

    Returns up to 8000 chars of cleaned plain text, or None if unavailable.
    """
    if not _CURL_CFFI_AVAILABLE:
        return None
    try:
        stats.start('jobstreet_jd_fetch')
        resp = cffi_requests.get(url, impersonate="chrome", timeout=15, allow_redirects=True)
        stats.stop('jobstreet_jd_fetch')
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'noscript']):
            tag.decompose()
        text = re.sub(r'\n{3,}', '\n\n', soup.get_text(separator='\n').strip())
        return text[:8000]
    except Exception:
        if 'jobstreet_jd_fetch' in getattr(stats._local, 'starts', {}):
            stats.stop('jobstreet_jd_fetch')
        return None

_CANON_URL_RE = re.compile(r'(https?://[a-z]{2}\.jobstreet\.com/job/(\d+))')

_SKIP_CELLS = frozenset({
    'Strong applicant', 'Recently posted', 'Profile salary match',
    'World Class Benefits', 'View job', "I'm not interested",
    'Unsubscribe', 'Yes', 'No',
})

# Prefixes that indicate a cell is noise or concatenated job-card noise
_NOISE_PREFIXES = (
    'Strong applicant', 'Recently posted', 'Profile salary match',
    'World Class Benefits',
)

# Keywords that identify footer / navigation anchors (not job listings).
# Checked against both the raw anchor text and the resolved card title.
_FOOTER_KEYWORDS = (
    'Unsubscribe', 'This email was sent', 'Edit frequency',
    'Privacy', 'Contact us', 'registered user',
    'career advice', 'View more jobs',
)


def _resolve_jobstreet_url(redirect_url, http_client):
    """Follow a Jobstreet redirect and return the canonical job URL, or None."""
    try:
        stats.start('jobstreet_url_resolve')
        resp = http_client.get(redirect_url, follow_redirects=True, timeout=10)
        stats.stop('jobstreet_url_resolve')
        final = str(resp.url)
        m = _CANON_URL_RE.search(final)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        if 'jobstreet_url_resolve' in getattr(stats._local, 'starts', {}):
            stats.stop('jobstreet_url_resolve')
    return None, None


def _parse_tds(tds):
    """Extract structured job fields from a list of <td> elements.

    Returns a dict with keys: title, company (opt), location (opt),
    salary (opt).
    """
    seen = set()
    cells = []
    for td in tds:
        text = re.sub(r'\s+', ' ', td.get_text(separator=' ', strip=True)).strip()
        if not text or len(text) > 80:
            continue
        # Skip cells that are (or start with) a known noise label — handles
        # the case where Jobstreet prepends a badge-like label to the title td.
        if any(text.startswith(p) for p in _NOISE_PREFIXES):
            continue
        if text in _SKIP_CELLS:
            continue
        if text in seen:
            continue
        seen.add(text)
        cells.append(text)

    out = {}
    if cells:
        out['title'] = cells[0]
    if len(cells) >= 2:
        out['company'] = cells[1]
    if len(cells) >= 3:
        out['location'] = cells[2]
    for cell in cells[3:]:
        if cell.startswith('$') or re.match(r'\$[\d,]', cell):
            out['salary'] = cell
            break
    return out


class JobStreetStrategy(JobAlertStrategy):
    name = 'Jobstreet'
    email_query = 'from:noreply@e.jobstreet.com'
    max_results = 5
    start_anchors = []
    end_anchors = []
    blacklist = []

    def _extract_job_urls(self, soup, http_client=None) -> dict:
        job_urls = {}
        seen_ids = set()

        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if 'url.jobstreet.com' not in href:
                continue
            title_text = a.get_text(strip=True)
            if not title_text or title_text in _SKIP_CELLS:
                continue
            # Filter footer / navigation links that are not job listings
            if any(kw in title_text for kw in _FOOTER_KEYWORDS):
                continue

            # Resolve canonical URL via HTTP redirect
            clean_url, job_id = None, None
            if http_client:
                clean_url, job_id = _resolve_jobstreet_url(href, http_client)

            # Fallback: scan nearby HTML text for a canonical URL
            if not job_id:
                node = a.parent
                for _ in range(8):
                    if node is None:
                        break
                    m = _CANON_URL_RE.search(node.get_text())
                    if m:
                        job_id, clean_url = m.group(2), m.group(1)
                        break
                    node = node.parent

            # Parse card data before the job_id check so we can build a
            # content-based pseudo-ID when URL resolution is blocked.
            inner_table = a.find('table')
            if inner_table:
                card = _parse_tds(inner_table.find_all('td'))
            else:
                card = {}
                node = a.parent
                for _ in range(6):
                    if node is None:
                        break
                    if node.name == 'tbody':
                        card = _parse_tds(node.find_all('td'))
                        break
                    node = node.parent

            if not card.get('title'):
                card['title'] = title_text

            # Reject footer/nav entries based on the resolved card title too
            if any(kw in card['title'] for kw in _FOOTER_KEYWORDS):
                continue

            # When canonical resolution fails (e.g. corporate proxy blocks it),
            # derive a pseudo-ID from title+company so the job is still listed.
            if not job_id:
                key = f"{card.get('title','').lower()}|{card.get('company','').lower()}"
                if not key.strip('|'):
                    continue
                job_id = 'u_' + hashlib.md5(key.encode()).hexdigest()[:12]
                clean_url = href  # tracking URL as display link

            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            job_urls[job_id] = {'url': clean_url, '_id': job_id, **card}

        return job_urls
