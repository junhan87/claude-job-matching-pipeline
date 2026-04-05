---
description: "Audit analyzer and parser changes for cost guardrail violations before committing"
agent: agent
tools: [read, search]
---

Perform a cost and security audit on any recently modified analyzer or parser files in this project.

## What to audit

Check every file in `analyzers/` and `parsers/` (or the specific files I mention) against the rules below.
Read [core/config.py](../../core/config.py) first to confirm the current values for `MODEL_NAME` and `MAX_TOKENS`.

## Cost guardrail checklist

For every `client.messages.create()` call found:

| Rule | What to look for | Pass / Fail |
|------|-----------------|-------------|
| Correct model | `model=MODEL_NAME` (imported from `core.config`) — never a hardcoded string | |
| Token limit | `max_tokens=MAX_TOKENS` — never a hardcoded integer above 1024 | |
| Temperature | `temperature=0` — must be exactly zero, not parameterised | |
| Prompt caching | System message list entry contains `"cache_control": {"type": "ephemeral"}` | |
| Stats tracking | `stats.start()` called before and `stats.stop()` + `stats.record_usage(response.usage)` called after | |
| No streaming | `stream=True` must not appear anywhere in the call | |

## Security checklist

| Rule | What to look for |
|------|-----------------|
| API key source | `ANTHROPIC_API_KEY` only via `os.getenv()` — never hardcoded or logged |
| SSL verification | No `verify=False` anywhere in HTTP calls |
| No execution of user content | Job description text must only be passed as a string to the LLM — never to `eval()`, `exec()`, `subprocess`, or string-formatted SQL |
| Secrets not logged | No `print()` / `logging` of env vars, credentials, or API keys |
| HTML output bounded | `fetch_url_text()` truncation limit not raised above 8000 characters |

## Report format

For each violation found, output:
```
FILE: <path>
LINE: <approximate line>
RULE: <rule name>
ISSUE: <what is wrong>
FIX: <exact change needed>
```

If no violations are found, confirm: "All audited files pass cost and security guardrails."

Do not suggest changes beyond what the rules above require.
