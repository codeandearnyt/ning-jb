"use client";

import { useEffect, useMemo, useState } from "react";

import type { ProviderStatus } from "@/lib/providers";

interface ProviderPickerProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  model: string;
  onModelChange: (value: string) => void;
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

/**
 * Provider select plus the model field. Statuses come from /api/providers —
 * booleans only, so this component never sees a key.
 */
export function ProviderPicker({
  id,
  value,
  onChange,
  model,
  onModelChange,
  disabled,
}: ProviderPickerProps) {
  const [statuses, setStatuses] = useState<ProviderStatus[] | null>(null);

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

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <label htmlFor={id} className="label">
          forge provider
        </label>
        <div className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              active?.configured ? "bg-heat" : "bg-muted/40"
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
            }}
            disabled={disabled || !statuses}
          >
            {grouped.length === 0 && <option value={value}>Loading…</option>}
            {grouped.map((group) => (
              <optgroup key={group.type} label={group.type}>
                {group.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                    {p.configured ? " ✓" : " — not configured"}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>
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
          className="field"
          type="text"
          list={listId}
          maxLength={120}
          placeholder={active?.defaultModel || "provider default"}
          value={model}
          onChange={(e) => onModelChange(e.target.value)}
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
            {active.missing.length > 0 && (
              <span className="mt-1 block font-mono text-[11px] text-danger/80">
                missing on server: {active.missing.join(", ")}
              </span>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
