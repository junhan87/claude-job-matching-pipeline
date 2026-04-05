---
description: "Scaffold a new job-source email parser following the JobAlertStrategy registry pattern"
argument-hint: "Platform name, e.g. Indeed, Glassdoor, MyWorkdayjobs"
agent: agent
tools: [read, edit, search]
---

Scaffold a new email parser for the job platform: **${input:platform}**.

Follow the registry pattern already used by LinkedIn, MCF and Jobstreet in this project.

## Steps

### 1. Read context files first
Read these files before writing any code:
- [parsers/base.py](../../parsers/base.py) — `JobAlertStrategy` abstract base class
- [parsers/linkedin.py](../../parsers/linkedin.py) — reference implementation
- [parsers/__init__.py](../../parsers/__init__.py) — existing registry
- [core/config.py](../../core/config.py) — platform ID constants

### 2. Create the parser module
Create `parsers/${input:platform_lower}.py` with a class that:
- Subclasses `JobAlertStrategy`
- Sets all required class attributes: `name`, `email_query`, `max_results`, `start_anchors`, `end_anchors`, `blacklist`, `subject_pattern`
- Implements `_extract_job_urls(self, soup, http_client) -> dict` returning `{job_id: {'url': str, 'title': str, ...}}`
- Uses `str` type hints on all new methods

Leave a `# TODO:` comment on any attribute that needs platform-specific values once real emails are available.

### 3. Register the new platform
- Add a platform ID constant to `core/config.py` (e.g. `INDEED = 3`)
- Import and register the new strategy in `parsers/__init__.py` under the `STRATEGIES` dict

### 4. Create a test file
Create `tests/test_${input:platform_lower}_parser.py` with:
- A `TestCase` class using `unittest`
- A `conftest.py`-compatible import block (follow the pattern in `tests/conftest.py`)
- At least one test that instantiates the strategy and verifies `name` and `email_query` are set
- A `# TODO:` stub test for `extract_jobs()` once real email HTML is available

## Guardrails
- Do not hardcode platform IDs outside `core/config.py`
- Do not add any new `requirements.txt` dependency without checking stdlib + existing packages first
- The new parser must not call the Anthropic API — parsing is pure HTML/text extraction
