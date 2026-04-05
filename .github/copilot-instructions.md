# Copilot Instructions

This file defines how GitHub Copilot assists in this project.
It signals intentional constraints on AI usage — Copilot assists, but the developer owns every decision.

## Scope

Python 3.11+ job-matching pipeline that calls the Anthropic Claude API to rank job listings
extracted from email alerts (LinkedIn, MCF, Jobstreet).

## Anthropic API — Cost Optimisation Rules

These constraints are deliberate cost decisions. Do not change them without explicit discussion.

- **Model**: Always use `MODEL_NAME` from `core/config.py` (`claude-haiku-4-5`). Never suggest upgrading to a larger model unless accuracy is measurably insufficient.
- **Max tokens**: Keep `MAX_TOKENS = 1024`. Structured JSON responses do not need more.
- **Temperature**: Always `temperature=0`. Deterministic output is required for reproducible ranking.
- **Prompt caching**: System messages **must** carry `"cache_control": {"type": "ephemeral"}`. Never remove this. The system prompt (2 resumes + instructions) is the largest token block and is reused across all jobs in a run.
- **System prompt construction**: Built once per process via `@functools.lru_cache(maxsize=1)` on `_build_system_text()`. Do not move prompt assembly into the per-job path.
- **Concurrency cap**: `ThreadPoolExecutor(max_workers=3)` is intentional — it limits parallel API calls to stay within rate limits and avoid unexpected spend spikes. Do not raise this value without profiling.
- **No streaming**: Streaming adds complexity with no cost benefit for short structured responses.

## Architecture — Design Patterns to Follow

### Strategy Pattern for Analyzers

New job sources or analysis modes must be added as a new `AnalysisStrategy` subclass in `analyzers/`, not by branching inside existing classes.

```
AnalysisStrategy (abstract, analyzers/base.py)
  └── DirectAnalysisStrategy  (analyzers/direct.py)  ← fallback, matches() always True
  └── LinkedInAnalysisStrategy (analyzers/linkedin.py) ← platform-specific, matches() checks source
```

Register new strategies in `analyzers/__init__.py` `ANALYZERS` list. Order matters — first `matches()` wins.

### Registry Pattern for Parsers

Platform parsers live in `parsers/` and are registered in `STRATEGIES` dict keyed by platform ID constants from `core/config.py`. Add new platforms there, not as inline conditionals.

### Immutable Result Type

`AnalysisResult` is a `NamedTuple`. Keep it immutable — do not convert to a dataclass or add mutable fields.

### Config Centralisation

All tunable values (model name, token limits, platform IDs, URL templates, regex patterns) belong in `core/config.py`. Do not hardcode these in parsers, analyzers, or `main.py`.

## Security Guardrails

- **API keys via environment variables only.** `ANTHROPIC_API_KEY` must come from `os.getenv()`. Never suggest inline keys, `.env` commits, or `os.environ` writes.
- **SSL verification is mandatory.** `build_ssl_context()` in `core/http_utils.py` merges the certifi bundle with the Windows certificate store. Do not suggest `verify=False` under any circumstances.
- **User-supplied content is never executed.** Job description text from emails or HTTP responses is only passed as string content to the LLM, never `eval()`-ed, templated into SQL, or used in subprocess calls.
- **HTML scraping output is bounded.** `fetch_url_text()` truncates to 8000 characters. Do not raise this limit without profiling token costs.
- **No secrets in logs.** Do not add `print()` or `logging` calls that output environment variables, API keys, or email credentials.

## Python Conventions

- Type hints on all new functions. Use `Optional[X]` over `X | None` for consistency with existing code.
- Prefer `NamedTuple` for simple read-only result containers.
- `core/stats.py` records timing and token usage — call `stats.record_usage()` in any new analyzer that consumes API tokens.
- Tests live in `tests/`. Any new parser or analyzer must have a corresponding test file. Use the existing `conftest.py` fixtures.
- Do not add dependencies to `requirements.txt` without checking whether the stdlib or an already-listed package covers the need.

## What Copilot Should Not Do Without Explicit Request

- Refactor working code for style alone
- Replace `NamedTuple` with `@dataclass`
- Add logging frameworks (plain `print()` is intentional for this CLI tool)
- Suggest async/await — the concurrency model is `ThreadPoolExecutor` by design
- Add retry libraries — retry logic is handled inline to keep the dependency list minimal
