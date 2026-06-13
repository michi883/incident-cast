import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

/** Repo root, one level above the Next.js `web/` working dir (dev server cwd). */
export const REPO_ROOT = path.resolve(process.cwd(), "..");
const VENV_PY = path.join(REPO_ROOT, ".venv", "bin", "python");
const VENV_ICAST = path.join(REPO_ROOT, ".venv", "bin", "incidentcast");

export const BACKENDS = ["fixture", "sdk", "mcp"] as const;
export type Backend = (typeof BACKENDS)[number];

const SAFE_ID = /^[a-z0-9_]+$/;

/** Validate a case id and confirm the authored YAML exists. Throws on anything suspicious. */
export function resolveCaseId(caseId: string): string {
  if (!SAFE_ID.test(caseId)) throw new Error(`invalid case id: ${caseId}`);
  const yaml = path.join(REPO_ROOT, "data", "cases", `${caseId}.yaml`);
  if (!fs.existsSync(yaml)) throw new Error(`no case at data/cases/${caseId}.yaml`);
  return caseId;
}

export function assertQueryName(name: string): string {
  if (!SAFE_ID.test(name)) throw new Error(`invalid query name: ${name}`);
  return name;
}

type RunResult = { ok: boolean; stdout: string; stderr: string };

async function run(file: string, args: string[]): Promise<RunResult> {
  try {
    const { stdout, stderr } = await execFileAsync(file, args, {
      cwd: REPO_ROOT,
      timeout: 120_000,
      maxBuffer: 16 * 1024 * 1024,
    });
    return { ok: true, stdout, stderr };
  } catch (e: unknown) {
    const err = e as { stdout?: string; stderr?: string; message?: string };
    return { ok: false, stdout: err.stdout ?? "", stderr: err.stderr || err.message || "exec failed" };
  }
}

/** Re-cast the replay for a case with a fixed, whitelisted backend (no shell, fixed argv). */
export async function castReplay(caseId: string, backend: Backend): Promise<RunResult> {
  resolveCaseId(caseId);
  if (!BACKENDS.includes(backend)) throw new Error(`invalid backend: ${backend}`);
  return run(VENV_ICAST, ["cast", `data/cases/${caseId}.yaml`, "--backend", backend]);
}

/** Run a scripts.splunk_admin subcommand and parse its single JSON object. */
export async function splunkAdmin(args: string[]): Promise<Record<string, unknown>> {
  const res = await run(VENV_PY, ["-m", "scripts.splunk_admin", ...args]);
  if (!res.ok && !res.stdout.trim()) {
    return { reachable: false, ok: false, error: res.stderr.trim().split("\n").slice(-3).join(" ") };
  }
  try {
    return JSON.parse(res.stdout);
  } catch {
    return { ok: false, error: `unparseable output: ${res.stdout.slice(0, 200)}` };
  }
}
