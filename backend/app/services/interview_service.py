from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import (
    build_first_question_graph,
    build_question_graph,
    build_routing_graph,
    build_state_from_db,
)
from app.agents.state import InterviewState
from app.models.database_models import CandidateSession, Interview, Response
from app.models.schemas import (
    AnswerResponse,
    EvaluationResponse,
    NextQuestionResponse,
    QuestionResponse,
    ResponseDetail,
    SessionProgressResponse,
    SessionResultResponse,
)
from app.services.guardrails import (
    TokenBudgetExceededError,
    check_token_budget,
    consistency_checked_evaluation,
    record_tokens,
    sanitize_answer,
)
from app.services.llm_service import llm_service
from app.services.redis_service import redis_service

logger = logging.getLogger(__name__)

_STATE_TTL = 30 * 60  # session-state cache: 30 minutes
_EVAL_TTL = 60 * 60  # evaluation cache: 1 hour
_CONSERVE_HISTORY = 3  # Q&A pairs kept when conserving tokens

_FALLBACK_EVALUATION = EvaluationResponse(
    score=5.0,
    accuracy=5.0,
    completeness=5.0,
    clarity=5.0,
    feedback="Evaluation could not be completed reliably. Please review manually.",
)


class NoQuestionPendingError(Exception):
    """The candidate submitted an answer with no question pending. Call /next first."""


class InterviewService:
    @staticmethod
    def _question_to_response(question: dict[str, Any]) -> QuestionResponse:
        corpus_id = question.get("corpus_question_id")
        qid = uuid.UUID(corpus_id) if corpus_id else uuid.uuid4()
        return QuestionResponse(
            id=qid,
            text=question.get("question_text", ""),
            domain=question.get("domain", ""),
            difficulty=question.get("difficulty", "medium"),
            created_at=datetime.now(timezone.utc),
        )

    @staticmethod
    async def _load_state(
        session: CandidateSession, interview: Interview, db: AsyncSession
    ) -> InterviewState:
        """Reconstruct InterviewState, preferring the Redis cache over DB queries."""
        key = redis_service.state_key(str(session.id))
        cached = await redis_service.get_cached(key)
        if cached is not None:
            logger.info("State cache hit: %s", key)
            return cast(InterviewState, cached)

        logger.info("State cache miss: %s", key)
        state = await build_state_from_db(session, interview, db)
        await redis_service.set_cached(key, dict(state), ttl_seconds=_STATE_TTL)
        return state

    @staticmethod
    async def _invalidate_state(session: CandidateSession) -> None:
        await redis_service.delete(redis_service.state_key(str(session.id)))

    async def get_next_question(
        self,
        session: CandidateSession,
        interview: Interview,
        db: AsyncSession,
    ) -> NextQuestionResponse:
        mode = await check_token_budget(str(session.id))
        if mode == "exceeded":
            raise TokenBudgetExceededError

        state = await self._load_state(session, interview, db)
        questions_asked = state.get("questions_asked", 0)
        remaining = max(interview.max_questions - questions_asked, 0)

        # Double-/next: a question is already pending — return it without an LLM call.
        if session.current_question_data:
            question = json.loads(session.current_question_data)
            return NextQuestionResponse(
                completed=False,
                question=self._question_to_response(question),
                questions_remaining=remaining,
            )

        if questions_asked >= interview.max_questions:
            return NextQuestionResponse(
                completed=True, question=None, questions_remaining=0
            )

        if mode == "conserve":
            state["interview_history"] = state.get("interview_history", [])[-_CONSERVE_HISTORY:]

        # First question runs resume analysis first; later questions skip it.
        if not state.get("interview_history"):
            graph = build_first_question_graph(db)
        else:
            graph = build_question_graph(db)

        tokens_before = llm_service.total_tokens
        result = await graph.ainvoke(state)
        await record_tokens(str(session.id), llm_service.total_tokens - tokens_before)
        question = result.get("current_question") or {}

        # Persist the resume-derived profile on the first turn.
        profile = result.get("candidate_profile")
        if profile and not session.candidate_profile:
            session.candidate_profile = json.dumps(profile)
            await self._invalidate_state(session)  # cached state lacks the new profile

        session.current_question_data = json.dumps(question)

        return NextQuestionResponse(
            completed=False,
            question=self._question_to_response(question),
            questions_remaining=remaining,
        )

    async def evaluate_and_record(
        self,
        session: CandidateSession,
        interview: Interview,
        answer_text: str,
        db: AsyncSession,
    ) -> AnswerResponse:
        if not session.current_question_data:
            raise NoQuestionPendingError

        question: dict[str, Any] = json.loads(session.current_question_data)
        is_follow_up = bool(question.get("is_follow_up", False))

        answer_text, warnings = sanitize_answer(answer_text, str(session.id))
        for w in warnings:
            logger.info("Answer sanitization (session=%s): %s", session.id, w)

        mode = await check_token_budget(str(session.id))
        if mode == "exceeded":
            raise TokenBudgetExceededError

        state = await self._load_state(session, interview, db)
        state["current_question"] = question
        state["current_answer"] = answer_text
        # build_state_from_db counts follow-ups already persisted; the answer being
        # evaluated is itself the pending follow-up, so add one for it.
        state["follow_up_count"] = state.get("follow_up_count", 0) + (1 if is_follow_up else 0)
        # control_interview must see the count *after* this answer is recorded.
        state["questions_asked"] = state.get("questions_asked", 0) + (0 if is_follow_up else 1)
        if mode == "conserve":
            state["interview_history"] = state.get("interview_history", [])[-_CONSERVE_HISTORY:]

        role_level = interview.role_level or ""
        digest = hashlib.sha256(
            (question.get("question_text", "") + answer_text + role_level).encode()
        ).hexdigest()
        eval_key = redis_service.eval_key(digest)

        tokens_before = llm_service.total_tokens
        start = time.monotonic()
        try:
            cached_eval = await redis_service.get_cached(eval_key)
            if cached_eval is not None:
                logger.info("Evaluation cache hit: %s", eval_key)
                evaluation = cached_eval
            else:
                logger.info("Evaluation cache miss: %s", eval_key)
                evaluation = await consistency_checked_evaluation(
                    state, conserve=(mode == "conserve")
                )
                await redis_service.set_cached(eval_key, evaluation, ttl_seconds=_EVAL_TTL)

            state["current_evaluation"] = evaluation
            result = await build_routing_graph().ainvoke(state)
            needs_follow_up = bool(result.get("needs_follow_up", False))
            is_complete = bool(result.get("is_complete", False))
            follow_up_question = result.get("current_question") if needs_follow_up else None
        except Exception as exc:
            # The agents degrade internally, but never lose the candidate's answer.
            logger.error("Evaluation pipeline failed, recording fallback: %s", exc)
            evaluation = _FALLBACK_EVALUATION.model_dump()
            needs_follow_up = False
            is_complete = state["questions_asked"] >= interview.max_questions
            follow_up_question = None
        latency_ms = round((time.monotonic() - start) * 1000)
        await record_tokens(str(session.id), llm_service.total_tokens - tokens_before)

        corpus_id = question.get("corpus_question_id")
        response = Response(
            session_id=session.id,
            question_id=uuid.UUID(corpus_id) if corpus_id else None,
            question_text=question.get("question_text", ""),
            is_follow_up=is_follow_up,
            domain=question.get("domain"),
            answer_text=answer_text,
            score=evaluation["score"],
            accuracy=evaluation["accuracy"],
            completeness=evaluation["completeness"],
            clarity=evaluation["clarity"],
            feedback=evaluation["feedback"],
            latency_ms=latency_ms,
        )
        db.add(response)

        if needs_follow_up and follow_up_question:
            session.current_question_data = json.dumps(follow_up_question)
        else:
            session.current_question_data = None
            if is_complete:
                session.status = "completed"
                session.completed_at = datetime.now(timezone.utc)

        await db.flush()
        # A new response (and possibly completion) makes the cached state stale.
        await self._invalidate_state(session)

        return AnswerResponse(
            response_id=response.id,
            question_text=question.get("question_text", ""),
            evaluation=EvaluationResponse(**evaluation),
            is_last_question=is_complete and not needs_follow_up,
        )

    async def get_progress(
        self,
        session: CandidateSession,
        interview: Interview,
        db: AsyncSession,
    ) -> SessionProgressResponse:
        rows = list(
            (
                await db.execute(
                    select(Response.score, Response.is_follow_up).where(
                        Response.session_id == session.id
                    )
                )
            ).all()
        )
        # answered_questions counts main questions only; follow-ups are probes within one.
        main_answered = sum(1 for _, is_follow_up in rows if not is_follow_up)
        non_null = [score for score, _ in rows if score is not None]
        current_score = sum(non_null) / len(non_null) if non_null else None

        return SessionProgressResponse(
            total_questions=interview.max_questions,
            answered_questions=main_answered,
            current_score=current_score,
        )

    async def get_results(
        self,
        session: CandidateSession,
        interview: Interview,
        db: AsyncSession,
    ) -> SessionResultResponse:
        responses = list(
            (
                await db.execute(
                    select(Response)
                    .where(Response.session_id == session.id)
                    .order_by(Response.created_at)
                )
            )
            .scalars()
            .all()
        )
        details = [ResponseDetail.model_validate(r) for r in responses]
        non_null_scores = [r.score for r in responses if r.score is not None]
        overall = sum(non_null_scores) / len(non_null_scores) if non_null_scores else 0.0
        # answered_questions counts main questions only; follow-ups are probes within one.
        main_answered = sum(1 for r in responses if not r.is_follow_up)

        return SessionResultResponse(
            session_id=session.id,
            candidate_name=session.candidate_name,
            candidate_email=session.candidate_email,
            overall_score=overall,
            total_questions=interview.max_questions,
            answered_questions=main_answered,
            responses=details,
            started_at=session.started_at,
            completed_at=session.completed_at,
        )


interview_service = InterviewService()
