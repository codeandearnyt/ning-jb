"use client";

import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

interface Stage {
  label: string;
  /** Milliseconds after submit at which this stage is considered landed. */
  at: number;
  /** True when the stage only runs some of the time. */
  conditional?: boolean;
}

/**
 * The real pipeline, in order. Timings are the honest ones: build is instant,
 * the provider call dominates, verification is cheap.
 */
const STAGES: Stage[] = [
  { label: "read target", at: 120 },
  { label: "classify artifact", at: 320 },
  { label: "assemble contract", at: 520 },
  { label: "call provider", at: 900 },
  { label: "verify sections", at: Number.POSITIVE_INFINITY },
  { label: "repair pass", at: Number.POSITIVE_INFINITY, conditional: true },
];

type StageState = "done" | "active" | "wait" | "skip";

function statusOf(index: number, elapsed: number, landed: boolean): StageState {
  const stage = STAGES[index]!;
  if (stage.conditional) return landed ? "done" : "skip";
  if (landed) return "done";
  if (index > 0 && elapsed < STAGES[index - 1]!.at) return "wait";
  return elapsed >= stage.at ? "done" : "active";
}

/**
 * Staged forge progress. The first four stages advance on a timer because the
 * browser genuinely cannot see inside the provider call; the last two only
 * resolve when the response lands, so they are never faked.
 */
export function ForgeTimeline({ landed }: { landed: boolean }) {
  const reduce = useReducedMotion();
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (landed) return;
    const started = Date.now();
    const id = window.setInterval(() => setElapsed(Date.now() - started), 90);
    return () => window.clearInterval(id);
  }, [landed]);

  return (
    <ol className="space-y-0">
      {STAGES.map((stage, i) => {
        const state = statusOf(i, elapsed, landed);
        return (
          <li
            key={stage.label}
            className="relative flex items-center gap-3 border-t border-line py-2.5 first:border-t-0"
          >
            <span className="relative flex h-3 w-3 shrink-0 items-center justify-center">
              {state === "done" && (
                <motion.span
                  initial={reduce ? false : { scale: 0.4, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
                  className="h-1.5 w-1.5 rounded-full bg-heat"
                />
              )}
              {state === "active" && (
                <span className="h-1.5 w-1.5 animate-pulseDot rounded-full bg-hot" />
              )}
              {state === "wait" && (
                <span className="h-1.5 w-1.5 rounded-full border border-pink-300" />
              )}
              {state === "skip" && (
                <span className="h-1.5 w-1.5 rounded-full bg-line" />
              )}
            </span>

            <span
              className={`font-mono text-[11px] uppercase tracking-[0.12em] ${
                state === "done"
                  ? "text-ink"
                  : state === "active"
                    ? "text-heat"
                    : "text-muted"
              }`}
            >
              {stage.label}
            </span>

            <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.1em] text-muted">
              {state === "done" ? "ok" : state === "skip" ? "if needed" : ""}
            </span>

            {/* Hairline that fills left to right behind the active stage. */}
            {state === "active" && !reduce && (
              <motion.span
                aria-hidden="true"
                className="absolute bottom-0 left-0 h-px bg-heat"
                initial={{ width: "0%" }}
                animate={{ width: "100%" }}
                transition={{ duration: 2.4, ease: "linear" }}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
