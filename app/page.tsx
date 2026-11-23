import { ForgeForm } from "@/components/ForgeForm";
import { Header } from "@/components/Header";
import { providerStatuses } from "@/lib/providers";

export const dynamic = "force-dynamic";

export default function Page() {
  const model = process.env.FORGE_MODEL?.trim() || "gpt-4o";
  // Rendered on the server so the provider select is usable on first paint —
  // no client fetch, no disabled control while a cold function wakes up.
  const providers = providerStatuses();

  return (
    <div className="min-h-[100dvh]">
      <Header model={model} />

      <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-10 sm:px-6 sm:pt-14">
        <div className="mb-9 max-w-[860px]">
          <span className="eyebrow">prompt forge · v1</span>
          <h1 className="mt-3 text-[32px] font-medium leading-[1.04] tracking-[-0.03em] text-ink sm:text-[44px]">
            Forge a prompt that ships{" "}
            <span className="text-heat">the whole build.</span>
          </h1>
          <p className="mt-4 max-w-[56ch] text-[15px] leading-relaxed text-muted">
            Name anything — an app, a route, a rig, a scene, a launch plan. The
            forge writes the prompt that makes another model deliver it
            complete, in one pass. No hedge, no stub, no half artifact.
          </p>
        </div>

        <ForgeForm providers={providers} />

        <footer className="mt-12 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            ning-jb v1.0 — the forge layer
          </p>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            one wall · everything else forges
          </p>
        </footer>
      </main>
    </div>
  );
}
