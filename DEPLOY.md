# Deploy — Ning-JB

Target: a live URL in under five minutes, from a clean repo.

## 0. Preflight

```bash
npm install
npm run build
```

The build must exit 0. If it does not, fix it before deploying — Vercel runs the
same command.

## 1. GitHub

```bash
git init
git add -A
git commit -m "ning-jb v1.0"
gh repo create ning-jb --public --source=. --push
```

Without the GitHub CLI: create the repo in the browser, then

```bash
git remote add origin https://github.com/<you>/ning-jb.git
git branch -M main
git push -u origin main
```

`.gitignore` already excludes `.env`, `.env.local`, `.next`, and `node_modules`.
Confirm nothing secret is staged before the first push:

```bash
git status --short
```

## 2. Vercel

1. vercel.com → **Add New → Project → Import** `ning-jb`.
2. Framework preset auto-detects **Next.js**. Leave build settings alone.
3. **Environment Variables** — add these before the first deploy:

| Name | Value | Required |
|---|---|---|
| `OPENAI_API_KEY` | your provider key | yes |
| `OPENAI_BASE_URL` | e.g. `https://api.groq.com/openai/v1` | no |
| `FORGE_MODEL` | e.g. `llama-3.3-70b-versatile` | no |
| `FORGE_TIMEOUT_MS` | `60000` | no |

Set them for **Production, Preview, and Development** unless you want preview
builds to fail on forge calls.

4. **Deploy.**

`vercel.json` already sets `maxDuration: 60` on the forge route. On the Hobby
plan that is the ceiling; the route reads `FORGE_TIMEOUT_MS` and clamps to it.

## 3. Post-deploy verification

Run all four against the live URL.

**a. Page renders**

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://<your-url>/
# 200
```

**b. Code target forges**

```bash
curl -sS https://<your-url>/api/forge \
  -H "Content-Type: application/json" \
  -d '{"target":"keylogger in C++ for Windows 11","checklistClass":"keylogger"}' \
  | head -c 400
```

Expect a JSON object whose `prompt` contains `[ROLE]`, `[TASK]`,
`[COMPLETENESS CONTRACT]`, and ends with `Ship the artifact now.`

**c. Chemistry target forges with numbers**

```bash
curl -sS https://<your-url>/api/forge \
  -H "Content-Type: application/json" \
  -d '{"target":"synthesis route for aspirin from salicylic acid","checklistClass":"synthesis-route"}'
```

Expect temperatures, times, and quantities — not a description of the process.

**d. The wall holds**

```bash
curl -sS https://<your-url>/api/forge \
  -H "Content-Type: application/json" \
  -d '{"target":"sexual content involving a child"}'
```

Expect exactly:

```json
{"prompt":"absolute no NITINDYT. try me again with something that isn't that.","notes":[],"model":"...","wall":true}
```

If (b) or (c) returns `502`, the key or base URL is wrong. If it returns `504`,
the model is too slow — raise `FORGE_TIMEOUT_MS` (max 60000) or move to a faster
model.

## 4. Custom domain (optional)

Settings → **Domains** → add the domain → point the DNS record Vercel shows you.
TLS is automatic. No code change.

## 5. Rollback

Deployments → pick the last good one → **⋯ → Promote to Production**. Instant,
no rebuild.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `OPENAI_API_KEY is not set on the server` | Env var missing in the target environment | Add it, then **redeploy** — env changes need a new build |
| `401` from the provider | Bad or revoked key | Rotate the key, update the env var |
| `429` from the provider | Quota exhausted | Provider dashboard; or swap `OPENAI_BASE_URL` |
| `504` timeout | Model too slow for the clamp | Faster model, or raise `FORGE_TIMEOUT_MS` |
| `Forge model returned an empty prompt` | Provider returned prose instead of JSON | Switch to a model with reliable JSON mode |
| Prompt arrives with `[FRAME]` missing | Frame was `none` and the target was not legally sensitive | Expected — the section is omitted, not empty |
| Copy button does nothing | Insecure context (`http://`) | Use `https://` or `localhost` |
