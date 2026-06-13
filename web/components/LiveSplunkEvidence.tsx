"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  EVIDENCE_ROW_LIMIT,
  resultLabel,
  unionColumns,
  type EvidenceProof,
} from "@/lib/splunkEvidence";
import { splunkSearchLink } from "@/lib/splunkLink";

// How long we wait for the live MCP round-trip before falling back to captured evidence, so a
// hung MCP server can never freeze the modal mid-demo.
const MCP_TIMEOUT_MS = 25_000;

const SPLUNK_RUN_QUERY = "splunk_run_query";

// The four honest states the modal can be in. We never blur "live MCP" with "captured replay".
type Mode = "captured" | "connecting" | "live" | "unavailable";

type LiveMeta = { toolName: string; source: string; executedAt: string | null };

// The compact "is this real?" proof for the end of the demo. It confirms the room's conclusion is
// backed by a *runtime* Splunk MCP query — connecting to the Splunk MCP Server, invoking the
// splunk_run_query tool, and showing the rows Splunk returned. If MCP is unconfigured or fails it
// degrades to the captured evidence from the investigation run and says so plainly; it never
// claims "live" without a real MCP call having succeeded.
export function LiveSplunkEvidence({
  proof,
  caseId,
  splunkWebUrl = "http://localhost:8000",
  onClose,
}: {
  proof: EvidenceProof;
  // When absent there is no live case to query, so the modal stays captured-only.
  caseId?: string;
  splunkWebUrl?: string;
  onClose: () => void;
}) {
  const [rows, setRows] = useState(proof.rows);
  const [columns, setColumns] = useState(proof.columns);
  const [result, setResult] = useState(proof.resultLabel);
  const [mode, setMode] = useState<Mode>("captured");
  const [meta, setMeta] = useState<LiveMeta | null>(null);
  const didAutoRun = useRef(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Invoke the Splunk MCP Server at runtime: run this finding's OWN owned SPL through the MCP
  // splunk_run_query tool (ownership validated server-side) and show the rows it returns.
  const runLiveMcp = useCallback(async () => {
    if (!caseId) return;
    setMode("connecting");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), MCP_TIMEOUT_MS);
    try {
      const r = await fetch(
        `/api/splunk/evidence?caseId=${encodeURIComponent(caseId)}&name=${encodeURIComponent(
          proof.queryName,
        )}&backend=mcp`,
        { cache: "no-store", signal: ctrl.signal },
      );
      const data = await r.json();
      const fresh = Array.isArray(data?.rows) ? (data.rows as Record<string, unknown>[]) : null;
      if (!data?.ok || data.backend !== "mcp" || !fresh) {
        throw new Error(data?.error || "MCP returned no rows");
      }
      const shown = fresh.slice(0, EVIDENCE_ROW_LIMIT);
      setRows(shown);
      setColumns(unionColumns(shown));
      setResult(`${fresh.length} ${fresh.length === 1 ? "row" : "rows"} returned`);
      setMeta({
        toolName: typeof data.tool_name === "string" ? data.tool_name : SPLUNK_RUN_QUERY,
        source: typeof data.source === "string" ? data.source : "Splunk MCP Server",
        executedAt: typeof data.executed_at === "string" ? data.executed_at : null,
      });
      setMode("live");
    } catch {
      // Keep the captured evidence on screen and say plainly that MCP did not run.
      setRows(proof.rows);
      setColumns(proof.columns);
      setResult(proof.resultLabel);
      setMeta(null);
      setMode("unavailable");
    } finally {
      clearTimeout(timer);
    }
  }, [caseId, proof]);

  // Try the live MCP path once on open (when a live case is available) so a judge sees the real
  // call without an extra click. The "Run live MCP query" button re-runs it on demand.
  useEffect(() => {
    if (caseId && !didAutoRun.current) {
      didAutoRun.current = true;
      runLiveMcp();
    }
  }, [caseId, runLiveMcp]);

  const live = mode === "live";
  const connecting = mode === "connecting";
  const sourceLabel = live && meta ? "Splunk MCP" : proof.sourceLabel;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center px-6 backdrop-blur-[3px] animate-[fadeIn_0.4s_ease]"
      style={{
        background:
          "radial-gradient(60% 60% at 50% 40%, rgba(8,47,73,0.18), transparent 70%), rgba(3,4,6,0.92)",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl animate-[popIn_0.45s_ease] border border-ink-700 bg-ink-900 p-6 shadow-2xl"
      >
        {/* ── Header: title + mode badge ── */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-sky-300/80">
              <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
              Live Splunk Evidence
            </div>
            <ModeBadge mode={mode} />
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-ink-400 hover:bg-ink-800 hover:text-ink-100"
            aria-label="Close evidence"
          >
            ✕
          </button>
        </div>

        {/* ── Live MCP banner: the runtime Splunk-AI proof, only when a call actually succeeded ── */}
        {live && (
          <div className="mt-4 flex flex-wrap items-center gap-2 border border-emerald-700/50 bg-emerald-950/25 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-emerald-300">
            <Chip>✓ Splunk MCP connected</Chip>
            <Chip>✓ Live MCP query executed</Chip>
            <Chip>✓ {result} from Splunk</Chip>
          </div>
        )}

        {/* ── Finding / Source / Runtime call / SPL / Rows / Status ── */}
        <dl className="mt-5 space-y-3 text-sm">
          <Field label="Finding">
            <span className="text-ink-100">{proof.findingText}</span>
          </Field>
          <Field label="Source">
            <span className="text-ink-200">{sourceLabel}</span>
          </Field>
          {live && meta && (
            <Field label="Runtime call">
              <span className="font-mono text-sky-200">{meta.toolName}</span>
              <span className="ml-2 text-ink-500">· {meta.source}</span>
            </Field>
          )}
          <Field label="SPL">
            <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded border border-ink-800 bg-ink-950 p-2.5 font-mono text-[11px] leading-relaxed text-ink-200">
              {proof.spl}
            </pre>
          </Field>
          <Field label="Rows">
            <span className="font-mono text-emerald-300/90">{result}</span>
          </Field>
          <Field label="Status">
            <StatusLine mode={mode} executedAt={meta?.executedAt ?? null} />
          </Field>
        </dl>

        {/* ── Compact rows table (3–5 rows; a stamp, not a dashboard) ── */}
        <div className="mt-4 overflow-x-auto rounded border border-ink-800">
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
                    <td
                      key={c}
                      className="max-w-[16rem] truncate px-2 py-1.5 font-mono text-ink-200"
                      title={formatCell(r[c])}
                    >
                      {formatCell(r[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Buttons: Close (primary) · Run live MCP query (secondary) · Open full search ── */}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            onClick={onClose}
            className="bg-emerald-500/90 px-4 py-2 text-sm font-semibold text-ink-950 transition hover:bg-emerald-400"
          >
            Close
          </button>
          {caseId && (
            <button
              onClick={runLiveMcp}
              disabled={connecting}
              className="border border-ink-700 bg-ink-900/70 px-4 py-2 text-sm text-ink-100 transition hover:border-sky-600/70 hover:bg-ink-800 disabled:opacity-50"
            >
              {connecting ? "Querying MCP…" : live ? "Re-run live MCP query" : "Run live MCP query"}
            </button>
          )}
          <a
            href={splunkSearchLink(splunkWebUrl, proof.spl, proof.earliest, proof.latest)}
            target="_blank"
            rel="noreferrer"
            className="ml-auto font-mono text-[11px] text-ink-500 transition hover:text-sky-300"
          >
            Open full search in Splunk ↗
          </a>
        </div>
      </div>
    </div>
  );
}

function ModeBadge({ mode }: { mode: Mode }) {
  const map: Record<Mode, { text: string; cls: string }> = {
    captured: { text: "Captured from investigation run", cls: "border-ink-700 text-ink-400" },
    connecting: { text: "Connecting to Splunk MCP…", cls: "border-sky-700/50 text-sky-300" },
    live: { text: "Live MCP query executed", cls: "border-emerald-600/50 text-emerald-300" },
    unavailable: { text: "MCP unavailable · captured evidence", cls: "border-amber-700/50 text-amber-300" },
  };
  const { text, cls } = map[mode];
  return (
    <span className={`mt-2 inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${cls}`}>
      {text}
    </span>
  );
}

function StatusLine({ mode, executedAt }: { mode: Mode; executedAt: string | null }) {
  if (mode === "live") {
    return (
      <span className="text-emerald-300">
        Live MCP call executed
        {executedAt && <span className="ml-2 font-mono text-[11px] text-ink-500">{executedAt}</span>}
      </span>
    );
  }
  if (mode === "connecting") return <span className="text-sky-300">Calling Splunk MCP Server…</span>;
  if (mode === "unavailable") {
    return <span className="text-amber-300">MCP unavailable. Showing captured Splunk evidence.</span>;
  }
  return <span className="text-ink-400">Captured from investigation run</span>;
}

function Chip({ children }: { children: React.ReactNode }) {
  return <span className="rounded-sm bg-emerald-500/10 px-1.5 py-0.5">{children}</span>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_1fr] gap-3">
      <dt className="pt-0.5 font-mono text-[10px] uppercase tracking-wider text-ink-500">{label}</dt>
      <dd className="min-w-0">{children}</dd>
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
