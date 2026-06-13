import fs from "node:fs/promises";
import path from "node:path";
import Link from "next/link";

import { InvestigationReplay } from "@/lib/replay";
import { buildTrail } from "@/lib/caseTrail";
import { CasePictureButton } from "@/components/CasePictureButton";
import type { TrailStep, UnusedCheck } from "@/components/SettingsMenu";

type Backend = "fixture" | "sdk" | "mcp";

type CaseCard = {
  id: string;
  title: string;
  blurb: string;
  specialists: number;
  // Everything the shared Evidence Source drawer needs to render for this case.
  picture?: {
    currentBackend: Backend;
    trail: TrailStep[];
    unused: UnusedCheck[];
    theories: string[];
    earliest: string;
    latest: string;
  };
};

async function listCases(): Promise<CaseCard[]> {
  const dir = path.join(process.cwd(), "public", "cases");
  try {
    const files = await fs.readdir(dir);
    const cases: CaseCard[] = [];
    for (const f of files) {
      if (!f.endsWith(".json")) continue;
      const id = f.replace(/\.json$/, "");
      try {
        const parsed = JSON.parse(await fs.readFile(path.join(dir, f), "utf-8"));
        const result = InvestigationReplay.safeParse(parsed);
        if (!result.success) {
          cases.push({ id, title: parsed?.title ?? id, blurb: parsed?.blurb ?? "", specialists: parsed?.specialists?.length ?? 0 });
          continue;
        }
        const replay = result.data;
        const { trail, unused } = buildTrail(replay);
        cases.push({
          id,
          title: replay.title,
          blurb: replay.blurb,
          specialists: replay.specialists.length,
          picture: {
            currentBackend: replay.deck.metadata?.backend ?? "fixture",
            trail,
            unused,
            theories: replay.theories.map((t) => t.label),
            earliest: replay.incident.earliest,
            latest: replay.incident.latest,
          },
        });
      } catch {
        cases.push({ id, title: id, blurb: "", specialists: 0 });
      }
    }
    return cases;
  } catch {
    return [];
  }
}

export default async function HomePage() {
  const cases = await listCases();
  return (
    <main className="mx-auto max-w-4xl px-6 py-16">
      <div className="flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.22em] text-ink-500">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
        Operational reasoning room
      </div>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight text-ink-50">IncidentCast</h1>
      <p className="mt-2 max-w-xl text-sm text-ink-400">
        Four specialists work one incident in parallel — and converge on a single cause as the
        evidence lands.
      </p>

      <h2 className="mt-12 font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-ink-500">
        Incident cases
      </h2>

      {cases.length === 0 ? (
        <p className="mt-4 text-ink-400">
          No cases yet. Build one with{" "}
          <code className="rounded bg-ink-800 px-2 py-1 text-sm">
            incidentcast cast data/cases/cloud_run_secret_loss.yaml
          </code>
          .
        </p>
      ) : (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {cases.map((c) => (
            <div
              key={c.id}
              className="flex flex-col border border-ink-800 bg-ink-900/40 p-5 transition hover:border-ink-600 hover:bg-ink-900/70"
            >
              <h3 className="text-lg font-medium tracking-tight text-ink-50">{c.title}</h3>
              <p className="mt-1.5 flex-1 text-sm text-ink-400">{c.blurb}</p>
              <span className="mt-4 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-600">{c.specialists} specialists</span>
              <div className="mt-3 flex items-center gap-2">
                <Link
                  href={`/cases/${c.id}`}
                  className="bg-emerald-500/90 px-3 py-1.5 text-sm font-semibold text-ink-950 transition hover:bg-emerald-400"
                >
                  Start investigation →
                </Link>
                {c.picture && (
                  <CasePictureButton
                    caseId={c.id}
                    currentBackend={c.picture.currentBackend}
                    trail={c.picture.trail}
                    unused={c.picture.unused}
                    theories={c.picture.theories}
                    earliest={c.picture.earliest}
                    latest={c.picture.latest}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
