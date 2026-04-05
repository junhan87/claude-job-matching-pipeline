import re
from urllib.parse import urlparse, unquote
from bs4 import BeautifulSoup
from .base import JobAlertStrategy
from core.config import MCF_JOB_API_URL
from core.stats import stats

# Legal entity suffixes common in Singapore company names
_COMPANY_SUFFIX_RE = re.compile(
    r'\b(pte\.?\s*ltd\.?|pte\.?\s*limited|sdn\.?\s*bhd\.?|co\.?\s*ltd\.?'
    r'|inc\.?|llc\.?|corp\.?|ltd\.?)\b',
    re.I,
)

_SKIP_CELLS = frozenset({
    'Strong applicant', 'Recently posted', 'Profile salary match',
    'Apply', 'Apply now', 'View job', 'See more jobs',
    'Unsubscribe', 'Manage alerts',
})


def _is_salary_text(text):
    """Return True if text looks like a salary range rather than a job title."""
    return bool(re.search(r'\$\s*\d', text) or re.search(r'\d[\d,]+\s*/\s*mth', text, re.I))


def _looks_like_company(text):
    """Return True if text looks like a company name rather than a job title."""
    return bool(_COMPANY_SUFFIX_RE.search(text))


def _company_to_slug(company_name):
    """Convert a company name to a URL-slug form, stripping legal suffixes."""
    name = _COMPANY_SUFFIX_RE.sub('', company_name)
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def _title_from_url(mcf_url, company_name):
    """Derive job title from MCF URL slug by removing the company slug portion.

    MCF URL path: /job/{category}/{title-slug}-{company-slug}-{32hexhash}
    """
    path = urlparse(mcf_url).path
    last_seg = path.split('/')[-1]
    m = re.match(r'^(.*)-([0-9a-f]{32})$', last_seg)
    if not m:
        return ''
    base = m.group(1)
    company_slug = _company_to_slug(company_name)
    if company_slug and base.endswith('-' + company_slug):
        title_slug = base[:-(len(company_slug) + 1)]
    else:
        title_slug = base
    return title_slug.replace('-', ' ').title()


def _fetch_mcf_description(url: str, http_client) -> str:
    """Fetch job description from the MCF public JSON API using the UUID in the URL."""
    m = re.search(r'-([0-9a-f]{32})(?:[/?#].*)?$', url)
    if not m or http_client is None:
        return ''
    uuid = m.group(1)
    api_url = MCF_JOB_API_URL.format(uuid=uuid)
    try:
        stats.start('mcf_jd_fetch')
        resp = http_client.get(api_url, headers={'Accept': 'application/json'})
        stats.stop('mcf_jd_fetch')
        data = resp.json()
        html_desc = data.get('description', '')
        if not html_desc:
            return ''
        soup = BeautifulSoup(html_desc, 'html.parser')
        text = soup.get_text(separator='\n').strip()
        skills = data.get('skills', [])
        if skills:
            skill_names = [
                s.get('skill', str(s)) if isinstance(s, dict) else str(s)
                for s in skills
            ]
            text = f"Required Skills: {', '.join(skill_names)}\n\n" + text
        return text[:8000]
    except Exception:
        if 'mcf_jd_fetch' in getattr(stats._local, 'starts', {}):
            stats.stop('mcf_jd_fetch')
        return ''


def _parse_job_card(anchor):
    """Walk up the DOM from an MCF anchor and extract location and salary."""
    result = {'location': '', 'salary': ''}

    # Walk up to the nearest table-row or tbody that contains the whole card
    node = anchor.parent
    container = None
    for _ in range(10):
        if node is None:
            break
        if node.name in ('tr', 'tbody', 'table', 'td'):
            container = node
            # Keep walking up past a single <td> to get the full row
            if node.name == 'td' and node.parent:
                container = node.parent
            break
        node = node.parent

    if container is None:
        return result

    text = re.sub(r'\s+', ' ', container.get_text(separator=' ')).strip()

    # Salary: "$X,XXX – $Y,XXX per month" / "$Xk - $Yk p.m." etc.
    m = re.search(
        r'(\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?[^<\n]{0,40}?(?:per\s+month|/\s*mth|p\.m\.)?)',
        text, re.I,
    )
    if m:
        result['salary'] = m.group(1).strip().rstrip('.,')

    # Location: Singapore region names, optionally followed by work arrangement
    m = re.search(
        r'([A-Z][a-zA-Z\s,\-]+(?:Region|Singapore)(?:\s*\([A-Za-z\s]+\))?)',
        text,
    )
    if m:
        result['location'] = m.group(1).strip()

    return result


class MCFStrategy(JobAlertStrategy):
    name = 'MyCareersFuture'
    email_query = 'from:job-alerts@mycareersfuture.gov.sg'
    max_results = 5
    start_anchors = ['matches your alert preferences.']
    end_anchors = ['If you have a question, contact us']
    blacklist = []

    def _extract_job_urls(self, soup, http_client=None) -> dict:
        mcf_candidates = {}
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            decoded_href = unquote(href)
            anchor_text = a.get_text(strip=True)
            match = re.search(
                r'(https?://(?:www\.)?mycareersfuture\.gov\.sg/job/[^?&#\s]+)',
                decoded_href,
            )
            if not match:
                continue
            mcf_url = match.group(1).rstrip('/')
            job_id = mcf_url.split('/')[-1]
            if job_id not in mcf_candidates:
                mcf_candidates[job_id] = {
                    'url': mcf_url,
                    'titles': [],
                    'companies': [],
                    'anchor': a,
                }
            if anchor_text:
                if _looks_like_company(anchor_text):
                    mcf_candidates[job_id]['companies'].append(anchor_text)
                else:
                    mcf_candidates[job_id]['titles'].append(anchor_text)

        job_urls = {}
        for job_id, data in mcf_candidates.items():
            company = data['companies'][0] if data['companies'] else ''

            good_titles = [t for t in data['titles'] if not _is_salary_text(t) and t not in _SKIP_CELLS]
            if good_titles:
                title = good_titles[0]
            elif company:
                title = _title_from_url(data['url'], company)
            else:
                seg = data['url'].split('/')[-1]
                m = re.match(r'^(.*)-[0-9a-f]{32}$', seg)
                title = m.group(1).replace('-', ' ').title() if m else ''

            card = _parse_job_card(data['anchor'])
            description = _fetch_mcf_description(data['url'], http_client)

            job_urls[job_id] = {
                'url': data['url'],
                'title': title,
                'company': company,
                'location': card['location'],
                'salary': card['salary'],
                'description': description,
            }

        return job_urls
