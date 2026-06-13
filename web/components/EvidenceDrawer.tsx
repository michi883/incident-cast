"use client";

import { useEffect, useState } from "react";
import { format, parseISO } from "date-fns";

import type { Finding } from "@/lib/deck";
import { BACKEND_SOURCE_LABEL, SPECIALIST_LABEL } from "@/lib/deck";
import { proofFromFinding } from "@/lib/splunkEvidence";
import { LiveSplunkEvidence } from "./LiveSplunkEvidence";

export function EvidenceDrawer({
  finding,
  caseId,
  earliest,
  latest,
  onClose,
}: {
  finding: Finding | null;
  // Omitted on surfaces without a live case (e.g. the static deck view) — the modal then shows
  // captured evidence only, without the "Refresh from Splunk" action.
  caseId?: string;
  earliest: string;
  latest: string;
  onClose: () => void;
}) {
  // The compact "Live Splunk Evidence" stamp, launched from this proof's "Open" action.
  const [showProof, setShowProof] = useState(false);
  // Reset whenever the drawer switches to a different finding (or closes).
  useEffect(() => {
    setShowProof(false);
  }, [finding]);
  useEffect(() => {
    if (!finding) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finding, onClose]);

  if (!finding) return null;

  return (
    <>
    <div
      className="fixed inset-0 z-50 flex justify-end bg-ink-900/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="h-full w-full max-w-2xl overflow-y-auto border-l border-ink-700 bg-ink-900 p-6 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs uppercase tracking-widest text-ink-400">
            Evidence · {SPECIALIST_LABEL[finding.specialist]}
          </span>
          <button
            onClick={onClose}
            className="rounded p-1 text-ink-400 hover:bg-ink-800 hover:text-ink-100"
            aria-label="Close evidence drawer"
          >
            ✕
          </button>
        </div>

        <h2 className="mt-3 text-lg font-semibold text-ink-50">{finding.claim}</h2>
        <div className="mt-1 font-mono text-xs text-ink-500">
          {format(parseISO(finding.timestamp), "yyyy-MM-dd HH:mm:ss 'UTC'")} · {finding.severity}
        </div>

        {Object.keys(finding.entities).length > 0 && (
          <section className="mt-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
              Entities
            </h3>
            <dl className="mt-2 grid grid-cols-1 gap-1 text-sm">
              {Object.entries(finding.entities).map(([k, v]) => (
                <div key={k} className="flex gap-3">
                  <dt className="w-32 shrink-0 text-ink-500">{k}</dt>
                  <dd className="break-all font-mono text-ink-200">{v}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <section className="mt-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
              SPL query
            </h3>
            <button
              onClick={() => setShowProof(true)}
              className="border border-sky-700/60 bg-sky-950/30 px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-sky-200 transition hover:border-sky-500/70 hover:bg-sky-900/40"
            >
              View proof →
            </button>
          </div>
          <pre className="mt-2 max-h-48 overflow-auto rounded border border-ink-800 bg-ink-950 p-3 text-xs leading-relaxed text-ink-200">
            {finding.source_query_spl}
          </pre>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-ink-500">
            <span>query: {finding.source_query_name}</span>
            <span className="flex items-center gap-1 text-ink-400">
              <span
                aria-hidden
                className={
                  finding.backend === "fixture" ? "h-1.5 w-1.5 rounded-full bg-ink-600" : "h-1.5 w-1.5 rounded-full bg-emerald-400"
                }
              />
              source: {BACKEND_SOURCE_LABEL[finding.backend]}
            </span>
            {finding.job_id && <span>job: {finding.job_id}</span>}
          </div>
        </section>

        <section className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
            Cited rows ({finding.source_rows.length})
          </h3>
          <RowsTable rows={finding.source_rows} />
        </section>

        {finding.tags.length > 0 && (
          <section className="mt-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
              Tags
            </h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {finding.tags.map((t) => (
                <span
                  key={t}
                  className="rounded bg-ink-800 px-2 py-0.5 font-mono text-[10px] text-ink-300"
                >
                  {t}
                </span>
              ))}
            </div>
          </section>
        )}
      </aside>
    </div>

    {showProof && (
      <LiveSplunkEvidence
        proof={proofFromFinding(finding, earliest, latest)}
        caseId={caseId}
        onClose={() => setShowProof(false)}
      />
    )}
    </>
  );
}

function RowsTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) {
    return <p className="mt-2 text-sm text-ink-400">No rows recorded.</p>;
  }
  const columns = Array.from(
    rows.reduce((set, r) => {
      for (const k of Object.keys(r)) set.add(k);
      return set;
    }, new Set<string>()),
  );
  return (
    <div className="mt-2 overflow-x-auto rounded border border-ink-800">
      <table className="min-w-full text-xs">
        <thead className="bg-ink-800/60">
          <tr>
            {columns.map((c) => (
              <th
                key={c}
                className="px-2 py-1.5 text-left font-mono text-[10px] uppercase tracking-wider text-ink-400"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-ink-800/80">
              {columns.map((c) => (
                <td key={c} className="px-2 py-1.5 font-mono text-ink-200">
                  {formatCell(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return v ? "true" : "false";
  return JSON.stringify(v);
}
