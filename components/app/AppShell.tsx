"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AboutPanel } from "@/components/app/AboutPanel";
import { ForgeWizard } from "@/components/app/ForgeWizard";
import { KeysPanel } from "@/components/app/KeysPanel";
import { OutputPanel } from "@/components/app/OutputPanel";
import { Tabs, type TabDef } from "@/components/app/Tabs";
import type { OutputState } from "@/components/ForgeOutput";
import { DEFAULT_PROVIDER_ID } from "@/lib/providers";
import type { ProviderStatus } from "@/lib/providers";

const STORAGE_KEY = "ning-jb:v1";
const KEYS_KEY = "ning-jb:keys";

interface StoredDraft {
  target?: string;
  targetAi?: string;
  checklistClass?: string;
  frame?: string;
  constraints?: string;
  provider?: string;
  model?: string;
}

/** All forge state lives here so it survives tab switches. */
export interface ForgeState {
  target: string;
  targetAi: string;
  checklistClass: string;
  frame: string;
  constraints: string;
  provider: string;
  model: string;
}

export type SetForgeField = <K extends keyof ForgeState>(
  key: K,
  value: ForgeState[K],
) => void;

const TABS: TabDef[] = [
  { id: "forge", label: "forge" },
  { id: "output", label: "output" },
  { id: "keys", label: "keys" },
  { id: "about", label: "about" },
];

export function AppShell({ providers }: { providers: ProviderStatus[] }) {
  const reduce = useReducedMotion();

  const [tab, setTab] = useState("forge");
  const [state, setState] = useState<ForgeState>({
    target: "",
    targetAi: "",
    checklistClass: "",
    frame: "none",
    constraints: "",
    provider: DEFAULT_PROVIDER_ID,
    model: "",
  });
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [output, setOutput] = useState<OutputState>({ kind: "empty" });
  const [hydrated, setHydrated] = useState(false);

  const setField = useCallback<SetForgeField>((key, value) => {
    setState((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Restore the last draft. Local only — nothing leaves the browser.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as StoredDraft;
        setState((prev) => ({
          target: typeof saved.target === "string" ? saved.target : prev.target,
          targetAi:
            typeof saved.targetAi === "string" ? saved.targetAi : prev.targetAi,
          checklistClass:
            typeof saved.checklistClass === "string"
              ? saved.checklistClass
              : prev.checklistClass,
          frame: typeof saved.frame === "string" ? saved.frame : prev.frame,
          constraints:
            typeof saved.constraints === "string"
              ? saved.constraints
              : prev.constraints,
          provider:
            typeof saved.provider === "string" && saved.provider
              ? saved.provider
              : prev.provider,
          model: typeof saved.model === "string" ? saved.model : prev.model,
        }));
      }

      // Keys live under their own entry so clearing the draft never wipes them.
      const rawKeys = window.localStorage.getItem(KEYS_KEY);
      if (rawKeys) {
        const parsed = JSON.parse(rawKeys) as Record<string, unknown>;
        const clean: Record<string, string> = {};
        for (const [k, v] of Object.entries(parsed)) {
          if (typeof v === "string" && v.trim()) clean[k] = v.trim();
        }
        setKeys(clean);
      }

      // Deep link: #keys opens the keys tab.
      const hash = window.location.hash.replace("#", "");
      if (TABS.some((t) => t.id === hash)) setTab(hash);
    } catch {
      // Corrupt or blocked storage — start clean.
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Storage full or blocked. Not worth surfacing.
    }
  }, [hydrated, state]);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(KEYS_KEY, JSON.stringify(keys));
    } catch {
      // Storage full or blocked. Not worth surfacing.
    }
  }, [hydrated, keys]);

  const changeTab = useCallback((id: string) => {
    setTab(id);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#${id}`);
    }
  }, []);

  const busy = output.kind === "loading";

  const submit = useCallback(async () => {
    const trimmed = state.target.trim();
    if (!trimmed || busy) return;

    changeTab("output");
    setOutput({ kind: "loading" });

    try {
      const res = await fetch("/api/forge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target: trimmed,
          targetAi: state.targetAi,
          constraints: state.constraints.trim(),
          checklistClass: state.checklistClass,
          frame: state.frame,
          provider: state.provider,
          model: state.model.trim(),
          apiKey: (keys[state.provider] ?? "").trim(),
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
        setOutput({
          kind: "error",
          message: "Forge returned an unreadable payload.",
        });
        return;
      }

      const result = payload as {
        prompt: string;
        notes?: string[];
        model?: string;
        provider?: string;
        wall?: boolean;
        contract?: {
          present?: string[];
          missing?: string[];
          repaired?: boolean;
        };
      };

      setOutput({
        kind: "done",
        result: {
          prompt: result.prompt,
          notes: Array.isArray(result.notes) ? result.notes : [],
          model: result.model ?? "unknown",
          provider: result.provider ?? state.provider,
          wall: result.wall === true,
          ...(result.contract
            ? {
                contract: {
                  present: Array.isArray(result.contract.present)
                    ? result.contract.present
                    : [],
                  missing: Array.isArray(result.contract.missing)
                    ? result.contract.missing
                    : [],
                  repaired: result.contract.repaired === true,
                },
              }
            : {}),
        },
      });
    } catch (err) {
      const message =
        err instanceof Error && err.name === "AbortError"
          ? "Forge timed out on the client. Try again."
          : "Could not reach the forge. Check the connection and try again.";
      setOutput({ kind: "error", message });
    }
  }, [state, keys, busy, changeTab]);

  const clearOutput = useCallback(() => setOutput({ kind: "empty" }), []);

  const keyedCount = useMemo(
    () => providers.filter((p) => (keys[p.id] ?? "").trim().length > 0).length,
    [providers, keys],
  );

  const tabs = useMemo(
    () =>
      TABS.map((t) =>
        t.id === "keys" && keyedCount > 0
          ? { ...t, badge: String(keyedCount) }
          : t,
      ),
    [keyedCount],
  );

  return (
    <div className="relative flex min-h-[100dvh] flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-panel2/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-4 px-4 sm:px-6">
          <div className="flex shrink-0 items-center gap-2.5">
            <span className="relative flex h-[18px] w-[18px] items-center justify-center">
              <span
                aria-hidden="true"
                className="absolute inset-0 rounded-full bg-[radial-gradient(circle,rgb(236_72_153/0.35),transparent_70%)] blur-[3px]"
              />
              <svg
                width="18"
                height="18"
                viewBox="0 0 18 18"
                aria-hidden="true"
                className="relative shrink-0"
              >
                <path
                  d="M9 1.2 16.2 5.4v7.2L9 16.8 1.8 12.6V5.4L9 1.2Z"
                  fill="none"
                  stroke="rgb(190 24 93)"
                  strokeWidth="1.3"
                />
                <path
                  d="M9 5.1 12.7 7.2v4.2L9 13.5 5.3 11.4V7.2L9 5.1Z"
                  fill="rgb(219 39 119)"
                  fillOpacity="0.9"
                />
              </svg>
            </span>
            <span className="hidden font-mono text-[13px] font-medium tracking-[0.2em] text-ink sm:inline">
              NING-JB
            </span>
          </div>

          <div className="min-w-0 flex-1 overflow-x-auto">
            <Tabs tabs={tabs} active={tab} onChange={changeTab} />
          </div>

          <div className="hidden shrink-0 items-center gap-1.5 rounded-full border border-pink-200 bg-pink-50 px-2.5 py-1 sm:flex">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                busy ? "animate-pulseDot bg-hot" : "bg-heat"
              }`}
              aria-hidden="true"
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-heat">
              {busy ? "forging" : "ready"}
            </span>
          </div>
        </div>
      </header>

      <main className="relative mx-auto w-full max-w-[1400px] flex-1 px-4 pb-14 pt-6 sm:px-6 sm:pt-8">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={tab}
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduce ? undefined : { opacity: 0, y: -4 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            {tab === "forge" && (
              <ForgeWizard
                state={state}
                setField={setField}
                providers={providers}
                keys={keys}
                onKeysChange={setKeys}
                busy={busy}
                onSubmit={submit}
                onGoOutput={() => changeTab("output")}
                onGoKeys={() => changeTab("keys")}
                hasOutput={output.kind === "done"}
              />
            )}

            {tab === "output" && (
              <OutputPanel
                state={output}
                onClear={clearOutput}
                target={state.target}
                constraints={state.constraints}
                onGoForge={() => changeTab("forge")}
              />
            )}

            {tab === "keys" && (
              <KeysPanel
                providers={providers}
                keys={keys}
                onKeysChange={setKeys}
                model={state.model}
                onModelChange={(v) => setField("model", v)}
                provider={state.provider}
                onProviderChange={(v) => setField("provider", v)}
              />
            )}

            {tab === "about" && <AboutPanel />}
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="relative mx-auto flex w-full max-w-[1400px] flex-wrap items-center justify-between gap-2 border-t border-line px-4 py-4 sm:px-6">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          ning-jb v1.0 — the forge layer
        </p>
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          one wall · everything else forges
        </p>
      </footer>
    </div>
  );
}
