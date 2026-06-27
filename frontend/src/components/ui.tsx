// Small shared UI bits. Functional, not fancy.

// Score color: 8-10 green, 5-7 amber, 0-4 red.
export function scoreColorClass(score: number | null): string {
  if (score === null) return "text-gray-400";
  if (score >= 8) return "text-green-600";
  if (score >= 5) return "text-amber-600";
  return "text-red-600";
}

const BADGE_COLORS: Record<string, string> = {
  draft: "bg-gray-200 text-gray-700",
  active: "bg-green-100 text-green-800",
  archived: "bg-gray-300 text-gray-600",
  pending: "bg-yellow-100 text-yellow-800",
  completed: "bg-blue-100 text-blue-800",
};

export function Badge({ value }: { value: string }) {
  const cls = BADGE_COLORS[value] ?? "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}>
      {value}
    </span>
  );
}

// "3m 42s" between two ISO timestamps, or "—" if missing.
export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const secs = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}
