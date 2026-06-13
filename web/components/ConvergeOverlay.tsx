"use client";

import { useEffect, useState } from "react";

import { SPECIALIST_LABEL, type SpecialistName } from "@/lib/deck";

// The convergence climax. When the room converges, the board dims, "Room converged" lands as
// a single clear moment, then — after a short beat — the isolated root cause resolves in.
// Dismissing returns to the now-settled board (eliminated theories collapsed, survivor lit).
export function ConvergeOverlay({
  rootCause,
  revision,
  supporters,
  onDismiss,
}: {
  rootCause: string | null;
  revision: string | null;
  supporters: SpecialistName[];
  onDismiss: () => void;
}) {
  // Hold on "Room converged" for ~1s before the root cause resolves in — the pause is the beat.
  const [revealed, setRevealed] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setRevealed(true), 1000);
    return () => clearTimeout(t);
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-6 backdrop-blur-[3px] animate-[fadeIn_0.5s_ease]"
      style={{
        background:
          "radial-gradient(60% 60% at 50% 45%, rgba(6,78,59,0.18), transparent 70%), rgba(3,4,6,0.92)",
      }}
      onClick={onDismiss}
    >
      <div className="flex max-w-lg flex-col items-center text-center" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2.5 text-emerald-300 animate-[popIn_0.6s_ease]">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500/15 text-lg ring-1 ring-emerald-500/40">
            ✓
          </span>
          <span className="text-2xl font-semibold tracking-tight sm:text-3xl">Room converged</span>
        </div>

        {revealed && rootCause && (
          <div className="mt-7 w-full animate-[popIn_0.5s_ease] border border-emerald-600/40 bg-emerald-950/20 p-5 shadow-[0_0_70px_-20px] shadow-emerald-500/60">
            <div className="text-[11px] uppercase tracking-[0.2em] text-emerald-300/70">Root cause</div>
            <div className="mt-1 text-xl font-semibold text-emerald-50">{rootCause}</div>

            {revision && (
              <div className="mt-3 text-sm text-ink-300">
                <span className="text-ink-500">Tied to</span>{" "}
                <span className="font-mono text-ink-100">{revision}</span>
              </div>
            )}

            {supporters.length > 0 && (
              <div className="mt-2 text-sm text-ink-400">
                <span className="text-ink-500">Confirmed by</span>{" "}
                <span className="text-ink-200">
                  {supporters.map((s) => SPECIALIST_LABEL[s]).join(" + ")}
                </span>
              </div>
            )}

            <button
              onClick={onDismiss}
              className="mt-5 rounded-lg border border-emerald-600/60 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-100 transition hover:bg-emerald-500/20"
            >
              See the room
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
