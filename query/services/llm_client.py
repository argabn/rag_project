"""
Client untuk memanggil Groq LLM.
"""
import logging
import time
from collections import Counter

from groq import Groq, RateLimitError
from django.conf import settings

logger = logging.getLogger(__name__)
LLM_CALLS = Counter()


try:
    _client = Groq(
        api_key=settings.GROQ_API_KEY,
        timeout=getattr(settings, "GROQ_TIMEOUT", 30),
        max_retries=getattr(settings, "GROQ_MAX_RETRIES", 1),
    )
except Exception:  # pragma: no cover - fallback when config is invalid
    logger.exception("Failed to initialize Groq client")
    _client = None


def generate_answer(
    messages: list[dict],
    model: str = "openai/gpt-oss-20b",
    max_tokens: int = 1024,
) -> str:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")
    if _client is None:
        raise RuntimeError("Groq client is unavailable")

    backoff_seconds = 5
    for attempt in range(6):
        try:
            LLM_CALLS[model] += 1
            completion = _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
            )
            break
        except RateLimitError as exc:
            if attempt == 5:
                raise
            retry_after = None
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", {}) or {}
            value = headers.get("retry-after") or headers.get("Retry-After")
            if value:
                try:
                    retry_after = max(0, float(value))
                except (TypeError, ValueError):
                    retry_after = None
            wait_seconds = min(retry_after if retry_after is not None else backoff_seconds, 60)
            logger.warning(
                "Groq rate limit reached; retrying in %.1f seconds (attempt %d/5)",
                wait_seconds,
                attempt + 1,
            )
            time.sleep(wait_seconds)
            backoff_seconds = min(backoff_seconds * 2, 60)
    answer = completion.choices[0].message.content
    if not answer or not answer.strip():
        raise ValueError("Empty response from Groq")
    return answer.strip()
