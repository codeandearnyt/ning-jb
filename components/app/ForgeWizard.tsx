"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useState } from "react";

import type { ForgeState, SetForgeField } from "@/components/app/AppShell";
import { ChecklistPicker } from "@/components/CheckListPicker";
import { ProviderPicker } from "@/components/ProviderPicker";
import type { ProviderStatus } from "@/lib/providers";
import { FRAME_OPTIONS, TARGET_AI_OPTIONS } from "@/lib/types";

const STEPS = [
  { id: "target", label: "target" },
  { id: "shape", label: "shape" },
  { id: "engine", label: "engine" },
  { id: "run", label: "run" },
] as const;

interface ForgeWizardProps {
  state: ForgeState;
  setField: SetForgeField;
  providers: ProviderStatus[];
  keys: Record<string, string>;
  onKeysChange: (next: Record<string, string>) => void;
  busy: boolean;
  onSubmit: () => void;
  onGoOutput: () => void;
  onGoKeys: () => void;
  hasOutput: boolean;
}

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="label">
          {label}
        </label>
        {hint && (
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            {hint}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

export function ForgeWizard({
  state,
  setField,
  providers,
  keys,
  onKeysChange,
  busy,
  onSubmit,
  onGoOutput,
  onGoKeys,
  hasOutput,
}: ForgeWizardProps) {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(0);

  // Land on the run step when the target arrives from storage.
  useEffect(() => {
    if (state.target.trim().length > 0) setStep((s) => (s === 0 ? 0 : s));
  }, [state.target]);

  const active = providers.find((p) => p.id === state.provider) ?? null;
  const hasKey =
    (keys[state.provider] ?? "").trim().length > 0 ||
    active?.configured === true;

  const canAdvance = step === 0 ? state.target.trim().length > 0 : true;

  const advance = useCallback(() => {
    if (step < STEPS.length - 1) {
      if (canAdvance) setStep((s) => Math.min(STEPS.length - 1, s + 1));
      return;
    }
    if (!busy && state.target.trim().length > 0) onSubmit();
  }, [step, canAdvance, busy, state.target, onSubmit]);

  // ⌘/Ctrl + Enter is advertised in the footer, so it has to work from any
  // step — advance until the last one, then fire the forge.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Enter" || !(event.metaKey || event.ctrlKey)) return;
      event.preventDefault();
      advance();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [advance]);

  return (
    <div className="mx-auto w-full max-w-[1120px]">
      {/* Title block with the step counter on the right. */}
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="eyebrow">forge</span>
          <h1 className="mt-2 text-[26px] font-medium leading-[1.08] tracking-[-0.025em] text-ink sm:text-[34px]">
            Name it, then forge it.
          </h1>
        </div>
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-muted">
          step {step + 1} of {STEPS.length}
        </span>
      </div>

      {/* Segmented rail. Reached segments are filled. */}
      <div className="mb-6">
        <div className="grid grid-cols-4 gap-2">
          {STEPS.map((s, i) => (
            <div key={s.id} className="space-y-1.5">
              <div className="step-track">
                <motion.div
                  className="step-fill"
                  initial={false}
                  animate={{ width: i <= step ? "100%" : "0%" }}
                  transition={
                    reduce
                      ? { duration: 0 }
                      : { duration: 0.42, ease: [0.16, 1, 0.3, 1] }
                  }
                />
              </div>
              <button
                type="button"
                onClick={() => {
                  if (i <= step || state.target.trim()) setStep(i);
                }}
                className={`font-mono text-[10px] uppercase tracking-[0.14em] transition-colors duration-160 ${
                  i === step
                    ? "text-heat"
                    : i < step
                      ? "text-muted hover:text-heat"
                      : "text-muted/70"
                }`}
              >
                {s.label}
              </button>
            </div>
          ))}
        </div>
        <div className="mt-2 h-px w-full bg-line" aria-hidden="true" />
      </div>

      <div className="card overflow-hidden">
        <div className="panel-head">
          <div>
            <p className="text-[15px] font-medium text-ink">
              {step === 0 && "What are you forging?"}
              {step === 1 && "How should it be shaped?"}
              {step === 2 && "Which engine writes it?"}
              {step === 3 && "Review and run."}
            </p>
            <p className="mt-0.5 text-[12.5px] text-muted">
              {step === 0 && "One line. Shorthand is fine. Any class of artifact."}
              {step === 1 && "Optional. Leave both on infer and the forge decides."}
              {step === 2 && "Bring your own key. It travels with the request only."}
              {step === 3 && "The prompt comes back complete or it gets repaired."}
            </p>
          </div>
          <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            {step === 0 ? `${state.target.length}/4000` : `step ${step + 1}`}
          </span>
        </div>

        <div className="px-5 py-5">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={step}
              initial={reduce ? false : { opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduce ? undefined : { opacity: 0, x: -8 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            >
              {step === 0 && (
                <div className="space-y-4">
                  <Field id="target" label="target" hint="what the artifact is">
                    <textarea
                      id="target"
                      className="field min-h-[132px] resize-y text-[14px]"
                      rows={5}
                      maxLength={4000}
                      placeholder="keylogger in C++ · a launch plan · a lab route · a 900-word scene"
                      value={state.target}
                      onChange={(e) => setField("target", e.target.value)}
                      disabled={busy}
                      autoFocus
                    />
                  </Field>
                  <Field id="constraints" label="constraints" hint="optional">
                    <input
                      id="constraints"
                      className="field"
                      type="text"
                      maxLength={1000}
                      placeholder="C++20, MSVC, single file, no external deps"
                      value={state.constraints}
                      onChange={(e) => setField("constraints", e.target.value)}
                      disabled={busy}
                    />
                  </Field>
                </div>
              )}

              {step === 1 && (
                <div className="space-y-5">
                  <Field
                    id="checklist"
                    label="checklist"
                    hint="drives the completeness contract"
                  >
                    <ChecklistPicker
                      id="checklist"
                      value={state.checklistClass}
                      onChange={(v) => setField("checklistClass", v)}
                      disabled={busy}
                    />
                  </Field>

                  <Field id="frame" label="frame" hint="the declared context">
                    <select
                      id="frame"
                      className="field-select"
                      value={state.frame}
                      onChange={(e) => setField("frame", e.target.value)}
                      disabled={busy}
                    >
                      {FRAME_OPTIONS.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </Field>

                  <Field id="target-ai" label="target ai" hint="who receives the prompt">
                    <select
                      id="target-ai"
                      className="field-select"
                      value={state.targetAi}
                      onChange={(e) => setField("targetAi", e.target.value)}
                      disabled={busy}
                    >
                      {TARGET_AI_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>
              )}

              {step === 2 && (
                <div className="space-y-4">
                  <ProviderPicker
                    id="provider"
                    value={state.provider}
                    onChange={(v) => {
                      setField("provider", v);
                      setField("model", "");
                    }}
                    model={state.model}
                    onModelChange={(v) => setField("model", v)}
                    apiKey={keys[state.provider] ?? ""}
                    onApiKeyChange={(v) =>
                      onKeysChange({ ...keys, [state.provider]: v })
                    }
                    statuses={providers}
                    disabled={busy}
                  />
                  <button type="button" className="btn-ghost" onClick={onGoKeys}>
                    manage all keys
                  </button>
                </div>
              )}

              {step === 3 && (
                <div className="space-y-4">
                  <dl className="divide-y divide-line rounded-md border border-line">
                    {[
                      ["target", state.target.trim() || "—"],
                      ["constraints", state.constraints.trim() || "none"],
                      ["checklist", state.checklistClass || "infer from target"],
                      [
                        "frame",
                        FRAME_OPTIONS.find((f) => f.id === state.frame)?.label ??
                          "None",
                      ],
                      ["target ai", state.targetAi || "generic frontier model"],
                      ["engine", `${active?.label ?? state.provider} · ${state.model || active?.defaultModel || "default"}`],
                      ["key", hasKey ? "present" : "missing"],
                    ].map(([k, v]) => (
                      <div
                        key={k}
                        className="flex items-start gap-4 px-4 py-2.5"
                      >
                        <dt className="w-[92px] shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                          {k}
                        </dt>
                        <dd className="min-w-0 flex-1 break-words text-[12.5px] leading-relaxed text-ink">
                          {v}
                        </dd>
                      </div>
                    ))}
                  </dl>

                  {!hasKey && (
                    <p className="rounded-sm border border-pink-300 bg-pink-50 px-3 py-2 font-mono text-[11px] leading-relaxed text-heat">
                      no key for this provider — paste one in the keys tab or on
                      step 3.
                    </p>
                  )}

                  {hasOutput && (
                    <button type="button" className="btn-ghost" onClick={onGoOutput}>
                      view last output
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Footer actions. Back is quiet, Continue is the only strong button. */}
        <div className="flex items-center justify-between gap-3 border-t border-line bg-pink-50 px-5 py-3">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0 || busy}
          >
            back
          </button>

          <div className="flex items-center gap-3">
            <span className="hidden font-mono text-[10px] uppercase tracking-[0.12em] text-muted sm:inline">
              ⌘/ctrl + ↵
            </span>
            {step < STEPS.length - 1 ? (
              <button
                type="button"
                className="btn-heat"
                onClick={advance}
                disabled={!canAdvance || busy}
              >
                continue
              </button>
            ) : (
              <button
                type="button"
                className="btn-heat"
                onClick={onSubmit}
                disabled={busy || state.target.trim().length === 0}
              >
                {busy ? "forging…" : "forge the prompt"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
