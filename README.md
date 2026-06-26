# InterviewAI — Autonomous Technical Interview Platform

InterviewAI runs technical interviews end to end without a human in the loop. An interviewer creates a role (job description + required skills) and uploads candidate resumes; the system then **generates questions tailored to each candidate**, **evaluates every answer** with scores and specific feedback, and **probes weak answers with adaptive follow-ups** all orchestrated as a multi-agent pipeline on [LangGraph](https://langchain-ai.github.io/langgraph/). What sets it apart from a static question bank: questions are synthesized from the job description *and* the candidate's resume, evaluations are grounded in a hybrid RAG retrieval over a curated question corpus, and the interview adapts in real time to how the candidate is doing.

## Key features

- AI-generated interview questions tailored to the job description and candidate resume
- Real-time answer evaluation with sub-scores (accuracy, completeness, clarity) and specific feedback
- Adaptive follow-up probes on weak answers (capped at 2 per topic)
- Hybrid RAG pipeline: pgvector similarity + PostgreSQL BM25 + Jina cross-encoder reranking — benchmarked at **0.90 MRR@5** retrieval on a 2,532-question corpus ([details](ARCHITECTURE.md#retrieval-performance))
- Multi-agent orchestration with LangGraph (resume analysis → generation → evaluation → routing)
- Groq (Llama 3.3) primary with Google Gemini fallback behind a circuit breaker
- JWT authentication with per-route rate limiting
- Redis caching for LLM evaluations and reconstructed session state
- Self-consistency checks that re-score ambiguous answers, flag scoring variance and Token-budget enforcement

## Tech stack

| Layer | Technologies |
|-------|-------------|
| Backend | FastAPI, LangGraph, Groq (Llama 3.3), Google Gemini |
| AI/ML | Jina Embeddings v3, Jina Reranker, pgvector, BM25 |
| Database | PostgreSQL (pgvector, full-text search), Redis |
| Quality | Ruff, MyPy (strict), Pytest, GitHub Actions CI |

## Quick start

```bash
git clone git@github.com:zjohnjoseph/interview-ai.git
cd interview-ai
cp .env.example .env           # add JWT_SECRET_KEY + your API keys (Groq, Gemini, Jina)
docker compose up --build      # starts API, PostgreSQL (pgvector), Redis

# Seed and embed the 50-question RAG corpus
docker compose run --rm api python -m scripts.seed
docker compose run --rm api python -m scripts.embed_seed
```

Interactive API docs: http://localhost:8000/docs (Swagger) or `/redoc`.

## How it works

1. The interviewer creates an interview with a job description and required skills.
2. The interviewer uploads candidate resumes, each generating a unique invite link.
3. The candidate joins via the invite link.
4. The AI analyzes the resume and generates a tailored first question.
5. The candidate answers; the AI evaluates it with real scores and specific feedback.
6. Weak answers trigger adaptive follow-up probes (max 2 per main question).
7. The interview auto-completes at the configured question limit.
8. The interviewer reviews a detailed scorecard for every response.

## API overview

| Group | Endpoints | Description |
|-------|-----------|-------------|
| Auth | 4 | Signup, login, profile, candidate session join |
| Interviews | 8 | CRUD, publish, candidate/resume upload, list sessions |
| Questions | 4 | CRUD (RAG corpus) + semantic search |
| Sessions | 5 | Next question, submit answer, progress, results |
| Health | 1 | Dependency status (database, Redis, LLM circuits) |

22 endpoints total. Full interactive docs at `/docs`.

## Running tests

```bash
docker compose run --rm \
  -e TEST_DATABASE_URL="postgresql+asyncpg://interviewai:localdev123@db:5432/interviewai_test" \
  -e REDIS_URL="redis://redis:6379" \
  api bash -c "cd /app && ruff check app/ && mypy app/ --strict && pytest tests/ -v"
```

Tests run fully offline — the LLM and RAG calls are mocked, so no API keys are required in CI. Real LLM/RAG behavior is covered by `scripts/test_agents.py` and `scripts/test_llm.py`.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the system diagram, agent pipeline, RAG design, database schema, and key design decisions.

## Project status

**Phase 1 complete** — backend API, async PostgreSQL, JWT auth, rate limiting, 34 automated tests, CI/CD pipeline.

**Phase 2 (AI core) complete** — multi-agent interview pipeline, hybrid RAG, LLM evaluation with self-consistency, Redis caching, token budgets, and observability, all under strict type-checking and CI.

**Phase 3 (synthetic data + benchmarking) next** — generate synthetic candidates and answers to measure scoring quality, calibration, and retrieval metrics.
