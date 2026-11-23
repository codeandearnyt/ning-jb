"use client";

import { useMemo, useState } from "react";

import type { ProviderStatus } from "@/lib/providers";

interface KeysPanelProps {
  providers: ProviderStatus[];
  keys: Record<string, string>;
  onKeysChange: (next: Record<string, string>) => void;
  provider: string;
  onProviderChange: (id: string) => void;
  model: string;
  onModelChange: (v: string) => void;
}

const TYPE_LABEL: Record<string, string> = {
  "Cloud AI": "cloud",
  "AI Gateway": "gateway",
  "Multi-model API": "multi-model",
  "AI Model Provider": "provider",
  "Local AI": "local",
  "OpenAI-compatible API": "compatible",
};

/** Monogram tile. Two letters, no logo fetching, no external requests. */
function Monogram({ label }: { label: string }) {
  const words = label
    .replace(/[^A-Za-z0-9 ]/g, "")
    .split(/\s+/)
    .filter(Boolean);
  // Multi-word labels give their initials; a single word gives its first two
  // letters, so OpenAI and OpenRouter never collide on "O".
  const letters =
    words.length > 1
      ? words
          .slice(0, 2)
          .map((w) => w[0]!.toUpperCase())
          .join("")
      : (words[0] ?? "?").slice(0, 2).toUpperCase();
  return (
    <span
      aria-hidden="true"
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-pink-200 bg-pink-50 font-mono text-[11px] font-medium tracking-[0.06em] text-heat"
    >
      {letters || "?"}
    </span>
  );
}

/**
 * Keys tab. Every provider is a selectable chip with a status dot; the key
 * field, model field, and connection probe sit under the selection. Keys stay
 * in this browser — they are sent with a forge request and never stored on the
 * server.
 */
export function KeysPanel({
  providers,
  keys,
  onKeysChange,
  provider,
  onProviderChange,
  model,
  onModelChange,
}: KeysPanelProps) {
  const [reveal, setReveal] = useState(false);
  const [testing, setTesting] = useState(false);
  const [probe, setProbe] = useState<
    | { kind: "ok"; model: string; latencyMs: number; reply: string }
    | { kind: "fail"; message: string }
    | null
  >(null);

  const active = providers.find((p) => p.id === provider) ?? null;
  const key = keys[provider] ?? "";
  const willHaveKey = key.trim().length > 0 || active?.configured === true;

  const keyedCount = useMemo(
    () => providers.filter((p) => (keys[p.id] ?? "").trim().length > 0).length,
    [providers, keys],
  );

  async function runProbe() {
    setTesting(true);
    setProbe(null);
    try {
      const res = await fetch("/api/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          model: model.trim(),
          apiKey: key.trim(),
        }),
      });
      const payload = (await res.json().catch(() => null)) as {
        ok?: boolean;
        model?: string;
        latencyMs?: number;
        reply?: string;
        error?: string;
      } | null;

      if (res.ok && payload?.ok) {
        setProbe({
          kind: "ok",
          model: payload.model ?? model,
          latencyMs: payload.latencyMs ?? 0,
          reply: payload.reply ?? "",
        });
      } else {
        setProbe({
          kind: "fail",
          message: payload?.error ?? `Test failed with HTTP ${res.status}.`,
        });
      }
    } catch {
      setProbe({ kind: "fail", message: "Could not reach the test endpoint." });
    } finally {
      setTesting(false);
    }
  }

  const latency =
    probe?.kind === "ok"
      ? probe.latencyMs < 1_000
        ? `${probe.latencyMs} ms`
        : `${(probe.latencyMs / 1_000).toFixed(1)} s`
      : "";

  return (
    <div className="mx-auto w-full max-w-[1120px]">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="eyebrow">keys</span>
          <h1 className="mt-2 text-[26px] font-medium leading-[1.08] tracking-[-0.025em] text-ink sm:text-[34px]">
            Bring your own key.
          </h1>
          <p className="mt-2 max-w-[62ch] text-[13.5px] leading-relaxed text-muted">
            Ten backends, one OpenAI-compatible interface. Keys live in this
            browser only, travel with the forge request, and are never stored on
            the server.
          </p>
        </div>
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          {keyedCount} of {providers.length} keyed
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1.15fr_1fr]">
        {/* Provider grid */}
        <div className="card overflow-hidden">
          <div className="panel-head">
            <span className="eyebrow">providers</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              select one
            </span>
          </div>
          <div className="grid grid-cols-1 gap-1.5 p-3 sm:grid-cols-2">
            {providers.map((p) => {
              const has = (keys[p.id] ?? "").trim().length > 0;
              const server = p.configured && !has;
              const isActive = p.id === provider;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    onProviderChange(p.id);
                    onModelChange("");
                    setProbe(null);
                    setReveal(false);
                  }}
                  data-active={isActive}
                  className="choice items-center gap-2.5 px-3 py-2.5"
                >
                  <Monogram label={p.label} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-medium text-ink">
                      {p.label}
                    </span>
                    <span className="block font-mono text-[9.5px] uppercase tracking-[0.1em] text-muted">
                      {TYPE_LABEL[p.type] ?? p.type}
                    </span>
                  </span>
                  <span
                    aria-hidden="true"
                    title={
                      has
                        ? "key stored in this browser"
                        : p.keyOptional
                          ? "no key needed"
                          : server
                            ? "server key"
                            : "no key"
                    }
                    className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      has
                        ? "bg-heat"
                        : p.keyOptional
                          ? "border border-heat/50 bg-transparent"
                          : server
                            ? "bg-heat/40"
                            : "border border-pink-300 bg-transparent"
                    }`}
                  />
                </button>
              );
            })}
          </div>
        </div>

        {/* Key + model for the selected provider */}
        <div className="card overflow-hidden">
          <div className="panel-head">
            <span className="eyebrow">{active?.label ?? "provider"}</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              this browser only
            </span>
          </div>

          <div className="space-y-4 px-5 py-4">
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="label">api key</span>
                {active?.configured && !key.trim() && (
                  <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-heat">
                    server key in use
                  </span>
                )}
              </div>
              <div className="flex items-stretch gap-2">
                <input
                  className="field font-mono text-[12px]"
                  type={reveal ? "text" : "password"}
                  autoComplete="off"
                  spellCheck={false}
                  maxLength={500}
                  placeholder={
                    active ? `paste ${active.keyVars[0] ?? "key"}` : "paste key"
                  }
                  value={key}
                  onChange={(e) => {
                    onKeysChange({ ...keys, [provider]: e.target.value });
                    setProbe(null);
                  }}
                />
                <button
                  type="button"
                  className="btn-ghost shrink-0"
                  onClick={() => setReveal((r) => !r)}
                  disabled={key.length === 0}
                  aria-pressed={reveal}
                >
                  {reveal ? "hide" : "show"}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="label">model</span>
                {active?.defaultModel && (
                  <button
                    type="button"
                    className="font-mono text-[10px] text-muted underline-offset-2 hover:text-heat hover:underline"
                    onClick={() => onModelChange("")}
                    disabled={!model}
                  >
                    default: {active.defaultModel}
                  </button>
                )}
              </div>
              <input
                className="field font-mono text-[12px]"
                type="text"
                maxLength={120}
                placeholder={active?.defaultModel || "provider default"}
                value={model}
                onChange={(e) => {
                  onModelChange(e.target.value);
                  setProbe(null);
                }}
              />
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={runProbe}
                disabled={testing || !willHaveKey}
              >
                {testing ? "testing…" : "test connection"}
              </button>
              {probe && (
                <p
                  role="status"
                  aria-live="polite"
                  className="font-mono text-[11px] leading-relaxed"
                >
                  {probe.kind === "ok" ? (
                    <>
                      <span className="text-good">ok</span>
                      <span className="text-muted">
                        {" · "}
                        {latency} · {probe.model}
                      </span>
                    </>
                  ) : (
                    <span className="text-danger">{probe.message}</span>
                  )}
                </p>
              )}
            </div>

            {active && (
              <p className="border-t border-line pt-3 text-[12px] leading-relaxed text-muted">
                {active.note}
                {active.warning && (
                  <span className="mt-1 block font-mono text-[11px] text-heat">
                    {active.warning}
                  </span>
                )}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
