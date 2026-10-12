// Network-first for same-origin files so a deploy is picked up immediately,
// with the cache as the offline fallback. GitHub API calls are cross-origin
// and are deliberately never intercepted or cached here.
const CACHE_NAME = 'parkingtracker-clean-v1';
const APP_SHELL = [
  './',
  './index.html',
  './manifest.json',
  './glossary.html',
  './css/style.css',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/tracker-logo.png',
  './js/app.js',
  './js/config.js',
  './js/geo.js',
  './js/github.js',
  './js/index-manager.js',
  './js/local-manager.js',
  './js/lookup.js',
  './js/matching.js',
  './js/permissions.js',
  './js/photo-manager.js',
  './js/plate-manager.js',
  './js/state.js',
  './js/storage.js',
  './js/sync-manager.js',
  './js/ui.js',
  './js/vehicle-manager.js',
  './js/place-finder.js',
  './js/describe-search.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  if (new URL(request.url).origin !== self.location.origin) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match('./index.html')))
  );
});
