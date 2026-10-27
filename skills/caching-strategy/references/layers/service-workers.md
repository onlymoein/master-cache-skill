# Service workers and the Cache API

Last reviewed: 2026-10-27 · Applies to: Service Worker API, Cache API, Workbox 7.4.x

## Contents

- When to read this
- Default recipe
- Rules and gotchas
- Strategy per resource type
- Lifecycle and updates
- Storage, quotas and eviction
- Version notes
- Verify
- Sources

## When to read this

When the app has or wants a service worker (PWA, offline support, Workbox, `@serwist/*`, `vite-plugin-pwa`, `next-pwa`, a `sw.js`). Most sites don't need one for caching; HTTP caching plus a CDN covers online performance. Add a service worker for offline support, instant repeat navigations of an app shell, or control over flaky networks.

## Default recipe

Serve the SW script itself with `Cache-Control: no-cache` and an `ETag`. Full example: `assets/snippets/browser/workbox-sw.js`.

```js
import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching';
import { registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate, NetworkOnly } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';
import { pageCache, offlineFallback } from 'workbox-recipes';
import * as navigationPreload from 'workbox-navigation-preload';

precacheAndRoute(self.__WB_MANIFEST);           // hashed app shell
cleanupOutdatedCaches();
navigationPreload.enable();
pageCache();                                     // NetworkFirst, 3 s timeout, for navigations
offlineFallback();                               // needs /offline.html precached

registerRoute(({ url }) => url.pathname.startsWith('/assets/'),   // hashed only
  new CacheFirst({ cacheName: 'assets',
    plugins: [new ExpirationPlugin({ maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 })] }));
registerRoute(({ request }) => request.destination === 'image',
  new CacheFirst({ cacheName: 'images',
    plugins: [new ExpirationPlugin({ maxEntries: 60, maxAgeSeconds: 60 * 60 * 24 * 30 })] }));
registerRoute(({ url }) => url.pathname.startsWith('/api/'), new NetworkOnly(), 'POST');
registerRoute(({ url }) => url.pathname.startsWith('/api/public/'),
  new StaleWhileRevalidate({ cacheName: 'public-api' }));
```

## Rules and gotchas

1. The Cache API is separate from the HTTP cache. `Cache-Control` doesn't control what goes in, and entries never expire unless you delete them. Always set expiration (count and age) and delete old caches in `activate`.
2. Never use CacheFirst on unhashed URLs. It's the classic "stuck forever" bug: the SW never checks the network again.
3. Never cache personalized or authenticated responses in a shared-name cache that survives logout. Use NetworkOnly for user data, or namespace by user and clear on logout (`Clear-Site-Data: "storage"` unregisters SWs too).
4. NetworkFirst and StaleWhileRevalidate cache opaque (status 0) cross-origin responses by default; they carry quota padding and unknown status. Restrict to `[200]` for cross-origin unless you need opaque.
5. `skipWaiting()` + `clients.claim()` mixes old HTML with new precache entries. Prefer an "update available, reload" prompt, or keep both versions' assets reachable.
6. Clone responses before `cache.put`; bodies are streams.
7. Mutations (POST/PUT/DELETE) go NetworkOnly. Some data (availability, prices) is better missing than stale; keep it NetworkOnly.
8. Prerendered pages defer `register()`/`update()` until activation.

## Strategy per resource type

| Resource | Strategy | Notes |
|---|---|---|
| Precached app shell (hashed) | CacheOnly via precache | Updated when the SW updates |
| Hashed JS/CSS/fonts | CacheFirst + expiration | Hashed URLs only |
| Unhashed CSS/JS | StaleWhileRevalidate | `staticResourceCache()` recipe |
| Images | CacheFirst, `maxEntries` 60, 30 days | `imageCache()` recipe defaults |
| Navigations (HTML) | NetworkFirst, 3 s timeout, navigation preload, offline fallback | `pageCache()` recipe |
| Read APIs needing offline | NetworkFirst or StaleWhileRevalidate | Public data only unless namespaced per user |
| Mutations, real-time data | NetworkOnly | Queue with Background Sync if offline writes are needed |
| Google Fonts | `googleFontsCache()` | Better: self-host fonts |

## Lifecycle and updates

- Install → (waiting while old SW controls pages) → activate. First install controls pages only after reload unless `clients.claim()`.
- Since Chrome 68 the main SW script's update check bypasses the HTTP cache (`updateViaCache: 'imports'` default); `importScripts()` still uses it, so fingerprint imported scripts. `registration.update()` bypasses the HTTP cache after 24 h since the last check.
- Navigation preload runs the navigation request in parallel with SW boot: enable in `activate`, read `event.preloadResponse`. Requests carry `Service-Worker-Navigation-Preload: true`; add `Vary: Service-Worker-Navigation-Preload` if the server responds differently.
- Static Routing API (`InstallEvent.addRoutes()`) lets routes skip SW JavaScript: Chrome 123, Safari 27, not Firefox.
- Version caches by name and clean in `activate`:

```js
const CURRENT = 'app-v42';
self.addEventListener('activate', (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CURRENT).map((k) => caches.delete(k))))
));
```

## Storage, quotas and eviction

- Best-effort by default; evicted LRU per origin, all data at once. `navigator.storage.persist()` (Firefox prompts; others decide by engagement) protects offline-critical apps.
- Safari deletes script-written storage, including Cache API data, for origins without user interaction in the last 7 days of use.
- `navigator.storage.estimate()` returns padded numbers. Catch `QuotaExceededError` on writes.

## Version notes

- Workbox 7.4.1 (2026-05-04) is current. Long-term maintenance status wasn't confirmed; check the repo before adopting it for new projects. Serwist is a maintained Workbox fork used by some frameworks.
- Recipe defaults: `pageCache()` NetworkFirst 3 s, statuses `[0, 200]`; `imageCache()` 60 entries / 30 days; `googleFontsCache()` fonts 1 year / 30 entries.

<details><summary>Old patterns</summary>

- AppCache (`manifest=` attribute): removed from browsers.
- Hand-written SW without cache cleanup or expiration.
- Serving `sw.js` with a long `max-age` (older Chrome capped SW script max-age at 86400 s).

</details>

## Verify

- DevTools → Application → Service workers (update on reload, bypass for network) and Cache storage (inspect entries and sizes).
- DevTools Network shows `(ServiceWorker)` for SW-served responses.
- Test: deploy a new build, reload twice, confirm the new SW activates and old caches are gone.
- Test offline: DevTools → Network → Offline, navigate, expect the offline fallback.
- Log out, then check no user data remains in Cache storage or IndexedDB.

## Sources

- [MDN Service Worker API: using service workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)
- [MDN Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
- [MDN PWA caching guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching)
- [Chrome: service worker caching strategies](https://developer.chrome.com/docs/workbox/caching-strategies-overview)
- [Workbox (GitHub)](https://github.com/GoogleChrome/workbox)
- [MDN NavigationPreloadManager](https://developer.mozilla.org/en-US/docs/Web/API/NavigationPreloadManager)
- [MDN ServiceWorkerContainer.register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register)
- [MDN Storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
