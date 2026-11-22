import { NextResponse } from "next/server";

import { ForgeError } from "@/lib/forge";
import { parseProbeRequest, probeProvider } from "@/lib/probe";
import { DEFAULT_PROVIDER_ID, PROVIDER_IDS } from "@/lib/providers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

/**
 * Probes are cheap but they are still outbound calls. Same soft per-instance
 * cap as the forge route, a looser one because the button gets pressed while
 * a key is being sorted out.
 */
const WINDOW_MS = 60_000;
const MAX_PER_WINDOW = 20;
const buckets = new Map<string, number[]>();

function rateLimited(ip: string): boolean {
  const now = Date.now();
  const recent = (buckets.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  recent.push(now);
  buckets.set(ip, recent);

  if (buckets.size > 5_000) {
    for (const [key, times] of buckets) {
      if (times.every((t) => now - t >= WINDOW_MS)) buckets.delete(key);
    }
  }

  return recent.length > MAX_PER_WINDOW;
}

function clientIp(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0]!.trim();
  return req.headers.get("x-real-ip") ?? "unknown";
}

/**
 * POST /api/test — one tiny completion against the chosen provider.
 *
 * Uses the caller's key when one is supplied, otherwise the server's. Reports
 * whether the key, the base URL, and the model id actually line up, with the
 * measured latency. No prompt is forged and nothing is stored.
 */
export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Body must be valid JSON." },
      { status: 400 },
    );
  }

  let input;
  try {
    input = parseProbeRequest(body);
  } catch (err) {
    const status = err instanceof ForgeError ? err.status : 400;
    const message = err instanceof Error ? err.message : "Invalid request.";
    return NextResponse.json({ ok: false, error: message }, { status });
  }

  if (input.provider && !PROVIDER_IDS.has(input.provider)) {
    return NextResponse.json(
      { ok: false, error: `Unknown provider "${input.provider}".` },
      { status: 400 },
    );
  }
  if (!input.provider) input.provider = DEFAULT_PROVIDER_ID;

  if (rateLimited(clientIp(req))) {
    return NextResponse.json(
      { ok: false, error: "Too many tests from this address. Wait a minute." },
      { status: 429 },
    );
  }

  try {
    const result = await probeProvider(input);
    return NextResponse.json(
      { ok: true, ...result },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (err) {
    const status = err instanceof ForgeError ? err.status : 500;
    const message =
      err instanceof Error ? err.message : "Probe failed for an unknown reason.";
    return NextResponse.json(
      { ok: false, error: message },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export async function GET() {
  return NextResponse.json(
    { error: "POST a JSON body to test a provider. GET is not supported." },
    { status: 405, headers: { Allow: "POST" } },
  );
}
