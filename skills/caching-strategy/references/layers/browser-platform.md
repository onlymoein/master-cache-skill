# Browser platform caching

Last reviewed: 2026-10-27 · Applies to: Chrome 156, Edge 155, Firefox 158, Safari 27 (support data from MDN browser-compat-data 8.1.7)

## Contents

- When to read this
- Default recipe
- Rules and gotchas
- HTTP cache partitioning
- Back/forward cache (bfcache)
- Speculation rules, Early Hints, Server Push
- No-Vary-Search
- Compression dictionaries
- Clear-Site-Data
- Asset versioning and deploy skew
- Client-side storage as a cache
- Version notes
- Verify
- Sources

## When to read this

For any app that serves HTML to browsers. Header semantics live in `references/core/http-semantics.md`; service workers in `references/layers/service-workers.md`.

## Default recipe

```http
# Every HTML response
Cache-Control: no-cache            # or "private, no-cache" when personalized
ETag: "<content hash>"
Permissions-Policy: unload=()      # keep pages bfcache-eligible

# Logout response
Clear-Site-Data: "cache", "cookies", "storage", "prefetchCache", "prerenderCache"
```

```html
<!-- Same-origin speculative navigation, Chromium; harmless elsewhere.
     Exclude anything with side effects or per-user state changes. -->
<script type="speculationrules">
{ "prerender": [{
    "where": { "and": [
      { "href_matches": "/*" },
      { "not": { "href_matches": "/logout" } },
      { "not": { "href_matches": "/api/*" } },
      { "not": { "selector_matches": "[rel~=nofollow]" } }
    ] },
    "eagerness": "moderate"
} ] }
</script>
```

```js
// Re-check auth and refresh stale UI when a page comes back from bfcache
window.addEventListener('pageshow', (e) => {
  if (e.persisted) refreshSessionState();
});
```

## Rules and gotchas

1. Self-host third-party libraries and fonts. The HTTP cache is partitioned by top-level site, so a "shared" public CDN copy never gives cross-site hits; it only adds DNS/TLS cost and a dependency.
2. Keep HTML bfcache-eligible: avoid `unload` handlers (use `pagehide`), avoid needless `no-store`, close WebSocket/IndexedDB connections in `pagehide` and reopen in `pageshow`, use `rel="noopener"`.
3. Don't rely on `no-store` to hide a page after logout: Chrome may still bfcache it. Re-check auth on `pageshow` with `event.persisted` and send `Clear-Site-Data` on logout.
4. Speculation-rules prefetches are kept for up to 5 minutes. After a state change (logout, cart change) clear them with `Clear-Site-Data: "prefetchCache", "prerenderCache"`.
5. Treat `No-Vary-Search`, compression dictionaries and speculation rules as Chromium-first progressive enhancements, never as correctness mechanisms.
6. Hash filenames, not query strings. Keep old hashed assets deployed longer than the maximum cache age of the HTML and service worker that reference them.
7. Never store secrets or tokens in localStorage or IndexedDB if XSS is a concern.

## HTTP cache partitioning

- Chrome 86+ keys the HTTP cache by top-level site and current-frame site plus URL (sites are `scheme://eTLD+1`, so subdomains share). A 2025 change adds a cross-site-main-frame-navigation bit. Safari and Firefox also partition (details not re-verified).
- Compression dictionaries and storage (IndexedDB, Cache API, OPFS) are also per site/origin.
- Debug with `chrome://net-export` (look for `SplitCacheByNetworkIsolationKey`).

## Back/forward cache (bfcache)

| Blocker | Status |
|---|---|
| `unload` listener | Blocks in Chrome/Firefox desktop. From Chrome 155, `unload` fires only if `Permissions-Policy` opts in (`unload=self`); the default allowlist is `()` |
| `beforeunload` | Blocks in Firefox only. Add it only while there are unsaved changes |
| `Cache-Control: no-store` on the document | Chrome allows bfcache since the March–April 2025 rollout, with eviction on cookie/auth change, on WebSocket/WebTransport/WebRTC use, or if a fetch response had `no-store`; timeout 3 min instead of 10. Firefox/Safari may still block |
| Open IndexedDB, in-flight fetch, WebSocket/WebRTC, `window.opener` | Block in some browsers; close in `pagehide` |

Diagnostics: DevTools → Application → Back/forward cache → Run test; Lighthouse bfcache audit; `PerformanceNavigationTiming.notRestoredReasons` (Chrome 125+) in RUM. Measure: bfcache hit rate = bfcache / (bfcache + back-forward) from CrUX navigation types.

## Speculation rules, Early Hints, Server Push

| Feature | Status | Use |
|---|---|---|
| Speculation rules (`<script type="speculationrules">`, `Speculation-Rules` header) | Chromium full; Safari 26.2 behind a flag; Firefox Nightly prefetch only | `prefetch`/`prerender` with eagerness `conservative` (pointer down), `moderate` (hover), `eager`, `immediate`. Document rules default to `conservative`; list rules to `immediate`. Chrome caps `immediate`/`eager` at 50 prefetches/10 prerenders, `moderate`/`conservative` at 2 each (FIFO) |
| Prefetch cache | Per document, in memory, about 5 minutes | Requests carry `Sec-Purpose: prefetch` (or `prefetch;prerender`). Non-2xx cancels. Cross-site prefetch only without cookies. Prerender ignores `Cache-Control` |
| 103 Early Hints | Chrome 103 (HTTP/2+), Firefox 120, Safari 17 (HTTP/2+) | `Link: </app.css>; rel=preload; as=style` or `rel=preconnect`. Only the first 103 counts |
| HTTP/2 Server Push | Removed (Chrome 106, Firefox 132) | Use Early Hints |
| `<link rel=prerender>` | Deprecated (NoState Prefetch in Chrome) | Use speculation rules |

## No-Vary-Search

Experimental IETF draft. HTTP cache support: Chrome 141 (Android 143), Firefox 154, not Safari; speculation-rules prefetch since Chrome 121.

```http
No-Vary-Search: params=("utm_source" "utm_medium" "utm_campaign" "gclid" "fbclid"), key-order
```

- `params=(...)` (ignore listed params) is the safe form: unknown params still vary the key.
- `except=(...)`/`except=()` ignores everything else; easy to serve the wrong page. Avoid.
- It can defeat `?v=` cache busting and throwaway debug params.
- In January 2026 Chrome engineers warned a proposed syntax change could break deployments. Re-check before relying on it.

## Compression dictionaries

RFC 9842. `dcb`/`dcz`: Chrome/Edge 130+; Firefox behind a flag; not Safari.

```http
# Old bundle response declares itself a dictionary
Use-As-Dictionary: match="/js/app.*.js"
Cache-Control: public, max-age=31536000, immutable

# Delta-compressed new bundle
Content-Encoding: dcb
Vary: accept-encoding, available-dictionary
```

- A dictionary lives only as long as its HTTP freshness. `no-cache`/`no-store`/`must-revalidate` responses are silently never used as dictionaries (DevTools Issues panel reports it). HTML served `no-cache` can't be a dictionary.
- Same-origin only; partitioned like the HTTP cache. Plain `zstd` encoding: Chrome 123, Firefox 126, Safari 26.3.

## Clear-Site-Data

```http
Clear-Site-Data: "cache", "cookies", "storage", "prefetchCache", "prerenderCache"
```

- Header: Chrome 61, Firefox 63, Safari 17. `"cache"` is partial in Chrome (127+): some requests may still come from cache until reload, and it can hang for seconds. Firefox re-enabled `"cache"` in 138. `"prefetchCache"`/`"prerenderCache"` are Chrome 138+, non-standard. `"executionContexts"` is effectively unsupported.
- `"storage"` also unregisters service workers. `"cookies"` covers the whole registrable domain.
- It never touches shared caches. Don't send it on every page: it effectively disables caching while active. Use it on logout and emergency "fix my cache" endpoints.

## Asset versioning and deploy skew

- Hash in the filename; never reuse a hashed URL for different bytes.
- Deploy order: upload new hashed assets → switch HTML/manifest → keep the previous N builds' assets for weeks (longer than HTML/SW max age).
- Catch `ChunkLoadError` and reload once (guard with `sessionStorage`), or show "update available".
- Hash cascade with ES modules: changing one module changes every importer's hash. An import map (or bundler runtime/manifest chunk) confines the change. Import maps: Chrome 89, Firefox 108, Safari 16.4; `integrity` map Chrome 127, Firefox 138, Safari 18.
- Platform skew protection (Vercel, Netlify) is covered in the platform references.

## Client-side storage as a cache

- localStorage/sessionStorage: synchronous, strings only, 5 MiB per origin. Not for large or hot-path data.
- IndexedDB/Cache API: per-origin quotas (Chromium up to 60% of disk per origin; Firefox best-effort min(10% disk, 10 GiB); Safari about 60% for browser apps, 15% for WebViews).
- Best-effort storage is evicted LRU per origin, all at once. Safari deletes script-written storage for origins without user interaction in the last 7 days of use. Call `navigator.storage.persist()` for offline-critical apps; catch `QuotaExceededError`.
- Treat client storage as an evictable cache over a server source of truth. Clear it on logout and tenant switch.

## Version notes

- Chrome 155 (2026-10): `unload` disabled by default unless `Permissions-Policy` opts in.
- Chrome 2025: bfcache for `no-store` pages.
- Chrome 141 / Firefox 154: `No-Vary-Search` in the HTTP cache.
- Lighthouse "Use efficient cache lifetimes" insight replaced `uses-long-cache-ttl`. It skips `no-cache`/`no-store`/`must-revalidate`/`private` responses and TTLs ≥ 30 days, so a pass says nothing about HTML policy.

<details><summary>Old patterns</summary>

- Loading jQuery/fonts from a public CDN "because it's probably cached already" (dead since cache partitioning).
- HTTP/2 Server Push and `<link rel=prerender>`.
- Using `no-store` everywhere to "be safe".

</details>

## Verify

- DevTools Network: Size column shows `(memory cache)`, `(disk cache)`, `(ServiceWorker)`, `(prefetch cache)`. Use "Disable cache" only for cold-load tests.
- DevTools → Application → Back/forward cache → Run test.
- `curl -sI https://example.com/ | grep -iE 'cache-control|permissions-policy|no-vary-search'`.
- RUM: `performance.getEntriesByType('navigation')[0].notRestoredReasons` (Chrome).

## Sources

- [Chrome: HTTP cache partitioning](https://developer.chrome.com/blog/http-cache-partitioning)
- [web.dev: bfcache](https://web.dev/articles/bfcache)
- [Chrome: bfcache for Cache-Control: no-store](https://developer.chrome.com/docs/web-platform/bfcache-ccns)
- [MDN Speculation Rules API](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)
- [MDN No-Vary-Search](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/No-Vary-Search)
- [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
- [MDN Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- [MDN Storage quotas and eviction](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
- [MDN browser-compat-data](https://github.com/mdn/browser-compat-data)
- [Sentry: ChunkLoadError](https://sentry.io/answers/chunk-load-errors-javascript)
