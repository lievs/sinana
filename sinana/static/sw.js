const STATIC_CACHE = "sinana-static-v1";
const ASSETS = [
  "/static/css/app.css",
  "/static/css/layout.css",
  "/static/js/app.js",
  "/static/brand/sinana-monogram.png",
  "/static/brand/sinana-wordmark.png",
  "/static/offline.html"
];
self.addEventListener("install", event => event.waitUntil(caches.open(STATIC_CACHE).then(cache => cache.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== STATIC_CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())));
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  if (url.origin === location.origin && url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request)));
    return;
  }
  if (event.request.mode === "navigate") event.respondWith(fetch(event.request).catch(() => caches.match("/static/offline.html")));
});
