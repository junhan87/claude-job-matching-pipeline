"""Tests for core/http_utils._parse_html.

No API key or network access required — pure HTML parsing.
Run with:  python -m pytest tests/test_http_utils.py -v
"""

from core.http_utils import _parse_html


def test_strips_script_tags():
    html = "<html><body><script>alert('xss')</script><p>Hello</p></body></html>"
    result = _parse_html(html)
    assert "alert" not in result
    assert "Hello" in result


def test_strips_style_tags():
    html = "<html><body><style>.a { color: red; }</style><p>Content</p></body></html>"
    result = _parse_html(html)
    assert ".a {" not in result
    assert "Content" in result


def test_strips_nav_header_footer():
    html = (
        "<html><body>"
        "<nav>Navigation</nav>"
        "<header>Page Header</header>"
        "<footer>Page Footer</footer>"
        "<main>Main Content</main>"
        "</body></html>"
    )
    result = _parse_html(html)
    assert "Navigation" not in result
    assert "Page Header" not in result
    assert "Page Footer" not in result
    assert "Main Content" in result


def test_strips_noscript():
    html = "<html><body><noscript>Please enable JS</noscript><p>Real content</p></body></html>"
    result = _parse_html(html)
    assert "Please enable JS" not in result
    assert "Real content" in result


def test_truncates_at_8000_chars():
    html = "<p>" + ("x" * 20_000) + "</p>"
    result = _parse_html(html)
    assert len(result) <= 8000


def test_collapses_excessive_blank_lines():
    html = "<p>A</p>\n\n\n\n\n<p>B</p>"
    result = _parse_html(html)
    assert "\n\n\n" not in result


def test_preserves_meaningful_text():
    html = (
        "<html><body>"
        "<h1>Cloud Architect</h1>"
        "<p>We are looking for a Solution Architect to lead our platform team.</p>"
        "</body></html>"
    )
    result = _parse_html(html)
    assert "Cloud Architect" in result
    assert "Solution Architect" in result


def test_empty_html_returns_empty_string():
    assert _parse_html("") == ""


def test_plain_text_passthrough():
    """Non-HTML input should survive without raising."""
    result = _parse_html("Just plain text, no tags.")
    assert "Just plain text" in result
