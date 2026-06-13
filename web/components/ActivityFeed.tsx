"use client";

import clsx from "clsx";

import type { Finding } from "@/lib/deck";
import { SPECIALIST_LABEL } from "@/lib/deck";
import { SPECIALIST_COLOR, effectVerb, type Discovery } from "@/lib/discoveries";

export type ActivityPhase = "idle" | "investigating" | "deciding" | "converged";

// Belief in motion, not a log entry: "Reliability abandoning Traffic overload",
// "Access strengthening Secret access failure". Progressive verbs keep the feed evolving.
function beliefShift(d: Discovery): string {
  if (d.theoryStatus === "eliminated") return "abandoning";
  if (d.theoryStatus === "confirmed") return "confirmed";
  if (d.theoryStatus === "leading") return "converging on";
  if (d.stance === "weakens" || d.theoryStatus === "weakening") return "weakening";
  if (d.theoryStatus === "strengthening") return "strengthening";
  return "raising";
}

// One small "label: value" line inside an expanded trail row.
function Meta({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr] gap-2">
      <span className="pt-px font-mono text-[9px] uppercase tracking-wider text-ink-600">{label}</span>
      <div className="min-w-0 text-[11px] text-ink-300">{children}</div>
    </div>
  );
}

function Row({
  d,
  opacity,
  expanded,
  onToggle,
  onViewProof,
}: {
  d: Discovery;
  opacity: number;
  expanded: boolean;
  onToggle: () => void;
  onViewProof: (f: Finding) => void;
}) {
  const color = SPECIALIST_COLOR[d.specialist];
  const finding = d.finding;
  return (
    <div
      style={{ opacity: expanded ? 1 : opacity }}
      className="animate-[fadeIn_0.45s_ease] transition-opacity duration-700"
    >
      <button
        onClick={finding ? onToggle : undefined}
        className={clsx(
          "flex w-full items-baseline gap-1.5 text-left text-[12px] leading-tight",
          finding ? "cursor-pointer hover:!opacity-100" : "cursor-default",
        )}
      >
        {finding && (
          <span className="font-mono text-[9px] text-ink-600">{expanded ? "▾" : "▸"}</span>
        )}
        <span className="font-medium" style={{ color }}>
          {SPECIALIST_LABEL[d.specialist]}
        </span>
        <span className="text-ink-400">
          {beliefShift(d)} {d.theoryLabel}
        </span>
      </button>

      {expanded && finding && (
        <div className="ml-2 mt-2 max-h-[34vh] space-y-2 overflow-y-auto border-l border-ink-800 pl-3 animate-[fadeIn_0.3s_ease]">
          <Meta label="Specialist">
            <span style={{ color }}>{SPECIALIST_LABEL[d.specialist]}</span>
          </Meta>
          {d.purpose && <Meta label="Purpose">{d.purpose}</Meta>}
          <Meta label="SPL">
            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded border border-ink-800 bg-ink-950 p-2 font-mono text-[10px] leading-relaxed text-ink-300">
              {finding.source_query_spl}
            </pre>
          </Meta>
          <Meta label="Finding">
            <span className="text-ink-200">{finding.claim}</span>
          </Meta>
          {d.theoryLabel && (
            <Meta label="Impact">
              <span className="text-ink-300">
                {effectVerb(d.stance, d.theoryStatus)}{" "}
                <span style={{ color }}>{d.theoryLabel}</span>
              </span>
            </Meta>
          )}
          <button
            onClick={() => onViewProof(finding)}
            className="mt-1 border border-sky-700/60 bg-sky-950/30 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-sky-200 transition hover:border-sky-500/70 hover:bg-sky-900/40"
          >
            View proof →
          </button>
        </div>
      )}
    </div>
  );
}

// The room's activity, accumulating — and, once a finding lands, the evidence browser itself:
// click a row to expand it inline (purpose · SPL · finding · theory impact) and "View proof" to
// open the compact internal proof modal. Vertical and quiet — beliefs accrue, the UI doesn't
// perform.
export function ActivityFeed({
  discoveries,
  phase,
  expandedId,
  onToggle,
  onViewProof,
}: {
  discoveries: Discovery[];
  phase: ActivityPhase;
  expandedId: string | null;
  onToggle: (stepId: string) => void;
  onViewProof: (f: Finding) => void;
}) {
  const recent = discoveries.slice(-5);
  const hidden = discoveries.length - recent.length;

  // Before the room is pointed anywhere: no evidence exists yet — say so plainly. Nothing here
  // is precomputed; the trail fills in only as specialists actually query Splunk.
  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-1 text-[12px] leading-tight text-ink-600">
        <span>No evidence collected yet.</span>
        <span className="text-ink-700">Specialists have not queried Splunk yet.</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {hidden > 0 && <div className="text-[11px] text-ink-700">+{hidden} earlier</div>}
      {recent.map((d, i) => (
        <Row
          key={d.stepId}
          d={d}
          // Older shifts recede; the newest sits brightest.
          opacity={0.45 + (0.5 * (i + 1)) / recent.length}
          expanded={expandedId === d.stepId}
          onToggle={() => onToggle(d.stepId)}
          onViewProof={onViewProof}
        />
      ))}
      {/* The room keeps reasoning — including while the user is deciding. */}
      {(phase === "investigating" || phase === "deciding") && (
        <div className="flex items-baseline gap-2 text-[12px] leading-tight text-sky-300/70">
          <span className="animate-[breathe_2.4s_ease-in-out_infinite]">→</span>
          <span>{phase === "deciding" ? "specialists cross-checking…" : "room investigating…"}</span>
        </div>
      )}
      {phase === "converged" && (
        <div className="flex items-baseline gap-2 text-[12px] leading-tight text-emerald-300/90">
          <span className="h-1.5 w-1.5 self-center rounded-full bg-emerald-400" />
          <span>room reached agreement — open a step to see its proof</span>
        </div>
      )}
    </div>
  );
}
