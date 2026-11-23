# Design — Ning-JB

Locked direction. One page, one theme, one accent.

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

Background carries three radial washes (pink at 5–7% alpha: top-left, top-right,
bottom centre) and a fixed 72px hairline grid at 55% of `--line`, masked to fade
from the top. The grid is a `pointer-events-none` fixed pseudo-element — it never
repaints on scroll.

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

## Layout

Single page. Sticky 56px header, then a 12-column grid at `lg`:

- form — 5 columns
- output — 7 columns, `self-start` so a short card does not stretch

Below `lg` both stack full width, output first in reading order after submit.
The output panel scrolls internally at `62vh` so the page never grows with the
prompt.

## Motion

Three moves, all CSS:

1. Output panel entrance — 260ms fade + 6px rise (`animate-forgeIn`).
2. Loading heat sweep — 1.4s gradient bar across the skeleton.
3. Status dot pulse — 2.4s, header only.

Every one collapses under `prefers-reduced-motion: reduce`. No scroll listeners,
no parallax, no infinite decoration.

## States

- **Empty** — dashed panel, three numbered steps.
- **Loading** — twelve-line skeleton at varied widths plus the heat sweep.
- **Error** — red-tinted panel, mono message, no illustration.
- **Wall** — plain panel, one line, no code chrome, no notes.
- **Done** — header with word count + model, copy button, `<pre>`, numbered notes.

## Copy rules

Functional only. No "unleash", no "supercharge", no emoji. Sentence case in body,
uppercase mono in labels. Button says `forge the prompt` — one line at every width.
