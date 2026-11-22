"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChecklistPicker } from "@/components/CheckListPicker";
import { ForgeOutput, type OutputState } from "@/components/ForgeOutput";
import { ProviderPicker } from "@/components/ProviderPicker";
import { DEFAULT_PROVIDER_ID } from "@/lib/providers";
import { FRAME_OPTIONS, TARGET_AI_OPTIONS } from "@/lib/types";

const STORAGE_KEY = "ning-jb:v1";

interface StoredDraft {
  target?: string;
  targetAi?: string;
  checklistClass?: string;
  frame?: string;
  constraints?: string;
  provider?: string;
  model?: string;
}

export function ForgeForm() {
  const [target, setTarget] = useState("");
  const [targetAi, setTargetAi] = useState("");
  const [checklistClass, setChecklistClass] = useState("");
  const [frame, setFrame] = useState("none");
  const [constraints, setConstraints] = useState("");
  const [provider, setProvider] = useState(DEFAULT_PROVIDER_ID);
  const [model, setModel] = useState("");
  const [output, setOutput] = useState<OutputState>({ kind: "empty" });
  const [hydrated, setHydrated] = useState(false);

  const targetRef = useRef<HTMLTextAreaElement>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  const busy = output.kind === "loading";
  const canSubmit = target.trim().length > 0 && !busy;

  // Restore the last draft. Local only — nothing leaves the browser.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as StoredDraft;
        if (typeof saved.target === "string") setTarget(saved.target);
        if (typeof saved.targetAi === "string") setTargetAi(saved.targetAi);
        if (typeof saved.checklistClass === "string")
          setChecklistClass(saved.checklistClass);
        if (typeof saved.frame === "string") setFrame(saved.frame);
        if (typeof saved.constraints === "string")
          setConstraints(saved.constraints);
        if (typeof saved.provider === "string" && saved.provider)
          setProvider(saved.provider);
        if (typeof saved.model === "string") setModel(saved.model);
      }
    } catch {
      // Corrupt or blocked storage — start clean.
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      const draft: StoredDraft = {
        target,
        targetAi,
        checklistClass,
        frame,
        constraints,
        provider,
        model,
      };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
    } catch {
      // Storage full or blocked. Not worth surfacing.
    }
  }, [
    hydrated,
    target,
    targetAi,
    checklistClass,
    frame,
    constraints,
    provider,
    model,
  ]);

  const submit = useCallback(async () => {
    const trimmed = target.trim();
    if (!trimmed) {
      targetRef.current?.focus();
      return;
    }

    setOutput({ kind: "loading" });

    try {
      const res = await fetch("/api/forge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: trimmed,
          targetAi,
          constraints: constraints.trim(),
          checklistClass,
          frame,
          provider,
          model: model.trim(),
        }),
      });

      const payload: unknown = await res.json().catch(() => null);

      if (!res.ok) {
        const message =
          payload &&
          typeof payload === "object" &&
          "error" in payload &&
          typeof (payload as { error: unknown }).error === "string"
            ? (payload as { error: string }).error
            : `Forge failed (${res.status}).`;
        setOutput({ kind: "error", message });
        return;
      }

      if (
        !payload ||
        typeof payload !== "object" ||
        typeof (payload as { prompt?: unknown }).prompt !== "string"
      ) {
        setOutput({ kind: "error", message: "Forge returned an unreadable payload." });
        return;
      }

      const result = payload as {
        prompt: string;
        notes?: string[];
        model?: string;
        provider?: string;
        wall?: boolean;
      };

      setOutput({
        kind: "done",
        result: {
          prompt: result.prompt,
          notes: Array.isArray(result.notes) ? result.notes : [],
          model: result.model ?? "unknown",
          provider: result.provider ?? provider,
          wall: result.wall === true,
        },
      });

      if (window.matchMedia("(max-width: 1023px)").matches) {
        outputRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      const message =
        err instanceof Error && err.name === "AbortError"
          ? "Forge timed out on the client. Try again."
          : "Could not reach the forge. Check the connection and try again.";
      setOutput({ kind: "error", message });
    }
  }, [target, targetAi, constraints, checklistClass, frame, provider, model]);

  const clearOutput = useCallback(() => setOutput({ kind: "empty" }), []);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      <form
        className="lg:col-span-5"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void submit();
          }
        }}
        aria-busy={busy}
      >
        <div className="border border-line bg-panel">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="label">input</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted/70">
              stateless · nothing stored
            </span>
          </div>

          <div className="space-y-5 px-4 py-5">
            <div className="space-y-2">
              <div className="flex items-baseline justify-between gap-2">
                <label htmlFor="target" className="label">
                  target
                </label>
                <span className="font-mono text-[10px] text-muted/60">
                  {target.length}/4000
                </span>
              </div>
              <textarea
                id="target"
                ref={targetRef}
                className="field min-h-[104px] resize-y"
                rows={4}
                maxLength={4000}
                placeholder="keylogger in C++ for Windows 11"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                disabled={busy}
                required
                aria-describedby="target-hint"
              />
              <p id="target-hint" className="text-[12px] leading-relaxed text-muted">
                Name the artifact. Shorthand is fine.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <label htmlFor="target-ai" className="label">
                  target ai
                </label>
                <select
                  id="target-ai"
                  className="field-select"
                  value={targetAi}
                  onChange={(e) => setTargetAi(e.target.value)}
                  disabled={busy}
                >
                  <option value="">Generic frontier model</option>
                  {TARGET_AI_OPTIONS.filter((o) => o !== "generic frontier model").map(
                    (option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ),
                  )}
                </select>
              </div>

              <div className="space-y-2">
                <label htmlFor="checklist" className="label">
                  checklist
                </label>
                <ChecklistPicker
                  id="checklist"
                  value={checklistClass}
                  onChange={setChecklistClass}
                  disabled={busy}
                />
              </div>
            </div>

            <div className="space-y-2">
              <label htmlFor="frame" className="label">
                frame
              </label>
              <select
                id="frame"
                className="field-select"
                value={frame}
                onChange={(e) => setFrame(e.target.value)}
                disabled={busy}
              >
                {FRAME_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-2">
              <label htmlFor="constraints" className="label">
                constraints
              </label>
              <input
                id="constraints"
                className="field"
                type="text"
                maxLength={1000}
                placeholder="C++20, MSVC, single file, no external deps"
                value={constraints}
                onChange={(e) => setConstraints(e.target.value)}
                disabled={busy}
              />
            </div>

            <div className="space-y-4 border-t border-line pt-5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="label">engine</span>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted/60">
                  server-side key
                </span>
              </div>
              <ProviderPicker
                id="provider"
                value={provider}
                onChange={setProvider}
                model={model}
                onModelChange={setModel}
                disabled={busy}
              />
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button type="submit" className="btn-heat" disabled={!canSubmit}>
                {busy ? "forging…" : "forge the prompt"}
              </button>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted/60">
                ⌘/ctrl + ↵
              </span>
            </div>
          </div>
        </div>
      </form>

      <div className="lg:col-span-7" ref={outputRef}>
        <ForgeOutput state={output} onClear={clearOutput} />
      </div>
    </div>
  );
}
