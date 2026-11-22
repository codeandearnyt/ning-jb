import OpenAI from "openai";

import { ForgeError } from "@/lib/forge";
import {
  ProviderConfigError,
  resolveProvider,
  type ResolvedProvider,
} from "@/lib/providers";

/**
 * Connection probe. One tiny completion against the selected provider with the
 * key the caller supplied, so the UI can answer "does this key work?" without
 * burning a full forge.
 *
 * Deliberately single-attempt: a retry would hide the very failure the button
 * exists to surface.
 */

const PROBE_TIMEOUT_MS = 25_000;
const MAX_KEY_CHARS = 500;
const MAX_MODEL_CHARS = 120;
const MAX_REPLY_CHARS = 120;
const PROBE_TOKENS = 32;

export interface ProbeInput {
  provider: string;
  model: string;
  apiKey: string;
}

export interface ProbeResult {
  provider: string;
  model: string;
  latencyMs: number;
  /** What the model said back. Empty when a reasoner spent its tokens thinking. */
  reply: string;
}

export function parseProbeRequest(body: unknown): ProbeInput {
  if (typeof body !== "object" || body === null) {
    throw new ForgeError("Request body must be a JSON object.", 400);
  }
  const raw = body as Record<string, unknown>;
  return {
    provider:
      typeof raw.provider === "string"
        ? raw.provider.trim().toLowerCase()
        : "",
    model:
      typeof raw.model === "string"
        ? raw.model.trim().slice(0, MAX_MODEL_CHARS)
        : "",
    apiKey:
      typeof raw.apiKey === "string"
        ? raw.apiKey.trim().slice(0, MAX_KEY_CHARS)
        : "",
  };
}

/** Provider messages carry JSON bodies; keep them to one readable line. */
function shortDetail(err: InstanceType<typeof OpenAI.APIError>): string {
  const body = err.error as { message?: unknown } | undefined;
  const message =
    typeof body?.message === "string" && body.message.trim()
      ? body.message.trim()
      : err.message;
  return message.replace(/\s+/g, " ").slice(0, 160);
}

function mapError(
  err: unknown,
  resolved: ResolvedProvider | null,
): ForgeError {
  if (err instanceof ForgeError) return err;

  if (err instanceof ProviderConfigError) {
    return new ForgeError(err.message, 500);
  }

  if (err instanceof OpenAI.APIConnectionTimeoutError) {
    return new ForgeError(
      `No answer in ${Math.round(PROBE_TIMEOUT_MS / 1_000)}s. The endpoint is slow or unreachable — a reasoning model can do this on a short token budget.`,
      504,
    );
  }

  if (err instanceof OpenAI.APIConnectionError) {
    const host = resolved ? safeHost(resolved.baseUrl) : "the endpoint";
    return new ForgeError(`Could not reach ${host}.`, 502);
  }

  if (err instanceof OpenAI.APIError) {
    const label = resolved?.provider.label ?? "The provider";
    const model = resolved?.model ?? "the model";
    const fallback = resolved?.provider.defaultModel;
    const detail = shortDetail(err);

    switch (err.status) {
      case 401:
      case 403:
        return new ForgeError(
          `Key rejected (${err.status}). Wrong key, expired, or missing a scope.`,
          502,
        );
      case 404:
        return new ForgeError(
          fallback && fallback !== model
            ? `Model "${model}" not found on ${label}. Default is "${fallback}".`
            : `Model "${model}" not found on ${label}.`,
          502,
        );
      case 429:
        return new ForgeError(
          `Key is valid, but ${label} is throttling it (429).`,
          502,
        );
      case 400:
        return new ForgeError(
          `${label} rejected the request (400): ${detail}`,
          502,
        );
      default:
        return new ForgeError(
          `${label} error ${err.status ?? "unknown"}: ${detail}`,
          502,
        );
    }
  }

  if (err instanceof Error) {
    if (err.name === "AbortError") {
      return new ForgeError("Probe aborted before the provider answered.", 504);
    }
    return new ForgeError(err.message, 502);
  }

  return new ForgeError("Probe failed for an unknown reason.", 502);
}

function safeHost(baseUrl: string): string {
  try {
    return new URL(baseUrl).host;
  } catch {
    return "the endpoint";
  }
}

export async function probeProvider(input: ProbeInput): Promise<ProbeResult> {
  let resolved: ResolvedProvider | null = null;

  try {
    resolved = resolveProvider(input.provider, input.model, input.apiKey);

    const client = new OpenAI({
      apiKey: resolved.apiKey,
      baseURL: resolved.baseUrl,
      timeout: PROBE_TIMEOUT_MS,
      maxRetries: 0,
    });

    const startedAt = Date.now();
    const completion = await client.chat.completions.create({
      model: resolved.model,
      temperature: 0,
      max_tokens: PROBE_TOKENS,
      messages: [{ role: "user", content: "Reply with the single word: ok" }],
    });
    const latencyMs = Date.now() - startedAt;

    const reply = (completion.choices[0]?.message?.content ?? "")
      .trim()
      .slice(0, MAX_REPLY_CHARS);

    return {
      provider: resolved.provider.id,
      model: resolved.model,
      latencyMs,
      reply,
    };
  } catch (err) {
    const mapped = mapError(err, resolved);
    // A provider error can echo the request back. Never let a pasted key
    // survive into a response body.
    if (input.apiKey) {
      mapped.message = mapped.message.split(input.apiKey).join("[key]");
    }
    throw mapped;
  }
}
