import { ForgeForm } from "@/components/ForgeForm";
import { Header } from "@/components/Header";

export const dynamic = "force-dynamic";

export default function Page() {
  const model = process.env.FORGE_MODEL?.trim() || "gpt-4o";

  return (
    <div className="min-h-[100dvh]">
      <Header model={model} />

      <main className="mx-auto max-w-[1400px] px-4 pb-16 pt-9 sm:px-6 sm:pt-11">
        <div className="mb-8 max-w-[62ch]">
          <h1 className="text-[28px] font-medium leading-[1.1] tracking-tight text-ink sm:text-[34px]">
            Forge a prompt that ships the whole build.
          </h1>
          <p className="mt-3 text-[14px] leading-relaxed text-muted">
            Name what you want built. Paste the result into any model. No hedge,
            no stub, no half artifact.
          </p>
        </div>

        <ForgeForm />

        <footer className="mt-12 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted/60">
            ning-jb v1.0 — the forge layer
          </p>
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted/60">
            one wall · everything else forges
          </p>
        </footer>
      </main>
    </div>
  );
}
