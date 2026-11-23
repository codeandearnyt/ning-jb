"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { previewSections, type PreviewSection } from "@/lib/preview";

interface ForgePreviewProps {
  target: string;
  constraints: string;
  /** Shown instead of the preview once a real forge is in flight or done. */
  hidden: boolean;
}

const STAGGER = 0.045;

function Section({ section }: { section: PreviewSection }) {
  return (
    <motion.div
      layout="position"
      variants={{
        hidden: { opacity: 0, y: 6 },
        show: { opacity: 1, y: 0 },
      }}
      transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
      className="border-t border-line px-5 py-3 first:border-t-0"
    >
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-heat">
        {section.label}
      </p>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink">{section.body}</p>
    </motion.div>
  );
}

/**
 * Live shape preview. Assembles the nine contract sections from the target as
 * the user types, debounced, entirely client-side. It is a sketch of the shape
 * the forge will fill — the header says so, and the real prompt replaces it.
 */
export function ForgePreview({ target, constraints, hidden }: ForgePreviewProps) {
  const reduce = useReducedMotion();
  const [debounced, setDebounced] = useState(target);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(target), 320);
    return () => window.clearTimeout(id);
  }, [target]);

  const sections = previewSections(debounced, constraints);
  const ready = sections.length > 0;

  if (hidden) return null;

  return (
    <div className="card overflow-hidden">
      <div className="card-head">
        <div className="flex items-center gap-2.5">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              ready ? "bg-heat" : "bg-pink-300"
            } ${ready ? "" : "animate-pulseDot"}`}
            aria-hidden="true"
          />
          <span className="eyebrow">contract preview</span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          {ready ? `${sections.length} sections · shape only` : "waiting for target"}
        </span>
      </div>

      <div className="min-h-[268px]">
        {ready ? (
          <motion.div
            initial="hidden"
            animate="show"
            variants={{
              hidden: {},
              show: {
                transition: {
                  staggerChildren: reduce ? 0 : STAGGER,
                  delayChildren: 0,
                },
              },
            }}
          >
            <AnimatePresence initial={false} mode="popLayout">
              {sections.map((section) => (
                <Section key={section.label} section={section} />
              ))}
            </AnimatePresence>
          </motion.div>
        ) : (
          <div className="flex min-h-[268px] flex-col justify-center px-6 py-10">
            <p className="eyebrow">nothing forged yet</p>
            <p className="mt-3 max-w-[42ch] text-[13px] leading-relaxed text-muted">
              Name the artifact in the form. The {sections.length || 9} contract
              sections assemble here as you type — the forge then fills them for
              real.
            </p>
            <ol className="mt-6 space-y-4">
              {[
                ["01", "Name the target", "One line. What the artifact is."],
                ["02", "Forge", "The engine writes the prompt."],
                ["03", "Paste it", "Into any model. It ships the build."],
              ].map(([n, title, body]) => (
                <li key={n} className="flex gap-3">
                  <span className="mt-0.5 font-mono text-[10.5px] text-heat">
                    {n}
                  </span>
                  <span>
                    <span className="block text-sm text-ink">{title}</span>
                    <span className="block text-[12.5px] leading-relaxed text-muted">
                      {body}
                    </span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-line bg-pink-50 px-5 py-2.5">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          no api call · runs in your browser
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-heat">
          sketch
        </span>
      </div>
    </div>
  );
}
