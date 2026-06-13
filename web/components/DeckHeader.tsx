import { format, parseISO } from "date-fns";
import { BACKEND_LABEL, DATA_KIND_LABEL, type Deck } from "@/lib/deck";

export function DeckHeader({ deck }: { deck: Deck }) {
  const total = deck.specialists.reduce((acc, s) => acc + s.findings.length, 0);
  const shared = deck.shared_evidence.length;
  const md = deck.metadata;
  return (
    <header className="rounded-lg border border-ink-800 bg-ink-800/40 p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-xs uppercase tracking-widest text-ink-400">
            {deck.incident.id}
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink-50">
            {deck.incident.title}
          </h1>
        </div>
        {md && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="rounded bg-sky-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-300">
              {BACKEND_LABEL[md.backend]}
            </span>
            <span className="rounded bg-ink-700/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ink-300">
              {DATA_KIND_LABEL[md.data_kind]}
            </span>
            <span className="rounded bg-ink-700/60 px-2 py-0.5 font-mono text-[10px] text-ink-300">
              {md.scenario}
            </span>
          </div>
        )}
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
        <Stat label="Triggered" value={format(parseISO(deck.incident.triggered_at), "yyyy-MM-dd HH:mm 'UTC'")} />
        <Stat label="Specialists" value={String(deck.specialists.length)} />
        <Stat label="Findings" value={String(total)} />
        <Stat label="Shared evidence" value={String(shared)} />
      </dl>
      {md && (
        <details className="mt-4 text-xs text-ink-400">
          <summary className="cursor-pointer text-ink-300">how this deck was built</summary>
          <pre className="mt-2 overflow-x-auto rounded bg-ink-950 p-2 font-mono text-[11px] text-ink-200">
            {md.command}
          </pre>
          {md.model && (
            <div className="mt-1 font-mono text-[10px] text-ink-500">model: {md.model}</div>
          )}
        </details>
      )}
    </header>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-ink-500">{label}</dt>
      <dd className="mt-1 font-medium text-ink-100">{value}</dd>
    </div>
  );
}
