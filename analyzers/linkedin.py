from .base import AnalysisStrategy
from core.config import MODEL_NAME, MAX_TOKENS
from core.stats import stats

_TOOLS = [
    {"type": "web_search_20250305", "name": "web_search"},
]


class LinkedInAnalysisStrategy(AnalysisStrategy):
    """LinkedIn path: Claude uses web_search to find and read the JD via search snippets."""

    def matches(self, job: dict) -> bool:
        return 'linkedin.com' in job.get('url', '')

    def analyze(self, job: dict, system_text: str, client, http_client) -> str:
        title = job.get('title', '')
        company = job.get('company', '')
        url = job.get('url', '')
        location = job.get('location', '')
        salary = job.get('salary', '')
        description = job.get('description', '')  # preheader snippet if present

        if not description:
            # No JD available — skip the expensive tool-loop, score from title/company only
            job['_jd_missing'] = True
            user_prompt = (
                f"Job listing:\nTitle: {title}\nCompany: {company}\nLocation: {location}"
                f"\nSalary: {salary}\nURL: {url}\n\n"
                "No job description available. Score using title, company, and location only.\n\n"
                "Respond with ONLY the JSON object — no preamble, explanation, or markdown fences."
            )
            return self._call_no_jd(user_prompt, system_text, client)

        jd_block = f"<job_description>\n{description}\n</job_description>"
        user_prompt = (
            f"Job listing:\nTitle: {title}\nCompany: {company}\nLocation: {location}"
            f"\nSalary: {salary}\nURL: {url}\n\n{jd_block}"
        )
        user_prompt += "\n\nRespond with ONLY the JSON object — no preamble, explanation, or markdown fences."
        return self._call_with_tools(user_prompt, system_text, client)

    def _call_no_jd(
        self, user_prompt: str, system_text: str, client
    ) -> str:
        """Single low-token call for jobs with no JD — no tool loop."""
        messages = [{'role': 'user', 'content': user_prompt}]
        stats.start('claude_linkedin')
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=[{'type': 'text', 'text': system_text, 'cache_control': {'type': 'ephemeral'}}],
            messages=messages,
        )
        stats.stop('claude_linkedin')
        stats.record_usage(response, 'claude_linkedin')
        text = self._extract_text(response)
        cleaned = self._strip_json_fence(text)
        if cleaned.startswith('{'):
            return cleaned
        messages.append({'role': 'assistant', 'content': response.content})
        return self._force_json_reply(messages, system_text, client)

    def _call_with_tools(
        self, user_prompt: str, system_text: str, client
    ) -> str:
        messages = [{"role": "user", "content": user_prompt}]
        response = None
        for _ in range(3):
            stats.start('claude_linkedin')
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                temperature=0,
                tools=_TOOLS,
                tool_choice={"type": "auto"},
                system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
            )
            stats.stop('claude_linkedin')
            stats.record_usage(response, 'claude_linkedin')
            if response.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": response.content})
            # web_search is server-side — no tool_result needed

        if response.stop_reason == "tool_use":
            # Loop exhausted — assistant content was already appended inside the loop.
            # messages ends with user(tool_result); make a final no-tools call.
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
            return self._strip_json_fence(self._extract_text(final))

        # Loop exited via break (end_turn response) — check for JSON directly
        text = self._extract_text(response)
        cleaned = self._strip_json_fence(text)
        if cleaned.startswith('{'):
            return cleaned
        # Got text but not JSON — append and force JSON reply
        messages.append({"role": "assistant", "content": response.content})
        return self._force_json_reply(messages, system_text, client)
