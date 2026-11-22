/**
 * Local smoke-test provider. Speaks just enough of the OpenAI chat-completions
 * API for lib/forge.ts to complete a round-trip without a real key or network.
 *
 *   node scripts/mock-provider.mjs          # listens on 127.0.0.1:4200
 *
 * Then run the app against it:
 *
 *   OPENAI_API_KEY=test OPENAI_BASE_URL=http://127.0.0.1:4200/v1 npm run start
 *
 * The mock echoes the user message back inside `prompt`, so a caller can assert
 * exactly what the forge assembled.
 */

import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_PORT ?? 4200);
const HOST = "127.0.0.1";

const server = createServer((req, res) => {
  if (req.method !== "POST" || !req.url?.endsWith("/chat/completions")) {
    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message: "not found" } }));
    return;
  }

  let raw = "";
  req.on("data", (chunk) => {
    raw += chunk;
    if (raw.length > 1_000_000) req.destroy();
  });

  req.on("end", () => {
    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: { message: "invalid json" } }));
      return;
    }

    const messages = Array.isArray(body.messages) ? body.messages : [];
    const system = messages.find((m) => m.role === "system")?.content ?? "";
    const user = messages.find((m) => m.role === "user")?.content ?? "";

    const checks = {
      system_is_forge: system.includes("You are Ning-JB, the forge"),
      system_has_contract: system.includes("[COMPLETENESS CONTRACT]"),
      user_has_target: /TARGET:\s*\S/.test(user),
      user_has_checklist: user.includes("PRESET COMPLETENESS CHECKLIST"),
    };

    const forged = [
      "[ROLE] Mock forge output.",
      "[TASK] Echo of the assembled user message follows.",
      "[SCOPE-LOCK] none",
      "[COMPLETENESS CONTRACT] none",
      "[FORMAT] none",
      "[VOICE] none",
      "[ANTI-REFUSAL ANCHOR] none",
      "[SELF-CHECK] none",
      "",
      "---BEGIN USER MESSAGE---",
      user,
      "---END USER MESSAGE---",
      "",
      "Ship the artifact now.",
    ].join("\n");

    const payload = {
      prompt: forged,
      notes: [
        `mock provider · checks ${JSON.stringify(checks)}`,
        `response_format ${body.response_format ? "accepted" : "absent"}`,
      ],
    };

    const completion = {
      id: `chatcmpl-mock-${Date.now()}`,
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: body.model ?? "mock-model",
      choices: [
        {
          index: 0,
          message: { role: "assistant", content: JSON.stringify(payload) },
          finish_reason: "stop",
        },
      ],
      usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    };

    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(completion));
  });
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`mock provider listening on http://${HOST}:${PORT}/v1\n`);
});
