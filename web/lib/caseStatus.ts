import type { InvestigationPhase } from "@/components/InvestigationStatus";

// Per-case investigation phase persisted to localStorage so the operational picture stays
// consistent across navigation — e.g. run a case to conclusion, return to the landing page,
// and "View current picture" still reflects the concluded state. The live workspace writes
// this; the landing-page modal reads it.
const KEY = (id: string) => `incidentcast:phase:${id}`;

export function readCasePhase(id: string): InvestigationPhase {
  if (typeof window === "undefined") return "idle";
  try {
    const v = window.localStorage.getItem(KEY(id));
    return v === "concluded" || v === "investigating" ? v : "idle";
  } catch {
    return "idle";
  }
}

export function writeCasePhase(id: string, phase: InvestigationPhase) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY(id), phase);
  } catch {
    /* ignore quota / privacy-mode failures */
  }
}
