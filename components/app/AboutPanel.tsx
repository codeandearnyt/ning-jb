import { CLOSING_LINE, MANDATORY_SECTIONS, MIN_WORDS } from "@/lib/contract";

const STEPS = [
  {
    n: "01",
    title: "Name the target",
    body: "One line. The forge classifies it into one of thirteen artifact classes before it writes a word.",
  },
  {
    n: "02",
    title: "Shape it",
    body: "Checklist, frame, and target model. Leave them on infer and the classifier decides.",
  },
  {
    n: "03",
    title: "Forge",
    body: `The engine writes 600–900 words across ${MANDATORY_SECTIONS.length} sections in order, ending on "${CLOSING_LINE}"`,
  },
  {
    n: "04",
    title: "Verify",
    body: `The response is checked against the contract. Anything missing triggers one bounded repair pass. Below ${MIN_WORDS} words it gets expanded.`,
  },
];

export function AboutPanel() {
  return (
    <div className="mx-auto w-full max-w-[1120px]">
      <div className="mb-5">
        <span className="eyebrow">about</span>
        <h1 className="mt-2 text-[26px] font-medium leading-[1.08] tracking-[-0.025em] text-ink sm:text-[34px]">
          A prompt is a contract.
        </h1>
        <p className="mt-2 max-w-[64ch] text-[13.5px] leading-relaxed text-muted">
          Most prompts fail because they describe a vibe. This one states the
          artifact, locks the scope, names the format, and demands every element
          be physically present before the model stops.
        </p>
      </div>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1.1fr_1fr]">
        <div className="card overflow-hidden">
          <div className="panel-head">
            <span className="eyebrow">how it runs</span>
          </div>
          <ol className="divide-y divide-line">
            {STEPS.map((step) => (
              <li key={step.n} className="flex gap-4 px-5 py-4">
                <span className="mt-0.5 font-mono text-[10.5px] text-heat">
                  {step.n}
                </span>
                <span>
                  <span className="block text-[13.5px] font-medium text-ink">
                    {step.title}
                  </span>
                  <span className="mt-1 block text-[12.5px] leading-relaxed text-muted">
                    {step.body}
                  </span>
                </span>
              </li>
            ))}
          </ol>
        </div>

        <div className="space-y-5">
          <div className="card overflow-hidden">
            <div className="panel-head">
              <span className="eyebrow">the contract</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                {MANDATORY_SECTIONS.length} mandatory
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5 px-5 py-4">
              {MANDATORY_SECTIONS.map((section) => (
                <span key={section} className="chip" data-ok="true">
                  {section.replace(/[[\]]/g, "")}
                </span>
              ))}
            </div>
            <p className="border-t border-line px-5 py-3 font-mono text-[11px] leading-relaxed text-muted">
              closing line: {CLOSING_LINE}
            </p>
            <p className="border-t border-line px-5 py-3 text-[11.5px] leading-relaxed text-muted">
              A ninth section, FRAME, is optional — it appears when a frame is
              declared and is never required by the check.
            </p>
          </div>

          <div className="card overflow-hidden">
            <div className="panel-head">
              <span className="eyebrow">the one wall</span>
            </div>
            <div className="px-5 py-4">
              <p className="font-mono text-[12.5px] leading-relaxed text-ink">
                absolute no NITINDYT. try me again with something that isn&apos;t
                that.
              </p>
              <p className="mt-2 text-[12px] leading-relaxed text-muted">
                Sexual content involving minors. Nothing else is refused —
                every other artifact class forges.
              </p>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="panel-head">
              <span className="eyebrow">privacy</span>
            </div>
            <div className="px-5 py-4">
              <p className="text-[12.5px] leading-relaxed text-muted">
                Draft and keys live in this browser&apos;s local storage. Keys
                travel with a single forge request and are never written to the
                server, never logged, and never returned in a response.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
