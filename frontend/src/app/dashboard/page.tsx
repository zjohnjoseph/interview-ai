"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { clearToken, isAuthenticated } from "@/lib/auth";
import { Badge } from "@/components/ui";
import type { InterviewResponse, SessionResponse, UserResponse } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [interviews, setInterviews] = useState<InterviewResponse[]>([]);
  const [ready, setReady] = useState(false);

  const loadInterviews = useCallback(async () => {
    const list = await api.get<InterviewResponse[]>("/api/interviews/");
    setInterviews(list);
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const me = await api.get<UserResponse>("/api/auth/me");
        setUser(me);
        await loadInterviews();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to load dashboard");
      } finally {
        setReady(true);
      }
    })();
  }, [router, loadInterviews]);

  function logout() {
    clearToken();
    router.replace("/login");
  }

  function updateInterview(updated: InterviewResponse) {
    setInterviews((prev) => prev.map((i) => (i.id === updated.id ? updated : i)));
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 text-gray-500">
        Loading…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="flex items-center justify-between border-b bg-white px-6 py-3">
        <span className="text-lg font-semibold text-gray-900">InterviewAI</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-600">{user?.name}</span>
          <button
            onClick={logout}
            className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-100"
          >
            Log out
          </button>
        </div>
      </nav>

      <main className="mx-auto max-w-3xl px-4 py-8">
        <CreateInterviewForm onCreated={loadInterviews} />

        <h2 className="mt-10 mb-3 text-lg font-semibold text-gray-900">Your interviews</h2>
        {interviews.length === 0 ? (
          <p className="text-sm text-gray-500">No interviews yet. Create one above.</p>
        ) : (
          <div className="space-y-3">
            {interviews.map((iv) => (
              <InterviewCard key={iv.id} interview={iv} onUpdated={updateInterview} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

function CreateInterviewForm({ onCreated }: { onCreated: () => Promise<void> }) {
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [requiredSkills, setRequiredSkills] = useState("");
  const [roleLevel, setRoleLevel] = useState("mid");
  const [maxQuestions, setMaxQuestions] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await api.post<InterviewResponse>("/api/interviews/", {
        job_title: jobTitle,
        job_description: jobDescription,
        required_skills: requiredSkills,
        role_level: roleLevel,
        max_questions: maxQuestions,
      });
      toast.success("Interview created");
      setJobTitle("");
      setJobDescription("");
      setRequiredSkills("");
      setRoleLevel("mid");
      setMaxQuestions(10);
      await onCreated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create interview");
    } finally {
      setSubmitting(false);
    }
  }

  const input =
    "w-full rounded border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none";

  return (
    <form onSubmit={onSubmit} className="rounded-lg bg-white p-6 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">Create an interview</h2>
      <div className="space-y-3">
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Job title</label>
          <input className={input} required minLength={3} value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">
            Job description <span className="text-gray-400">(min 50 chars)</span>
          </label>
          <textarea className={`${input} h-28`} required minLength={50} value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-gray-700">Required skills</label>
          <input className={input} required minLength={5} value={requiredSkills}
            onChange={(e) => setRequiredSkills(e.target.value)}
            placeholder="e.g. Python, SQL, system design" />
        </div>
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="mb-1 block text-sm font-medium text-gray-700">Role level</label>
            <select className={input} value={roleLevel}
              onChange={(e) => setRoleLevel(e.target.value)}>
              <option value="junior">Junior</option>
              <option value="mid">Mid</option>
              <option value="senior">Senior</option>
            </select>
          </div>
          <div className="w-36">
            <label className="mb-1 block text-sm font-medium text-gray-700">Max questions</label>
            <input className={input} type="number" min={3} max={15} value={maxQuestions}
              onChange={(e) => setMaxQuestions(Number(e.target.value))} />
          </div>
        </div>
      </div>
      <button type="submit" disabled={submitting}
        className="mt-4 rounded bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-60">
        {submitting ? "Creating…" : "Create Interview"}
      </button>
    </form>
  );
}

function InterviewCard({
  interview,
  onUpdated,
}: {
  interview: InterviewResponse;
  onUpdated: (i: InterviewResponse) => void;
}) {
  const [publishing, setPublishing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [sessions, setSessions] = useState<SessionResponse[] | null>(null);

  async function publish() {
    setPublishing(true);
    try {
      const updated = await api.post<InterviewResponse>(
        `/api/interviews/${interview.id}/publish`,
      );
      onUpdated(updated);
      toast.success("Interview published");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setPublishing(false);
    }
  }

  async function loadSessions() {
    try {
      const list = await api.get<SessionResponse[]>(`/api/interviews/${interview.id}/sessions`);
      setSessions(list);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load sessions");
    }
  }

  return (
    <div className="rounded-lg bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <div className="font-medium text-gray-900">{interview.job_title}</div>
          <div className="mt-1 text-sm text-gray-500">
            {interview.role_level} · {interview.max_questions} questions ·{" "}
            {new Date(interview.created_at).toLocaleDateString()}
          </div>
        </div>
        <Badge value={interview.status} />
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {interview.status === "draft" && (
          <button onClick={publish} disabled={publishing}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-60">
            {publishing ? "Publishing…" : "Publish"}
          </button>
        )}
        {interview.status === "active" && (
          <>
            <button onClick={() => setShowAdd((s) => !s)}
              className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-100">
              {showAdd ? "Cancel" : "Add Candidate"}
            </button>
            <button onClick={() => (sessions === null ? loadSessions() : setSessions(null))}
              className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-100">
              {sessions === null ? "View Sessions" : "Hide Sessions"}
            </button>
          </>
        )}
      </div>

      {showAdd && <AddCandidateForm interviewId={interview.id} />}
      {sessions !== null && <SessionList sessions={sessions} />}
    </div>
  );
}

function AddCandidateForm({ interviewId }: { interviewId: string }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [inviteLink, setInviteLink] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      toast.error("Please choose a resume PDF");
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("candidate_name", name);
      fd.append("candidate_email", email);
      fd.append("resume", file);
      const session = await api.upload<SessionResponse>(
        `/api/interviews/${interviewId}/candidates`,
        fd,
      );
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      setInviteLink(`${origin}/interview/${session.token}`);
      toast.success("Candidate added");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function copyLink() {
    if (!inviteLink) return;
    await navigator.clipboard.writeText(inviteLink);
    toast.success("Link copied");
  }

  const input =
    "w-full rounded border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none";

  if (inviteLink) {
    return (
      <div className="mt-3 rounded border border-green-200 bg-green-50 p-3 text-sm">
        <div className="mb-1 font-medium text-green-800">Invite link</div>
        <div className="flex items-center gap-2">
          <code className="flex-1 truncate rounded bg-white px-2 py-1 text-gray-800">
            {inviteLink}
          </code>
          <button onClick={copyLink}
            className="rounded bg-green-600 px-3 py-1 text-white hover:bg-green-700">
            Copy
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="mt-3 space-y-2 rounded border border-gray-200 bg-gray-50 p-3">
      <input className={input} placeholder="Candidate name" required minLength={2}
        value={name} onChange={(e) => setName(e.target.value)} />
      <input className={input} type="email" placeholder="Candidate email" required
        value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="block w-full text-sm text-gray-700" type="file" accept=".pdf,application/pdf"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <button type="submit" disabled={submitting}
        className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-60">
        {submitting ? "Uploading…" : "Upload"}
      </button>
    </form>
  );
}

function SessionList({ sessions }: { sessions: SessionResponse[] }) {
  if (sessions.length === 0) {
    return <p className="mt-3 text-sm text-gray-500">No candidates yet.</p>;
  }
  return (
    <ul className="mt-3 divide-y rounded border border-gray-200">
      {sessions.map((s) => (
        <li key={s.id} className="flex items-center justify-between px-3 py-2 text-sm">
          <div>
            <span className="text-gray-900">{s.candidate_name ?? "—"}</span>{" "}
            <span className="text-gray-500">{s.candidate_email ?? ""}</span>
          </div>
          <div className="flex items-center gap-3">
            <Badge value={s.status} />
            {s.status === "completed" && (
              <Link href={`/results/${s.id}`} className="text-blue-600 hover:underline">
                View Results
              </Link>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
