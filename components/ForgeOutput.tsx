"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useMemo, useState } from "react";

import { ForgeTimeline } from "@/components/ForgeTimeline";
import { MANDATORY_SECTIONS } from "@/lib/contract";
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

interface ParsedSection {
  /** Header text without brackets, or "" for the preamble before [ROLE]. */
  label: string;
  body: string;
}

/** Split the forged prompt on its [SECTION] headers. Order is preserved. */
function parseSections(prompt: string): ParsedSection[] {
  const lines = prompt.split("\n");
  const out: ParsedSection[] = [];
  let label = "";
  let buffer: string[] = [];

  const flush = () => {
    const body = buffer.join("\n").trim();
    if (label || body) out.push({ label, body });
    buffer = [];
  };

  for (const line of lines) {
    // Header may stand alone or lead the line — models do both. Anything after
    // the bracket is that section's first line of body.
    const match = /^\[([A-Z][A-Z0-9 _/-]*)\]\s*(.*)$/.exec(line.trim());
    if (match) {
      flush();
      label = match[1]!;
      if (match[2]) buffer.push(match[2]);
    } else {
      buffer.push(line);
    }
  }
  flush();

  return out.filter((s) => s.label || s.body);
}

/** Short label for a mandatory section, brackets stripped. */
function shortLabel(section: string): string {
  return section.replace(/[[\]]/g, "");
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-[340px] flex-col justify-center rounded-lg border border-dashed border-pink-300 bg-pink-50 px-6 py-10">
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
      <div className="card-head">
        <div className="flex items-center gap-2.5">
          <span
            className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-hot"
            aria-hidden="true"
          />
          <span className="eyebrow">forging</span>
        </div>
        <span className="font-mono text-[10.5px] text-muted">building contract…</span>
      </div>

      <div className="px-5 py-4">
        <ForgeTimeline landed={false} />
      </div>

      <div className="relative h-0.5 overflow-hidden bg-pink-100">
        <div className="absolute inset-y-0 w-1/3 animate-heatSweep bg-gradient-to-r from-transparent via-heat to-transparent" />
      </div>
    </div>
  );
}

function ContractChips({
  present,
  repaired,
}: {
  present: string[];
  repaired: boolean;
}) {
  const ok = present.length;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {MANDATORY_SECTIONS.map((section) => {
        const has = present.includes(section);
        return (
          <span
            key={section}
            data-ok={has}
            className="chip"
            title={has ? `${shortLabel(section)} present` : `${shortLabel(section)} missing`}
          >
            <span aria-hidden="true">{has ? "✓" : "·"}</span>
            {shortLabel(section)}
          </span>
        );
      })}
      <span className="ml-1 font-mono text-[10px] uppercase tracking-[0.12em] text-heat">
        {ok}/{MANDATORY_SECTIONS.length}
        {repaired && <span className="text-muted"> · repaired</span>}
      </span>
    </div>
  );
}

export function ForgeOutput({ state, onClear }: ForgeOutputProps) {
  const reduce = useReducedMotion();
  const [copied, setCopied] = useState(false);

  const sections = useMemo(
    () => (state.kind === "done" ? parseSections(state.result.prompt) : []),
    [state],
  );

  const handleCopy = useCallback(async () => {
    if (state.kind !== "done") return;
    const ok = await copyText(state.result.prompt);
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }, [state]);

  const handleDownload = useCallback(() => {
    if (state.kind !== "done") return;
    const blob = new Blob([state.result.prompt], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "forged-prompt.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [state]);

  if (state.kind === "loading") return <LoadingState />;

  if (state.kind === "error") {
    return (
      <motion.div
        role="alert"
        initial={reduce ? false : { opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
        className="rounded-lg border border-danger/40 bg-danger/[0.05] px-5 py-4"
      >
        <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-danger">
          forge failed
        </p>
        <p className="mt-2 font-mono text-[13px] leading-relaxed text-ink">
          {state.message}
        </p>
      </motion.div>
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
  const present = result.contract?.present ?? [];
  const missing = result.contract?.missing ?? [];
  const repaired = result.contract?.repaired ?? false;

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
      className="card"
    >
      {/* Header + scorecard stay pinned while a 900-word prompt scrolls, so
          copy and clear are always one click away. */}
      <div className="sticky top-16 z-10 rounded-t-lg bg-panel">
        <div className="card-head">
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
              className="inline-flex items-center gap-2 rounded-sm border border-pink-300 bg-pink-100 px-3 py-1.5 font-mono text-[10.5px] uppercase tracking-[0.14em] text-heat transition-colors duration-160 hover:bg-pink-200 active:translate-y-px"
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={copied ? "copied" : "copy"}
                  initial={reduce ? false : { opacity: 0, y: 3 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduce ? undefined : { opacity: 0, y: -3 }}
                  transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                >
                  {copied ? "✓ copied" : "copy prompt"}
                </motion.span>
              </AnimatePresence>
            </button>
          </div>
        </div>

        {/* Contract scorecard. The detail that makes this read as an instrument. */}
        <div className="border-b border-line bg-pink-50 px-5 py-3">
          <ContractChips present={present} repaired={repaired} />
          {missing.length > 0 && (
            <p className="mt-2 font-mono text-[10.5px] leading-relaxed text-danger">
              missing: {missing.join(" · ")}
            </p>
          )}
        </div>
      </div>

      {/* Rendered as a document, not a log dump. Page scrolls, not the card —
          a nested scrollbar inside a page scrollbar traps the wheel. */}
      <div>
        {sections.map((section, i) => (
          <motion.div
            key={`${section.label}-${i}`}
            initial={reduce ? false : { opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.24,
              delay: reduce ? 0 : Math.min(i * 0.03, 0.24),
              ease: [0.16, 1, 0.3, 1],
            }}
            className="border-t border-line px-5 py-4 first:border-t-0"
          >
            {section.label && (
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-heat">
                {section.label}
              </p>
            )}
            <p className="mt-1.5 whitespace-pre-wrap break-words text-[13px] leading-relaxed text-ink">
              {section.body}
            </p>
          </motion.div>
        ))}
      </div>

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

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-b-lg border-t border-line bg-pink-50 px-5 py-2.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          paste into your target model
        </span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-heat" aria-live="polite">
            {copied ? "on the clipboard" : ""}
          </span>
          <button type="button" className="btn-ghost" onClick={handleDownload}>
            .md
          </button>
        </div>
      </div>
    </motion.div>
  );
}
