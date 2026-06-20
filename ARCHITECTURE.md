# Architecture

InterviewAI is a FastAPI backend that orchestrates a multi-agent interview pipeline on LangGraph, grounded by a hybrid RAG retrieval layer and hardened with caching, guardrails, and observability. This document describes how the pieces fit together and why the non-obvious decisions were made.

## System overview

```
Interviewer → FastAPI → Interview CRUD
                      → Resume Upload → PDF Parser (PyMuPDF)

Candidate   → FastAPI → Session Router → Interview Service
                                              ↓
                                        LangGraph Pipeline
                                     ┌──────────────────────────┐
                                     │  Resume Analyzer          │
                                     │  Question Generator   ←→  RAG (pgvector + BM25 + reranker)
                                     │  Answer Evaluator         │
                                     │  Follow-up Decider        │
                                     │  Interview Controller     │
                                     └──────────────────────────┘
                                              ↓
                                        LLM Service
                                     ┌──────────────────────────┐
                                     │  Groq (primary)           │
                                     │  Gemini (fallback)        │
                                     │  Circuit breaker          │
                                     │  Retry + JSON validation  │
                                     └──────────────────────────┘

Cross-cutting:  Redis (eval + state cache, token counters) · Guardrails (consistency,
                budget, sanitization) · /health (db + redis + circuit states)
```

## Agent pipeline

Five agents (`app/agents/`) cooperate over a shared `InterviewState` TypedDict:

- **Resume Analyzer** (`resume_analyzer.py`) — extracts skills, seniority, strengths, and gaps from the parsed resume. Runs once, on the first turn only.
- **Question Generator** (`question_generator.py`) — synthesizes the next question from the job description, candidate profile, interview history, and RAG-retrieved corpus questions. Built via the closure factory `make_question_generator(db)`.
- **Answer Evaluator** (`answer_evaluator.py`) — scores an answer (score, accuracy, completeness, clarity + feedback) against a `EvaluationResponse` Pydantic guardrail, retrying once on a parse/validation failure and falling back to neutral 5.0s.
- **Follow-up Decider** (`follow_up_decider.py`) — decides whether to probe deeper; hard-capped at **2 follow-ups per main question**.
- **Interview Controller** (`interview_controller.py`) — ends the interview when `questions_asked >= max_questions`.

### Two-phase, four-graph design

An interview cannot run as one graph to completion — it must *pause* to wait for the candidate to type an answer. So the pipeline is split into small compiled graphs (`app/agents/graph.py`):

- **Generation:** `build_first_question_graph(db)` (analyze → generate) on turn one, `build_question_graph(db)` (generate only) thereafter.
- **Scoring/routing:** the evaluation is produced on its own (so it can be cached and consistency-checked), then `build_routing_graph()` (`decide_follow_up` → conditional → `control_interview`) decides whether to probe again or advance. `build_evaluation_graph()` (the original coupled evaluate→decide→control graph) is retained for the standalone agent test harness.

### State reconstruction

Interview state must survive between independent HTTP requests. Rather than holding it in memory or Redis as the source of truth, `build_state_from_db(session, interview, db)` **reconstructs** the full `InterviewState` from persisted rows on each request: job context from the interview, `candidate_profile` from stored JSON, and `interview_history` / `topics_covered` / `questions_asked` / the trailing `follow_up_count` from the response rows. Redis caches this reconstruction (see below) but is never authoritative — a cache miss simply rebuilds from the database.

## RAG pipeline

The Question Generator retrieves relevant corpus questions through a three-stage hybrid search (`app/services/rag_service.py`):

1. **Vector search** — Jina Embeddings v3 (Matryoshka-truncated to 768 dims) over pgvector, ranked by cosine distance, using an HNSW index on `questions.embedding`.
2. **Keyword search (BM25)** — PostgreSQL full-text search via `plainto_tsquery` / `ts_rank` against the `search_vector` column (GIN-indexed), with normalized scores.
3. **Cross-encoder reranking** — Jina Reranker re-orders the merged candidate set by true query relevance.

Hybrid beats either alone: vector search captures semantic similarity but misses exact-term matches; BM25 nails keywords but misses paraphrase; the reranker resolves the disagreement. If the embedding/reranker API is unavailable, the pipeline degrades to vector-only or keyword-only results.

## Database schema

Six tables (`app/models/database_models.py`), PostgreSQL with the `pgvector` extension:

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `users` | Interviewer accounts | `email` (unique), `hashed_password`, `role` |
| `questions` | RAG question corpus | `text`, `domain`, `difficulty`, `reference_answer`, **`embedding` Vector(768)**, **`search_vector` TSVECTOR** |
| `interviews` | A role being interviewed for | `user_id` (FK), `job_description`, `required_skills`, `role_level`, `max_questions`, `status` |
| `interview_questions` | Legacy junction (kept, no longer populated — questions are generated dynamically) | `interview_id`, `question_id`, `order` |
| `candidate_sessions` | One candidate's interview run | `token` (unique), `resume_text`, `candidate_profile` (JSON), **`current_question_data`** (pending question JSON), `status`, `expires_at` |
| `responses` | Each answer + its evaluation | `session_id` (FK), `question_text`, **`is_follow_up`**, **`domain`**, `answer_text`, `score`/`accuracy`/`completeness`/`clarity`, `feedback`, `latency_ms` |

Notable schema mechanics:

- **`questions.embedding`** — a `pgvector` column queried with cosine distance; an **HNSW index** keeps similarity search fast at corpus scale.
- **`questions.search_vector`** — a `TSVECTOR` kept current by a database trigger and backed by a **GIN index**, powering the BM25 stage.
- **`responses.domain`** — lets `build_state_from_db` reconstruct `topics_covered` without re-deriving it.
- **`candidate_sessions.current_question_data`** — server-side cache of the pending question, so the candidate never round-trips the reference answer and a double `/next` costs no LLM call.

## Guardrails and resilience

- **Self-consistency** (`app/services/guardrails.py`) — ambiguous main-question scores (4.0–7.0) are re-evaluated; results within 1.5 are averaged, larger divergences are averaged *and* flagged in the feedback for manual review. Skipped on follow-ups, clear pass/fail scores, and in conserve mode.
- **Token budgets** — daily and per-session token counters live in Redis (48 h TTL), incremented from `llm_service.total_tokens` deltas. `conserve` mode (over the soft limit) skips self-consistency and truncates history to the last 3 Q&A pairs; `exceeded` mode (over 120 % of the daily cap) returns HTTP 503.
- **Circuit breaker** (`app/services/llm_service.py`) — per-provider breakers trip after repeated failures and recover via a half-open probe, so Groq → Gemini failover happens automatically and a dead provider isn't hammered.
- **Redis caching with graceful degradation** (`app/services/redis_service.py`) — evaluations (keyed on `sha256(question + answer + role_level)`, 1 h TTL) and reconstructed session state (30 min TTL, invalidated on each new response) are cached. Every Redis operation is wrapped so a Redis outage degrades to a cache miss — the interview keeps running.
- **Input sanitization** — candidate answers are stripped and truncated to 5000 chars; prompt-injection markers are logged (not rejected, to avoid false positives).
- **Observability** — `GET /health` reports database, Redis, and per-provider circuit states; `unhealthy` only if the database is down, `degraded` if a non-critical dependency is.

## Key design decisions

- **Four small graphs over one interrupt-driven graph** — interviews inherently pause for human input; explicit per-phase graphs are simpler to reason about and let evaluation be cached/consistency-checked independently of session-stateful routing (re-running a coupled graph would double-count follow-ups).
- **Database state reconstruction over in-memory/Redis persistence** — state survives restarts and horizontal scaling with no sticky sessions; Redis is a pure optimization, never the source of truth.
- **Closure pattern for DB access in nodes** — `make_question_generator(db)` captures the `AsyncSession` in a closure so the LangGraph state stays JSON-serializable (no live DB handle in state).
- **Synchronous LLM service with async wrappers** — the Groq/Gemini SDKs are synchronous; `call_llm_async` offloads them to a thread executor so FastAPI's event loop is never blocked.
- **Follow-up cap of 2 per main question** — bounds interview length and LLM cost while still allowing meaningful probing; enforced across requests via the trailing-follow-up count in reconstructed state.
- **Evaluations cached, questions never cached** — identical answers to the same question deserve the same score (cacheable), but every question must stay tailored to the specific candidate (never cached).
