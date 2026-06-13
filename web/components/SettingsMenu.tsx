"use client";

import { useCallback, useEffect, useState } from "react";

import { BACKEND_SOURCE_LABEL, SPECIALIST_LABEL, type SpecialistName } from "@/lib/deck";
import { splunkSearchLink } from "@/lib/splunkLink";
import {
  EVIDENCE_ROW_LIMIT,
  resultLabel,
  unionColumns,
  type EvidenceProof,
} from "@/lib/splunkEvidence";
import { useInvestigationStatus, type InvestigationPhase } from "./InvestigationStatus";
import { LiveSplunkEvidence } from "./LiveSplunkEvidence";
import { CurrentPicture } from "./CurrentPicture";

// One thing a specialist actually did during the investigation (a query that produced a
// finding), with everything needed to expand it into purpose / SPL / backend / rows / theory.
export type TrailStep = {
  name: string;
  specialist: SpecialistName;
  timestamp: string;
  claim: string;
  purpose: string;
  spl: string;
  backend: Backend;
  rowCount: number;
  rows: Record<string, unknown>[];
  jobId?: string | null;
};

// A repertoire query that was available but never produced a finding — shown, collapsed,
// under "Additional checks" so the main trail never reads "not run yet".
export type UnusedCheck = { name: string; specialist: SpecialistName; purpose: string; spl: string };

type Backend = "fixture" | "sdk" | "mcp";

type SplunkStatus = {
  reachable?: boolean;
  host?: string;
  web_url?: string;
  indexes?: { name: string; count: number }[];
  error?: string;
};

type QueryResult = {
  ok?: boolean;
  sid?: string | null;
  count?: number;
  rows?: Record<string, unknown>[];
  spl?: string;
  error?: string;
};

const BACKENDS: Backend[] = ["fixture", "sdk", "mcp"];

const MODE: Record<Backend, { label: string; blurb: string; current: string }> = {
  fixture: {
    label: "Fixture",
    blurb: "Replay canned findings",
    current: "replaying canned findings — no Splunk in the loop",
  },
  sdk: {
    label: "Splunk SDK",
    blurb: "Run SPL live and materialize findings",
    current: "findings generated from live Splunk query results",
  },
  mcp: {
    label: "Splunk MCP",
    blurb: "Let agents inspect Splunk interactively",
    current: "agents inspect Splunk interactively via the MCP server",
  },
};

function prettify(id: string) {
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function SettingsMenu({
  caseId,
  currentBackend,
  trail,
  unused,
  theories,
  earliest,
  latest,
  symptom,
  open: controlledOpen,
  onClose,
  phase: phaseProp,
  rootCause: rootCauseProp,
  showTrigger = true,
}: {
  caseId: string;
  currentBackend: Backend;
  trail: TrailStep[];
  unused: UnusedCheck[];
  theories: string[];
  earliest: string;
  latest: string;
  // The incident symptom (e.g. "checkout-api 5xx spike"), shown in the pre-investigation
  // uncertainty view. Optional — the landing "current picture" view omits it.
  symptom?: string;
  // Controlled open (landing page opens this from a card button). Omit on the case page to
  // use the built-in ⚙ trigger and internal open state.
  open?: boolean;
  onClose?: () => void;
  // Override the operational phase/root-cause (landing reads it from localStorage). When
  // omitted, falls back to the live InvestigationStatus context (the case page).
  phase?: InvestigationPhase;
  rootCause?: string | null;
  showTrigger?: boolean;
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const close = isControlled ? () => onClose?.() : () => setInternalOpen(false);
  const [status, setStatus] = useState<SplunkStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [showUnused, setShowUnused] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [backend, setBackend] = useState<Backend>(currentBackend);
  const [casting, setCasting] = useState(false);
  const [castMsg, setCastMsg] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { loading: boolean; data?: QueryResult }>>({});
  // The compact internal "View proof" modal (never external navigation).
  const [proof, setProof] = useState<EvidenceProof | null>(null);

  // A query that produced a finding → captured rows + live re-proof.
  const proofFromTrail = (t: TrailStep): EvidenceProof => {
    const rows = t.rows.slice(0, EVIDENCE_ROW_LIMIT);
    return {
      queryName: t.name,
      findingText: t.claim,
      sourceLabel: BACKEND_SOURCE_LABEL[t.backend],
      backend: t.backend,
      spl: t.spl,
      resultLabel: resultLabel(t.rows),
      columns: unionColumns(rows),
      rows,
      earliest,
      latest,
      jobId: t.jobId ?? null,
    };
  };

  // An available-but-unused repertoire query → no captured rows; the modal proves it live.
  const proofFromUnused = (u: UnusedCheck): EvidenceProof => ({
    queryName: u.name,
    findingText: u.purpose || prettify(u.name),
    sourceLabel: "Not run in this investigation",
    backend: currentBackend,
    spl: u.spl,
    resultLabel: "not run — query live to prove",
    columns: [],
    rows: [],
    earliest,
    latest,
    jobId: null,
  });

  const web = status?.web_url ?? "http://localhost:8000";
  const indexes = status?.indexes ?? [];
  const reachable = !!status?.reachable;
  // "Relevant" = the change/audit/metric signal, excluding the high-volume raw access log.
  const relevantRows = indexes.filter((i) => i.name !== "app_logs").reduce((s, i) => s + i.count, 0);

  const ctx = useInvestigationStatus();
  // When the caller drives phase (landing page), it owns root cause too; otherwise read live.
  const phase = phaseProp ?? ctx.phase;
  const rootCause = phaseProp !== undefined ? rootCauseProp ?? null : ctx.rootCause;
  const concluded = phase === "concluded";
  // Until the room is pointed somewhere, no query has run — keep the panel quiet and uncertain,
  // exposing no proof, counts, or evidence. Proof unlocks once the investigation begins.
  const started = phase !== "idle";

  // Evidence rows behind this case: live relevant-row count when Splunk is reachable, else the
  // deterministic sum of rows cited by the findings.
  const citedRows = trail.reduce((s, t) => s + t.rowCount, 0);
  const evidenceRows = reachable && relevantRows > 0 ? relevantRows : citedRows;

  const loadStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      const r = await fetch("/api/splunk/status", { cache: "no-store" });
      setStatus(await r.json());
    } catch (e) {
      setStatus({ reachable: false, error: (e as Error).message });
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && status === null) loadStatus();
  }, [open, status, loadStatus]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  async function recast() {
    setCasting(true);
    setCastMsg(null);
    try {
      const r = await fetch("/api/cast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caseId, backend }),
      });
      const data = await r.json();
      if (data.ok) {
        setCastMsg("Re-cast complete — reloading…");
        setTimeout(() => window.location.reload(), 600);
      } else {
        setCastMsg(`Failed: ${data.error || data.summary || "see server logs"}`);
      }
    } catch (e) {
      setCastMsg(`Failed: ${(e as Error).message}`);
    } finally {
      setCasting(false);
    }
  }

  async function runQuery(name: string) {
    setResults((p) => ({ ...p, [name]: { loading: true, data: p[name]?.data } }));
    try {
      const r = await fetch("/api/splunk/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ caseId, name }),
      });
      const data = await r.json();
      setResults((p) => ({ ...p, [name]: { loading: false, data } }));
    } catch (e) {
      setResults((p) => ({ ...p, [name]: { loading: false, data: { ok: false, error: (e as Error).message } } }));
    }
  }

  const recastPrimary = reachable && backend !== "fixture";

  return (
    <>
      {showTrigger && (
        <button
          onClick={() => setInternalOpen(true)}
          aria-label="Settings"
          className="fixed right-4 top-4 z-40 flex h-9 w-9 items-center justify-center rounded-full border border-ink-700 bg-ink-900/80 text-ink-300 backdrop-blur transition hover:border-ink-500 hover:text-ink-100"
        >
          <span className="text-base leading-none">⚙</span>
        </button>
      )}

      {open && (
        <div className="fixed inset-0 z-50 flex justify-end bg-ink-900/60 backdrop-blur-sm" onClick={close}>
          <aside
            onClick={(e) => e.stopPropagation()}
            className="h-full w-full max-w-xs overflow-y-auto border-l border-ink-800 bg-ink-950/95 p-4 text-ink-300 shadow-2xl"
          >
            {/* ---- Header ---- */}
            <div className="flex items-center justify-between">
              <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-500">
                Evidence source
              </h2>
              <button onClick={close} aria-label="Close" className="rounded p-1 text-ink-500 hover:bg-ink-800 hover:text-ink-200">✕</button>
            </div>

            {/* ---- Connection status (always shown) ---- */}
            <div className="mt-3 flex items-center gap-2 text-[12px]">
              <span className={`h-1.5 w-1.5 rounded-full ${reachable ? "bg-emerald-400" : backend === "fixture" ? "bg-ink-500" : "bg-rose-500"}`} />
              <span className="text-ink-200">{MODE[currentBackend].label}</span>
              <span className="text-ink-600">{reachable ? "connected" : backend === "fixture" ? "fixture replay" : statusLoading ? "checking…" : "offline"}</span>
            </div>

            {started ? (
              <>
                {/* ---- Proof summary: unlocked once the investigation is underway ---- */}
                <dl className="mt-1.5 space-y-1.5 text-[12px]">
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-mono text-ink-200">{evidenceRows.toLocaleString()}</span>
                    <span className="text-ink-500">rows analyzed</span>
                  </div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="font-mono text-ink-200">{trail.length}</span>
                    <span className="text-ink-500">queries executed</span>
                  </div>
                </dl>
                <a href={`${web}/en-US/app/search/search`} target="_blank" rel="noreferrer" className="mt-2 inline-block font-mono text-[11px] text-ink-500 transition hover:text-emerald-300">
                  open in Splunk ↗
                </a>
              </>
            ) : (
              /* ---- Pre-investigation: active incident + uncertainty, no proof yet ---- */
              <div className="mt-1.5 space-y-2 text-[12px]">
                <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-rose-300/80">
                  <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                  Active incident
                </div>
                {symptom && <p className="text-ink-300">{symptom}</p>}
                <p className="font-mono text-[11px] uppercase tracking-wider text-ink-600">Not yet investigated</p>
                {theories.length > 0 && (
                  <div>
                    <div className="font-mono text-[10px] uppercase tracking-widest text-ink-600">Competing theories</div>
                    <ul className="mt-1 space-y-0.5">
                      {theories.map((t) => (
                        <li key={t} className="flex items-baseline gap-2 text-ink-300">
                          <span className="h-1 w-1 shrink-0 translate-y-1.5 rounded-full bg-ink-600" />
                          <span>{t}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-[11px] leading-relaxed text-ink-600">
                  No evidence collected yet — specialists have not queried Splunk. Point the room to begin.
                </p>
              </div>
            )}

            {/* ---- Change source (secondary) ---- */}
            <details className="mt-3 group">
              <summary className="cursor-pointer select-none font-mono text-[10px] uppercase tracking-widest text-ink-600 hover:text-ink-400">
                ▸ change source
              </summary>
              <div className="mt-2 space-y-0.5">
                {BACKENDS.map((b) => (
                  <label key={b} className={`flex cursor-pointer items-baseline gap-2 px-1.5 py-1 transition ${backend === b ? "bg-ink-800/60" : "hover:bg-ink-800/30"}`}>
                    <input type="radio" name="backend" checked={backend === b} onChange={() => setBackend(b)} className="translate-y-0.5 accent-emerald-500" />
                    <span className="flex-1">
                      <span className="text-[12px] text-ink-200">{MODE[b].label}</span>
                      {b === currentBackend && <span className="ml-1.5 font-mono text-[9px] uppercase tracking-wide text-emerald-300/70">active</span>}
                    </span>
                  </label>
                ))}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <button onClick={recast} disabled={casting} className={recastPrimary ? "bg-emerald-500/90 px-2.5 py-1 text-[11px] font-semibold text-ink-950 transition hover:bg-emerald-400 disabled:opacity-50" : "border border-ink-700 px-2.5 py-1 text-[11px] text-ink-200 transition hover:border-ink-500 disabled:opacity-50"}>
                  {casting ? "re-casting…" : backend === "fixture" ? "re-cast (fixture)" : `re-cast · ${MODE[backend].label}`}
                </button>
                <button onClick={loadStatus} className="px-2 py-1 font-mono text-[10px] text-ink-500 transition hover:text-ink-200">refresh</button>
              </div>
              {castMsg && <p className="mt-1.5 text-[11px] text-ink-500">{castMsg}</p>}
              {status?.error && <p className="mt-1 text-[11px] text-rose-300/70">{status.error}</p>}
            </details>

            {/* The operational picture belongs to the landing "current picture" view (no main
                stage there). In-case the main stage already shows it — don't duplicate it here. */}
            {isControlled && (
              <section className="mt-4 border-t border-ink-800/70 pt-3">
                <CurrentPicture
                  concluded={concluded}
                  phase={phase}
                  rootCause={rootCause}
                  theoryCount={theories.length}
                  evidenceRows={evidenceRows}
                />
              </section>
            )}

            {/* ---- SPL proof: only exists once the investigation is underway (proof is earned,
                 not precomputed). Hidden entirely before the room is pointed anywhere. ---- */}
            {started && (
            <details className="mt-3 group">
              <summary className="cursor-pointer select-none font-mono text-[10px] uppercase tracking-widest text-ink-600 hover:text-ink-400">
                ▸ SPL proof{concluded ? ` · ${trail.length} queries` : ""}
              </summary>
              {!concluded ? (
                <p className="mt-2 text-[11px] leading-relaxed text-ink-600">
                  {phase === "investigating"
                    ? "Querying Splunk now — proof fills in as findings land."
                    : "Run the investigation to see the SPL behind each finding."}
                </p>
              ) : (
              <>
              <ul className="mt-2 divide-y divide-ink-800/60">
                {trail.map((t) => {
                  const isOpen = !!expanded[t.name];
                  const r = results[t.name];
                  return (
                    <li key={t.name}>
                      <button
                        onClick={() => setExpanded((p) => ({ ...p, [t.name]: !p[t.name] }))}
                        className="flex w-full items-center gap-2 py-1.5 text-left"
                      >
                        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-400">
                          {prettify(t.name)}
                        </span>
                        <span className="shrink-0 font-mono text-[10px] text-ink-600">{t.rowCount} rows</span>
                        <span className="shrink-0 font-mono text-[10px] text-ink-700">{isOpen ? "▾" : "▸"}</span>
                      </button>

                      {isOpen && (
                        <div className="space-y-2 pb-2.5 text-[11px]">
                          <pre className="overflow-x-auto whitespace-pre-wrap break-words bg-ink-900/60 p-2 font-mono text-[10px] leading-relaxed text-ink-300">{t.spl}</pre>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-ink-600">
                            <span>{MODE[t.backend].label}</span>
                            <span>{t.rowCount} rows</span>
                            {t.jobId && <span>sid {t.jobId}</span>}
                            <button onClick={() => setProof(proofFromTrail(t))} className="text-sky-400/80 hover:text-sky-200">View proof →</button>
                            <button onClick={() => runQuery(t.name)} className="text-ink-500 hover:text-emerald-300">
                              {r?.loading ? "running…" : "re-run"}
                            </button>
                          </div>
                          {r?.data && (
                            r.data.ok ? (
                              <div>
                                <div className="flex items-center justify-between font-mono text-[10px] text-ink-600">
                                  <span>{r.data.count} rows{r.data.sid ? ` · sid ${r.data.sid}` : ""}</span>
                                  {r.data.sid && (
                                    <a href={splunkSearchLink(web, `| loadjob ${r.data.sid}`)} target="_blank" rel="noreferrer" className="hover:text-emerald-300">open job ↗</a>
                                  )}
                                </div>
                                <RowsPreview rows={r.data.rows ?? []} />
                              </div>
                            ) : (
                              <p className="text-[10px] text-rose-300/70">{r.data.error || "query failed"}</p>
                            )
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>

              {/* ---- Additional checks (available, not used on the main path) ---- */}
              {unused.length > 0 && (
                <div className="mt-3">
                  <button onClick={() => setShowUnused((v) => !v)} className="font-mono text-[10px] text-ink-500 hover:text-ink-300">
                    {showUnused ? "▾ hide" : "▸"} additional checks ({unused.length} available, not used)
                  </button>
                  {showUnused && (
                    <ul className="mt-1.5 space-y-1 border-t border-ink-800 pt-1.5">
                      {unused.map((u) => (
                        <li key={u.name} className="flex items-start justify-between gap-2 text-[11px]">
                          <span className="min-w-0">
                            <span className="text-ink-300">{SPECIALIST_LABEL[u.specialist]}</span>
                            <span className="text-ink-500"> · {u.purpose || prettify(u.name)}</span>
                          </span>
                          <button onClick={() => setProof(proofFromUnused(u))} className="shrink-0 font-mono text-[10px] text-sky-400/80 hover:text-sky-200">View proof →</button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              </>
              )}
            </details>
            )}
          </aside>
        </div>
      )}

      {proof && (
        <LiveSplunkEvidence proof={proof} caseId={caseId} onClose={() => setProof(null)} />
      )}
    </>
  );
}

function RowsPreview({ rows }: { rows: Record<string, unknown>[] }) {
  if (rows.length === 0) return <p className="mt-1 text-[10px] text-ink-600">no rows</p>;
  const cols = Array.from(rows.slice(0, 3).reduce((s, r) => { Object.keys(r).forEach((k) => s.add(k)); return s; }, new Set<string>())).slice(0, 4);
  return (
    <div className="mt-1.5 overflow-x-auto">
      <table className="min-w-full text-[10px]">
        <thead>
          <tr>{cols.map((c) => <th key={c} className="px-1.5 py-0.5 text-left font-mono uppercase text-ink-600">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 3).map((row, i) => (
            <tr key={i} className="border-t border-ink-800/70">
              {cols.map((c) => <td key={c} className="px-1.5 py-0.5 font-mono text-ink-300">{String(row[c] ?? "")}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
