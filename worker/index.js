// 알림 구독 보관소 (Cloudflare Worker + KV)
//
// 환경 변수(Worker Secrets): REGISTER_CODE, ADMIN_TOKEN
// 환경 변수(vars): ALLOWED_ORIGIN  예) https://<user>.github.io
// KV 바인딩: SUBS
//
// POST   /subscribe            {code, subscription, ua}  (앱에서 호출)
// GET    /subscriptions        Bearer ADMIN_TOKEN        (GitHub Actions)
// DELETE /subscriptions/:id    Bearer ADMIN_TOKEN

const MAX_SUBS = 20;

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
    "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Max-Age": "86400",
  };
}

function json(env, data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...cors(env) },
  });
}

// 길이가 달라도 시간 차이가 나지 않게 비교
function safeEqual(a, b) {
  a = String(a || ""); b = String(b || "");
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0 && a.length > 0;
}

async function idFor(endpoint) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return [...new Uint8Array(buf)].slice(0, 12).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function validSubscription(s) {
  return s && typeof s.endpoint === "string" && s.endpoint.startsWith("https://") && s.endpoint.length < 1000
    && s.keys && typeof s.keys.p256dh === "string" && typeof s.keys.auth === "string";
}

function isAdmin(req, env) {
  const h = req.headers.get("Authorization") || "";
  return safeEqual(h.replace(/^Bearer\s+/i, ""), env.ADMIN_TOKEN);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env) });

    if (req.method === "POST" && url.pathname === "/subscribe") {
      let body;
      try { body = await req.json(); } catch { return json(env, { error: "bad json" }, 400); }
      if (!safeEqual(body.code, env.REGISTER_CODE)) return json(env, { error: "forbidden" }, 403);
      if (!validSubscription(body.subscription)) return json(env, { error: "bad subscription" }, 400);
      const id = await idFor(body.subscription.endpoint);
      const existing = await env.SUBS.get(id);
      if (!existing) {
        const list = await env.SUBS.list({ limit: MAX_SUBS + 1 });
        if (list.keys.length >= MAX_SUBS) return json(env, { error: "too many" }, 429);
      }
      const rec = {
        subscription: { endpoint: body.subscription.endpoint, keys: body.subscription.keys },
        ua: String(body.ua || "").slice(0, 120),
        updated_at: new Date().toISOString(),
      };
      await env.SUBS.put(id, JSON.stringify(rec));
      return json(env, { ok: true, id });
    }

    if (url.pathname === "/subscriptions" && req.method === "GET") {
      if (!isAdmin(req, env)) return json(env, { error: "unauthorized" }, 401);
      const list = await env.SUBS.list();
      const subs = [];
      for (const k of list.keys) {
        const v = await env.SUBS.get(k.name);
        if (v) subs.push({ id: k.name, ...JSON.parse(v) });
      }
      return json(env, { subscriptions: subs });
    }

    const m = url.pathname.match(/^\/subscriptions\/([0-9a-f]{24})$/);
    if (m && req.method === "DELETE") {
      if (!isAdmin(req, env)) return json(env, { error: "unauthorized" }, 401);
      await env.SUBS.delete(m[1]);
      return json(env, { ok: true });
    }

    return json(env, { error: "not found" }, 404);
  },
};
