// Service worker de Nova (PWA instalable). Shell offline:
// precarga la portada y cachea bajo demanda los assets del build (hasheados).
// Ruta servida en /sw.js para que el alcance cubra toda la app.

const CACHE = 'nova-v1'

const PRECACHE = [
  '/',
  '/static/manifest.json',
  '/static/favicon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/fonts/fraunces-latin.woff2',
  '/static/fonts/outfit-latin.woff2',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.origin !== self.location.origin) return

  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((resp) => {
          const copy = resp.clone()
          caches.open(CACHE).then((cache) => cache.put('/', copy))
          return resp
        })
        .catch(() => caches.match('/')),
    )
    return
  }

  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached
      return fetch(req).then((resp) => {
        if (resp.ok) {
          const copy = resp.clone()
          caches.open(CACHE).then((cache) => cache.put(req, copy))
        }
        return resp
      })
    }),
  )
})