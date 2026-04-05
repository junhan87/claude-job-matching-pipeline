# Refactored: HTTP utilities live in http_utils.py; domain config lives in config.py.
# This shim preserves backward compatibility for any code not yet updated.
from core.http_utils import build_ssl_context, fetch_url_text, _parse_html  # noqa: F401
from core.config import (  # noqa: F401
    TITLE_INCLUDE, TITLE_EXCLUDE, SALARY_RE,
    should_analyze, parse_salary_min, salary_meets_threshold,
)

