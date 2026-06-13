import type { InvestigationReplay } from "./replay";
import type { TrailStep, UnusedCheck } from "@/components/SettingsMenu";

// Build the specialist investigation trail from a case: one row per query a specialist
// actually ran (a query that produced a finding), ordered by when it happened. Repertoire
// queries that never produced a finding become "additional checks" (available, not used).
// Shared by the case page and the landing-page "View current picture" drawer so both show
// the same Evidence Source panel.
export function buildTrail(replay: InvestigationReplay): { trail: TrailStep[]; unused: UnusedCheck[] } {
  const seen = new Set<string>();
  const trail: TrailStep[] = [];
  const unused: UnusedCheck[] = [];
  for (const sp of replay.deck.specialists) {
    const purposeByName = new Map(sp.spec.query_repertoire.map((q) => [q.name, q.purpose]));
    const used = new Set<string>();
    for (const f of sp.findings) {
      used.add(f.source_query_name);
      if (seen.has(f.source_query_name)) continue;
      seen.add(f.source_query_name);
      trail.push({
        name: f.source_query_name,
        specialist: f.specialist,
        timestamp: f.timestamp,
        claim: f.claim,
        purpose: purposeByName.get(f.source_query_name) ?? "",
        spl: f.source_query_spl,
        backend: f.backend,
        rowCount: f.source_rows.length,
        rows: f.source_rows,
        jobId: f.job_id ?? null,
      });
    }
    for (const q of sp.spec.query_repertoire) {
      if (!used.has(q.name)) {
        unused.push({ name: q.name, specialist: sp.spec.name, purpose: q.purpose, spl: q.spl });
      }
    }
  }
  trail.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return { trail, unused };
}
