# Design — Ning-JB

Locked direction. One shell, one theme, one accent.

## Read

A working tool for technical builders, not a marketing site. The metaphor is a
forge, but the surface is paper: a clean instrument on a white bench, pink ink
where the heat is. Professional, quiet, exact — the interface should feel like a
machine with screws in it, not a landing page.

**Dials:** variance 5 / motion 3 / density 6.

## Palette (light, locked)

| Token | Value | Use |
|---|---|---|
| `--bg` | `255 255 255` | page |
| `--panel` | `255 255 255` | cards, inputs |
| `--panel2` | `253 246 249` | card headers, inset surfaces |
| `--line` | `236 219 227` | hairlines, borders |
| `--ink` | `26 16 22` | primary text |
| `--muted` | `107 88 99` | labels, hints, notes |
| `--heat` | `190 24 93` (pink-700) | accent, primary action, eyebrows |
| `--hot` | `219 39 119` (pink-600) | gradient end |
| `--danger` | `185 28 28` | error panel only |
| `--good` | `4 120 87` | probe success, ready dot |

Single accent. No purple, no glass, no glow. The only gradient on the page is the
primary button, which runs pink-700 → pink-600 with white text (6.0:1 at the
darker end, 5.1:1 at the lighter end).

**Contrast rule.** Every text token clears 4.5:1 on white, measured: ink 18.6,
muted 6.6, heat 6.0, danger 6.5, good 5.5. Hierarchy comes from size, weight and
tracking — never from opacity modifiers like `text-muted/60`, which fail on a
light ground.

Background is **flat pink paper** — `--panel2` across the whole page, white
cards on top. No gradient, no grid, no grain. Every masked wash tried here left a
visible seam where the mask terminated, and a seam reads as a bug. Surface
contrast alone carries the hierarchy: pink paper, white card, pink-tinted card
head.

The `--pink-50…800` ramp exists for surfaces only — card heads, chips, the
selected provider tile, the button. Text never uses it; text is `ink`, `muted`,
or `heat`.

**Theme is locked light.** Paper, not shop-at-night. There is no dark mode and
there will not be one; a mid-page theme flip would break the read.

## Type

- Display + UI: **Geist Sans** (`geist/font/sans`, self-hosted, no network at build)
- Labels, data, output, all numbers: **Geist Mono** (`geist/font/mono`)

Scale: 32/44 h1, 15 body, 13 output, 12.5 pre, 10.5 labels. Labels are uppercase
mono at `tracking-[0.18em]` in `--muted`; card eyebrows are the same size in
`--heat` at `tracking-[0.2em]`. The mono/sans split does the work — no display
serif, no decorative faces.

## Geometry

Radius scale is **soft-sharp**: 6px controls, 8px default, 14px cards. Borders
are 1px `--line`. Elevation is one shadow token (`shadow-card`): a 2px contact
shadow plus a wide, very low-alpha pink ambient shadow. No second elevation step.

## Layout — app shell, not a page

The surface is a **tool with tabs**, not a document that scrolls. Sticky 64px
header: logo mark, pill tab bar, live status chip. Four tabs, one at a time:

- **forge** — a four-step wizard (`target → shape → engine → run`) inside one
  card. A segmented rail above the card fills as steps are reached. Each step
  holds one question. The last step is a review table of everything selected,
  plus the key-missing warning.
- **output** — the forged prompt as a document. Card head and contract scorecard
  are `sticky top-16`; the document scrolls with the page beneath them.
- **keys** — provider chip grid (two columns, monogram tiles, status dot per
  provider) beside the key, model, and connection probe for the selected one.
- **about** — contract, the one wall, privacy.

Tab state, form state, keys, and output all live in one client component so a
tab switch never loses work. The URL hash mirrors the tab (`#keys`) so a tab is
linkable and survives a reload.

Content column is `max-w-[1120px]`; the shell is `max-w-[1400px]`. Below `sm` the
wordmark drops to the mark alone so all four tabs fit at 390px without clipping.

There is no nested scroll pane anywhere. A card that scrolls inside a page that
scrolls traps the wheel.

## Motion

One easing token, `--ease-forge: cubic-bezier(0.16, 1, 0.3, 1)`. Three durations:
160ms for state changes on hover/press, 240ms for entrances, 420ms for the wizard
rail. Transform and opacity only — nothing animates layout, colour, or a filter.

Moves, all via `motion` (`motion/react`):

1. **Tab switch** — `AnimatePresence mode="wait"`, 180ms fade plus a 6px slide.
2. **Tab pill** — one shared element (`layoutId="tab-pill"`) sliding between tabs
   on a spring (stiffness 380, damping 32). One animation instead of four.
3. **Wizard step** — 180ms fade plus an 8px horizontal slide in the direction of
   travel.
4. **Rail fill** — width animates 420ms as each step is reached.
5. **Section stagger** — document sections rise 5px, 30ms apart, capped at 240ms
   total so a long prompt never feels slow.
6. **Copy morph** — the button label swaps `copy prompt ↔ ✓ copied` on a 160ms
   fade.

Every one is guarded twice: `useReducedMotion()` skips the animation at the
component, and a global `@media (prefers-reduced-motion: reduce)` block zeroes
animation and transition durations as a backstop. No scroll listeners, no
parallax, no infinite decoration.

## States

- **Empty output** — the live contract sketch: every section the forge will fill,
  assembled client-side from the target as you type. Headed `9 sections · shape
  only` so it is never mistaken for a forge.
- **Loading** — twelve-line skeleton at varied widths plus the heat sweep.
- **Error** — red-tinted panel, mono message, no illustration.
- **Wall** — plain panel, one line, no code chrome, no notes.
- **Done** — sticky header with word count and model, contract scorecard (one chip
  per mandatory section, plus `n/8` and a `repaired` flag), the prompt parsed into
  document sections, then numbered notes.
- **Missing** — when the contract check found gaps, a `missing: …` line in
  `--danger` sits under the scorecard rather than replacing it. A repaired prompt
  still shows what was repaired.

## Copy rules

Functional only. No "unleash", no "supercharge", no emoji. Sentence case in body,
uppercase mono in labels. Button says `forge the prompt` — one line at every width.
