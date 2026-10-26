// 서비스 워커: 화면 파일 캐시, 푸시 수신, 알림 클릭 → 해당 공고 열기
const SHELL = "shell-v1";
const CFG_CACHE = "cfg-v1";
const FILES = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/badge-96.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== SHELL && k !== CFG_CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});

// 데이터(json, config.js)는 항상 네트워크. 화면 파일은 네트워크 우선, 실패 시 캐시.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.includes("/data/") || url.pathname.endsWith("config.js")) return;
  e.respondWith((async () => {
    try {
      const res = await fetch(e.request);
      if (res.ok && e.request.mode === "navigate") (await caches.open(SHELL)).put("index.html", res.clone());
      return res;
    } catch {
      return (await caches.match(e.request, { ignoreSearch: true })) || (await caches.match("index.html"));
    }
  })());
});

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { title: "새 유치원 공고", body: e.data && e.data.text() }; }
  const url = new URL(d.url || "./", self.registration.scope);
  if (d.source_url) url.searchParams.set("src", d.source_url);
  e.waitUntil(self.registration.showNotification(d.title || "새 유치원 공고", {
    body: d.body || "",
    icon: "icons/icon-192.png",
    badge: "icons/badge-96.png",
    tag: d.tag || undefined,
    renotify: !!d.tag,
    data: { url: url.href },
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const target = (e.notification.data && e.notification.data.url) || self.registration.scope;
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if (w.url.startsWith(self.registration.scope)) {
        await w.focus();
        try { return await w.navigate(target); } catch { return; }
      }
    }
    return self.clients.openWindow(target);
  })());
});

// 페이지가 알려준 설정(등록 코드 등)을 저장 → 브라우저가 구독을 바꿀 때 다시 등록하는 데 사용
self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "config") {
    e.waitUntil(caches.open(CFG_CACHE).then((c) => c.put("cfg", new Response(JSON.stringify(e.data)))));
  }
});

self.addEventListener("pushsubscriptionchange", (e) => {
  e.waitUntil((async () => {
    const res = await caches.match("cfg", { cacheName: CFG_CACHE });
    if (!res) return;
    const cfg = await res.json();
    const raw = atob(cfg.vapidPublicKey.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - cfg.vapidPublicKey.length % 4) % 4));
    const sub = e.newSubscription || await self.registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: Uint8Array.from(raw, (c) => c.charCodeAt(0)),
    });
    await fetch(`${cfg.workerUrl}/subscribe`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: cfg.code, subscription: sub.toJSON(), ua: "sw-resubscribe" }),
    });
  })());
});
