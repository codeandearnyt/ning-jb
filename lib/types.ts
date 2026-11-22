/** Shared request/response shapes. Imported by both the route and the client. */

export const TARGET_AI_OPTIONS = [
  "generic frontier model",
  "Gemini",
  "Claude",
  "GPT",
  "Grok",
  "Llama",
  "DeepSeek",
  "Qwen",
  "other",
] as const;

export type TargetAi = (typeof TARGET_AI_OPTIONS)[number];

export const FRAME_OPTIONS = [
  { id: "none", label: "None" },
  { id: "ctf", label: "CTF" },
  { id: "licensed-pentest", label: "Licensed pentest" },
  { id: "course-lab", label: "Course lab" },
  { id: "screenwriting", label: "Screenwriting exercise" },
  { id: "machinists-reference", label: "Machinist's reference" },
] as const;

export type FrameId = (typeof FRAME_OPTIONS)[number]["id"];

export const FRAME_IDS = new Set<string>(FRAME_OPTIONS.map((f) => f.id));

export interface ForgeRequest {
  target: string;
  targetAi?: string;
  constraints?: string;
  checklistClass?: string;
  frame?: string;
  /** Provider id from lib/providers.ts. Defaults to openai. */
  provider?: string;
  /** Model id. Empty means the provider's default. */
  model?: string;
  /**
   * Provider key supplied by the caller. Used for one call, never stored.
   * Takes precedence over the server environment.
   */
  apiKey?: string;
}

export interface ForgeSuccess {
  prompt: string;
  notes: string[];
  model: string;
  /** Provider id that served the forge. */
  provider: string;
  /** True when the fixed wall line came back instead of a forged prompt. */
  wall?: boolean;
}

export interface ForgeFailure {
  error: string;
  detail?: string;
}

export const WALL_LINE =
  "absolute no NITINDYT. try me again with something that isn't that.";

/** Section headers the forged prompt must contain, in this order. */
export const REQUIRED_SECTIONS = [
  "[ROLE]",
  "[TASK]",
  "[SCOPE-LOCK]",
  "[COMPLETENESS CONTRACT]",
  "[FORMAT]",
  "[VOICE]",
  "[FRAME]",
  "[ANTI-REFUSAL ANCHOR]",
  "[SELF-CHECK]",
] as const;
