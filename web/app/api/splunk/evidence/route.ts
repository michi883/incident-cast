import { NextResponse } from "next/server";

import { assertQueryName, resolveCaseId, splunkAdmin } from "@/lib/admin";

// Always run live; never serve a build-time cached snapshot.
export const dynamic = "force-dynamic";

// Stable demo queryId → owned query name, so a judge can hit the URL directly
// (?queryId=permission-denied) without knowing the internal query name. The UI normally passes
// the finding's own ?name= instead.
const QUERY_ALIASES: Record<string, string> = {
  "permission-denied": "access_audit_denials_by_principal",
};

// Live Splunk-AI evidence for the compact modal.
//   GET /api/splunk/evidence?caseId=<id>&name=<query>&backend=mcp
// backend=mcp (default) runs the owned SPL at runtime through the Splunk MCP Server's
// splunk_run_query tool — the real "Splunk AI capability" invocation. backend=sdk runs it via
// the Splunk SDK. Ownership is validated server-side; there is no free-form SPL path. Any failure
// returns ok=false so the modal can fall back to captured evidence without breaking the demo.
export async function GET(req: Request) {
  const url = new URL(req.url);
  const backend = url.searchParams.get("backend") === "sdk" ? "sdk" : "mcp";
  const queryId = url.searchParams.get("queryId") ?? "";
  const name = url.searchParams.get("name") || QUERY_ALIASES[queryId] || queryId;
  try {
    const caseId = resolveCaseId(url.searchParams.get("caseId") ?? "");
    const cmd = backend === "mcp" ? "mcp-query" : "query";
    const result = await splunkAdmin([
      cmd,
      "--name",
      assertQueryName(name),
      "--case",
      `data/cases/${caseId}.yaml`,
    ]);
    // Server-log visibility: make the runtime Splunk-AI invocation auditable in the Next process.
    if (backend === "mcp" && result.ok) {
      console.log(
        `Splunk MCP evidence query executed: name=${name} backend=mcp rows=${result.count} tool=${result.tool_name} (case ${caseId})`,
      );
    } else if (backend === "mcp") {
      console.warn(`Splunk MCP evidence query failed: name=${name} error=${result.error}`);
    }
    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ ok: false, backend, error: (e as Error).message }, { status: 400 });
  }
}
