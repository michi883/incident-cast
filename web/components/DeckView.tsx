"use client";

import { useState } from "react";

import type { Deck, Finding } from "@/lib/deck";
import { DeckHeader } from "./DeckHeader";
import { SharedTimeline } from "./SharedTimeline";
import { SharedEvidenceCard } from "./SharedEvidenceCard";
import { SpecialistSection } from "./SpecialistSection";
import { ReviewPrompts } from "./ReviewPrompts";
import { EvidenceDrawer } from "./EvidenceDrawer";

export function DeckView({ deck }: { deck: Deck }) {
  const [selected, setSelected] = useState<Finding | null>(null);

  return (
    <div className="mt-4 space-y-10">
      <DeckHeader deck={deck} />

      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
          Timeline of agreement
        </h2>
        <p className="mt-1 text-sm text-ink-400">
          What each specialist saw, when. Vertical highlights mark moments where multiple
          specialists' evidence aligned on the same entity.
        </p>
        <div className="mt-4">
          <SharedTimeline deck={deck} onSelect={setSelected} />
        </div>
      </section>

      {deck.shared_evidence.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
            Shared evidence
          </h2>
          <p className="mt-1 text-sm text-ink-400">
            One card per cluster of evidence that multiple specialists (or one specialist's
            repeated findings) point at together. Sorted by strength of agreement.
          </p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {deck.shared_evidence.map((ev, i) => (
              <SharedEvidenceCard key={i} evidence={ev} onSelect={setSelected} />
            ))}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
          What each specialist found
        </h2>
        <div className="mt-4 space-y-6">
          {deck.specialists.map((s) => (
            <SpecialistSection key={s.spec.name} section={s} onSelect={setSelected} />
          ))}
        </div>
      </section>

      {deck.review_prompts.length > 0 && (
        <section>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-ink-400">
            What to review next
          </h2>
          <p className="mt-1 text-sm text-ink-400">
            Suggestions for human attention. Not actions.
          </p>
          <ReviewPrompts prompts={deck.review_prompts} />
        </section>
      )}

      <EvidenceDrawer
        finding={selected}
        earliest={deck.incident.earliest}
        latest={deck.incident.latest}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
