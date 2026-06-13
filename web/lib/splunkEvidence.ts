import { BACKEND_SOURCE_LABEL, type Finding } from "./deck";

export type EvidenceProof = {
  queryName: string;
  findingText: string;
  sourceLabel: string;
  backend: Finding["backend"];
  spl: string;
  resultLabel: string;
  columns: string[];
  rows: Record<string, unknown>[];
  earliest: string;
  latest: string;
  jobId: string | null;
};

// How many rows the compact table shows — a quick stamp, not a dashboard.
export const EVIDENCE_ROW_LIMIT = 5;

// Fields whose value is a count of underlying events behind an aggregated row (e.g. denials=583).
// Surfacing these reads as "583 matching events" rather than the literal "1 row returned".
const COUNT_FIELDS = ["denials", "count", "errors"];

export function unionColumns(rows: Record<string, unknown>[]): string[] {
  const cols = new Set<string>();
  for (const r of rows) for (const k of Object.keys(r)) cols.add(k);
  return Array.from(cols);
}

// "583 matching events" when an aggregate count is present, else "<n> rows returned".
export function resultLabel(rows: Record<string, unknown>[]): string {
  const first = rows[0];
  if (first) {
    for (const field of COUNT_FIELDS) {
      const raw = first[field];
      const n = typeof raw === "number" ? raw : typeof raw === "string" ? Number(raw) : NaN;
      if (Number.isFinite(n) && n > 0) return `${n.toLocaleString()} matching events`;
    }
  }
  return `${rows.length} ${rows.length === 1 ? "row" : "rows"} returned`;
}

// Build the compact-modal proof from a single finding the viewer opened in the evidence drawer.
// This is the captured (fallback-first) source: it always reflects what the investigation
// returned, with no Splunk round-trip required.
export function proofFromFinding(
  finding: Finding,
  earliest: string,
  latest: string,
): EvidenceProof {
  const rows = finding.source_rows.slice(0, EVIDENCE_ROW_LIMIT);
  return {
    queryName: finding.source_query_name,
    findingText: finding.claim,
    sourceLabel: BACKEND_SOURCE_LABEL[finding.backend],
    backend: finding.backend,
    spl: finding.source_query_spl,
    resultLabel: resultLabel(finding.source_rows),
    columns: unionColumns(rows),
    rows,
    earliest,
    latest,
    jobId: finding.job_id ?? null,
  };
}
