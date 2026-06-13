import { z } from "zod";

import { Deck, IncidentContext, SpecialistName } from "./deck";

export const TheoryStatus = z.enum([
  "forming",
  "possible",
  "weakening",
  "strengthening",
  "leading",
  "eliminated",
  "confirmed",
]);
export type TheoryStatus = z.infer<typeof TheoryStatus>;

export const Stance = z.enum(["supports", "weakens", "neutral"]);
export type Stance = z.infer<typeof Stance>;

export const Activity = z.enum(["idle", "investigating", "posting", "revising"]);
export type Activity = z.infer<typeof Activity>;

export const Theory = z.object({ id: z.string(), label: z.string() });
export type Theory = z.infer<typeof Theory>;

export const TheoryState = z.object({
  id: z.string(),
  label: z.string(),
  status: TheoryStatus,
  reason: z.string().default(""),
});
export type TheoryState = z.infer<typeof TheoryState>;

export const WitnessState = z.object({
  specialist: SpecialistName,
  thought: z.string().default(""),
  supports: z.string().nullable().optional(),
  stance: Stance.default("neutral"),
  activity: Activity.default("idle"),
  finding_specialist: SpecialistName.nullable().optional(),
  finding_index: z.number().nullable().optional(),
});
export type WitnessState = z.infer<typeof WitnessState>;

export const ConsensusState = z.object({
  text: z.string(),
  remaining: z.number().default(0),
  converged: z.boolean().default(false),
  leading_theory: z.string().nullable().optional(),
});
export type ConsensusState = z.infer<typeof ConsensusState>;

export const FindingRef = z.object({
  specialist: SpecialistName,
  finding_index: z.number(),
});
export type FindingRef = z.infer<typeof FindingRef>;

export const Choice = z.object({ label: z.string(), goto: z.string() });
export type Choice = z.infer<typeof Choice>;

export const Step = z.object({
  id: z.string(),
  phase: z.string().default(""),
  headline: z.string().default(""),
  question: z.string().default("Why is checkout failing?"),
  theories: z.array(TheoryState).default([]),
  witnesses: z.array(WitnessState).default([]),
  consensus: ConsensusState,
  revealed_findings: z.array(FindingRef).default([]),
  prompt: z.string().default(""),
  choices: z.array(Choice).default([]),
  next: z.string().nullable().optional(),
  dwell: z.number().default(3.0),
});
export type Step = z.infer<typeof Step>;

export const InvestigationReplay = z.object({
  case_id: z.string(),
  title: z.string(),
  blurb: z.string(),
  summary: z.string(),
  incident: IncidentContext,
  specialists: z.array(SpecialistName),
  theories: z.array(Theory),
  start: z.string(),
  steps: z.array(Step),
  deck: Deck,
});
export type InvestigationReplay = z.infer<typeof InvestigationReplay>;

export const THEORY_STATUS_LABEL: Record<TheoryStatus, string> = {
  forming: "forming",
  possible: "possible",
  weakening: "weakening",
  strengthening: "strengthening",
  leading: "leading",
  eliminated: "ruled out",
  confirmed: "confirmed",
};

export const ACTIVITY_LABEL: Record<Activity, string> = {
  idle: "",
  investigating: "investigating…",
  posting: "new evidence",
  revising: "revising…",
};
