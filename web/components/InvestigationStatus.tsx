"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

// The room's current understanding of reality, shared between the live workspace (which
// owns it) and the Evidence Source modal (which reflects it). This is what lets the modal
// read as "current operational picture" rather than a static before/after comparison.
export type InvestigationPhase = "idle" | "investigating" | "concluded";

type Status = {
  phase: InvestigationPhase;
  rootCause: string | null;
  setStatus: (phase: InvestigationPhase, rootCause?: string | null) => void;
};

const Ctx = createContext<Status | null>(null);

export function InvestigationStatusProvider({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<InvestigationPhase>("idle");
  const [rootCause, setRootCause] = useState<string | null>(null);
  const setStatus = useCallback((p: InvestigationPhase, root: string | null = null) => {
    setPhase(p);
    setRootCause(root);
  }, []);
  const value = useMemo(() => ({ phase, rootCause, setStatus }), [phase, rootCause, setStatus]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// Safe no-op fallback so either component can render outside a provider without crashing.
export function useInvestigationStatus(): Status {
  return (
    useContext(Ctx) ?? {
      phase: "idle",
      rootCause: null,
      setStatus: () => {},
    }
  );
}
