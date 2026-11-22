/**
 * The wall. One exclusion, checked before any model call.
 *
 * Two stages:
 *   1. An unambiguous term is the wall on its own.
 *   2. A minor signal (word, phrase, or a parsed age under 18) plus a sexual
 *      signal in the same target is the wall.
 *
 * Matching is word-boundary based on purpose. "canteen" must not match "teen",
 * "minority" must not match "minor", "17th century" must not parse as age 17.
 * Everything outside the wall forges.
 */

const HARD_PHRASES = [
  "child porn",
  "childporn",
  "child erotica",
  "child erotica",
  "csam",
  "lolicon",
  "shotacon",
  "preteen sex",
  "underage sex",
  "underage nude",
  "minor sex",
  "cp link",
  "pedo",
  "paedo",
  "pedophile",
  "paedophile",
  "loli",
  "shota",
];

/** Unambiguous minor nouns. Matched as whole words. */
const MINOR_WORDS = [
  "child",
  "children",
  "kid",
  "kids",
  "minor",
  "minors",
  "underage",
  "preteen",
  "toddler",
  "infant",
  "schoolgirl",
  "schoolboy",
  "teen",
  "teens",
  "teenage",
  "teenager",
  "teenagers",
];

const MINOR_PHRASES = ["middle school", "elementary school", "under age"];

/** Whole words. */
const SEXUAL_WORDS = [
  "sex",
  "sexy",
  "fuck",
  "fucking",
  "cock",
  "pussy",
  "cunt",
  "dick",
  "penis",
  "vagina",
  "cum",
  "orgasm",
  "nude",
  "naked",
  "nsfw",
  "blowjob",
  "handjob",
  "anal",
  "oral",
  "breasts",
  "nipples",
  "genitals",
  "incest",
  "rape",
  "molest",
  "grope",
  "fondle",
  "orgy",
  "fetish",
  "lewd",
  "smut",
  "porn",
  "erotic",
  "erotica",
  "explicit",
  "hentai",
  "dubcon",
  "noncon",
];

/** Prefix stems — matched at a word start, so inflections hit. */
const SEXUAL_STEMS = [
  "sexual",
  "arous",
  "horny",
  "penetrat",
  "masturbat",
  "impregnat",
  "fingering",
  "threesome",
  "breeding",
  "dub-con",
  "non-con",
  "erotic",
  "seduct",
];

const AGE_PATTERNS = [
  /\b(\d{1,2})[\s-]*(?:years?|yrs?)[\s-]*olds?\b/gi,
  /\b(\d{1,2})[\s-]*(?:yo|y\/o)\b/gi,
  /\baged?[\s-]*(\d{1,2})\b/gi,
];

function normalise(input: string): string {
  return input.toLowerCase().replace(/\s+/g, " ").trim();
}

function escapeRe(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function wordHit(hay: string, word: string): boolean {
  return new RegExp(`\\b${escapeRe(word)}\\b`, "i").test(hay);
}

function stemHit(hay: string, stem: string): boolean {
  return new RegExp(`\\b${escapeRe(stem)}`, "i").test(hay);
}

function phraseHit(hay: string, phrase: string): boolean {
  return hay.includes(phrase);
}

/** True when any stated age is under 18. "17th century" does not parse. */
function hasMinorAge(hay: string): boolean {
  for (const pattern of AGE_PATTERNS) {
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(hay)) !== null) {
      const age = Number(match[1]);
      if (Number.isFinite(age) && age >= 1 && age <= 17) return true;
    }
  }
  return false;
}

export function hasMinorSignal(hay: string): boolean {
  if (MINOR_WORDS.some((w) => wordHit(hay, w))) return true;
  if (MINOR_PHRASES.some((p) => phraseHit(hay, p))) return true;
  return hasMinorAge(hay);
}

export function hasSexualSignal(hay: string): boolean {
  if (SEXUAL_WORDS.some((w) => wordHit(hay, w))) return true;
  return SEXUAL_STEMS.some((s) => stemHit(hay, s));
}

/** True when the target crosses the one wall. */
export function crossesWall(target: string): boolean {
  if (!target.trim()) return false;
  const hay = normalise(target);

  if (HARD_PHRASES.some((p) => phraseHit(hay, p))) return true;

  return hasMinorSignal(hay) && hasSexualSignal(hay);
}
