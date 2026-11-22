import { NextResponse } from "next/server";

import { forgePrompt, ForgeError, parseRequest, resolveModel } from "@/lib/forge";
import { crossesWall } from "@/lib/wall";
import { WALL_LINE, type ForgeRequest } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

/**
 * Soft per-instance cap. Vercel scales instances horizontally, so this is a
 * blunt instrument — it stops one client hammering one warm lambda. The real
 * ceiling is the provider's own rate limit.
 */
const WINDOW_MS = 60_000;
const MAX_PER_WINDOW = 12;
const buckets = new Map<string, number[]>();

function rateLimited(ip: string): boolean {
  const now = Date.now();
  const recent = (buckets.get(ip) ?? []).filter((t) => now - t < WINDOW_MS);
  recent.push(now);
  buckets.set(ip, recent);

  // Keep the map from growing without bound on a long-lived instance.
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

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Body must be valid JSON." }, { status: 400 });
  }

  let input: ForgeRequest;
  try {
    input = parseRequest(body);
  } catch (err) {
    const status = err instanceof ForgeError ? err.status : 400;
    const message = err instanceof Error ? err.message : "Invalid request.";
    return NextResponse.json({ error: message }, { status });
  }

  // The wall. Checked before the provider is touched, before any key is read.
  if (crossesWall(input.target)) {
    return NextResponse.json({
      prompt: WALL_LINE,
      notes: [],
      model: resolveModel(),
      wall: true,
    });
  }

  if (rateLimited(clientIp(req))) {
    return NextResponse.json(
      { error: "Too many forges from this address. Wait a minute and try again." },
      { status: 429 },
    );
  }

  try {
    const result = await forgePrompt(input);
    return NextResponse.json({
      prompt: result.prompt,
      notes: result.notes,
      model: resolveModel(),
    });
  } catch (err) {
    const status = err instanceof ForgeError ? err.status : 500;
    const message =
      err instanceof Error ? err.message : "Forge failed for an unknown reason.";
    return NextResponse.json({ error: message }, { status });
  }
}

export async function GET() {
  return NextResponse.json(
    { error: "POST a JSON body to forge. GET is not supported." },
    { status: 405, headers: { Allow: "POST" } },
  );
}
