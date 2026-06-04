"""
LLM service integration test script.

Usage:
    docker compose run --rm api python -m scripts.test_llm

Tests:
    1. Basic call with simple JSON prompt
    2. Answer evaluation prompt with Pydantic validation
    3. Resume analysis prompt
    4. Groq fallback to Gemini (invalid Groq key; Gemini call mocked to avoid quota)
    5. Both providers down → LLMProviderError
"""
import logging
import sys
import time
from unittest.mock import patch

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")

from google import genai
from groq import Groq

from app.models.schemas import EvaluationResponse
from app.services.llm_prompts import ANSWER_EVALUATION_PROMPT, RESUME_ANALYSIS_PROMPT
from app.services.llm_service import (
    CircuitBreaker,
    LLMProviderError,
    LLMService,
    _CircuitState,
)

_PASS = "PASS"
_FAIL = "FAIL"

SAMPLE_RESUME = """
Jane Doe — Software Engineer
Experience: 4 years

Work History:
- Backend Engineer at Acme Corp (2021–present): Built REST APIs with Python/FastAPI,
  designed PostgreSQL schemas, deployed to AWS EC2. Led migration from monolith to microservices.
- Junior Developer at StartupXYZ (2020–2021): Developed Python scripts for data processing,
  maintained MySQL databases, wrote unit tests with pytest.

Skills: Python, FastAPI, PostgreSQL, MySQL, Redis, Docker, AWS, pytest, SQLAlchemy, REST APIs
Education: B.Sc. Computer Science, University of Example, 2020
"""


def _make_broken_groq_service() -> LLMService:
    """LLMService instance with an invalid Groq key but real Gemini key."""
    from app.config import settings

    svc = LLMService.__new__(LLMService)
    svc._groq = Groq(api_key="gsk_invalid_key_for_fallback_test")
    svc._gemini = genai.Client(api_key=settings.gemini_api_key)
    svc._groq_breaker = CircuitBreaker()
    svc._gemini_breaker = CircuitBreaker()
    svc.total_tokens = 0
    return svc


def _make_both_broken_service() -> LLMService:
    """LLMService with both providers invalid; breaker thresholds set to 1 for speed."""
    svc = LLMService.__new__(LLMService)
    svc._groq = Groq(api_key="gsk_invalid")
    svc._gemini = genai.Client(api_key="invalid_gemini_key")

    # Override thresholds so each provider fails fast (1 attempt, no cooldown)
    groq_breaker = CircuitBreaker()
    groq_breaker._failure_threshold = 1
    groq_breaker._cooldown_seconds = 0.0

    gemini_breaker = CircuitBreaker()
    gemini_breaker._failure_threshold = 1
    gemini_breaker._cooldown_seconds = 0.0

    svc._groq_breaker = groq_breaker
    svc._gemini_breaker = gemini_breaker
    svc.total_tokens = 0
    return svc


def run_tests() -> None:
    from app.services.llm_service import llm_service

    results: list[tuple[str, str, str]] = []
    total_tokens = 0

    # --- Test 1: Basic call ---
    label = "[1/5] Basic call"
    try:
        t0 = time.monotonic()
        result = llm_service.call_llm('Return a JSON object with a key "status" set to "ok".')
        elapsed = round((time.monotonic() - t0) * 1000)
        assert result.get("status") == "ok", f"Unexpected result: {result}"
        tokens = llm_service.total_tokens
        total_tokens = tokens
        results.append((label, _PASS, f"{elapsed}ms, {tokens} tokens"))
    except Exception as exc:
        results.append((label, _FAIL, str(exc)[:120]))

    # --- Test 2: Evaluation prompt with Pydantic validation ---
    label = "[2/5] Evaluation prompt"
    try:
        prompt = ANSWER_EVALUATION_PROMPT.format(
            job_description="Backend Python engineer at a fintech startup",
            role_level="mid",
            question_text="What is a Python list comprehension and when would you use one?",
            reference_answer=(
                "A list comprehension is a concise way to create lists using a single line of "
                "Python syntax: [expr for item in iterable if condition]. Use it when transforming "
                "or filtering iterables for cleaner, more Pythonic code."
            ),
            candidate_answer=(
                "List comprehensions let you create lists in one line. "
                "Like [x*2 for x in range(10)] gives you doubled numbers."
            ),
        )
        t0 = time.monotonic()
        result = llm_service.call_llm(prompt, response_model=EvaluationResponse)
        elapsed = round((time.monotonic() - t0) * 1000)
        score = result.get("score", -1)
        assert 0.0 <= float(score) <= 10.0, f"score out of range: {score}"
        total_tokens = llm_service.total_tokens
        results.append((label, _PASS, f"score={score}, {elapsed}ms"))
    except Exception as exc:
        results.append((label, _FAIL, str(exc)[:120]))

    # --- Test 3: Resume analysis ---
    label = "[3/5] Resume analysis"
    try:
        prompt = RESUME_ANALYSIS_PROMPT.format(resume_text=SAMPLE_RESUME)
        t0 = time.monotonic()
        result = llm_service.call_llm(prompt)
        elapsed = round((time.monotonic() - t0) * 1000)
        skills = result.get("technical_skills")
        assert isinstance(skills, list) and len(skills) > 0, f"Bad technical_skills: {skills}"
        assert isinstance(result.get("experience_years"), int), "experience_years not int"
        total_tokens = llm_service.total_tokens
        results.append((label, _PASS, f"skills={skills[:2]}, {elapsed}ms"))
    except Exception as exc:
        results.append((label, _FAIL, str(exc)[:120]))

    # --- Test 4: Fallback to Gemini ---
    # Gemini is mocked to avoid exhausting free-tier daily quota during repeated test runs.
    # The circuit breaker open/fallback logic is fully exercised; only the Gemini HTTP call
    # is replaced with a stub return value.
    label = "[4/5] Fallback to Gemini"
    try:
        svc = _make_broken_groq_service()
        mock_response = ('{"status": "ok"}', 42)
        t0 = time.monotonic()
        with patch.object(svc, "_call_gemini", return_value=mock_response):
            result = svc.call_llm('Return a JSON object with a key "status" set to "ok".')
        elapsed = round((time.monotonic() - t0) * 1000)
        assert result.get("status") == "ok", f"Unexpected result: {result}"
        breaker_open = svc._groq_breaker._state == _CircuitState.OPEN
        state = "OPEN" if breaker_open else "CLOSED"
        results.append((label, _PASS, f"groq_breaker={state}, gemini_mocked, {elapsed}ms"))
    except Exception as exc:
        results.append((label, _FAIL, str(exc)[:120]))

    # --- Test 5: Both providers down ---
    label = "[5/5] Both providers down"
    try:
        svc = _make_both_broken_service()
        raised = False
        try:
            svc.call_llm("Return JSON.")
        except LLMProviderError:
            raised = True
        assert raised, "LLMProviderError was not raised"
        results.append((label, _PASS, "LLMProviderError raised correctly"))
    except Exception as exc:
        results.append((label, _FAIL, str(exc)[:120]))

    # --- Print results ---
    print()
    all_passed = True
    for lbl, status, detail in results:
        dots = "." * max(1, 44 - len(lbl))
        print(f"{lbl} {dots} {status}  ({detail})")
        if status == _FAIL:
            all_passed = False

    print(f"\nTotal tokens used across tests: {total_tokens}")

    if not all_passed:
        sys.exit(1)
    print("All tests passed.")


if __name__ == "__main__":
    run_tests()
