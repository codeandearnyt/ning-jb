import { NextResponse } from "next/server";

import { providerStatuses } from "@/lib/providers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Provider availability for the browser. Booleans and names only — a key value
 * never leaves the server, so this route is safe to expose publicly.
 */
export async function GET() {
  return NextResponse.json(
    { providers: providerStatuses() },
    { headers: { "Cache-Control": "no-store" } },
  );
}
