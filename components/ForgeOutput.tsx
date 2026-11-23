"use client";

import { useCallback, useState } from "react";

import type { ForgeSuccess } from "@/lib/types";

export type OutputState =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "done"; result: ForgeSuccess };

interface ForgeOutputProps {
  state: OutputState;
  onClear: () => void;
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path — insecure context or denied permission.
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-[340px] flex-col justify-center rounded-lg border border-dashed border-line bg-panel2 px-6 py-10">
      <p className="eyebrow">nothing forged yet</p>
      <ol className="mt-6 space-y-5">
        {[
          ["01", "Name the target", "One line. What the artifact is."],
          ["02", "Forge", "The engine writes the prompt."],
          ["03", "Paste it", "Into any model. It ships the build."],
        ].map(([n, title, body]) => (
          <li key={n} className="flex gap-3">
            <span className="mt-0.5 font-mono text-[10.5px] text-heat">{n}</span>
            <span>
              <span className="block text-sm text-ink">{title}</span>
              <span className="block text-[13px] leading-relaxed text-muted">
                {body}
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="card min-h-[340px]" aria-busy="true">
      <div className="flex items-center justify-between rounded-t-lg border-b border-line bg-panel2 px-5 py-3">
        <span className="eyebrow">forging</span>
        <span className="font-mono text-[10.5px] text-muted">building contract…</span>
      </div>
      <div className="space-y-2.5 p-5">
        {[92, 78, 86, 64, 88, 71, 80, 58, 84, 69, 76, 52].map((w, i) => (
          <div
            key={i}
            className="h-2.5 animate-pulse rounded-sm bg-line"
            style={{ width: `${w}%`, animationDelay: `${i * 70}ms` }}
          />
        ))}
      </div>
      <div className="relative h-0.5 overflow-hidden rounded-b-lg bg-line">
        <div className="absolute inset-y-0 w-1/3 animate-heatSweep bg-gradient-to-r from-transparent via-heat to-transparent" />
      </div>
    </div>
  );
}

export function ForgeOutput({ state, onClear }: ForgeOutputProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    if (state.kind !== "done") return;
    const ok = await copyText(state.result.prompt);
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }, [state]);

  if (state.kind === "loading") return <LoadingState />;

  if (state.kind === "error") {
    return (
      <div
        role="alert"
        className="rounded-lg border border-danger/40 bg-danger/[0.06] px-5 py-4"
      >
        <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-danger">
          forge failed
        </p>
        <p className="mt-2 font-mono text-[13px] leading-relaxed text-ink">
          {state.message}
        </p>
      </div>
    );
  }

  if (state.kind === "empty") return <EmptyState />;

  const { result } = state;

  if (result.wall) {
    return (
      <div className="card px-5 py-8">
        <p className="eyebrow">refused</p>
        <p className="mt-3 font-mono text-sm leading-relaxed text-ink">
          {result.prompt}
        </p>
      </div>
    );
  }

  const wordCount = result.prompt.split(/\s+/).filter(Boolean).length;

  return (
    <div className="animate-forgeIn card">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-lg border-b border-line bg-panel2 px-5 py-3">
        <div className="flex items-center gap-3">
          <span className="eyebrow">forged prompt</span>
          <span className="font-mono text-[10.5px] text-muted">
            {wordCount} words · {result.model}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" onClick={onClear}>
            clear
          </button>
          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-2 rounded-sm border border-heat/30 bg-heat/10 px-3 py-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-heat transition-colors hover:bg-heat/20 active:translate-y-px"
          >
            {copied ? "copied" : "copy prompt"}
          </button>
        </div>
      </div>

      <pre className="max-h-[62vh] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-[12.5px] leading-relaxed text-ink">
        {result.prompt}
      </pre>

      {result.notes.length > 0 && (
        <div className="border-t border-line px-5 py-3.5">
          <p className="eyebrow">notes</p>
          <ul className="mt-2 space-y-1.5">
            {result.notes.map((note, i) => (
              <li
                key={i}
                className="flex gap-2.5 font-mono text-[11.5px] leading-relaxed text-muted"
              >
                <span className="text-heat">{String(i + 1).padStart(2, "0")}</span>
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center justify-between rounded-b-lg border-t border-line bg-panel2 px-5 py-2.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          paste into your target model
        </span>
        <span className="font-mono text-[10px] text-muted" aria-live="polite">
          {copied ? "on the clipboard" : ""}
        </span>
      </div>
    </div>
  );
}
