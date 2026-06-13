"use client";

import { useState } from "react";

import { readCasePhase } from "@/lib/caseStatus";
import type { InvestigationPhase } from "./InvestigationStatus";
import { SettingsMenu, type TrailStep, type UnusedCheck } from "./SettingsMenu";

type Backend = "fixture" | "sdk" | "mcp";

// Landing-page entry point to the operational picture: a secondary action on each case card
// that opens the SAME right-side Evidence Source drawer used on the case page — so viewers
// see the operational understanding change in the same panel before vs after the run. Phase
// is read from localStorage (persisted by the workspace) so a concluded case shows the
// concluded picture even back on the landing page.
export function CasePictureButton({
  caseId,
  currentBackend,
  trail,
  unused,
  theories,
  earliest,
  latest,
}: {
  caseId: string;
  currentBackend: Backend;
  trail: TrailStep[];
  unused: UnusedCheck[];
  theories: string[];
  earliest: string;
  latest: string;
}) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState<InvestigationPhase>("idle");

  const openDrawer = () => {
    setPhase(readCasePhase(caseId));
    setOpen(true);
  };

  return (
    <>
      <button
        onClick={openDrawer}
        className="rounded border border-ink-700 px-2.5 py-1.5 text-sm text-ink-300 transition hover:border-ink-500 hover:text-ink-100"
      >
        View current picture
      </button>

      <SettingsMenu
        caseId={caseId}
        currentBackend={currentBackend}
        trail={trail}
        unused={unused}
        theories={theories}
        earliest={earliest}
        latest={latest}
        open={open}
        onClose={() => setOpen(false)}
        phase={phase}
        rootCause={null}
        showTrigger={false}
      />
    </>
  );
}
