"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Finding, SpecialistName } from "@/lib/deck";
import type {
  InvestigationReplay,
  Step,
  TheoryState,
  WitnessState,
} from "@/lib/replay";
import { TheoryStrip } from "./TheoryStrip";
import { ActivityFeed } from "./ActivityFeed";
import { ActiveDiscoveryStage, AlertStage, ConvergedStage } from "./InvestigationStage";
import { ConvergeOverlay } from "./ConvergeOverlay";
import { ChoicePrompt } from "./ChoicePrompt";
import { DemoControls } from "./DemoControls";
import { LiveSplunkEvidence } from "./LiveSplunkEvidence";
import { useInvestigationStatus } from "./InvestigationStatus";
import { buildDiscoveries, deriveRevision } from "@/lib/discoveries";
import { proofFromFinding } from "@/lib/splunkEvidence";
import { writeCasePhase } from "@/lib/caseStatus";

// Theory-identity palette, distinct from specialist colors.
const THEORY_PALETTE = ["#6366f1", "#06b6d4", "#f43f5e", "#84cc16", "#f59e0b"];

export function InvestigationWorkspace({ replay }: { replay: InvestigationReplay }) {
  const stepsById = useMemo(
    () => new Map(replay.steps.map((s) => [s.id, s])),
    [replay],
  );
  // The path the user has steered. Folding deltas along it gives the room's current state.
  const [history, setHistory] = useState<string[]>([replay.start]);
  // The trail row currently expanded inline (the investigation trail is the evidence browser).
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);
  // The finding whose compact internal proof modal is open ("View proof").
  const [proofFinding, setProofFinding] = useState<Finding | null>(null);
  // The convergence climax overlay — shown once, when the room first converges.
  const [showConverge, setShowConverge] = useState(false);
  const wasConverged = useRef(false);

  const currentId = history[history.length - 1];
  const current = stepsById.get(currentId) ?? replay.steps[0];

  // Between decisions the room runs itself: an auto step advances to `next` after `dwell`.
  // Decision steps (with choices) wait for the user. Pause while a trail row is expanded or a
  // proof modal is open so inspecting evidence never makes the investigation move underneath you.
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const paused = Boolean(expandedStepId || proofFinding);
  useEffect(() => {
    if (!current.next || paused) return;
    const goto = current.next;
    timer.current = setTimeout(
      // Guard against a double-append (e.g. React StrictMode re-running the effect) so the
      // room never skips a beat.
      () => setHistory((h) => (h[h.length - 1] === goto ? h : [...h, goto])),
      Math.max(0.4, current.dwell) * 1000,
    );
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [currentId, current.next, current.dwell, paused]);

  const { accents, theoryLabels } = useMemo(() => {
    const accents: Record<string, string> = {};
    const theoryLabels: Record<string, string> = {};
    replay.theories.forEach((t, i) => {
      accents[t.id] = THEORY_PALETTE[i % THEORY_PALETTE.length];
      theoryLabels[t.id] = t.label;
    });
    return { accents, theoryLabels };
  }, [replay.theories]);

  // Accumulate theory + witness state by folding each visited step's deltas in path order.
  const { theories, witnesses } = useMemo(() => {
    const tMap = new Map<string, TheoryState>();
    const wMap = new Map<SpecialistName, WitnessState>();
    for (const id of history) {
      const step = stepsById.get(id);
      if (!step) continue;
      for (const t of step.theories) tMap.set(t.id, t);
      for (const w of step.witnesses) wMap.set(w.specialist, w);
    }
    const theories = replay.theories
      .map((t) => tMap.get(t.id))
      .filter((t): t is TheoryState => Boolean(t));
    const witnesses = replay.specialists
      .map((s) => wMap.get(s))
      .filter((w): w is WitnessState => Boolean(w));
    return { theories, witnesses };
  }, [history, stepsById, replay.theories, replay.specialists]);

  const resolveFinding = useCallback(
    (w: WitnessState): Finding | null => {
      if (w.finding_specialist == null || w.finding_index == null) return null;
      const section = replay.deck.specialists.find(
        (s) => s.spec.name === (w.finding_specialist as SpecialistName),
      );
      return section?.findings[w.finding_index] ?? null;
    },
    [replay],
  );

  // The narrative spine: fold the steered path into an ordered list of discoveries. The latest
  // is the "active discovery" the feed puts in focus; older ones collapse into a timeline.
  const discoveries = useMemo(
    () => buildDiscoveries(history, stepsById, replay, resolveFinding, theoryLabels),
    [history, stepsById, replay, resolveFinding, theoryLabels],
  );

  const { setStatus } = useInvestigationStatus();

  const choose = (goto: string) => setHistory((h) => [...h, goto]);
  const restart = () => setHistory([replay.start]);
  const back = () => setHistory((h) => (h.length > 1 ? h.slice(0, -1) : h));
  const jump = (id: string) => setHistory((h) => [...h, id]);

  const converged = current.consensus.converged && current.choices.length === 0;

  // The isolated root cause + a representative citation, for the completion panel.
  const rootTheory =
    theories.find((t) => t.status === "confirmed") ??
    theories.find((t) => t.id === current.consensus.leading_theory) ??
    null;

  // Fire the convergence climax the moment the room first converges; reset if the user steps
  // back out of the converged terminal (e.g. via demo controls).
  useEffect(() => {
    if (converged && !wasConverged.current) setShowConverge(true);
    if (!converged) setShowConverge(false);
    wasConverged.current = converged;
  }, [converged]);

  // Summary for the climax + completion panel: the affected revision and the specialists that
  // back the verdict.
  const revision = useMemo(
    () => deriveRevision(theories.map((t) => t.reason), discoveries),
    [theories, discoveries],
  );
  const supporters = useMemo(
    () => witnesses.filter((w) => w.stance === "supports").map((w) => w.specialist),
    [witnesses],
  );
  // Publish the room's current understanding so the Evidence Source modal can reflect it
  // (idle before any step, investigating mid-run, concluded once the root cause is isolated).
  useEffect(() => {
    const phase = converged ? "concluded" : history.length > 1 ? "investigating" : "idle";
    setStatus(phase, converged ? rootTheory?.label ?? null : null);
    // Persist so the landing-page "View current picture" modal reflects the run afterwards.
    writeCasePhase(replay.case_id, phase);
  }, [converged, history.length, rootTheory, setStatus, replay.case_id]);

  // Center-stage state: the latest discovery is the focus; before any discovery the alert is.
  const activeDiscovery = discoveries.length > 0 ? discoveries[discoveries.length - 1] : null;
  const isDecision = current.choices.length > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* ── Spine: the question + live theory state (the emotional through-line) ── */}
      <header className="shrink-0 px-8 pt-5 pb-4 text-center">
        <h1 className="text-xl font-semibold tracking-tight text-ink-50 sm:text-2xl">
          {current.question}
        </h1>
        <div className="mt-3">
          <TheoryStrip theories={theories} accents={accents} />
        </div>
        {!converged && (
          <div
            key={current.consensus.text}
            className="mt-3 animate-[fadeIn_0.5s_ease] font-mono text-[11px] uppercase tracking-[0.16em] text-ink-500"
          >
            {current.consensus.text}
          </div>
        )}
      </header>

      {/* ── Stage: one discovery dominates the frame ── */}
      <main className="flex min-h-0 flex-1 flex-col items-center justify-center gap-8 px-8">
        {converged ? (
          <ConvergedStage
            rootCause={rootTheory?.label ?? null}
            revision={revision}
            supporters={supporters}
          />
        ) : activeDiscovery ? (
          <ActiveDiscoveryStage
            d={activeDiscovery}
            accent={activeDiscovery.theoryId ? accents[activeDiscovery.theoryId] ?? null : null}
            onSelect={setProofFinding}
          />
        ) : (
          <AlertStage headline={current.headline} />
        )}

        {/* Interaction band: steer the room, or watch it work, or close it out. */}
        <div className="flex min-h-[3.5rem] items-center justify-center">
          {converged ? (
            <div className="flex flex-wrap items-center justify-center gap-2">
              {/* The investigation trail below is the evidence entry point — keep this minimal. */}
              <Link
                href={`/decks/${replay.case_id}`}
                className="border border-ink-700 bg-ink-900/70 px-4 py-2 text-sm text-ink-100 transition hover:border-sky-600/70 hover:bg-ink-800"
              >
                Open incident deck
              </Link>
              <Link
                href="/"
                className="border border-ink-800 px-4 py-2 text-sm text-ink-400 transition hover:border-ink-600 hover:text-ink-100"
              >
                New case
              </Link>
            </div>
          ) : isDecision ? (
            <ChoicePrompt prompt={current.prompt} choices={current.choices} onChoose={choose} />
          ) : (
            <RoomWorking />
          )}
        </div>
      </main>

      {/* ── Activity: the room's reasoning, accumulating quietly ── */}
      <footer className="flex shrink-0 items-end justify-between px-8 pb-3 pt-2">
        <ActivityFeed
          discoveries={discoveries}
          phase={
            history.length === 1
              ? "idle"
              : converged
                ? "converged"
                : isDecision
                  ? "deciding"
                  : "investigating"
          }
          expandedId={expandedStepId}
          onToggle={(id) => setExpandedStepId((cur) => (cur === id ? null : id))}
          onViewProof={setProofFinding}
        />
        <DemoControls
          steps={replay.steps}
          currentId={currentId}
          canBack={history.length > 1}
          onBack={back}
          onJump={jump}
          onRestart={restart}
        />
      </footer>

      {showConverge && (
        <ConvergeOverlay
          rootCause={rootTheory?.label ?? null}
          revision={revision}
          supporters={supporters}
          onDismiss={() => setShowConverge(false)}
        />
      )}

      {proofFinding && (
        <LiveSplunkEvidence
          proof={proofFromFinding(
            proofFinding,
            replay.incident.earliest,
            replay.incident.latest,
          )}
          caseId={replay.case_id}
          onClose={() => setProofFinding(null)}
        />
      )}
    </div>
  );
}

// Shown between decisions: the room is progressing on its own.
function RoomWorking() {
  return (
    <div className="flex items-center justify-center gap-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.2em] text-ink-500">
      <span className="flex gap-1" aria-hidden>
        <Dot delay="0ms" />
        <Dot delay="150ms" />
        <Dot delay="300ms" />
      </span>
      <span>Room investigating</span>
    </div>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-400"
      style={{ animationDelay: delay }}
    />
  );
}
