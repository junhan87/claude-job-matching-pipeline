from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
import quopri
import re


class JobAlertStrategy(ABC):
    """Abstract base class for job alert email parsing strategies."""

    name: str = ''
    email_query: str = ''
    max_results: int = 5
    start_anchors: list = None
    end_anchors: list = None
    blacklist: list = None
    subject_pattern: re.Pattern = None  # if set, only process emails whose subject matches

    @abstractmethod
    def _extract_job_urls(self, soup, http_client) -> dict:
        """Extract job URLs from parsed HTML.

        Returns a dict of {job_id: {'url': str, 'title': str, ...}}.
        """
        ...

    def extract_jobs(self, html_content: str, http_client=None) -> dict:
        """Parse raw email HTML and return cleaned text and job URLs.

        Returns:
            {
                'text':     str,   # cleaned plain-text preview
                'job_urls': list,  # [{'url': str, 'title': str, ...}, ...]
            }
        """
        html_content = quopri.decodestring(
            html_content.encode('utf-8')
        ).decode('utf-8', errors='replace')

        soup = BeautifulSoup(html_content, 'html.parser')

        job_urls = self._extract_job_urls(soup, http_client)

        for element in soup(['script', 'style', 'meta', 'link', 'noscript', 'header', 'footer']):
            element.decompose()

        text = soup.get_text(separator=' ')
        text = re.sub(r'[^\x20-\x7E]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        for anchor in (self.start_anchors or []):
            if anchor in text:
                text = text.split(anchor, 1)[-1]
                break

        for anchor in (self.end_anchors or []):
            if anchor in text:
                text = text.split(anchor, 1)[0]
                break

        for word in (self.blacklist or []):
            text = text.replace(word, '')

        return {'text': text.strip(), 'job_urls': list(job_urls.values())}
