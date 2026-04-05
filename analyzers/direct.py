from .base import AnalysisStrategy, _FORCE_JSON_MSG
from core.config import MODEL_NAME, MAX_TOKENS
from core.http_utils import fetch_url_text
from core.stats import stats


class DirectAnalysisStrategy(AnalysisStrategy):
    """MCF/Jobstreet path: JD is fetched and embedded in the prompt; single API call."""

    def matches(self, job: dict) -> bool:
        return True  # fallback — always last in registry

    def analyze(self, job: dict, system_text: str, client, http_client) -> str:
        title = job.get('title', '')
        company = job.get('company', '')
        url = job.get('url', '')
        location = job.get('location', '')
        salary = job.get('salary', '')
        description = job.get('description', '')

        if description:
            jd_text = description
        elif url and ('mycareersfuture.gov.sg' in url or 'jobstreet.com' in url):
            jd_text = fetch_url_text(url, http_client)
            if not jd_text:
                job['_jd_missing'] = True
                jd_text = 'No job description available.'
        else:
            job['_jd_missing'] = True
            jd_text = 'No job description available.'

        user_prompt = (
            f"Job listing:\nTitle: {title}\nCompany: {company}\nLocation: {location}"
            f"\nSalary: {salary}\nURL: {url}\n\n"
            f"<job_description>\n{jd_text}\n</job_description>\n\n"
            f"{_FORCE_JSON_MSG}"
        )
        return self._call_direct(user_prompt, system_text, client)

    def _call_direct(self, user_prompt: str, system_text: str, client) -> str:
        messages = [{"role": "user", "content": user_prompt}]
        stats.start('claude_direct')
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            temperature=0,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        stats.stop('claude_direct')
        stats.record_usage(response, 'claude_direct')
        text = self._extract_text(response)
        cleaned = self._strip_json_fence(text)
        if cleaned.startswith(('{', '[')):
            return cleaned
        # First response wasn't JSON (e.g. Claude narrated instead) — force it
        messages.append({"role": "assistant", "content": response.content})
        return self._force_json_reply(messages, system_text, client)
