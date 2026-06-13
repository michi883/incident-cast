import { NextResponse } from "next/server";

import { BACKENDS, type Backend, castReplay } from "@/lib/admin";

// Local dev admin endpoint: re-cast a case's replay with a chosen evidence backend.
export async function POST(req: Request) {
  let body: { caseId?: string; backend?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON body" }, { status: 400 });
  }
  const caseId = body.caseId ?? "";
  const backend = body.backend ?? "";
  if (!BACKENDS.includes(backend as Backend)) {
    return NextResponse.json({ ok: false, error: `backend must be one of ${BACKENDS.join(", ")}` }, { status: 400 });
  }
  try {
    const res = await castReplay(caseId, backend as Backend);
    const summary = (res.stdout + res.stderr).split("\n").filter(Boolean).slice(-4).join("\n");
    return NextResponse.json({ ok: res.ok, backend, summary }, { status: res.ok ? 200 : 500 });
  } catch (e) {
    return NextResponse.json({ ok: false, error: (e as Error).message }, { status: 400 });
  }
}
