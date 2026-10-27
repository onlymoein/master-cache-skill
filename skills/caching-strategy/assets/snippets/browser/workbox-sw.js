// Service worker with Workbox 7 (bundle with workbox-build injectManifest, vite-plugin-pwa or
// @serwist/* equivalents). One strategy per resource type; never cache per-user API responses
// or auth flows in the SW; version caches so deploys can drop old ones.
//
// Serve sw.js itself with `Cache-Control: no-cache` (a stale SW pins old app versions).

import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'
import { registerRoute, NavigationRoute } from 'workbox-routing'
import { NetworkFirst, StaleWhileRevalidate, CacheFirst } from 'workbox-strategies'
import { ExpirationPlugin } from 'workbox-expiration'
import { CacheableResponsePlugin } from 'workbox-cacheable-response'

const VERSION = 'v1' // bump to drop runtime caches on the next activation

// Build-time precache of hashed app-shell files (manifest injected by the build tool).
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// Navigations: network first so users get fresh HTML; fall back to the cached copy offline.
registerRoute(
  new NavigationRoute(
    new NetworkFirst({
      cacheName: `pages-${VERSION}`,
      networkTimeoutSeconds: 3,
      plugins: [
        new CacheableResponsePlugin({ statuses: [200] }),
        new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 7 * 24 * 3600 }),
      ],
    }),
    { denylist: [/^\/account/, /^\/checkout/, /^\/api\//, /^\/auth/, /^\/logout/] },
  ),
)

// Hashed static assets not in the precache: immutable, cache first.
registerRoute(
  ({ request, url }) => ['script', 'style', 'font'].includes(request.destination) && /[.-][0-9a-f]{8,}\./.test(url.pathname),
  new CacheFirst({
    cacheName: `assets-${VERSION}`,
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 365 * 24 * 3600, purgeOnQuotaError: true }),
    ],
  }),
)

// Images: stale-while-revalidate, bounded (opaque cross-origin responses can count ~7 MB each
// against quota in Chromium; only allow status 200 so opaque responses aren't stored).
registerRoute(
  ({ request }) => request.destination === 'image',
  new StaleWhileRevalidate({
    cacheName: `images-${VERSION}`,
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 100, maxAgeSeconds: 30 * 24 * 3600, purgeOnQuotaError: true }),
    ],
  }),
)

// Public, non-personalized API reads only (allow-list). Everything else under /api goes to the network.
registerRoute(
  ({ url, request }) => request.method === 'GET' && url.pathname.startsWith('/api/catalog/'),
  new NetworkFirst({
    cacheName: `api-public-${VERSION}`,
    networkTimeoutSeconds: 3,
    plugins: [
      new CacheableResponsePlugin({ statuses: [200] }),
      new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 24 * 3600 }),
    ],
  }),
)

// On logout the page should postMessage({ type: 'CLEAR_USER_CACHES' }) to drop anything user-scoped.
self.addEventListener('message', (event) => {
  if (event.data?.type === 'CLEAR_USER_CACHES') {
    event.waitUntil(caches.keys().then((names) => Promise.all(names.filter((n) => n.startsWith('pages-')).map((n) => caches.delete(n)))))
  }
})
