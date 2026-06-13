import type { InvestigationPhase } from "./InvestigationStatus";

const ROOT_CAUSE_DEFAULT = "Secret Manager access failure";
const AFFECTED_REVISION = "checkout-api-00042";

// The room's current understanding, compressed to a few high-confidence lines. No prose, no
// links, no competing-theory restatement — the proof itself lives below in the trail. Shows
// the unknown picture before convergence and the isolated root cause after.
export function CurrentPicture({
  concluded,
  phase,
  rootCause,
  theoryCount,
  evidenceRows,
}: {
  concluded: boolean;
  phase: InvestigationPhase;
  rootCause: string | null;
  theoryCount: number;
  evidenceRows: number;
}) {
  return (
    <>
      <h3 className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-500">
        Current picture
      </h3>
      {concluded ? (
        <ul className="mt-2 space-y-0.5 text-[13px] leading-relaxed">
          <li className="flex gap-2 text-emerald-200">
            <span className="text-emerald-400/80">✓</span> root cause isolated
          </li>
          <li className="pl-5 font-medium text-ink-100">{rootCause ?? ROOT_CAUSE_DEFAULT}</li>
          <li className="pl-5 text-ink-400">
            revision <span className="font-mono text-ink-300">{AFFECTED_REVISION}</span>
          </li>
          <li className="pl-5 text-ink-400">specialists converged</li>
        </ul>
      ) : (
        <ul className="mt-2 space-y-0.5 text-[13px] leading-relaxed text-ink-300">
          <li className="flex gap-2">
            <span className="text-rose-400/80">•</span> checkout-api failing
          </li>
          <li className="flex gap-2">
            <span className="text-ink-600">•</span>{" "}
            {phase === "investigating" ? "cause narrowing…" : "cause unknown"}
          </li>
          <li className="flex gap-2">
            <span className="text-ink-600">•</span> {theoryCount} competing theories
          </li>
          {evidenceRows > 0 && (
            <li className="flex gap-2">
              <span className="text-ink-600">•</span> {evidenceRows.toLocaleString()} evidence rows
              available
            </li>
          )}
        </ul>
      )}
    </>
  );
}
