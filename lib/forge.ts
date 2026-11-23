import OpenAI from "openai";

import { getChecklist } from "@/lib/checklists";
import { CLOSING_LINE, missingContract, presentSections } from "@/lib/contract";
import { FORGE_SYSTEM_PROMPT } from "@/lib/prompt-template";
import {
  ProviderConfigError,
  resolveProvider,
  type ResolvedProvider,
} from "@/lib/providers";
import { FRAME_OPTIONS, type ForgeRequest } from "@/lib/types";

const DEFAULT_TIMEOUT_MS = 60_000;
const MIN_TIMEOUT_MS = 8_000;
const MAX_TIMEOUT_MS = 60_000;
const MAX_TARGET_CHARS = 4_000;
const MAX_CONSTRAINTS_CHARS = 1_000;
const MAX_MODEL_CHARS = 120;
const MAX_KEY_CHARS = 500;
const MAX_NOTES = 3;

export class ForgeError extends Error {
  readonly status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "ForgeError";
    this.status = status;
  }
}

export function resolveTimeoutMs(): number {
  const raw = Number(process.env.FORGE_TIMEOUT_MS);
  if (!Number.isFinite(raw) || raw <= 0) return DEFAULT_TIMEOUT_MS;
  return Math.min(MAX_TIMEOUT_MS, Math.max(MIN_TIMEOUT_MS, Math.floor(raw)));
}

/** Validated, trimmed input. Throws ForgeError(400) on bad payloads. */
export function parseRequest(body: unknown): ForgeRequest {
  if (typeof body !== "object" || body === null) {
    throw new ForgeError("Request body must be a JSON object.", 400);
  }
  const raw = body as Record<string, unknown>;

  const target = typeof raw.target === "string" ? raw.target.trim() : "";
  if (!target) throw new ForgeError("TARGET is required.", 400);
  if (target.length > MAX_TARGET_CHARS) {
    throw new ForgeError(
      `TARGET is too long (${target.length} chars, max ${MAX_TARGET_CHARS}).`,
      400,
    );
  }

  const constraints =
    typeof raw.constraints === "string"
      ? raw.constraints.trim().slice(0, MAX_CONSTRAINTS_CHARS)
      : "";
  const targetAi =
    typeof raw.targetAi === "string" ? raw.targetAi.trim() : "";
  const checklistClass =
    typeof raw.checklistClass === "string" ? raw.checklistClass.trim() : "";
  const frame = typeof raw.frame === "string" ? raw.frame.trim() : "";
  const provider =
    typeof raw.provider === "string" ? raw.provider.trim().toLowerCase() : "";
  const model =
    typeof raw.model === "string"
      ? raw.model.trim().slice(0, MAX_MODEL_CHARS)
      : "";
  const apiKey =
    typeof raw.apiKey === "string" ? raw.apiKey.trim().slice(0, MAX_KEY_CHARS) : "";

  return {
    target,
    targetAi,
    constraints,
    checklistClass,
    frame,
    provider,
    model,
    apiKey,
  };
}

export function buildUserMessage(input: ForgeRequest): string {
  const checklist = getChecklist(input.checklistClass);
  const frame = FRAME_OPTIONS.find((f) => f.id === input.frame);
  const frameLabel = frame && frame.id !== "none" ? frame.label : "";

  const lines: string[] = [
    `TARGET: ${input.target}`,
    `TARGET_AI: ${input.targetAi || "generic frontier model"}`,
    `CONSTRAINTS: ${input.constraints || "none"}`,
    `FRAME: ${frameLabel || "none"}`,
    "",
  ];

  if (checklist) {
    lines.push(
      `PRESET COMPLETENESS CHECKLIST (${checklist.label}) — inject these into [COMPLETENESS CONTRACT], numbered, verbatim:`,
    );
    checklist.items.forEach((item, i) => lines.push(`${i + 1}. ${item}`));
  } else {
    lines.push(
      "PRESET COMPLETENESS CHECKLIST: none selected. Derive 6 to 10 concrete items from the target class and state them in [COMPLETENESS CONTRACT].",
    );
  }

  lines.push(
    "",
    "Forge the prompt. JSON only.",
  );

  return lines.join("\n");
}

function getClient(resolved: ResolvedProvider): OpenAI {
  return new OpenAI({
    apiKey: resolved.apiKey,
    baseURL: resolved.baseUrl,
    timeout: resolveTimeoutMs(),
    maxRetries: 0,
  });
}

/** Pull the first JSON object out of a model reply, fences and prose included. */
export function extractJson(text: string): unknown {
  const trimmed = text.trim();
  const candidates: string[] = [trimmed];

  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]) candidates.push(fenced[1].trim());

  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start !== -1 && end > start) candidates.push(trimmed.slice(start, end + 1));

  for (const candidate of candidates) {
    try {
      return JSON.parse(candidate);
    } catch {
      continue;
    }
  }
  return null;
}

interface ParsedForge {
  prompt: string;
  notes: string[];
}

/** What the contract check found. Surfaced to the UI, never invented. */
export interface ContractReport {
  /** Sections present, in contract order. */
  present: string[];
  /** Pieces missing, including order, closing line, and length. */
  missing: string[];
  /** True when the bounded repair pass ran and produced a better prompt. */
  repaired: boolean;
}

/** What forgePrompt returns: the artifact plus the provider that served it. */
export interface ForgeResult extends ParsedForge {
  provider: string;
  model: string;
  contract: ContractReport;
}

/** Sections that must survive the round-trip. [FRAME] is optional by design. */

function parseForgePayload(payload: unknown): ParsedForge {
  if (typeof payload !== "object" || payload === null) {
    throw new ForgeError("Forge model did not return a JSON object.", 502);
  }
  const obj = payload as Record<string, unknown>;

  const prompt = typeof obj.prompt === "string" ? obj.prompt.trim() : "";
  if (!prompt) {
    throw new ForgeError("Forge model returned an empty prompt.", 502);
  }

  const rawNotes = Array.isArray(obj.notes) ? obj.notes : [];
  const notes = rawNotes
    .filter((n): n is string => typeof n === "string")
    .map((n) => n.trim())
    .filter((n) => n.length > 0)
    .slice(0, MAX_NOTES);

  return { prompt, notes };
}

function isUnsupportedParam(err: unknown): boolean {
  if (!(err instanceof OpenAI.APIError)) return false;
  if (err.status !== 400 && err.status !== 422) return false;
  const text = `${err.message} ${JSON.stringify(err.error ?? "")}`.toLowerCase();
  return (
    text.includes("response_format") ||
    text.includes("json_object") ||
    text.includes("unsupported") ||
    text.includes("unrecognized")
  );
}

/** Transient upstream failure: worth one retry inside the same deadline. */
function isTransient(err: unknown): boolean {
  if (!(err instanceof OpenAI.APIError)) return false;
  return err.status === 500 || err.status === 502 || err.status === 503 || err.status === 504;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Free tiers throw bare 5xx under load. Two short retries, then give up. */
const MAX_TRANSIENT_RETRIES = 2;
const TRANSIENT_BACKOFF_MS = [1_500, 3_000];

function toForgeError(err: unknown): ForgeError {
  if (err instanceof ForgeError) return err;

  // A missing env var is an operator error, not a provider failure. Surface the
  // exact name so the fix is one line.
  if (err instanceof ProviderConfigError) {
    return new ForgeError(err.message, 500);
  }

  if (err instanceof OpenAI.APIError) {
    if (err.status === 401) {
      return new ForgeError("Provider rejected the API key (401).", 502);
    }
    if (err.status === 429) {
      return new ForgeError("Provider rate limit or quota reached (429).", 502);
    }
    return new ForgeError(
      `Provider error ${err.status ?? "unknown"}: ${err.message}`,
      502,
    );
  }

  if (err instanceof Error) {
    if (err.name === "AbortError" || err.name === "APIConnectionTimeoutError") {
      return new ForgeError(
        "Forge timed out. Raise FORGE_TIMEOUT_MS, use a faster model, or shorten the target.",
        504,
      );
    }
    return new ForgeError(err.message, 502);
  }

  return new ForgeError("Forge failed for an unknown reason.", 502);
}

function readForge(
  completion: OpenAI.Chat.Completions.ChatCompletion,
): ParsedForge {
  const text = completion.choices[0]?.message?.content ?? "";
  if (!text.trim()) {
    throw new ForgeError("Forge model returned an empty response.", 502);
  }
  return parseForgePayload(extractJson(text));
}

/**
 * One forge round-trip. Returns the deployable prompt and up to three notes.
 *
 * Two attempts maximum for provider quirks (response_format rejection), plus one
 * bounded repair pass when the returned prompt is missing contract sections.
 * All of it shares a single deadline.
 */
export async function forgePrompt(input: ForgeRequest): Promise<ForgeResult> {
  const userMessage = buildUserMessage(input);
  const timeoutMs = resolveTimeoutMs();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const baseMessages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
    { role: "system", content: FORGE_SYSTEM_PROMPT },
    { role: "user", content: userMessage },
  ];

  try {
    // Resolved inside the try so a missing env var becomes a clean 500 that
    // names the variable, not an unhandled throw.
    const resolved = resolveProvider(input.provider, input.model, input.apiKey);
    const client = getClient(resolved);
    const model = resolved.model;

    const callOnce = async (
      messages: OpenAI.Chat.Completions.ChatCompletionMessageParam[],
    ) => {
      const params = {
        model,
        temperature: 0.7,
        max_tokens: 2_400,
        messages,
      };

      const attempt = async (withFormat: boolean) =>
        client.chat.completions.create(
          withFormat
            ? { ...params, response_format: { type: "json_object" as const } }
            : params,
          { signal: controller.signal },
        );

      // Up to three tries: response_format rejection, or a transient 5xx.
      for (let i = 0; ; i += 1) {
        try {
          return await attempt(true);
        } catch (err) {
          // Some OpenAI-compatible providers reject response_format outright.
          if (isUnsupportedParam(err)) return await attempt(false);
          if (isTransient(err) && i < MAX_TRANSIENT_RETRIES) {
            await sleep(TRANSIENT_BACKOFF_MS[i] ?? 3_000);
            continue;
          }
          throw err;
        }
      }
    };

    let result: ForgeResult = {
      ...readForge(await callOnce(baseMessages)),
      provider: resolved.provider.id,
      model,
      contract: { present: [], missing: [], repaired: false },
    };

    const missing = missingContract(result.prompt);
    let repaired = false;
    if (missing.length > 0) {
      const repairMessages: OpenAI.Chat.Completions.ChatCompletionMessageParam[] = [
        ...baseMessages,
        {
          role: "assistant",
          content: JSON.stringify({ prompt: result.prompt, notes: result.notes }),
        },
        {
          role: "user",
          content: `Your forged prompt is missing: ${missing.join(
            ", ",
          )}. Return the complete JSON again with every required section present and in order, expanded to 600-900 words of concrete detail (real names, real numbers, no filler), ending with "${CLOSING_LINE}".`,
        },
      ];

      const candidate = readForge(await callOnce(repairMessages));
      if (missingContract(candidate.prompt).length <= missing.length) {
        result = {
          ...candidate,
          provider: resolved.provider.id,
          model,
          contract: { present: [], missing: [], repaired: true },
        };
        repaired = true;
      } else {
        result.notes = [
          ...result.notes,
          `Contract incomplete: ${missing.join(", ")}`,
        ].slice(0, MAX_NOTES);
      }
    }

    // Computed from the prompt that actually ships, after any repair.
    result.contract = {
      present: presentSections(result.prompt),
      missing: missingContract(result.prompt),
      repaired,
    };

    return result;
  } catch (err) {
    const mapped = toForgeError(err);
    // A provider error can echo the request back. Never let a pasted key
    // survive into a response body.
    if (input.apiKey) {
      mapped.message = mapped.message.split(input.apiKey).join("[key]");
    }
    throw mapped;
  } finally {
    clearTimeout(timer);
  }
}
