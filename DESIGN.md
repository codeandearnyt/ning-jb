# Design — Ning-JB

Locked direction. One page, one theme, one accent.

## Read

A working tool for technical builders, not a marketing site. The metaphor is a
forge: cold shop, hot metal, work orders going out. The interface should feel
like a machine with screws in it, not a landing page.

**Dials:** variance 6 / motion 3 / density 6.

## Palette (dark, locked)

| Token | Value | Use |
|---|---|---|
| `--bg` | `9 9 11` (zinc-950) | page |
| `--panel` | `17 17 19` | panels, inputs |
| `--panel2` | `24 24 27` | raised rows |
| `--line` | `39 39 42` | hairlines, borders |
| `--ink` | `244 244 245` | primary text |
| `--muted` | `138 138 148` | labels, hints |
| `--heat` | `245 158 11` (amber-500) | accent, primary action |
| `--hot` | `249 115 22` (orange-500) | gradient end |
| `--danger` | `248 113 113` | error panel only |

Single accent. No purple, no glass, no glow. The only gradient on the page is
the primary button, which runs amber → orange: heat.

Background carries two radial washes (amber at the bottom, orange top-right) and
a fixed 72px hairline grid at 16% opacity, masked to fade from the top. The grid
is a `pointer-events-none` fixed pseudo-element — it never repaints on scroll.

**Theme is locked dark.** This is a shop at night. There is no light mode and
there will not be one; a mid-page theme flip would break the read.

## Type

- Display + UI: **Geist Sans** (`geist/font/sans`, self-hosted, no network at build)
- Labels, data, output, all numbers: **Geist Mono** (`geist/font/mono`)

Scale: 28/34 h1, 14 body, 13 output, 12.5 pre, 10.5 labels. Labels are uppercase
mono at `tracking-[0.18em]`. The mono/sans split does the work — no display serif,
no decorative faces.

## Geometry

Radius scale is **all-sharp**: 2px default, 3px max. No pills, no 12px cards.
Borders are 1px `--line`. Elevation is expressed by background step
(`bg` → `panel` → `panel2`), never by drop shadows.

## Layout

Single page. Sticky 56px header, then a 12-column grid at `lg`:

- form — 5 columns
- output — 7 columns

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
