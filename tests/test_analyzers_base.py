"""Tests for AnalysisStrategy._strip_json_fence in analyzers/base.py.

No API key or network access required — pure string manipulation.
Run with:  python -m pytest tests/test_analyzers_base.py -v
"""

import json
import pytest
from analyzers.direct import DirectAnalysisStrategy

# Convenience alias — _strip_json_fence is a @staticmethod
strip = DirectAnalysisStrategy._strip_json_fence


# ---------------------------------------------------------------------------
# Already clean JSON — no modification needed
# ---------------------------------------------------------------------------

def test_plain_json_unchanged():
    text = '{"rank": "HIGH", "score": 9}'
    assert strip(text) == text


def test_json_array_unchanged():
    text = '[{"rank": "HIGH"}, {"rank": "LOW"}]'
    assert strip(text) == text


# ---------------------------------------------------------------------------
# Markdown code fences stripped
# ---------------------------------------------------------------------------

def test_strips_json_code_fence():
    text = '```json\n{"rank": "HIGH"}\n```'
    result = strip(text)
    assert result == '{"rank": "HIGH"}'


def test_strips_generic_code_fence():
    text = '```\n{"rank": "HIGH"}\n```'
    result = strip(text)
    assert result == '{"rank": "HIGH"}'


def test_strips_fence_with_trailing_whitespace():
    text = '```json\n{"rank": "HIGH"}\n```  '
    result = strip(text)
    assert result.startswith('{"rank"')


# ---------------------------------------------------------------------------
# JSON embedded after prose
# ---------------------------------------------------------------------------

def test_extracts_json_from_prose_prefix():
    text = 'Here is the analysis:\n{"rank": "HIGH", "score": 8}'
    result = strip(text)
    assert result == '{"rank": "HIGH", "score": 8}'


def test_extracts_json_from_longer_prose():
    text = (
        "I have analyzed the job description carefully. "
        'Based on the requirements, here is my assessment:\n\n'
        '{"rank": "MEDIUM", "score": 6, "verdict": "Possible fit"}'
    )
    result = strip(text)
    assert json.loads(result)["rank"] == "MEDIUM"


# ---------------------------------------------------------------------------
# Result is always valid JSON (parse round-trip)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    '{"rank": "HIGH", "score": 9}',
    '```json\n{"rank": "SKIP", "score": 1}\n```',
    'Sure!\n{"rank": "LOW", "score": 3}',
])
def test_result_is_parseable_json(text):
    result = strip(text)
    parsed = json.loads(result)
    assert "rank" in parsed
