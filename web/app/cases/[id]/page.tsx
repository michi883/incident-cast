import fs from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";
import Link from "next/link";

import { InvestigationReplay } from "@/lib/replay";
import { buildTrail } from "@/lib/caseTrail";
import { InvestigationWorkspace } from "@/components/InvestigationWorkspace";
import { InvestigationStatusProvider } from "@/components/InvestigationStatus";
import { SettingsMenu } from "@/components/SettingsMenu";

async function loadReplay(id: string) {
  const filePath = path.join(process.cwd(), "public", "cases", `${id}.json`);
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    const result = InvestigationReplay.safeParse(parsed);
    if (!result.success) {
      console.error(`Replay schema mismatch for ${id}:`, result.error);
      return null;
    }
    return result.data;
  } catch {
    return null;
  }
}

export default async function CasePage({ params }: { params: { id: string } }) {
  const replay = await loadReplay(params.id);
  if (!replay) notFound();

  const { trail, unused } = buildTrail(replay);

  return (
    <main className="flex h-screen flex-col overflow-hidden">
      <InvestigationStatusProvider>
        <SettingsMenu
          caseId={params.id}
          currentBackend={replay.deck.metadata?.backend ?? "fixture"}
          trail={trail}
          unused={unused}
          theories={replay.theories.map((t) => t.label)}
          earliest={replay.incident.earliest}
          latest={replay.incident.latest}
          symptom={replay.incident.title}
        />
        <div className="flex shrink-0 items-center gap-3 border-b border-ink-800/80 px-6 py-2.5 pr-16 font-mono text-[11px] uppercase tracking-[0.18em]">
          <Link href="/" className="text-ink-500 transition hover:text-ink-200">
            ← cases
          </Link>
          <span className="text-ink-700">/</span>
          <span className="flex items-center gap-1.5">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-500/70" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-rose-500" />
            </span>
            <span className="text-rose-300/80">live</span>
          </span>
          <span className="text-ink-600">{replay.case_id}</span>
        </div>
        <InvestigationWorkspace replay={replay} />
      </InvestigationStatusProvider>
    </main>
  );
}
