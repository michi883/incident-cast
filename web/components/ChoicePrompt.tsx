"use client";

import type { Choice } from "@/lib/replay";

// The primary interaction: the user steers what the room investigates next. Operational
// verbs only — never Next/Prev. Choices reveal reasoning priorities, not right answers.
export function ChoicePrompt({
  prompt,
  choices,
  onChoose,
}: {
  prompt: string;
  choices: Choice[];
  onChoose: (goto: string) => void;
}) {
  if (choices.length === 0) return null;
  return (
    <section key={prompt} className="flex animate-[fadeIn_0.5s_ease] flex-col items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-600">
        direct the room
      </span>
      <div className="flex flex-wrap items-center justify-center gap-1.5">
        {choices.map((c, i) => (
          <button
            key={`${c.label}-${i}`}
            onClick={() => onChoose(c.goto)}
            className="border border-ink-800 bg-ink-900/40 px-3 py-1.5 text-[13px] text-ink-300 transition hover:border-ink-500 hover:bg-ink-800/80 hover:text-ink-50"
          >
            {c.label}
          </button>
        ))}
      </div>
    </section>
  );
}
