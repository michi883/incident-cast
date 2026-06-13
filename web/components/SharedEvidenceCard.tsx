"use client";

import { format, parseISO } from "date-fns";
import clsx from "clsx";

import type { Finding, SharedEvidence, SpecialistName } from "@/lib/deck";
import { SPECIALIST_LABEL } from "@/lib/deck";
import { EvidenceChip } from "./EvidenceChip";

const SPECIALIST_BG: Record<SpecialistName, string> = {
  reliability: "bg-specialist-reliability/15 text-specialist-reliability",
  deployment: "bg-specialist-deployment/15 text-specialist-deployment",
  access: "bg-specialist-access/15 text-specialist-access",
  blast_radius: "bg-specialist-blast_radius/15 text-specialist-blast_radius",
};

export function SharedEvidenceCard({
  evidence,
  onSelect,
}: {
  evidence: SharedEvidence;
  onSelect: (f: Finding) => void;
}) {
  const support = evidence.supporting_specialists.length;
  return (
    <article className="rounded-lg border border-ink-800 bg-ink-800/30 p-5">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm text-ink-100">{evidence.text}</p>
        <SupportBadge n={support} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {evidence.supporting_specialists.map((s) => (
          <span
            key={s}
            className={clsx("rounded px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider", SPECIALIST_BG[s])}
          >
            {SPECIALIST_LABEL[s]}
          </span>
        ))}
      </div>
      {Object.keys(evidence.entities).length > 0 && (
        <dl className="mt-3 grid grid-cols-1 gap-1.5 text-xs">
          {Object.entries(evidence.entities).map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <dt className="text-ink-500">{k}</dt>
              <dd className="truncate font-mono text-ink-200">{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="mt-3 text-xs text-ink-400">
        {format(parseISO(evidence.window[0]), "HH:mm:ss")} →{" "}
        {format(parseISO(evidence.window[1]), "HH:mm:ss")} UTC
      </div>
      <div className="mt-4 space-y-2">
        {evidence.supporting_findings.map((f, i) => (
          <EvidenceChip key={i} finding={f} onClick={() => onSelect(f)} />
        ))}
      </div>
    </article>
  );
}

function SupportBadge({ n }: { n: number }) {
  return (
    <span
      className={clsx(
        "shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wider",
        n >= 3
          ? "bg-emerald-500/20 text-emerald-300"
          : n === 2
            ? "bg-sky-500/20 text-sky-300"
            : "bg-ink-700/60 text-ink-300",
      )}
    >
      {n} {n === 1 ? "specialist" : "specialists"}
    </span>
  );
}
