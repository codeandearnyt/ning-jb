"use client";

import { motion, useReducedMotion } from "motion/react";

export interface TabDef {
  id: string;
  label: string;
  /** Short badge, e.g. the number of forged prompts held. */
  badge?: string;
}

interface TabsProps {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}

/**
 * Pill tab bar. The selected pill is a single shared element that slides
 * between tabs — one layout animation instead of a border on every button.
 */
export function Tabs({ tabs, active, onChange }: TabsProps) {
  const reduce = useReducedMotion();

  return (
    <nav
      aria-label="Sections"
      className="flex items-center gap-0.5 overflow-x-auto rounded-full border border-line bg-pink-50/80 p-1"
    >
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            aria-current={isActive ? "page" : undefined}
            data-active={isActive}
            className="tab shrink-0"
          >
            {isActive && (
              <motion.span
                layoutId="tab-pill"
                aria-hidden="true"
                className="absolute inset-0 -z-10 rounded-full border border-pink-300 bg-panel shadow-[0_2px_10px_-4px_rgb(190_24_93/0.45)]"
                transition={
                  reduce
                    ? { duration: 0 }
                    : { type: "spring", stiffness: 380, damping: 32 }
                }
              />
            )}
            {tab.label}
            {tab.badge && (
              <span className="font-mono text-[9.5px] text-heat">{tab.badge}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
