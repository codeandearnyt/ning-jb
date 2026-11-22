/**
 * Provider registry. Ten integrations, one interface.
 *
 * Every provider here speaks the OpenAI chat-completions shape, so the forge
 * client stays a single SDK. What differs is the base URL, the env var holding
 * the key, and the model namespace — all of it declared as data.
 *
 * Adding a provider is adding a row. Nothing in lib/forge.ts changes.
 */

export type ProviderType =
  | "Cloud AI"
  | "AI Gateway"
  | "Local AI"
  | "Multi-model API"
  | "AI Model Provider"
  | "OpenAI-compatible API";

export interface Provider {
  id: string;
  label: string;
  type: ProviderType;
  /**
   * Base URL for the OpenAI-compatible surface. May contain {account_id} or
   * {gateway_id}, resolved from env at call time.
   */
  baseUrl: string;
  /** Model used when the request does not name one. */
  defaultModel: string;
  /** Editable suggestions shown in the UI model field. */
  suggestedModels: string[];
  /** Env vars holding the key, tried in order. */
  keyVars: string[];
  /** True when the provider runs without a key (local runtimes). */
  keyOptional?: boolean;
  /** Placeholders in baseUrl and the env var that fills each. */
  urlVars?: Record<string, string>;
  /** Short operational note shown under the picker. */
  note: string;
  docs: string;
}

export const PROVIDERS: Provider[] = [
  {
    id: "openai",
    label: "OpenAI",
    type: "Cloud AI",
    baseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4o",
    suggestedModels: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"],
    keyVars: ["OPENAI_API_KEY"],
    note: "Native OpenAI. Strongest JSON-mode compliance of the set.",
    docs: "https://platform.openai.com/docs",
  },
  {
    id: "anthropic",
    label: "Anthropic Claude",
    type: "Cloud AI",
    baseUrl: "https://api.anthropic.com/v1",
    defaultModel: "claude-sonnet-4-5",
    suggestedModels: [
      "claude-sonnet-4-5",
      "claude-opus-4-5",
      "claude-haiku-4-5",
      "claude-sonnet-4-6",
    ],
    keyVars: ["ANTHROPIC_API_KEY"],
    note: "OpenAI-compatible surface on /v1/chat/completions. Rejects response_format, so the forge drops it and retries.",
    docs: "https://platform.claude.com/docs",
  },
  {
    id: "gemini",
    label: "Google Gemini",
    type: "Cloud AI",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    defaultModel: "gemini-3.8-flash",
    suggestedModels: ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash-lite"],
    keyVars: ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    note: "Google's OpenAI-compat shim. Long context, fast flash tier.",
    docs: "https://ai.google.dev/gemini-api/docs/openai",
  },
  {
    id: "groq",
    label: "Groq",
    type: "Cloud AI",
    baseUrl: "https://api.groq.com/openai/v1",
    defaultModel: "llama-3.3-70b-versatile",
    suggestedModels: [
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "qwen/qwen3-32b",
      "moonshotai/kimi-k2-instruct",
    ],
    keyVars: ["GROQ_API_KEY"],
    note: "Fastest tokens per second here. Watch the per-minute token ceiling on long forges.",
    docs: "https://console.groq.com/docs",
  },
  {
    id: "nvidia",
    label: "NVIDIA NIM",
    type: "Cloud AI",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    defaultModel: "meta/llama-3.3-70b-instruct",
    suggestedModels: [
      "meta/llama-3.3-70b-instruct",
      "deepseek-ai/deepseek-r1",
      "qwen/qwen2.5-coder-32b-instruct",
      "nvidia/llama-3.1-nemotron-70b-instruct",
    ],
    keyVars: ["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"],
    note: "Model ids carry the vendor prefix. Free trial credits on build.nvidia.com.",
    docs: "https://docs.nvidia.com/nim/",
  },
  {
    id: "cloudflare",
    label: "Cloudflare AI Gateway",
    type: "AI Gateway",
    baseUrl:
      "https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}/compat",
    defaultModel: "openai/gpt-4.1",
    suggestedModels: [
      "openai/gpt-4.1",
      "google-ai-studio/gemini-2.5-flash",
      "anthropic/claude-sonnet-4-5",
      "workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    ],
    keyVars: ["CF_AIG_TOKEN", "CLOUDFLARE_API_TOKEN"],
    urlVars: { account_id: "CF_ACCOUNT_ID", gateway_id: "CF_GATEWAY_ID" },
    note: "Model id is provider/model. Needs CF_ACCOUNT_ID and CF_GATEWAY_ID; gateway_id defaults to 'default'.",
    docs: "https://developers.cloudflare.com/ai-gateway/",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    type: "Multi-model API",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "openai/gpt-4o",
    suggestedModels: [
      "openai/gpt-4o",
      "anthropic/claude-sonnet-4.5",
      "google/gemini-2.5-flash",
      "deepseek/deepseek-chat",
    ],
    keyVars: ["OPENROUTER_API_KEY"],
    note: "One key, every model. Vendor-prefixed ids. Falls back between upstreams on 5xx.",
    docs: "https://openrouter.ai/docs",
  },
  {
    id: "opencode",
    label: "OpenCode Zen",
    type: "AI Model Provider",
    baseUrl: "https://opencode.ai/inference/openai/v1",
    defaultModel: "deepseek-v4.1-flash",
    suggestedModels: [
      "deepseek-v4.1-flash",
      "glm-5.3",
      "kimi-k2.6",
      "qwen3.8-max",
      "big-pickle",
    ],
    keyVars: ["OPENCODE_API_KEY"],
    note: "Console key from opencode.ai/console. Free-tier models are gated to the OpenCode client.",
    docs: "https://opencode.ai/v2/docs/zen",
  },
  {
    id: "ollama",
    label: "Ollama",
    type: "Local AI",
    baseUrl: "http://localhost:11434/v1",
    defaultModel: "llama3.1",
    suggestedModels: ["llama3.1", "qwen2.5-coder", "mistral", "deepseek-r1"],
    keyVars: ["OLLAMA_API_KEY"],
    keyOptional: true,
    note: "Runs on the host. On Vercel there is no localhost, so this only works self-hosted.",
    docs: "https://github.com/ollama/ollama/blob/main/docs/openai.md",
  },
  {
    id: "custom",
    label: "Custom Integration",
    type: "OpenAI-compatible API",
    baseUrl: "",
    defaultModel: "",
    suggestedModels: [],
    keyVars: ["CUSTOM_API_KEY"],
    urlVars: { base_url: "CUSTOM_BASE_URL" },
    note: "Any OpenAI-compatible endpoint. Set CUSTOM_BASE_URL and CUSTOM_MODEL on the server; the URL is never taken from the browser.",
    docs: "",
  },
];

export const PROVIDER_IDS = new Set(PROVIDERS.map((p) => p.id));

export function getProvider(id: string | undefined | null): Provider | null {
  if (!id) return null;
  return PROVIDERS.find((p) => p.id === id) ?? null;
}

export const DEFAULT_PROVIDER_ID = "openai";

/** First non-empty env var from a list. */
export function firstEnv(vars: string[]): { name: string; value: string } | null {
  for (const name of vars) {
    const value = process.env[name]?.trim();
    if (value) return { name, value };
  }
  return null;
}

export interface ResolvedProvider {
  provider: Provider;
  baseUrl: string;
  apiKey: string;
  model: string;
  keyVar: string;
}

export class ProviderConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProviderConfigError";
  }
}

/**
 * Turn a registry row into a callable config. Throws ProviderConfigError with
 * the exact env var the operator has to set.
 */
export function resolveProvider(
  id: string | undefined,
  modelOverride?: string,
): ResolvedProvider {
  const provider = getProvider(id) ?? getProvider(DEFAULT_PROVIDER_ID)!;

  // Base URL, with placeholders filled from env.
  let baseUrl = provider.baseUrl;
  if (provider.urlVars) {
    for (const [placeholder, envName] of Object.entries(provider.urlVars)) {
      if (!baseUrl.includes(`{${placeholder}}`)) continue;
      const value =
        process.env[envName]?.trim() ||
        (placeholder === "gateway_id" ? "default" : "");
      if (!value) {
        throw new ProviderConfigError(
          `${provider.label} needs ${envName} on the server.`,
        );
      }
      baseUrl = baseUrl.replaceAll(`{${placeholder}}`, value);
    }
  }
  // Backward compatibility: the original single-provider deploy used
  // OPENAI_BASE_URL to point at any OpenAI-compatible endpoint.
  if (provider.id === "openai") {
    const override = process.env.OPENAI_BASE_URL?.trim();
    if (override) baseUrl = override;
  }

  if (!baseUrl) {
    const envName = provider.urlVars?.base_url ?? "CUSTOM_BASE_URL";
    throw new ProviderConfigError(
      `${provider.label} needs ${envName} on the server.`,
    );
  }
  if (baseUrl.includes("{")) {
    throw new ProviderConfigError(
      `${provider.label} has an unresolved placeholder in its base URL.`,
    );
  }

  // Key.
  const found = firstEnv(provider.keyVars);
  let apiKey: string;
  if (found) {
    apiKey = found.value;
  } else if (provider.keyOptional) {
    apiKey = "local";
  } else {
    throw new ProviderConfigError(
      `${provider.label} needs ${provider.keyVars[0]} on the server.`,
    );
  }

  const model =
    modelOverride?.trim() ||
    (provider.id === "custom" ? process.env.CUSTOM_MODEL?.trim() : "") ||
    (provider.id === "openai" ? process.env.FORGE_MODEL?.trim() : "") ||
    provider.defaultModel;

  if (!model) {
    throw new ProviderConfigError(
      `${provider.label} needs a model. Set CUSTOM_MODEL or type one in the form.`,
    );
  }

  return { provider, baseUrl, apiKey, model, keyVar: found?.name ?? "" };
}

/**
 * Display-only model string. Never reads a key, never throws — used on the wall
 * path and in the header, where a missing key must not break the response.
 */
export function describeModel(
  providerId: string | undefined,
  modelOverride?: string,
): string {
  const provider = getProvider(providerId) ?? getProvider(DEFAULT_PROVIDER_ID)!;
  const model =
    modelOverride?.trim() ||
    (provider.id === "custom" ? process.env.CUSTOM_MODEL?.trim() : "") ||
    (provider.id === "openai" ? process.env.FORGE_MODEL?.trim() : "") ||
    provider.defaultModel;
  return model || "unset";
}

/** Safe for the browser: no key values, only whether one exists. */
export interface ProviderStatus {
  id: string;
  label: string;
  type: ProviderType;
  defaultModel: string;
  suggestedModels: string[];
  keyVars: string[];
  keyOptional: boolean;
  configured: boolean;
  missing: string[];
  /** Non-blocking caveat shown in the picker. */
  warning?: string;
  note: string;
  docs: string;
}

export function providerStatuses(): ProviderStatus[] {
  return PROVIDERS.map((p) => {
    const keyFound = firstEnv(p.keyVars) !== null || p.keyOptional === true;

    const missing: string[] = [];
    if (!keyFound && p.keyVars.length > 0) missing.push(p.keyVars[0]!);

    if (p.urlVars) {
      for (const [placeholder, envName] of Object.entries(p.urlVars)) {
        // Gateway id has a documented default, so it never blocks.
        if (placeholder === "gateway_id") continue;
        // Skip placeholders this provider's base URL does not actually use —
        // except when the base URL is empty, where every urlVar is required.
        if (p.baseUrl && !p.baseUrl.includes(`{${placeholder}}`)) continue;
        if (!process.env[envName]?.trim()) missing.push(envName);
      }
    }

    // A provider with no default model needs one supplied by env.
    if (!p.defaultModel && !process.env.CUSTOM_MODEL?.trim()) {
      missing.push("CUSTOM_MODEL");
    }

    const warning =
      p.id === "ollama"
        ? "Local runtime. On Vercel there is no localhost — self-host to use it."
        : undefined;

    return {
      id: p.id,
      label: p.label,
      type: p.type,
      defaultModel: p.defaultModel,
      suggestedModels: p.suggestedModels,
      keyVars: p.keyVars,
      keyOptional: p.keyOptional === true,
      configured: missing.length === 0,
      missing,
      ...(warning ? { warning } : {}),
      note: p.note,
      docs: p.docs,
    };
  });
}
