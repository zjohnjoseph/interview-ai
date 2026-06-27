"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { Badge, scoreColorClass } from "@/components/ui";
import type {
  AnswerResponse,
  NextQuestionResponse,
  ProgressResponse,
  QuestionData,
} from "@/lib/types";

type Phase = "loading" | "join" | "answering" | "feedback" | "complete" | "error";

export default function InterviewPage() {
  const params = useParams<{ token: string }>();
  const token = Array.isArray(params.token) ? params.token[0] : params.token;

  const [phase, setPhase] = useState<Phase>("loading");
  const [errorMsg, setErrorMsg] = useState("");
  const [question, setQuestion] = useState<QuestionData | null>(null);
  const [remaining, setRemaining] = useState(0);
  const [questionNo, setQuestionNo] = useState(0);
  const [answer, setAnswer] = useState("");
  const [evaluation, setEvaluation] = useState<AnswerResponse | null>(null);
  const [progress, setProgress] = useState<ProgressResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  const fetchNext = useCallback(async () => {
    setBusy(true);
    try {
      const res = await api.get<NextQuestionResponse>(`/api/sessions/${token}/next`);
      if (res.completed || !res.question) {
        try {
          setProgress(await api.get<ProgressResponse>(`/api/sessions/${token}/progress`));
        } catch {
          /* progress is optional */
        }
        setPhase("complete");
      } else {
        setQuestion(res.question);
        setRemaining(res.questions_remaining);
        setQuestionNo((n) => n + 1);
        setAnswer("");
        setPhase("answering");
      }
    } catch (err) {
      // A 400 just means "not joined yet" — show the join form. Other statuses
      // are terminal (bad/expired token, or service busy).
      if (err instanceof ApiError && err.status === 400) {
        setPhase("join");
      } else if (err instanceof ApiError && err.status === 404) {
        setErrorMsg("Invalid invite link.");
        setPhase("error");
      } else if (err instanceof ApiError && err.status === 410) {
        setErrorMsg("This invite link has expired.");
        setPhase("error");
      } else if (err instanceof ApiError && err.status === 503) {
        setErrorMsg("The service is busy. Please try again shortly.");
        setPhase("error");
      } else {
        setErrorMsg(err instanceof Error ? err.message : "Something went wrong.");
        setPhase("error");
      }
    } finally {
      setBusy(false);
    }
  }, [token]);

  // On load, probe /next: resumes an in-progress interview, or falls to the join form.
  useEffect(() => {
    if (!token || started.current) return;
    started.current = true;
    fetchNext();
  }, [token, fetchNext]);

  if (phase === "loading") return <Centered>Loading…</Centered>;
  if (phase === "error") return <Centered>{errorMsg}</Centered>;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-2xl px-4 py-10">
        {phase === "join" && <JoinForm token={token} onJoined={fetchNext} />}

        {phase === "answering" && question && (
          <AnswerForm
            question={question}
            questionNo={questionNo}
            remaining={remaining}
            answer={answer}
            setAnswer={setAnswer}
            busy={busy}
            onSubmit={async () => {
              setBusy(true);
              try {
                const res = await api.post<AnswerResponse>(
                  `/api/sessions/${token}/answers`,
                  { answer_text: answer },
                );
                setEvaluation(res);
                setPhase("feedback");
              } catch (err) {
                toast.error(err instanceof Error ? err.message : "Failed to submit answer");
              } finally {
                setBusy(false);
              }
            }}
          />
        )}

        {phase === "feedback" && evaluation && (
          <Feedback
            data={evaluation}
            busy={busy}
            onNext={fetchNext}
          />
        )}

        {phase === "complete" && <Complete progress={progress} />}
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center text-gray-600">
      {children}
    </div>
  );
}

function JoinForm({ token, onJoined }: { token: string; onJoined: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post(`/api/sessions/${token}/join`, {
        candidate_name: name,
        candidate_email: email,
      });
      await onJoined();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start the interview");
      setSubmitting(false);
    }
  }

  const input =
    "w-full rounded border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none";

  return (
    <form onSubmit={onSubmit} className="rounded-lg bg-white p-8 shadow-md">
      <h1 className="mb-2 text-2xl font-semibold text-gray-900">Technical Interview</h1>
      <p className="mb-6 text-sm text-gray-600">
        Enter your details to begin. You&apos;ll answer a series of questions and get
        scored feedback after each one.
      </p>
      <label className="mb-1 block text-sm font-medium text-gray-700">Full name</label>
      <input className={`mb-4 ${input}`} required minLength={2}
        value={name} onChange={(e) => setName(e.target.value)} />
      <label className="mb-1 block text-sm font-medium text-gray-700">Email</label>
      <input className={`mb-6 ${input}`} type="email" required
        value={email} onChange={(e) => setEmail(e.target.value)} />
      <button type="submit" disabled={submitting}
        className="w-full rounded bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
        {submitting ? "Starting…" : "Start Interview"}
      </button>
    </form>
  );
}

function AnswerForm({
  question, questionNo, remaining, answer, setAnswer, busy, onSubmit,
}: {
  question: QuestionData;
  questionNo: number;
  remaining: number;
  answer: string;
  setAnswer: (v: string) => void;
  busy: boolean;
  onSubmit: () => void;
}) {
  return (
    <div className="rounded-lg bg-white p-8 shadow-md">
      <div className="mb-4 flex items-center justify-between text-sm text-gray-500">
        <span>Question {questionNo}</span>
        <span className="flex items-center gap-2">
          <Badge value={question.domain} />
          <Badge value={question.difficulty} />
          <span>{remaining} remaining</span>
        </span>
      </div>
      <p className="mb-5 text-lg font-medium text-gray-900">{question.text}</p>
      <textarea
        className="h-48 w-full rounded border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none"
        placeholder="Type your answer…"
        value={answer}
        onChange={(e) => setAnswer(e.target.value)}
      />
      <button
        onClick={onSubmit}
        disabled={busy || answer.trim().length === 0}
        className="mt-4 w-full rounded bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60"
      >
        {busy ? "Evaluating…" : "Submit Answer"}
      </button>
    </div>
  );
}

function Feedback({
  data, busy, onNext,
}: {
  data: AnswerResponse;
  busy: boolean;
  onNext: () => void;
}) {
  const e = data.evaluation;
  return (
    <div className="rounded-lg bg-white p-8 shadow-md">
      <div className="mb-4 flex items-baseline gap-3">
        <span className={`text-5xl font-bold ${scoreColorClass(e.score)}`}>
          {e.score.toFixed(1)}
        </span>
        <span className="text-gray-500">/ 10</span>
      </div>
      <div className="mb-4 grid grid-cols-3 gap-3 text-center text-sm">
        <Metric label="Accuracy" value={e.accuracy} />
        <Metric label="Completeness" value={e.completeness} />
        <Metric label="Clarity" value={e.clarity} />
      </div>
      <p className="mb-6 whitespace-pre-line text-gray-700">{e.feedback}</p>
      {data.is_last_question ? (
        <button onClick={onNext} disabled={busy}
          className="w-full rounded bg-green-600 py-2 font-medium text-white hover:bg-green-700 disabled:opacity-60">
          {busy ? "Finishing…" : "Finish Interview"}
        </button>
      ) : (
        <button onClick={onNext} disabled={busy}
          className="w-full rounded bg-blue-600 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
          {busy ? "Loading…" : "Next Question"}
        </button>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-gray-200 py-2">
      <div className={`text-xl font-semibold ${scoreColorClass(value)}`}>{value.toFixed(1)}</div>
      <div className="text-gray-500">{label}</div>
    </div>
  );
}

function Complete({ progress }: { progress: ProgressResponse | null }) {
  return (
    <div className="rounded-lg bg-white p-8 text-center shadow-md">
      <h1 className="mb-2 text-2xl font-semibold text-gray-900">Interview Complete</h1>
      <p className="text-gray-600">Thanks for your time — your responses have been recorded.</p>
      {progress && (
        <div className="mt-6 text-sm text-gray-700">
          <div>
            Answered {progress.answered_questions} of {progress.total_questions} questions
          </div>
          {progress.current_score !== null && (
            <div className="mt-1">
              Overall score:{" "}
              <span className={`font-semibold ${scoreColorClass(progress.current_score)}`}>
                {progress.current_score.toFixed(1)}
              </span>{" "}
              / 10
            </div>
          )}
        </div>
      )}
    </div>
  );
}
