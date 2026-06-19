from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from groq import APIStatusError, Groq, RateLimitError
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

# SYNC NOTE: Groq and google-genai SDKs are synchronous.
# call_llm() is a blocking method. In async FastAPI endpoints, call via:
#   await asyncio.get_event_loop().run_in_executor(None, llm_service.call_llm, prompt, system)
# interview_service.py (Phase 2) will handle this wrapping.

logger = logging.getLogger(__name__)

_LOG_DIR = Path("/app/logs")
_LOG_FILE = _LOG_DIR / "llm_responses.jsonl"


def _append_response_log(record: dict[str, Any]) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Failed to write LLM response log: %s", exc)


class LLMProviderError(Exception):
    """Both Groq and Gemini failed to return a response."""


class LLMResponseParseError(Exception):
    """The LLM returned a response that could not be parsed as JSON."""


class LLMValidationError(Exception):
    """The LLM returned valid JSON that failed Pydantic model validation."""


class _CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class CircuitBreaker:
    _failure_threshold: int = 3
    _cooldown_seconds: float = 30.0

    def __init__(self) -> None:
        self._state = _CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None

    def is_available(self) -> bool:
        if self._state == _CircuitState.CLOSED or self._state == _CircuitState.HALF_OPEN:
            return True
        # OPEN state — check if cooldown has elapsed
        assert self._opened_at is not None
        if time.monotonic() - self._opened_at >= self._cooldown_seconds:
            self._state = _CircuitState.HALF_OPEN
            self._failure_count = 0
            return True
        return False

    def record_success(self) -> None:
        self._state = _CircuitState.CLOSED
        self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._state = _CircuitState.OPEN
            self._opened_at = time.monotonic()


class LLMService:
    def __init__(self) -> None:
        self._groq = Groq(api_key=settings.groq_api_key)
        self._gemini = genai.Client(api_key=settings.gemini_api_key)
        self._groq_breaker = CircuitBreaker()
        self._gemini_breaker = CircuitBreaker()
        self.total_tokens: int = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type((RateLimitError, APIStatusError)),
        reraise=True,
    )
    def _call_groq(self, prompt: str, system_prompt: str) -> tuple[str, int]:
        response = self._groq.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        text = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        return text, tokens

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _call_gemini(self, prompt: str, system_prompt: str) -> tuple[str, int]:
        response = self._gemini.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_tokens,
            ),
        )
        text = response.text or ""
        tokens = (
            response.usage_metadata.total_token_count or 0
            if response.usage_metadata
            else 0
        )
        return text, tokens

    @staticmethod
    def _strip_fences(text: str) -> str:
        pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
        match = re.search(pattern, text.strip(), re.DOTALL)
        return match.group(1).strip() if match else text.strip()

    def _parse_response(
        self,
        raw: str,
        response_model: type[BaseModel] | None,
    ) -> dict[str, Any]:
        cleaned = self._strip_fences(raw)
        try:
            parsed: dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMResponseParseError(
                f"LLM response is not valid JSON: {exc}\nRaw (first 200 chars): {raw[:200]}"
            ) from exc

        if response_model is not None:
            try:
                response_model.model_validate(parsed)
            except ValidationError as exc:
                raise LLMValidationError(
                    f"LLM JSON failed {response_model.__name__} validation: {exc}"
                ) from exc

        return parsed

    def call_llm(
        self,
        prompt: str,
        system_prompt: str = (
            "You are a technical interviewer AI. Return structured JSON only."
        ),
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        # --- Try Groq first ---
        if self._groq_breaker.is_available():
            start = time.monotonic()
            try:
                raw_text, tokens = self._call_groq(prompt, system_prompt)
                self._groq_breaker.record_success()
                self.total_tokens += tokens
                latency_ms = round((time.monotonic() - start) * 1000)
                logger.info(
                    "LLM call succeeded",
                    extra={
                        "provider": "groq",
                        "model": settings.groq_model,
                        "prompt_len": len(prompt),
                        "response_len": len(raw_text),
                        "latency_ms": latency_ms,
                        "tokens": tokens,
                    },
                )
                parsed = self._parse_response(raw_text, response_model)
                _append_response_log({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "provider": "groq",
                    "model": settings.groq_model,
                    "latency_ms": latency_ms,
                    "tokens": tokens,
                    "prompt": prompt,
                    "raw_response": raw_text,
                    "parsed_response": parsed,
                })
                return parsed
            except (LLMResponseParseError, LLMValidationError):
                raise
            except Exception as exc:
                self._groq_breaker.record_failure()
                logger.warning(
                    "Groq call failed, falling back to Gemini",
                    extra={"error": str(exc)},
                )

        # --- Fall back to Gemini ---
        if self._gemini_breaker.is_available():
            start = time.monotonic()
            try:
                raw_text, tokens = self._call_gemini(prompt, system_prompt)
                self._gemini_breaker.record_success()
                self.total_tokens += tokens
                latency_ms = round((time.monotonic() - start) * 1000)
                logger.info(
                    "LLM call succeeded",
                    extra={
                        "provider": "gemini",
                        "model": settings.gemini_model,
                        "prompt_len": len(prompt),
                        "response_len": len(raw_text),
                        "latency_ms": latency_ms,
                        "tokens": tokens,
                    },
                )
                parsed = self._parse_response(raw_text, response_model)
                _append_response_log({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "provider": "gemini",
                    "model": settings.gemini_model,
                    "latency_ms": latency_ms,
                    "tokens": tokens,
                    "prompt": prompt,
                    "raw_response": raw_text,
                    "parsed_response": parsed,
                })
                return parsed
            except (LLMResponseParseError, LLMValidationError):
                raise
            except Exception as exc:
                self._gemini_breaker.record_failure()
                logger.error(
                    "Gemini call failed",
                    extra={"error": str(exc)},
                )

        raise LLMProviderError("All LLM providers unavailable")

    def circuit_states(self) -> dict[str, str]:
        """Current circuit-breaker state per provider, for the health endpoint."""
        return {
            "groq": self._groq_breaker._state.name.lower(),
            "gemini": self._gemini_breaker._state.name.lower(),
        }


llm_service = LLMService()
