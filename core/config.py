import re

# ---------------------------------------------------------------------------
# Platform IDs — used as keys in STRATEGIES and on the --platform CLI flag.
# ---------------------------------------------------------------------------
LINKEDIN = 0
MCF = 1
JOBSTREET = 2

# ---------------------------------------------------------------------------
# Resume path — single resume file used for job matching.
# ---------------------------------------------------------------------------
RESUME_PATH = "resumes/resume.md"

# ---------------------------------------------------------------------------
# AI model configuration
# ---------------------------------------------------------------------------
MODEL_NAME = "claude-haiku-4-5"
MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# External API URLs
# ---------------------------------------------------------------------------
MCF_JOB_API_URL = 'https://api.mycareersfuture.gov.sg/v2/jobs/{uuid}'

# ---------------------------------------------------------------------------
# Title pre-filter — applied before calling the AI (--analyze only).
#
# TITLE_INCLUDE: at least one pattern must match for a job to be analysed.
#   Add seniority levels or role types you are targeting.
#   Patterns are matched case-insensitively via re.search().
#
# TITLE_EXCLUDE: if any pattern matches, the job is skipped regardless of
#   TITLE_INCLUDE. Use this to drop role categories, seniority levels, or
#   tech stacks that are outside your target. Plain strings and raw regex
#   strings (r"...") are both accepted.
# ---------------------------------------------------------------------------
TITLE_INCLUDE = [
    "principal",
    "architect",
    r"\blead\b",
    "staff",
]
TITLE_EXCLUDE = [
    "frontend",
    r"\bqa\b",
    "mobile",
    "android",
    r"\bios\b",
    r"\bjava\b",
    r"\.net\b",
    "data analyst",
    "product manager",
    "marketing",
    "sales",
]


def should_analyze(title: str) -> bool:
    """Return True if the job title passes the include/exclude pre-filter."""
    if not title or title == '(Unknown Title)':
        return False
    included = any(re.search(p, title, re.IGNORECASE) for p in TITLE_INCLUDE)
    if not included:
        return False
    excluded = any(re.search(p, title, re.IGNORECASE) for p in TITLE_EXCLUDE)
    return not excluded


# ---------------------------------------------------------------------------
# Salary filter — applied to all jobs regardless of --analyze flag.
# Jobs with no salary information are always kept (unknown ≠ below threshold).
# ---------------------------------------------------------------------------

SALARY_RE = re.compile(r'\$\s*([\d,]+)')


def parse_salary_min(salary: str):
    """Extract the minimum (first) salary figure from a salary string.

    Handles formats such as:
      '$5,000 – $8,000'  →  5000
      '$5,000/mth'       →  5000
      '$5,000 per month' →  5000
    Returns None if the string is empty or no number can be parsed.
    """
    if not salary:
        return None
    m = SALARY_RE.search(salary)
    if not m:
        return None
    return int(m.group(1).replace(',', ''))


def salary_meets_threshold(salary: str, min_salary: int) -> bool:
    """Return True if salary is absent OR its minimum figure >= min_salary.

    When min_salary is 0 (default / not set), no filtering is applied.
    Jobs without a parseable salary are never filtered out.
    """
    if not min_salary:
        return True
    parsed = parse_salary_min(salary)
    if parsed is None:
        return True  # no salary info — keep the job
    return parsed >= min_salary
