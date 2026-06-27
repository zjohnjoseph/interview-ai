"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import { Badge, formatDuration, scoreColorClass } from "@/components/ui";
import type { ResponseDetail, SessionResultResponse } from "@/lib/types";

export default function ResultsPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = Array.isArray(params.sessionId) ? params.sessionId[0] : params.sessionId;
  const router = useRouter();
  const [result, setResult] = useState<SessionResultResponse | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        setResult(await api.get<SessionResultResponse>(`/api/sessions/${sessionId}/results`));
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to load results");
      } finally {
        setReady(true);
      }
    })();
  }, [sessionId, router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 text-gray-500">
        Loading…
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-gray-50 text-gray-600">
        <p>Results not available.</p>
        <Link href="/dashboard" className="text-blue-600 hover:underline">
          Back to dashboard
        </Link>
      </div>
    );
  }

  // Precompute labels (follow-ups attach to their main question, e.g. "Q2 follow-up").
  const labels: string[] = [];
  let mainCount = 0;
  for (const r of result.responses) {
    if (!r.is_follow_up) mainCount += 1;
    labels.push(r.is_follow_up ? `Q${mainCount} follow-up` : `Q${mainCount}`);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="border-b bg-white px-6 py-3">
        <Link href="/dashboard" className="text-sm text-blue-600 hover:underline">
          ← Back to dashboard
        </Link>
      </nav>

      <main className="mx-auto max-w-3xl px-4 py-8">
        <div className="rounded-lg bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold text-gray-900">
            {result.candidate_name ?? "Candidate"}
          </h1>
          <p className="text-sm text-gray-500">{result.candidate_email ?? ""}</p>
          <div className="mt-4 flex flex-wrap gap-6">
            <Stat label="Overall score">
              <span className={`text-3xl font-bold ${scoreColorClass(result.overall_score)}`}>
                {result.overall_score !== null ? result.overall_score.toFixed(1) : "—"}
              </span>
              <span className="text-gray-400"> / 10</span>
            </Stat>
            <Stat label="Answered">
              <span className="text-3xl font-bold text-gray-900">
                {result.answered_questions}
              </span>
              <span className="text-gray-400"> / {result.total_questions}</span>
            </Stat>
            <Stat label="Duration">
              <span className="text-3xl font-bold text-gray-900">
                {formatDuration(result.started_at, result.completed_at)}
              </span>
            </Stat>
          </div>
        </div>

        <h2 className="mt-8 mb-3 text-lg font-semibold text-gray-900">Responses</h2>
        <div className="space-y-4">
          {result.responses.map((r, i) => (
            <ResponseCard key={r.id} response={r} label={labels[i]} />
          ))}
        </div>
      </main>
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function ResponseCard({ response: r, label }: { response: ResponseDetail; label: string }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-500">{label}</span>
        <span className={`text-2xl font-bold ${scoreColorClass(r.score)}`}>
          {r.score !== null ? r.score.toFixed(1) : "—"}
        </span>
      </div>
      <p className="mb-3 font-medium text-gray-900">{r.question_text}</p>

      <div className="mb-3 rounded bg-gray-50 p-3 text-sm text-gray-700">
        <div className="mb-1 text-xs font-semibold uppercase text-gray-400">Answer</div>
        <p className="whitespace-pre-line">{r.answer_text}</p>
      </div>

      <div className="mb-3 grid grid-cols-3 gap-2 text-center text-sm">
        <SubScore label="Accuracy" value={r.accuracy} />
        <SubScore label="Completeness" value={r.completeness} />
        <SubScore label="Clarity" value={r.clarity} />
      </div>

      {r.feedback && (
        <p className="mb-3 whitespace-pre-line text-sm text-gray-700">{r.feedback}</p>
      )}

      <div className="flex items-center gap-3 text-xs text-gray-400">
        {r.is_follow_up && <Badge value="follow-up" />}
        {r.latency_ms !== null && <span>{r.latency_ms} ms</span>}
      </div>
    </div>
  );
}

function SubScore({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="rounded border border-gray-200 py-2">
      <div className={`text-lg font-semibold ${scoreColorClass(value)}`}>
        {value !== null ? value.toFixed(1) : "—"}
      </div>
      <div className="text-gray-500">{label}</div>
    </div>
  );
}
