"use client";

import { ForgeOutput, type OutputState } from "@/components/ForgeOutput";
import { ForgePreview } from "@/components/ForgePreview";

interface OutputPanelProps {
  state: OutputState;
  onClear: () => void;
  target: string;
  constraints: string;
  onGoForge: () => void;
}

export function OutputPanel({
  state,
  onClear,
  target,
  constraints,
  onGoForge,
}: OutputPanelProps) {
  const heading =
    state.kind === "empty"
      ? "Nothing forged yet."
      : state.kind === "loading"
        ? "Forging."
        : "The forged prompt.";

  return (
    <div className="mx-auto w-full max-w-[1120px]">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="eyebrow">output</span>
          <h1 className="mt-2 text-[26px] font-medium leading-[1.08] tracking-[-0.025em] text-ink sm:text-[34px]">
            {heading}
          </h1>
        </div>
        <button type="button" className="btn-ghost" onClick={onGoForge}>
          back to forge
        </button>
      </div>

      {state.kind === "empty" ? (
        <div className="space-y-4">
          <ForgePreview target={target} constraints={constraints} hidden={false} />
          <p className="text-center font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
            run a forge and the finished prompt lands here
          </p>
        </div>
      ) : (
        <ForgeOutput state={state} onClear={onClear} />
      )}
    </div>
  );
}
