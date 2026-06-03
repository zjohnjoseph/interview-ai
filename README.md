# InterviewAI

Autonomous technical interview platform powered by LLM-based evaluation. Interviewers publish a question bank and an invite link; candidates answer questions at their own pace; the system scores every response automatically and produces a detailed scorecard.

## Tech stack

- **FastAPI** — async Python API, Pydantic v2 validation
- **PostgreSQL + pgvector** — relational store with vector embeddings (Phase 2)
- **Redis** — job queue and caching (Phase 2)
- **Docker Compose** — single-command local dev environment

## Quick start

```bash
cp .env.example .env          # fill in JWT_SECRET_KEY at minimum
docker compose up --build     # starts API, PostgreSQL, Redis
```

API docs: http://localhost:8000/docs

## Seed the database

Populate 50 realistic interview questions across 6 domains:

```bash
docker compose run --rm api python -m scripts.seed
```

## Run tests

```bash
docker compose run --rm \
  -e TEST_DATABASE_URL="postgresql+asyncpg://interviewai:localdev123@db:5432/interviewai_test" \
  api bash -c "cd /app && pytest tests/ -v"
```

## API overview

| Group | Endpoints | Description |
|-------|-----------|-------------|
| Auth | 4 | Signup, login, profile, session join |
| Interviews | 9 | CRUD, publish, question attachment, session list |
| Questions | 3 | Create, list (with filters), get by ID |
| Sessions | 5 | Next question, submit answer, progress, results |

Full interactive docs at `/docs` (Swagger UI) or `/redoc`.

## Project status

**Phase 1 complete** — backend API (25 routes), async PostgreSQL, JWT auth, rate limiting, 34 automated tests, CI/CD pipeline.

**Phase 2 in progress** — LLM evaluation (Groq), vector embeddings (Jina AI), RAG-based question retrieval.
