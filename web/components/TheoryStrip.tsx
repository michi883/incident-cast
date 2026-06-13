"use client";

import clsx from "clsx";

import { THEORY_STATUS_LABEL, type TheoryState, type TheoryStatus } from "@/lib/replay";

// Survivors left, dying theories right — elimination reads as the board reordering.
const STATUS_RANK: Record<TheoryStatus, number> = {
  confirmed: 0,
  leading: 1,
  strengthening: 2,
  possible: 3,
  forming: 4,
  weakening: 5,
  eliminated: 6,
};

const STATUS_ARROW: Partial<Record<TheoryStatus, string>> = {
  weakening: "↓",
  strengthening: "↑",
  leading: "★",
  confirmed: "✓",
  eliminated: "✕",
};

const STATUS_TONE: Record<TheoryStatus, string> = {
  forming: "text-ink-500",
  possible: "text-ink-400",
  weakening: "text-amber-300/70",
  strengthening: "text-sky-200/90",
  leading: "text-sky-100",
  eliminated: "text-ink-600",
  confirmed: "text-emerald-200",
};

function Chip({ t, accent }: { t: TheoryState; accent: string }) {
  const eliminated = t.status === "eliminated";
  const confirmed = t.status === "confirmed";
  const weakening = t.status === "weakening";
  const dominant = confirmed || t.status === "leading";

  return (
    <div
      className={clsx(
        // Borders only where they carry meaning: the dominant theory gets an accent edge,
        // everything else floats on subtle fill so the survivor is what the eye lands on.
        "flex items-center gap-2 transition-all duration-700",
        dominant ? "scale-110 border px-3.5 py-2" : "border-0 px-3 py-1.5",
        !dominant && !eliminated && "bg-ink-900/40",
        weakening && "opacity-55",
        eliminated && "scale-[0.82] opacity-25 saturate-0",
      )}
      style={{
        borderColor: dominant ? accent : undefined,
        boxShadow: confirmed
          ? `0 0 34px -6px ${accent}`
          : dominant
          ? `0 0 30px -14px ${accent}, inset 0 0 30px -18px ${accent}`
          : undefined,
      }}
    >
      <span
        className="shrink-0 rounded-full"
        style={{
          background: eliminated ? "#3b3f4c" : accent,
          width: dominant ? 9 : 8,
          height: dominant ? 9 : 8,
          boxShadow: dominant ? `0 0 10px -1px ${accent}` : undefined,
        }}
      />
      <span
        className={clsx(
          "font-medium tracking-tight",
          dominant ? "text-base text-white" : "text-sm",
          eliminated ? "text-ink-600 line-through" : !dominant && "text-ink-300",
        )}
      >
        {t.label}
      </span>
      <span
        className={clsx(
          "font-mono uppercase tracking-wide",
          dominant ? "text-[11px]" : "text-[10px]",
          STATUS_TONE[t.status],
        )}
      >
        {STATUS_ARROW[t.status] ?? ""} {THEORY_STATUS_LABEL[t.status]}
      </span>
    </div>
  );
}

// The emotional spine: live hypotheses as a single compact row. No vertical board — the demo
// frame shows theory state at a glance, with elimination felt through dim/strike/reorder.
export function TheoryStrip({
  theories,
  accents,
}: {
  theories: TheoryState[];
  accents: Record<string, string>;
}) {
  // Nothing yet: stay quiet (the consensus line carries "no theories yet").
  if (theories.length === 0) return null;

  const ordered = theories
    .map((t, i) => ({ t, i }))
    .sort((a, b) => STATUS_RANK[a.t.status] - STATUS_RANK[b.t.status] || a.i - b.i)
    .map(({ t }) => t);

  // Once a cause is confirmed, ruled-out theories collapse to a quiet count so the surviving
  // theory stands alone — convergence as a distinct state, not just another recolor.
  const converged = ordered.some((t) => t.status === "confirmed");
  const shown = converged ? ordered.filter((t) => t.status !== "eliminated") : ordered;
  const ruledOut = ordered.length - shown.length;

  return (
    <div className="flex flex-wrap items-center justify-center gap-2">
      {shown.map((t) => (
        <Chip key={t.id} t={t} accent={accents[t.id] ?? "#64748b"} />
      ))}
      {ruledOut > 0 && (
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-600">
          ✕ {ruledOut} ruled out
        </span>
      )}
    </div>
  );
}
