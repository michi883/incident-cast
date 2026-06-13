"use client";

import { useMemo } from "react";
import { format, parseISO } from "date-fns";
import clsx from "clsx";

import type { Deck, Finding, SpecialistName, TimelineEvent } from "@/lib/deck";
import { SPECIALIST_LABEL } from "@/lib/deck";

const SPECIALIST_COLOR: Record<SpecialistName, string> = {
  reliability: "bg-specialist-reliability",
  deployment: "bg-specialist-deployment",
  access: "bg-specialist-access",
  blast_radius: "bg-specialist-blast_radius",
};

const SPECIALIST_TEXT: Record<SpecialistName, string> = {
  reliability: "text-specialist-reliability",
  deployment: "text-specialist-deployment",
  access: "text-specialist-access",
  blast_radius: "text-specialist-blast_radius",
};

export function SharedTimeline({
  deck,
  onSelect,
}: {
  deck: Deck;
  onSelect: (f: Finding) => void;
}) {
  const { tMin, tMax, bands, agreementMarks } = useMemo(() => buildTimeline(deck), [deck]);

  if (deck.timeline.length === 0) {
    return <p className="text-sm text-ink-400">No findings to plot yet.</p>;
  }

  return (
    <div className="rounded-lg border border-ink-800 bg-ink-800/30 p-4">
      <div className="relative">
        {/* agreement highlight columns */}
        {agreementMarks.map((m, i) => (
          <div
            key={i}
            className="pointer-events-none absolute top-0 z-0 h-full w-px bg-ink-100/20"
            style={{ left: `${pct(m.t, tMin, tMax)}%` }}
            aria-hidden
          />
        ))}
        <div className="relative z-10 space-y-3">
          {bands.map((band) => (
            <div key={band.specialist} className="flex items-center gap-3">
              <div className="w-32 shrink-0 text-right">
                <span
                  className={clsx(
                    "font-mono text-xs uppercase tracking-wider",
                    SPECIALIST_TEXT[band.specialist],
                  )}
                >
                  {SPECIALIST_LABEL[band.specialist]}
                </span>
              </div>
              <div className="relative h-9 flex-1 rounded bg-ink-900/80">
                <div className="absolute inset-y-1/2 h-px w-full -translate-y-1/2 bg-ink-700" />
                {band.events.map((e, i) => (
                  <button
                    key={i}
                    onClick={() => {
                      const f = findFinding(deck, e);
                      if (f) onSelect(f);
                    }}
                    className={clsx(
                      "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-ink-900 transition hover:scale-125",
                      SPECIALIST_COLOR[e.specialist],
                      sizeForSeverity(e.severity),
                    )}
                    style={{ left: `${pct(parseISO(e.timestamp).getTime(), tMin, tMax)}%` }}
                    title={`${format(parseISO(e.timestamp), "HH:mm:ss")} · ${e.label}`}
                    aria-label={e.label}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <TimeAxis tMin={tMin} tMax={tMax} />
    </div>
  );
}

function TimeAxis({ tMin, tMax }: { tMin: number; tMax: number }) {
  const ticks = 5;
  const marks: number[] = [];
  for (let i = 0; i <= ticks; i++) {
    marks.push(tMin + ((tMax - tMin) * i) / ticks);
  }
  return (
    <div className="mt-3 flex items-center gap-3">
      <div className="w-32 shrink-0" />
      <div className="relative h-4 flex-1">
        {marks.map((m, i) => (
          <div
            key={i}
            className="absolute -translate-x-1/2 font-mono text-[10px] text-ink-500"
            style={{ left: `${pct(m, tMin, tMax)}%` }}
          >
            {format(new Date(m), "HH:mm")}
          </div>
        ))}
      </div>
    </div>
  );
}

function buildTimeline(deck: Deck) {
  const all = deck.timeline.map((e) => parseISO(e.timestamp).getTime());
  let tMin = Math.min(...all);
  let tMax = Math.max(...all);
  if (tMin === tMax) {
    tMin -= 60_000;
    tMax += 60_000;
  } else {
    const pad = (tMax - tMin) * 0.05;
    tMin -= pad;
    tMax += pad;
  }

  const specialistOrder: SpecialistName[] = deck.specialists.map((s) => s.spec.name);
  const bandsMap = new Map<SpecialistName, TimelineEvent[]>();
  for (const s of specialistOrder) bandsMap.set(s, []);
  for (const e of deck.timeline) {
    if (!bandsMap.has(e.specialist)) bandsMap.set(e.specialist, []);
    bandsMap.get(e.specialist)!.push(e);
  }
  const bands = Array.from(bandsMap.entries()).map(([specialist, events]) => ({
    specialist,
    events,
  }));

  // Agreement marks: timestamps where >=2 specialists have a finding within 2 minutes.
  const agreementMarks: { t: number }[] = [];
  for (const ev of deck.shared_evidence) {
    if (ev.supporting_specialists.length >= 2) {
      const mid = (parseISO(ev.window[0]).getTime() + parseISO(ev.window[1]).getTime()) / 2;
      agreementMarks.push({ t: mid });
    }
  }
  return { tMin, tMax, bands, agreementMarks };
}

function findFinding(deck: Deck, e: TimelineEvent): Finding | undefined {
  const section = deck.specialists.find((s) => s.spec.name === e.specialist);
  return section?.findings[e.finding_index];
}

function pct(t: number, tMin: number, tMax: number) {
  if (tMax === tMin) return 50;
  return ((t - tMin) / (tMax - tMin)) * 100;
}

function sizeForSeverity(s: Finding["severity"]) {
  if (s === "critical") return "h-5 w-5";
  if (s === "notable") return "h-4 w-4";
  return "h-3 w-3";
}
