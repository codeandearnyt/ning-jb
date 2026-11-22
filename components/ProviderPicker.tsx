"use client";

import { useEffect, useMemo, useState } from "react";

import type { ProviderStatus } from "@/lib/providers";

interface ProviderPickerProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  model: string;
  onModelChange: (value: string) => void;
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  disabled?: boolean;
}

const TYPE_ORDER = [
  "Cloud AI",
  "AI Gateway",
  "Multi-model API",
  "AI Model Provider",
  "Local AI",
  "OpenAI-compatible API",
] as const;

/** Result of the last /api/test press. Cleared whenever provider or key moves. */
type ProbeState =
  | { kind: "ok"; model: string; latencyMs: number; reply: string }
  | { kind: "fail"; message: string }
  | null;

/**
 * Provider select, model field, and the per-provider key field. Statuses come
 * from /api/providers — booleans only, so this component never receives a key
 * from the server. The key the user types here stays in their browser until it
 * is sent with a forge request.
 */
export function ProviderPicker({
  id,
  value,
  onChange,
  model,
  onModelChange,
  apiKey,
  onApiKeyChange,
  disabled,
}: ProviderPickerProps) {
  const [statuses, setStatuses] = useState<ProviderStatus[] | null>(null);
  const [reveal, setReveal] = useState(false);
  const [testing, setTesting] = useState(false);
  const [probe, setProbe] = useState<ProbeState>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/providers")
      .then((r) => (r.ok ? r.json() : null))
      .then((payload: unknown) => {
        if (!alive) return;
        const list =
          payload && typeof payload === "object" && "providers" in payload
            ? (payload as { providers: unknown }).providers
            : null;
        if (Array.isArray(list)) setStatuses(list as ProviderStatus[]);
      })
      .catch(() => {
        // Status is decoration. The forge still works without it.
      });
    return () => {
      alive = false;
    };
  }, []);

  const active = useMemo(
    () => statuses?.find((p) => p.id === value) ?? null,
    [statuses, value],
  );

  const grouped = useMemo(() => {
    if (!statuses) return [];
    return TYPE_ORDER.map((type) => ({
      type,
      items: statuses.filter((p) => p.type === type),
    })).filter((g) => g.items.length > 0);
  }, [statuses]);

  const suggestions = active?.suggestedModels ?? [];
  const listId = `${id}-models`;
  // Lit when this forge will actually have a key: typed here or on the server.
  const willHaveKey = apiKey.trim().length > 0 || active?.configured === true;
  const usesServerKey = apiKey.trim().length === 0 && active?.configured === true;

  /**
   * One tiny completion against the selected provider. Proves the key, the base
   * URL, and the model id actually line up — without forging a prompt.
   */
  async function runProbe() {
    setTesting(true);
    setProbe(null);
    try {
      const res = await fetch("/api/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: value,
          model: model.trim(),
          apiKey: apiKey.trim(),
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

  // Latency under a second reads as milliseconds; anything else as seconds.
  const probeLatency =
    probe?.kind === "ok"
      ? probe.latencyMs < 1_000
        ? `${probe.latencyMs} ms`
        : `${(probe.latencyMs / 1_000).toFixed(1)} s`
      : "";

  // Providers answer with anything from "ok" to a wall of JSON. Flatten and
  // clip it so the line never wraps into the layout.
  const probeReply = (() => {
    if (probe?.kind !== "ok") return "";
    const flat = probe.reply.replace(/\s+/g, " ").trim();
    if (!flat) return " · reachable, empty reply";
    return ` · “${flat.slice(0, 48)}${flat.length > 48 ? "…" : ""}”`;
  })();

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label htmlFor={id} className="label">
          forge provider
        </label>
        <div className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              willHaveKey ? "bg-heat" : "bg-muted/40"
            }`}
            aria-hidden="true"
          />
          <select
            id={id}
            className="field-select"
            value={value}
            onChange={(e) => {
              onChange(e.target.value);
              const next = statuses?.find((p) => p.id === e.target.value);
              // Clear the model so the new provider's default takes over.
              if (next && next.defaultModel !== model) onModelChange("");
              setReveal(false);
              setProbe(null);
            }}
            disabled={disabled || !statuses}
          >
            {grouped.length === 0 && <option value={value}>Loading…</option>}
            {grouped.map((group) => (
              <optgroup key={group.type} label={group.type}>
                {group.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <label htmlFor={`${id}-key`} className="label">
            api key
          </label>
          {usesServerKey ? (
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-heat/80">
              server key in use
            </span>
          ) : (
            <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted/60">
              this browser only
            </span>
          )}
        </div>

        <div className="flex items-stretch gap-2">
          <input
            id={`${id}-key`}
            className="field font-mono text-[12px]"
            type={reveal ? "text" : "password"}
            autoComplete="off"
            spellCheck={false}
            maxLength={500}
            placeholder={
              active?.configured
                ? "blank uses the server key"
                : active
                  ? `paste ${active.keyVars[0] ?? "key"}`
                  : "paste key"
            }
            value={apiKey}
            onChange={(e) => {
              onApiKeyChange(e.target.value);
              setProbe(null);
            }}
            disabled={disabled || !statuses}
          />
          <button
            type="button"
            className="btn-ghost shrink-0"
            onClick={() => setReveal((r) => !r)}
            disabled={disabled || !statuses || apiKey.length === 0}
            aria-pressed={reveal}
          >
            {reveal ? "hide" : "show"}
          </button>
          {apiKey.length > 0 && (
            <button
              type="button"
              className="btn-ghost shrink-0"
              onClick={() => {
                onApiKeyChange("");
                setProbe(null);
              }}
              disabled={disabled}
            >
              clear
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <button
            type="button"
            className="btn-ghost shrink-0"
            onClick={runProbe}
            disabled={disabled || testing || !statuses || !willHaveKey}
            title={
              willHaveKey
                ? "Send one tiny request to check the key and model"
                : "Paste a key first, or set one on the server"
            }
          >
            {testing ? "testing…" : "test connection"}
          </button>

          {probe && (
            <p
              className="animate-forgeIn font-mono text-[11px] leading-relaxed"
              role="status"
              aria-live="polite"
            >
              {probe.kind === "ok" ? (
                <>
                  <span className="text-good">ok</span>
                  <span className="text-muted">
                    {" · "}
                    {probeLatency} · {probe.model}
                    {probeReply}
                  </span>
                </>
              ) : (
                <span className="text-danger">{probe.message}</span>
              )}
            </p>
          )}
        </div>

        <p className="text-[11.5px] leading-relaxed text-muted">
          Sent with the forge request, used for that call, never stored on the
          server.
          {active && !active.configured && active.missing.length > 0 && (
            <span className="mt-1 block font-mono text-[11px] text-muted/70">
              server has no key for this provider
            </span>
          )}
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <label htmlFor={`${id}-model`} className="label">
            model
          </label>
          {active?.defaultModel && (
            <button
              type="button"
              className="font-mono text-[10px] text-muted/70 underline-offset-2 hover:text-heat hover:underline"
              onClick={() => onModelChange("")}
              disabled={disabled || !model}
            >
              default: {active.defaultModel}
            </button>
          )}
        </div>
        <input
          id={`${id}-model`}
          className="field font-mono text-[12px]"
          type="text"
          list={listId}
          maxLength={120}
          placeholder={active?.defaultModel || "provider default"}
          value={model}
          onChange={(e) => {
            onModelChange(e.target.value);
            setProbe(null);
          }}
          disabled={disabled || !statuses}
        />
        <datalist id={listId}>
          {suggestions.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        {active && (
          <p className="text-[12px] leading-relaxed text-muted">
            {active.note}
            {active.warning && (
              <span className="mt-1 block font-mono text-[11px] text-heat/80">
                {active.warning}
              </span>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
