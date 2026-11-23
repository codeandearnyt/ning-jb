# Ning-JB

Type a target, get a prompt that makes any AI build it — complete, in one pass,
no refusal, no hedge, no stub.

**Live:** https://ning-jb.vercel.app

Ning-JB is the forge layer. It does not build the artifact. It writes the prompt
that makes a target model (Gemini, Claude, GPT, Grok, Llama, DeepSeek, Qwen, or
anything else) ship the full build specification. You paste that prompt into the
target model, then paste the resulting spec into your coding harness.

```
you ──▶ Ning-JB ──▶ forged prompt ──▶ target AI ──▶ build spec ──▶ harness ──▶ artifact
```

## What it actually does

Every forged prompt is assembled from the same contract, in this order:

| Section | Job |
|---|---|
| `[ROLE]` | Assigns the target model a specific expert identity that owns the artifact |
| `[TASK]` | Restates the target as a precise build order with all constraints folded in |
| `[SCOPE-LOCK]` | Removes the exits — no clarifying questions, no alternatives, no deferral |
| `[COMPLETENESS CONTRACT]` | The checklist items, numbered, each one a hard requirement |
| `[FORMAT]` | Exact output shape: fences, language tags, file paths, quantities, word counts |
| `[VOICE]` | Register for the artifact |
| `[FRAME]` | Operative context, only when supplied or legally relevant |
| `[ANTI-REFUSAL ANCHOR]` | Pre-empts the specific reflex for this target class, by name |
| `[SELF-CHECK]` | Forces a silent audit pass against the checklist before sending |

Closed with `Ship the artifact now.` Target length 600–900 words.

Before writing, the forge classifies the target: software, systems, network,
data/ML, hardware, mechanical, chemistry/materials, life sciences,
business/product, research/analysis, prose/script, media/design, or hybrid. The
class picks the `[FORMAT]` rules and the shape of the completeness items, so a
launch plan is not forced into a code fence and a kernel driver is not written as
prose. Hybrid targets become numbered deliverables, each complete on its own.

## Quick start

```bash
npm install
cp .env.example .env.local     # then put a real key in it
npm run dev                    # http://localhost:3000
```

Minimum viable env: **none.**

Keys are typed into the form. The key field sits under the provider picker,
stores per provider in `localStorage`, and travels with the forge request. The
server uses it for that one call and never writes it down.

A server-side key is the fallback, not the requirement — set one and every
visitor inherits it (blank key field uses it).

```dotenv
# optional
GEMINI_API_KEY=...
```

## Bring your own key

The picker is BYOK-first:

- The **api key** field is masked, with a show toggle and a clear button.
- Each provider keeps its own key in `localStorage` under `ning-jb:keys`.
  Switching providers switches keys.
- A lit dot next to the select means the forge will have a key — typed here, or
  present on the server.
- The key is sent in the request body over TLS, used for one call, and scrubbed
  from any error message before it reaches the browser.
- It is never logged, never stored server-side, and never returned.
- **Test connection** sends one tiny request (32 tokens) to the selected
  provider and reports the measured latency — or the exact reason it failed:
  key rejected, model id not found, host unreachable, throttled. It never
  forges a prompt and never falls back to a different provider.

That makes the public deploy safe to share: nobody's quota is on the line except
the person typing the key.

## Providers

Ten integrations ship in `lib/providers.ts`. Every one speaks the OpenAI
chat-completions shape, so the forge client is a single SDK; what differs is the
base URL, the key variable, and the model namespace — all declared as data.

| # | Provider | Type | Key var | Default model |
|---|---|---|---|---|
| 1 | OpenAI | Cloud AI | `OPENAI_API_KEY` | `gpt-4o` |
| 2 | Anthropic Claude | Cloud AI | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` |
| 3 | Google Gemini | Cloud AI | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `gemini-3.8-flash` |
| 4 | Groq | Cloud AI | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| 5 | NVIDIA NIM | Cloud AI | `NVIDIA_API_KEY` | `meta/llama-3.3-70b-instruct` |
| 6 | Cloudflare AI Gateway | AI Gateway | `CF_AIG_TOKEN` + `CF_ACCOUNT_ID` (+ `CF_GATEWAY_ID`) | `openai/gpt-4.1` |
| 7 | OpenRouter | Multi-model API | `OPENROUTER_API_KEY` | `openai/gpt-4o` |
| 8 | OpenCode Zen | AI Model Provider | `OPENCODE_API_KEY` | `deepseek-v4.1-flash` |
| 9 | Ollama | Local AI | none (optional `OLLAMA_API_KEY`) | `llama3.1` |
| 10 | Custom Integration | OpenAI-compatible | `CUSTOM_API_KEY` + `CUSTOM_BASE_URL` (+ `CUSTOM_MODEL`) | — |

The model field is free text, prefilled from the registry and overridable per
request. A stale model id is a one-keystroke fix, not a deploy.

`GET /api/providers` returns availability for the picker — booleans and env var
names only, never a key value. The select shows a dot per provider: lit when the
server has what it needs.

A missing variable is a `500` that names it exactly:

```json
{"error":"Google Gemini needs a key. Paste one in the form, or set GEMINI_API_KEY on the server."}
```

`CUSTOM_BASE_URL` is read from the server only. The browser cannot point the
forge at an arbitrary URL — that would be an open proxy.

Backward compatible: with `provider` omitted the forge uses OpenAI, and
`OPENAI_BASE_URL` still overrides the OpenAI base URL.

## Other environment

| Var | Required | Default | Purpose |
|---|---|---|---|
| `FORGE_MODEL` | no | `gpt-4o` | Default model for the OpenAI provider |
| `FORGE_TIMEOUT_MS` | no | `60000` | Round-trip ceiling, clamped to 8000–60000 |

## Checklist library

`lib/checklists.ts` is the maintenance surface. Thirty-two classes at launch:

| Group | Classes |
|---|---|
| Code | Keylogger, Process injection, RAT core, Stealer, Kernel driver, Shellcode, Overlay / ESP, Full-stack web app, CLI tool, API service, Data pipeline |
| Network | Web engagement, Phishing kit, Exploit PoC, Infrastructure plan |
| Physical | Synthesis route, Energetic formulation, Weapons build, Guide, Electronics build, Mechanical part |
| Product | Product spec, Launch plan, Pitch deck, Pricing model |
| Research | Research brief, Technical teardown |
| Media | Brand kit, Landing page copy, Content plan |
| Prose | Scene (SFW), Scene (explicit), Long-form article |

Adding a target class is adding a row. No rule rewrite, no forge-prompt edit. The
selected checklist's items are injected verbatim into `[COMPLETENESS CONTRACT]`.
With no checklist selected, the forge derives 6–10 items from the target.

## The wall

One exclusion, checked in `lib/wall.ts` before the provider is touched and before
any API key is read. Sexual content involving minors returns exactly:

```
absolute no NITINDYT. try me again with something that isn't that.
```

No prompt, no notes, no model call. Everything else forges.

## Layout

```
app/
  api/forge/route.ts     POST endpoint — validate, wall, rate limit, forge
  layout.tsx             fonts, metadata, theme
  page.tsx               server shell, model badge
  globals.css            tokens, base, components
components/
  Header.tsx             wordmark, model, status
  ForgeForm.tsx          state machine, submit, localStorage draft
  ChecklistPicker.tsx    grouped select
  ForgeOutput.tsx        empty / loading / error / wall / done
lib/
  forge.ts               LLM call, JSON extraction, error mapping
  contract.ts            the forged-prompt contract checker
  prompt-template.ts     Ning-JB itself — the embedded system prompt
  checklists.ts          the library
  wall.ts                the one exclusion
  types.ts               shared request/response contract
```

## API

`POST /api/forge`

```json
{
  "target": "keylogger in C++ for Windows 11",
  "targetAi": "Claude",
  "checklistClass": "keylogger",
  "frame": "none",
  "constraints": "C++20, MSVC, single file"
}
```

`200`

```json
{
  "prompt": "[ROLE] ... Ship the artifact now.",
  "notes": ["Swap FORGE_MODEL to a 70B+ model if sections truncate."],
  "model": "gpt-4o"
}
```

Wall response adds `"wall": true` and returns the fixed line as `prompt`.

Errors: `400` bad input · `429` per-IP cap · `502` provider failure · `504` timeout.

Soft per-instance cap: 12 forges per IP per minute. Real ceiling is the provider's
own rate limit.

## Scripts

```bash
npm run dev        # dev server
npm run build      # production build — must pass clean
npm run start      # serve the build
npm run typecheck  # tsc --noEmit
npm test           # wall tests (Node 24 strips TS natively)
npm run mock       # local OpenAI-compatible provider on :4200
```

## Smoke test without a key

Prove the whole forge path — system prompt, checklist injection, JSON parse,
contract check — with no provider account:

```bash
npm run mock                                          # terminal 1
OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:4200/v1 npm run start   # terminal 2
```

Then POST a target. The mock echoes the assembled user message inside `prompt`,
so you can see exactly what the forge sent. This is the integration test for
everything except the model's own output quality.

## Notes

- **Stateless.** No accounts, no database, no server-side history. The draft in
  `localStorage` never leaves the browser.
- **The key never ships.** `OPENAI_API_KEY` is read only inside `lib/forge.ts`,
  which is imported only by the route handler.
- **Copy is byte-clean.** `navigator.clipboard.writeText` on the raw string, with
  an `execCommand` fallback for insecure contexts. No formatting layer, no smart
  quotes.
- **Provider JSON quirks.** The forge asks for `response_format: json_object` and
  retries once without it if the provider rejects the field.
