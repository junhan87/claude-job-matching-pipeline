---
description: "Scaffold a new AnalysisStrategy subclass with required cost guardrails and stats tracking"
argument-hint: "Strategy name, e.g. IndeedAnalysisStrategy; describe what makes it different from DirectAnalysisStrategy"
agent: agent
tools: [read, edit, search]
---

Scaffold a new `AnalysisStrategy` subclass: **${input:strategy_name}**.

## Steps

### 1. Read context files first
Read these files before writing any code:
- [analyzers/base.py](../../analyzers/base.py) — abstract base and helper methods
- [analyzers/direct.py](../../analyzers/direct.py) — reference implementation (fallback strategy)
- [analyzers/linkedin.py](../../analyzers/linkedin.py) — platform-specific strategy example
- [analyzers/__init__.py](../../analyzers/__init__.py) — ANALYZERS registry
- [core/config.py](../../core/config.py) — MODEL_NAME, MAX_TOKENS constants

### 2. Create the analyzer module
Create `analyzers/${input:module_name}.py` with a class that:
- Subclasses `AnalysisStrategy`
- Implements `matches(self, job: dict) -> bool` — return True only for jobs this strategy should handle
- Implements `analyze(self, job: dict, system_text: str, client, http_client) -> str` — returns raw JSON string
- Uses `MODEL_NAME` and `MAX_TOKENS` from `core.config` — never hardcode these
- Calls `client.messages.create()` with **exactly** these parameters:
  - `temperature=0` — required for deterministic output
  - `system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}]` — required for prompt caching
  - `model=MODEL_NAME`, `max_tokens=MAX_TOKENS`
- Wraps the API call with `stats.start('<timer_name>')` / `stats.stop('<timer_name>')`
- Calls `stats.record_usage(response.usage)` after a successful API call
- Uses `_strip_json_fence()` and `_force_json_reply()` inherited from `AnalysisStrategy` for JSON extraction

### 3. Register the strategy
Add the new strategy to `analyzers/__init__.py` `ANALYZERS` list **before** `DirectAnalysisStrategy` (which is the fallback). Order matters — first `matches()` wins.

### 4. Create a test file
Create `tests/test_${input:module_name}_analyzer.py` with:
- A `unittest.TestCase` subclass
- A `conftest.py`-compatible import block
- A test that verifies `matches()` returns True/False for the expected job dict shapes
- A `# TODO:` stub for `analyze()` tests requiring a mocked Anthropic client

## Non-negotiable guardrails
- `temperature` must be `0` — do not parameterise it
- `cache_control` on the system message must not be removed or moved to the user message
- `stats.record_usage()` must be called — this feeds the cost dashboard
- Do not use streaming (`stream=True`)
- Do not raise `max_workers` in `ThreadPoolExecutor` — concurrency is capped at 3 globally in `main.py`
