"use client";

import clsx from "clsx";

import type { Step } from "@/lib/replay";

// Manual stepping is demoted to a hidden, secondary surface — never the primary interaction.
export function DemoControls({
  steps,
  currentId,
  canBack,
  onBack,
  onJump,
  onRestart,
}: {
  steps: Step[];
  currentId: string;
  canBack: boolean;
  onBack: () => void;
  onJump: (id: string) => void;
  onRestart: () => void;
}) {
  return (
    <details className="group ml-auto w-fit">
      <summary className="cursor-pointer select-none px-2 py-1 text-right font-mono text-[10px] uppercase tracking-[0.16em] text-ink-700 hover:text-ink-400">
        controls
      </summary>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 border border-ink-800/80 bg-ink-900/50 px-3 py-2.5">
        <button
          onClick={onBack}
          disabled={!canBack}
          className="rounded border border-ink-700 px-2 py-1 font-mono text-[11px] text-ink-400 transition hover:text-ink-100 disabled:opacity-30"
        >
          ← back
        </button>
        <button
          onClick={onRestart}
          className="rounded border border-ink-700 px-2 py-1 font-mono text-[11px] text-ink-400 transition hover:text-ink-100"
        >
          restart
        </button>
        <span className="mx-1 h-4 w-px bg-ink-800" />
        {steps.map((s) => (
          <button
            key={s.id}
            onClick={() => onJump(s.id)}
            className={clsx(
              "rounded border px-2 py-1 font-mono text-[11px] transition",
              s.id === currentId
                ? "border-ink-500 bg-ink-800 text-ink-100"
                : "border-ink-800 text-ink-500 hover:text-ink-200",
            )}
          >
            {s.phase || s.id}
          </button>
        ))}
      </div>
    </details>
  );
}
