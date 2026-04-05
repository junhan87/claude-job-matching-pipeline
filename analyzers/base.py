from abc import ABC, abstractmethod
from core.config import MODEL_NAME, MAX_TOKENS
from core.stats import stats

_FORCE_JSON_MSG = "Output ONLY the JSON object now. No prose, no markdown, no explanation."


class AnalysisStrategy(ABC):
    """Abstract base class for job analysis strategies."""

    @abstractmethod
    def matches(self, job: dict) -> bool:
        """Return True if this strategy handles the given job."""
        ...

    @abstractmethod
    def analyze(self, job: dict, system_text: str, client, http_client) -> str:
        """Analyze the job and return a raw JSON string from the model."""
        ...

    # ------------------------------------------------------------------
    # Shared output-format helpers
    # ------------------------------------------------------------------

    def _extract_text(self, response) -> str:
        """Return the first text block found in an Anthropic response."""
        for block in reversed(response.content):
            if hasattr(block, 'text'):
                return block.text
        return ""

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        """Strip markdown code fences and return the JSON object found anywhere in the text."""
        stripped = text.strip()
        if stripped.startswith('```'):
            lines = stripped.splitlines()
            inner_lines = lines[1:]
            if inner_lines and inner_lines[-1].strip() == '```':
                inner_lines = inner_lines[:-1]
            stripped = '\n'.join(inner_lines).strip()
        # If JSON is preceded by prose, extract the object/array directly.
        if not stripped.startswith(('{', '[')):
            start = next((i for i, c in enumerate(stripped) if c in ('{', '[')), -1)
            if start != -1:
                end_char = '}' if stripped[start] == '{' else ']'
                end = stripped.rfind(end_char)
                if end != -1:
                    stripped = stripped[start:end + 1]
        return stripped

    def _force_json_reply(self, messages: list, system_text: str, client) -> str:
        """Append a JSON-only instruction, fire a final API call, and return the text."""
        messages.append({"role": "user", "content": _FORCE_JSON_MSG})
        stats.start('claude_retry')
        final = client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        stats.stop('claude_retry')
        stats.record_usage(final, 'claude_retry')
        return self._extract_text(final)
