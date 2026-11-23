/**
 * The forged-prompt contract, checked after the round-trip.
 *
 * Kept free of imports so it can be unit-tested directly with Node's native
 * TypeScript stripping — no bundler, no path aliases.
 */

/** Sections that must survive the round-trip. [FRAME] is optional by design. */
export const MANDATORY_SECTIONS = [
  "[ROLE]",
  "[TASK]",
  "[SCOPE-LOCK]",
  "[COMPLETENESS CONTRACT]",
  "[FORMAT]",
  "[VOICE]",
  "[ANTI-REFUSAL ANCHOR]",
  "[SELF-CHECK]",
] as const;

export const CLOSING_LINE = "Ship the artifact now.";

/** The contract's stated floor. Below this the forge re-asks once. */
export const MIN_WORDS = 550;

/** Sections the prompt actually carries, in contract order. For the UI. */
export function presentSections(prompt: string): string[] {
  return MANDATORY_SECTIONS.filter((s) => prompt.includes(s));
}

/** Returns the contract pieces the forged prompt is missing, in order. */
export function missingContract(prompt: string): string[] {
  const missing: string[] = MANDATORY_SECTIONS.filter((s) => !prompt.includes(s));

  // Order matters: each section must appear after the previous one.
  let cursor = -1;
  for (const section of MANDATORY_SECTIONS) {
    const at = prompt.indexOf(section, cursor + 1);
    if (at === -1) {
      if (!missing.includes(section)) missing.push(`${section} (out of order)`);
      break;
    }
    cursor = at;
  }

  if (!prompt.trimEnd().endsWith(CLOSING_LINE)) {
    missing.push(`closing line "${CLOSING_LINE}"`);
  }

  // Terse models satisfy the sections and stop early. The contract asks for
  // 600-900 words; below the floor the prompt is thin, so it gets one re-ask.
  const words = prompt.split(/\s+/).filter(Boolean).length;
  if (words < MIN_WORDS) {
    missing.push(`length (${words} words, target 600-900)`);
  }

  return missing;
}
