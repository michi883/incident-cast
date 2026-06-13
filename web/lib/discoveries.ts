import type { Finding, SpecialistName } from "./deck";
import type { InvestigationReplay, Step, TheoryStatus, WitnessState } from "./replay";

// One thing the room actually discovered on a beat: a specialist posting (or revising onto)
// new evidence. This is the narrative spine of the main UI — the latest one is the "active
// discovery" shown large; older ones collapse into compact timeline rows.
export type Discovery = {
  stepId: string;
  phase: string;
  specialist: SpecialistName; // who made the discovery
  coAuthors: SpecialistName[]; // other specialists who posted on the same beat
  text: string; // the discovery, in the specialist's own words
  theoryId: string | null; // the theory this discovery moves
  theoryLabel: string | null;
  theoryStatus: TheoryStatus | null; // that theory's new status after this beat
  stance: "supports" | "weakens" | "neutral";
  finding: Finding | null; // backing evidence (SPL + rows), if any
  purpose: string | null; // why the backing query was run (from its QueryTemplate)
  timestamp: string | null;
};

// Per-specialist accent (mirrors tailwind.config `specialist.*`) so a discovery's author
// color carries through to its card edge and dot.
export const SPECIALIST_COLOR: Record<SpecialistName, string> = {
  reliability: "#d97706",
  deployment: "#0ea5e9",
  access: "#a855f7",
  blast_radius: "#10b981",
};

// How a discovery moved its theory, phrased as a verb for the effect chip. Driven by the
// theory's resulting status so the chip matches the board (rules out / weakens / strengthens…).
export function effectVerb(stance: Discovery["stance"], status: TheoryStatus | null): string {
  if (status === "eliminated") return "rules out";
  if (status === "confirmed") return "confirms";
  if (stance === "weakens") return "weakens";
  if (status === "leading") return "puts in front";
  if (status === "strengthening") return "strengthens";
  return "raises"; // forming / possible
}

// Fold the steered path into the ordered list of discoveries. A step contributes a discovery
// when a witness posts or revises new evidence (a thought); standing-by/idle beats and pure
// decision prompts contribute nothing. The first time a step is seen wins (deltas are
// idempotent), so stepping back and forward never double-counts a beat.
export function buildDiscoveries(
  history: string[],
  stepsById: Map<string, Step>,
  replay: InvestigationReplay,
  resolveFinding: (w: WitnessState) => Finding | null,
  theoryLabels: Record<string, string>,
): Discovery[] {
  const out: Discovery[] = [];
  const seen = new Set<string>();
  // query name → its authored purpose, so an expanded trail row can say WHY the query was run.
  const purposeByQuery = new Map<string, string>();
  for (const s of replay.deck.specialists) {
    for (const t of s.spec.query_repertoire) purposeByQuery.set(t.name, t.purpose);
  }
  for (const id of history) {
    if (seen.has(id)) continue;
    seen.add(id);
    const step = stepsById.get(id);
    if (!step) continue;
    const posters = step.witnesses.filter(
      (w) => (w.activity === "posting" || w.activity === "revising") && w.thought,
    );
    if (posters.length === 0) continue;
    // The main event of the beat: prefer a fresh post over a revision.
    const primary = posters.find((w) => w.activity === "posting") ?? posters[0];
    const tid = primary.supports ?? null;
    const theoryStatus = tid ? step.theories.find((t) => t.id === tid)?.status ?? null : null;
    const finding = resolveFinding(primary);
    out.push({
      stepId: id,
      phase: step.phase,
      specialist: primary.specialist,
      coAuthors: posters.filter((w) => w !== primary).map((w) => w.specialist),
      text: primary.thought,
      theoryId: tid,
      theoryLabel: tid ? theoryLabels[tid] ?? null : null,
      theoryStatus,
      stance: primary.stance,
      finding,
      purpose: finding ? purposeByQuery.get(finding.source_query_name) ?? null : null,
      timestamp: finding?.timestamp ?? null,
    });
  }
  return out;
}

// Best-effort extraction of the affected revision (e.g. checkout-api-00042) from whatever the
// room has surfaced — theory reasons, discovery text, finding entities — for the convergence
// and concluded-picture summaries. Returns null if nothing matches.
export function deriveRevision(
  theoryReasons: string[],
  discoveries: Discovery[],
): string | null {
  const re = /\b[a-z][a-z0-9-]*-\d{3,}\b/i;
  for (const r of theoryReasons) {
    const m = r.match(re);
    if (m) return m[0];
  }
  for (const d of discoveries) {
    const fromEntity = d.finding?.entities?.revision;
    if (fromEntity) return fromEntity;
    const m = d.text.match(re);
    if (m) return m[0];
  }
  return null;
}
