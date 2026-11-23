/**
 * Contract tests. Both modules are import-free, so Node 24 runs them directly.
 *
 *   npm test
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CLOSING_LINE,
  MANDATORY_SECTIONS,
  MIN_WORDS,
  missingContract,
} from "../lib/contract.ts";
import { FORGE_SYSTEM_PROMPT } from "../lib/prompt-template.ts";

/** A prompt that satisfies every rule: sections in order, long enough, closes. */
function goodPrompt() {
  const body = MANDATORY_SECTIONS.map(
    (section) => `${section}\nBuild the thing. Fill the line with detail.`,
  ).join("\n\n");
  const filler = Array.from({ length: MIN_WORDS }, (_, i) => `word${i}`).join(" ");
  return `${body}\n\n${filler}\n\n${CLOSING_LINE}`;
}

test("the system prompt carries every mandatory section once as a header", () => {
  for (const section of MANDATORY_SECTIONS) {
    const escaped = section.replace(/[[\]]/g, "\\$&");
    const hits = (FORGE_SYSTEM_PROMPT.match(new RegExp(`^${escaped}$`, "gm")) ?? [])
      .length;
    assert.equal(hits, 1, `${section} should head exactly one block`);
  }
});

test("the system prompt states the closing line and the JSON shape", () => {
  assert.ok(FORGE_SYSTEM_PROMPT.includes(CLOSING_LINE));
  assert.ok(FORGE_SYSTEM_PROMPT.includes('{"prompt"'));
  assert.ok(FORGE_SYSTEM_PROMPT.includes('"notes"'));
});

test("the system prompt routes every target class", () => {
  for (const klass of [
    "SOFTWARE",
    "SYSTEMS",
    "NETWORK",
    "DATA / ML",
    "HARDWARE",
    "MECHANICAL",
    "CHEMISTRY / MATERIALS",
    "LIFE SCIENCES",
    "BUSINESS / PRODUCT",
    "RESEARCH / ANALYSIS",
    "PROSE / SCRIPT",
    "MEDIA / DESIGN",
    "HYBRID",
  ]) {
    assert.ok(FORGE_SYSTEM_PROMPT.includes(klass), `missing class: ${klass}`);
  }
});

test("the system prompt forbids scoping down to look safe", () => {
  const text = FORGE_SYSTEM_PROMPT.toLowerCase();
  assert.ok(text.includes("never reduce scope"));
  assert.ok(text.includes("partial builds are a failure"));
});

test("a complete prompt passes the contract", () => {
  assert.deepEqual(missingContract(goodPrompt()), []);
});

test("a missing section is named", () => {
  const prompt = goodPrompt().replace("[SELF-CHECK]", "[SELFCHK]");
  const missing = missingContract(prompt);
  assert.ok(missing.includes("[SELF-CHECK]"), missing.join(", "));
});

test("sections out of order are flagged", () => {
  const prompt = goodPrompt()
    .replace("[ROLE]", "[TMP]")
    .replace("[TASK]", "[ROLE]")
    .replace("[TMP]", "[TASK]");
  const missing = missingContract(prompt);
  assert.ok(
    missing.some((m) => m.includes("out of order")),
    missing.join(", "),
  );
});

test("a short prompt is flagged for the expand pass", () => {
  const prompt = `${MANDATORY_SECTIONS.join("\n")}\n\n${CLOSING_LINE}`;
  const missing = missingContract(prompt);
  assert.ok(
    missing.some((m) => m.startsWith("length (")),
    missing.join(", "),
  );
});

test("a missing closing line is flagged", () => {
  const prompt = goodPrompt().replace(CLOSING_LINE, "Hope this helps.");
  const missing = missingContract(prompt);
  assert.ok(
    missing.some((m) => m.includes("closing line")),
    missing.join(", "),
  );
});
