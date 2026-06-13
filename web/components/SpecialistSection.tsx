"use client";

import clsx from "clsx";

import type { Finding, SpecialistName, SpecialistSection as Section } from "@/lib/deck";
import { SPECIALIST_LABEL } from "@/lib/deck";
import { EvidenceChip } from "./EvidenceChip";

const SPECIALIST_ACCENT: Record<SpecialistName, string> = {
  reliability: "border-specialist-reliability/40",
  deployment: "border-specialist-deployment/40",
  access: "border-specialist-access/40",
  blast_radius: "border-specialist-blast_radius/40",
};

const SPECIALIST_TEXT: Record<SpecialistName, string> = {
  reliability: "text-specialist-reliability",
  deployment: "text-specialist-deployment",
  access: "text-specialist-access",
  blast_radius: "text-specialist-blast_radius",
};

export function SpecialistSection({
  section,
  onSelect,
}: {
  section: Section;
  onSelect: (f: Finding) => void;
}) {
  const { spec, findings, summary } = section;
  return (
    <article
      className={clsx(
        "rounded-lg border-l-4 bg-ink-800/30 p-5",
        SPECIALIST_ACCENT[spec.name],
        "border-y border-r border-ink-800",
      )}
    >
      <header className="flex items-baseline justify-between gap-4">
        <div>
          <h3 className={clsx("text-base font-semibold", SPECIALIST_TEXT[spec.name])}>
            {SPECIALIST_LABEL[spec.name]} · {spec.title}
          </h3>
          <p className="mt-0.5 text-xs italic text-ink-400">"{spec.lead_question}"</p>
        </div>
        <span className="font-mono text-xs text-ink-500">
          {findings.length} finding{findings.length === 1 ? "" : "s"}
        </span>
      </header>
      <p className="mt-3 text-sm text-ink-300">{summary}</p>
      {findings.length > 0 && (
        <div className="mt-4 space-y-2">
          {findings.map((f, i) => (
            <EvidenceChip key={i} finding={f} onClick={() => onSelect(f)} />
          ))}
        </div>
      )}
    </article>
  );
}
