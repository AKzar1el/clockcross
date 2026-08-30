const MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const MAX_BODY_CHARS = 12000;
const MAX_INPUT_CHARS = 7000;
const ALLOWED_ROLES = new Set(["system", "user"]);
const ACTIONS = new Set(["continuation", "reversion", "abstain"]);
const DRIVERS = new Set([
  "crypto_cross_market",
  "company_specific",
  "macro",
  "unclear",
]);

const DECISION_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    action: {
      type: "string",
      enum: ["continuation", "reversion", "abstain"],
    },
    confidence: { type: "number", minimum: 0, maximum: 1 },
    idiosyncratic_news_detected: { type: "boolean" },
    driver: {
      type: "string",
      enum: [
        "crypto_cross_market",
        "company_specific",
        "macro",
        "unclear",
      ],
    },
    reason: { type: "string", maxLength: 400 },
  },
  required: [
    "action",
    "confidence",
    "idiosyncratic_news_detected",
    "driver",
    "reason",
  ],
};

function response(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-content-type-options": "nosniff",
    },
  });
}

function error(status, code) {
  return response({ error: { code } }, status);
}

function validDecision(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value).sort();
  const expected = [
    "action",
    "confidence",
    "driver",
    "idiosyncratic_news_detected",
    "reason",
  ].sort();
  if (JSON.stringify(keys) !== JSON.stringify(expected)) return false;
  if (!ACTIONS.has(value.action)) return false;
  if (!DRIVERS.has(value.driver)) return false;
  if (
    typeof value.confidence !== "number" ||
    !Number.isFinite(value.confidence) ||
    value.confidence < 0 ||
    value.confidence > 1
  ) {
    return false;
  }
  if (typeof value.idiosyncratic_news_detected !== "boolean") return false;
  if (
    typeof value.reason !== "string" ||
    value.reason.length === 0 ||
    value.reason.length > 400
  ) {
    return false;
  }
  return true;
}

function validateMessages(messages) {
  if (!Array.isArray(messages) || messages.length < 1 || messages.length > 4) {
    return null;
  }
  let total = 0;
  const normalized = [];
  for (const message of messages) {
    if (!message || typeof message !== "object") return null;
    if (!ALLOWED_ROLES.has(message.role) || typeof message.content !== "string") {
      return null;
    }
    const content = message.content.trim();
    if (!content) return null;
    total += content.length;
    if (total > MAX_INPUT_CHARS) return null;
    normalized.push({ role: message.role, content });
  }
  return normalized;
}

function extractDecision(result) {
  const responseText = typeof result?.response === "string" ? result.response : "";
  const choiceText =
    result?.choices?.[0]?.message?.content ?? result?.choices?.[0]?.text ?? "";
  const candidate = responseText || choiceText;
  if (candidate && typeof candidate === "object") return candidate;
  if (typeof candidate !== "string" || candidate.length > 3000) return null;
  try {
    return JSON.parse(candidate);
  } catch {
    return null;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/health") {
      return response({ ok: true, provider: "cloudflare-workers-ai" });
    }

    if (request.method !== "POST" || url.pathname !== "/v1/chat/completions") {
      return error(404, "not_found");
    }

    if (
      typeof env.CLOCKCROSS_AI_AUTH !== "string" ||
      !env.CLOCKCROSS_AI_AUTH ||
      request.headers.get("Authorization") !== `Bearer ${env.CLOCKCROSS_AI_AUTH}`
    ) {
      return error(401, "unauthorized");
    }

    let raw;
    try {
      raw = await request.text();
    } catch {
      return error(400, "invalid_body");
    }
    if (!raw || raw.length > MAX_BODY_CHARS) {
      return error(413, "body_too_large");
    }

    let body;
    try {
      body = JSON.parse(raw);
    } catch {
      return error(400, "invalid_json");
    }
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return error(400, "invalid_request");
    }

    const messages = validateMessages(body.messages);
    if (!messages) {
      return error(400, "invalid_messages");
    }

    let result;
    try {
      result = await env.AI.run(MODEL, {
        messages,
        response_format: {
          type: "json_schema",
          json_schema: DECISION_SCHEMA,
        },
        temperature: 0,
        max_tokens: 220,
      });
    } catch {
      return error(502, "provider_failure");
    }

    const decision = extractDecision(result);
    if (!validDecision(decision)) {
      return error(502, "invalid_provider_response");
    }

    return response({
      id: crypto.randomUUID(),
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: MODEL,
      choices: [
        {
          index: 0,
          message: {
            role: "assistant",
            content: JSON.stringify(decision),
          },
          finish_reason: "stop",
        },
      ],
    });
  },
};
