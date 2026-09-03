"""
Client untuk memanggil Groq LLM.
"""
import logging

from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)


try:
    _client = Groq(
        api_key=settings.GROQ_API_KEY,
        timeout=getattr(settings, "GROQ_TIMEOUT", 30),
        max_retries=getattr(settings, "GROQ_MAX_RETRIES", 1),
    )
except Exception:  # pragma: no cover - fallback when config is invalid
    logger.exception("Failed to initialize Groq client")
    _client = None


def generate_answer(messages: list[dict], model: str = "openai/gpt-oss-20b") -> str:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured")
    if _client is None:
        raise RuntimeError("Groq client is unavailable")

    completion = _client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
        max_tokens=1024,
    )
    answer = completion.choices[0].message.content
    if not answer or not answer.strip():
        raise ValueError("Empty response from Groq")
    return answer.strip()
