import { NextResponse } from "next/server";

import { splunkAdmin } from "@/lib/admin";

// Always query Splunk live; never serve a build-time cached snapshot.
export const dynamic = "force-dynamic";

// Local dev admin endpoint: Splunk reachability + per-index event counts + web UI base URL.
export async function GET() {
  const result = await splunkAdmin(["status"]);
  return NextResponse.json(result);
}
