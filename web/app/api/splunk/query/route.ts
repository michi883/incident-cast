import { NextResponse } from "next/server";

import { assertQueryName, resolveCaseId, splunkAdmin } from "@/lib/admin";

// Local dev admin endpoint: run one of the case's OWNED queries live against Splunk and
// return its rows + the resulting job sid (the python side validates ownership).
export async function POST(req: Request) {
  let body: { caseId?: string; name?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON body" }, { status: 400 });
  }
  try {
    const caseId = resolveCaseId(body.caseId ?? "");
    const name = assertQueryName(body.name ?? "");
    const result = await splunkAdmin([
      "query",
      "--name",
      name,
      "--case",
      `data/cases/${caseId}.yaml`,
    ]);
    return NextResponse.json(result);
  } catch (e) {
    return NextResponse.json({ ok: false, error: (e as Error).message }, { status: 400 });
  }
}
