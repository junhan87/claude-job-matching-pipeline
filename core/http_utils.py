import re
import ssl
import sys
import certifi
from bs4 import BeautifulSoup


def _parse_html(html: str) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'noscript']):
        tag.decompose()
    text = soup.get_text(separator='\n')
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text[:8000]


def fetch_url_text(url: str, http_client) -> str:
    """Fetch a URL and return up to 8000 chars of cleaned plain text."""
    if 'jobstreet.com' in url:
        from parsers.jobstreet import fetch_jd
        result = fetch_jd(url)
        if result:
            return result

    try:
        resp = http_client.get(url)
        return _parse_html(resp.text)
    except Exception as e:
        return f"Error fetching URL: {e}"


def build_ssl_context():
    """Combine certifi bundle with Windows certificate store (handles corporate proxies).
    On non-Windows platforms, certifi alone is used."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    if sys.platform == "win32" and hasattr(ssl, "enum_certificates"):
        for store in ("CA", "ROOT"):
            for cert_data, encoding, _ in ssl.enum_certificates(store):
                if encoding == "x509_asn":
                    try:
                        ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(cert_data))
                    except ssl.SSLError:
                        pass
    return ctx
