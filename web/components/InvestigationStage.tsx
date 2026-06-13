"use client";

import type { Finding, SpecialistName } from "@/lib/deck";
import { BACKEND_SOURCE_LABEL, SPECIALIST_LABEL } from "@/lib/deck";
import { effectVerb, SPECIALIST_COLOR, type Discovery } from "@/lib/discoveries";

// The theory this discovery moved — "↑ strengthens Secret access failure", in the theory's color.
function EffectChip({ d, accent }: { d: Discovery; accent: string | null }) {
  if (!d.theoryLabel) return null;
  const weakens = d.stance === "weakens" || d.theoryStatus === "eliminated";
  const color = accent ?? "#64748b";
  return (
    <span
      className="inline-flex items-center gap-1.5 border px-2.5 py-1 text-xs"
      style={{ borderColor: `${color}66`, color }}
    >
      <span aria-hidden>{weakens ? "↓" : "↑"}</span>
      {effectVerb(d.stance, d.theoryStatus)} {d.theoryLabel}
    </span>
  );
}

function EvidenceLink({ finding, onSelect }: { finding: Finding; onSelect: (f: Finding) => void }) {
  return (
    <span className="flex items-center gap-1.5">
      {finding.backend !== "fixture" && (
        <span
          className="font-mono text-[9px] uppercase tracking-wider text-emerald-300/70"
          title={`Evidence sourced live from ${BACKEND_SOURCE_LABEL[finding.backend]}`}
        >
          via {finding.backend}
        </span>
      )}
      <button
        onClick={() => onSelect(finding)}
        className="font-mono text-[11px] text-sky-400/80 transition hover:text-sky-200"
      >
        view proof →
      </button>
    </span>
  );
}

// The one discovery in focus — the largest, most readable thing in the frame.
export function ActiveDiscoveryStage({
  d,
  accent,
  onSelect,
}: {
  d: Discovery;
  accent: string | null;
  onSelect: (f: Finding) => void;
}) {
  const authors: SpecialistName[] = [d.specialist, ...d.coAuthors];
  return (
    <div key={d.stepId} className="flex max-w-3xl animate-[popIn_0.5s_ease] flex-col items-center text-center">
      {/* Just who is reasoning — no "active discovery" scaffolding. The content is the signal. */}
      <div className="flex items-center gap-2.5 text-sm font-medium tracking-tight">
        {authors.map((s) => (
          <span key={s} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: SPECIALIST_COLOR[s] }} />
            <span style={{ color: SPECIALIST_COLOR[s] }}>{SPECIALIST_LABEL[s]}</span>
          </span>
        ))}
      </div>

      <p className="mt-3 text-2xl font-medium leading-tight tracking-tight text-ink-50 sm:text-3xl">
        {d.text}
      </p>

      <div className="mt-5 flex items-center gap-4">
        <EffectChip d={d} accent={accent} />
        {d.finding && <EvidenceLink finding={d.finding} onSelect={onSelect} />}
      </div>
    </div>
  );
}

// Before the first discovery: the alert is the centerpiece.
export function AlertStage({ headline }: { headline: string }) {
  return (
    <div className="flex max-w-2xl animate-[popIn_0.5s_ease] flex-col items-center text-center">
      <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-rose-300/80">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-500/70" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-rose-500" />
        </span>
        Incident open
      </div>
      <p className="mt-5 text-2xl font-medium leading-tight tracking-tight text-ink-100 sm:text-3xl">
        {headline}
      </p>
    </div>
  );
}

// The persistent converged statement (the transient overlay is the climax; this is what stays).
export function ConvergedStage({
  rootCause,
  revision,
  supporters,
}: {
  rootCause: string | null;
  revision: string | null;
  supporters: SpecialistName[];
}) {
  return (
    <div className="flex max-w-2xl animate-[popIn_0.5s_ease] flex-col items-center text-center">
      <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-emerald-300/90">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        Room converged
      </div>
      <div className="mt-4 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-500">Root cause</div>
      <p
        className="mt-1 text-3xl font-semibold leading-tight tracking-tight text-emerald-50 sm:text-4xl"
        style={{ textShadow: "0 0 40px rgba(16,185,129,0.35)" }}
      >
        {rootCause}
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-x-6 gap-y-1 text-sm text-ink-400">
        {revision && (
          <span>
            <span className="text-ink-600">revision</span>{" "}
            <span className="font-mono text-ink-200">{revision}</span>
          </span>
        )}
        {supporters.length > 0 && (
          <span>
            <span className="text-ink-600">confirmed by</span>{" "}
            <span className="text-ink-200">{supporters.map((s) => SPECIALIST_LABEL[s]).join(" + ")}</span>
          </span>
        )}
      </div>
    </div>
  );
}

export { EffectChip, EvidenceLink };
