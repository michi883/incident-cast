"use client";

import { format, parseISO } from "date-fns";
import clsx from "clsx";

import type { Finding, SpecialistName } from "@/lib/deck";
import { SPECIALIST_LABEL } from "@/lib/deck";

const SPECIALIST_DOT: Record<SpecialistName, string> = {
  reliability: "bg-specialist-reliability",
  deployment: "bg-specialist-deployment",
  access: "bg-specialist-access",
  blast_radius: "bg-specialist-blast_radius",
};

export function EvidenceChip({ finding, onClick }: { finding: Finding; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group flex w-full items-start gap-3 rounded-md border border-ink-800 bg-ink-900/60 px-3 py-2 text-left transition hover:border-ink-600 hover:bg-ink-800"
    >
      <span
        className={clsx(
          "mt-1.5 h-2 w-2 shrink-0 rounded-full",
          SPECIALIST_DOT[finding.specialist],
          finding.severity === "critical" && "ring-2 ring-severity-critical/40",
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="text-xs text-ink-100">{finding.claim}</div>
        <div className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-ink-500">
          <span>{SPECIALIST_LABEL[finding.specialist]}</span>
          <span>·</span>
          <span>{format(parseISO(finding.timestamp), "HH:mm:ss")}</span>
          <span>·</span>
          <span className="truncate">{finding.source_query_name}</span>
        </div>
      </div>
      <span className="font-mono text-[10px] text-ink-600 group-hover:text-ink-300">→</span>
    </button>
  );
}
