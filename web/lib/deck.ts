import { z } from "zod";

export const SpecialistName = z.enum([
  "reliability",
  "deployment",
  "access",
  "blast_radius",
]);
export type SpecialistName = z.infer<typeof SpecialistName>;

export const Severity = z.enum(["info", "notable", "critical"]);
export type Severity = z.infer<typeof Severity>;

export const QueryTemplate = z.object({
  name: z.string(),
  purpose: z.string(),
  spl: z.string(),
  owned_by: SpecialistName,
  expected_columns: z.array(z.string()),
});

export const SpecialistSpec = z.object({
  name: SpecialistName,
  title: z.string(),
  goal: z.string(),
  lead_question: z.string(),
  sub_questions: z.array(z.string()),
  query_repertoire: z.array(QueryTemplate),
  output_tags: z.array(z.string()),
});
export type SpecialistSpec = z.infer<typeof SpecialistSpec>;

export const Finding = z.object({
  specialist: SpecialistName,
  timestamp: z.string(),
  claim: z.string(),
  severity: Severity,
  entities: z.record(z.string()),
  source_query_name: z.string(),
  source_query_spl: z.string(),
  source_rows: z.array(z.record(z.unknown())),
  tags: z.array(z.string()),
  backend: z.enum(["fixture", "sdk", "mcp"]).default("fixture"),
  job_id: z.string().nullable().optional(),
});
export type Finding = z.infer<typeof Finding>;

export const BACKEND_SOURCE_LABEL: Record<"fixture" | "sdk" | "mcp", string> = {
  fixture: "Fixture",
  sdk: "Splunk SDK",
  mcp: "Splunk MCP",
};

export const SharedEvidence = z.object({
  text: z.string(),
  window: z.tuple([z.string(), z.string()]),
  entities: z.record(z.string()),
  supporting_findings: z.array(Finding),
  supporting_specialists: z.array(SpecialistName),
});
export type SharedEvidence = z.infer<typeof SharedEvidence>;

export const IncidentContext = z.object({
  id: z.string(),
  title: z.string(),
  triggered_at: z.string(),
  earliest: z.string(),
  latest: z.string(),
  hints: z.record(z.unknown()),
});
export type IncidentContext = z.infer<typeof IncidentContext>;

export const TimelineEvent = z.object({
  specialist: SpecialistName,
  timestamp: z.string(),
  label: z.string(),
  severity: Severity,
  entities: z.record(z.string()),
  finding_index: z.number(),
});
export type TimelineEvent = z.infer<typeof TimelineEvent>;

export const SpecialistSection = z.object({
  spec: SpecialistSpec,
  findings: z.array(Finding),
  summary: z.string(),
});
export type SpecialistSection = z.infer<typeof SpecialistSection>;

export const DeckMetadata = z.object({
  backend: z.enum(["fixture", "sdk", "mcp"]),
  data_kind: z.enum(["fixture_json", "synthetic_splunk", "real_cloud_run"]),
  scenario: z.string(),
  specialists_included: z.array(SpecialistName),
  command: z.string(),
  model: z.string().nullable().optional(),
});
export type DeckMetadata = z.infer<typeof DeckMetadata>;

export const Deck = z.object({
  incident: IncidentContext,
  generated_at: z.string(),
  timeline: z.array(TimelineEvent),
  specialists: z.array(SpecialistSection),
  shared_evidence: z.array(SharedEvidence),
  review_prompts: z.array(z.string()),
  metadata: DeckMetadata.nullable().optional(),
});
export type Deck = z.infer<typeof Deck>;

export const BACKEND_LABEL: Record<DeckMetadata["backend"], string> = {
  fixture: "Fixture",
  sdk: "Splunk SDK",
  mcp: "Splunk MCP",
};

export const DATA_KIND_LABEL: Record<DeckMetadata["data_kind"], string> = {
  fixture_json: "Canned JSON",
  synthetic_splunk: "Synthetic data in Splunk",
  real_cloud_run: "Real Cloud Run logs",
};

export const SPECIALIST_LABEL: Record<SpecialistName, string> = {
  reliability: "Reliability",
  deployment: "Deployment",
  access: "Access",
  blast_radius: "Blast Radius",
};
