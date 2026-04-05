import re
from urllib.parse import urlparse, urlunparse, unquote
from .base import JobAlertStrategy


def _clean_job_url(url):
    """Strip tracking parameters and normalise to canonical job URL.

    LinkedIn email links use /comm/jobs/view/<id>/ while the canonical
    public URL is /jobs/view/<id>/ — normalise both to the latter.
    """
    parsed = urlparse(url)
    path = re.sub(r'^/comm/', '/', parsed.path)
    path = path.rstrip('/') if path != '/' else path
    return urlunparse((parsed.scheme, parsed.netloc, path, '', '', ''))


class LinkedInStrategy(JobAlertStrategy):
    name = 'LinkedIn'
    email_query = 'from:jobalerts-noreply@linkedin.com'
    max_results = 10
    start_anchors = ['New jobs match your alert']
    end_anchors = ['Edit alert Stand out and let hirers']
    blacklist = [
        'Manage alerts', 'Privacy Policy', 'Help Center',
        'User Agreement', 'Account Settings', 'View Job',
        'View All Matches Please do not reply to this computer-generated email',
    ]
    # LinkedIn changed their subject format (no longer uses smart-quoted titles).
    # The Gmail query already scopes to jobalerts-noreply@linkedin.com, so no
    # additional subject filtering is needed.
    subject_pattern = None

    def _extract_job_urls(self, soup, http_client=None) -> dict:
        job_urls = {}

        # Extract preheader snippet — LinkedIn includes a JD preview for the first job only
        preheader_snippet = ''
        preheader_div = soup.find(attrs={'data-email-preheader': True})
        if preheader_div:
            text = preheader_div.get_text(strip=True)
            # Format: "Company Title: Description snippet…"
            if ': ' in text:
                preheader_snippet = text.split(': ', 1)[1].rstrip('\u2026').strip()

        # Primary: structured job card extraction (extracts company + location)
        for card in soup.find_all('td', attrs={'data-test-id': 'job-card'}):
            title_a = card.find('a', class_=lambda c: c and 'font-bold' in c)
            if not title_a:
                continue
            href = title_a.get('href', '')
            decoded_href = unquote(href)
            match = re.search(r'(?:/comm)?/jobs/view/(\d+)', decoded_href)
            if not match:
                continue
            job_id = match.group(1)
            clean_url = _clean_job_url(decoded_href)
            title = title_a.get_text(strip=True)

            company = ''
            location = ''
            meta_p = card.find('p', class_=lambda c: c and 'text-system-gray-100' in c)
            if meta_p:
                meta_text = meta_p.get_text(strip=True)
                if '\u00b7' in meta_text:  # &middot; separator between company and location
                    parts = meta_text.split('\u00b7', 1)
                    company = parts[0].strip()
                    location = parts[1].strip()

            if job_id not in job_urls:
                job_urls[job_id] = {
                    'url': clean_url, 'title': title,
                    'company': company, 'location': location,
                }

        # Fallback: plain link scan (no company/location)
        if not job_urls:
            for a in soup.find_all('a', href=True):
                href = a.get('href', '')
                decoded_href = unquote(href)
                title_text = a.get_text(strip=True)
                match = re.search(r'(?:/comm)?/jobs/view/(\d+)', decoded_href)
                if match:
                    job_id = match.group(1)
                    clean_url = _clean_job_url(decoded_href)
                    if job_id not in job_urls or title_text:
                        job_urls[job_id] = {'url': clean_url, 'title': title_text}

        # Attach preheader snippet to the first job only
        if preheader_snippet and job_urls:
            first_id = next(iter(job_urls))
            job_urls[first_id]['description'] = preheader_snippet

        return job_urls
