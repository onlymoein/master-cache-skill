# HTTP caching semantics

Last reviewed: 2026-10-27 · Applies to: RFC 9110, RFC 9111, RFC 5861, RFC 8246, RFC 9211, RFC 9213; browsers as of Chrome 156, Firefox 158, Safari 27

## Contents

- When to read this
- Default recipe (headers per resource type)
- Rules and gotchas
- Response directives
- Request directives and reloads
- Freshness and heuristic caching
- Validators and conditional requests
- Vary and the cache key
- Targeted headers (CDN-Cache-Control)
- Cache-Status
- Version notes
- Verify
- Sources

## When to read this

Always. Every header the plan recommends must be correct per these rules. Vendor-specific behavior lives in `references/platforms/*.md`.

## Default recipe (headers per resource type)

| Resource | Response headers |
|---|---|
| Fingerprinted JS/CSS/fonts/images (`app.3f9a1c.js`) | `Cache-Control: public, max-age=31536000, immutable` + strong `ETag`. Drop `public` if requests to these URLs can carry `Authorization` |
| Unhashed static images/media (CMS uploads) | `Cache-Control: max-age=86400, stale-while-revalidate=604800` + `ETag`; edge `CDN-Cache-Control: max-age=2592000` + purge on change. Better: rename on edit |
| Public HTML | `Cache-Control: no-cache` + `ETag`/`Last-Modified`; edge `CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400` (longer with purge) |
| Personalized HTML | `Cache-Control: private, no-cache` + `ETag` |
| Sensitive pages (banking, PII, tokens) | `Cache-Control: no-store` |
| Public API JSON | `Cache-Control: no-cache` + `ETag` (or `public, max-age=60, stale-while-revalidate=300` if clients tolerate it); edge TTL via targeted header; `Vary: Accept-Encoding` (+ `Origin` if CORS is dynamic) |
| User-specific API JSON | `Cache-Control: private, no-cache` + `ETag` |
| Mutation responses | `Cache-Control: no-store` |
| `manifest.webmanifest`, `favicon.ico`, `robots.txt`, `/.well-known/*` | `Cache-Control: no-cache` + `ETag` (or `max-age=3600–86400` if staleness is fine) |
| Service worker script | `Cache-Control: no-cache` + `ETag`; fingerprint `importScripts` URLs |
| Import map / module entry HTML | Same as HTML |
| 301/308 | Explicit `Cache-Control: max-age=86400` at first; raise to 30 days–1 year once sure |
| 302/303/307 | `Cache-Control: no-store` (or a deliberate short `max-age`) |
| 404 | `Cache-Control: max-age=60` (or `no-cache`); 410 can be long |
| 5xx | `Cache-Control: no-store` (at most 5–10 s at the edge); rely on `stale-if-error` on the last 200 |
| Compression dictionary resource | `max-age=…` or `max-age=0, stale-while-revalidate=…`; never `no-cache`/`no-store`/`must-revalidate` |

Site-wide default when nothing else matches: `no-store` for apps that haven't classified their routes yet (routes opt in), then `no-cache` (+ `private` when personalized) once classified. Never leave a response without `Cache-Control`.

## Rules and gotchas

1. **`no-cache` stores.** It means "store, but revalidate before every reuse". Only `no-store` prevents storage.
2. **`no-store` doesn't delete** an already-stored copy for the same URL, and it costs bfcache in Firefox/Safari. Prefer `private, no-cache` unless the data is truly sensitive.
3. **`must-revalidate` only acts once stale.** Added to `max-age=3600` it does not force revalidation; it forbids serving stale, so an origin outage becomes 504s. For resilience use SIE at the CDN instead.
4. **`s-maxage` implies `proxy-revalidate`** (shared caches can't serve it stale) and applies to shared caches only.
5. **`public` is a footgun.** It lets a cache store a response "even if it would otherwise be prohibited", including responses to requests with `Authorization`. Hashed assets don't need it unless they sit behind HTTP auth.
6. **`Authorization` + shared cache:** a shared cache may reuse a response to a request with `Authorization` only if the response has `public`, `s-maxage` or `must-revalidate`. Don't add those to authenticated responses.
7. **Request collapsing:** shared caches merge concurrent identical requests even when the response is `max-age=0`/`no-cache`. Personalized responses need `private`.
8. **Kitchen sink:** `private, no-cache, no-store, max-age=0, must-revalidate` is equivalent to `no-store`. `max-age=0, must-revalidate` is a pre-HTTP/1.1 spelling of `no-cache`. Don't send `max-age` with `no-cache`.
9. **Conflicting directives:** the most restrictive wins. Duplicated directives may make the response stale. Use lowercase directive names and token form (`max-age=5`, not `max-age="5"`).
10. **Unsafe methods invalidate:** a non-error response to POST/PUT/DELETE invalidates the target URI in caches that see it. CDNs and browsers you don't route through won't know.
11. **No protocol purge:** nothing in HTTP deletes a response a shared cache stored with a long TTL. Only CDN purge APIs can. `Clear-Site-Data: "cache"` clears the browser only.
12. **Never send `Set-Cookie` on a shared-cacheable response.** Shared caches either refuse to store it (Cloudflare: `BYPASS`) or store the cookie and hand it to everyone.
13. **History navigation is not cache reuse.** `no-cache`/`max-age` don't force revalidation on back/forward; bfcache restores a snapshot. See `references/layers/browser-platform.md`.
14. **Cache busting:** hash in the filename, not the query string. CDNs may strip queries and `No-Vary-Search` can collapse them.
15. **Deploy skew:** old tabs request chunks a deploy removed (`ChunkLoadError`). Keep old hashed assets longer than the max cache age of the HTML and service worker that reference them.

## Response directives

| Directive | Meaning | Note |
|---|---|---|
| `max-age=N` | Fresh for N s from generation (minus `Age`) | Token form only |
| `s-maxage=N` | Shared caches only; overrides `max-age`/`Expires`; implies `proxy-revalidate` | Allows shared caching of `Authorization` responses |
| `no-cache` | May store; must revalidate before each reuse | Qualified `no-cache="Set-Cookie"` is often treated as unqualified |
| `no-store` | No cache may store request or response | Not a privacy guarantee per the RFC |
| `private` | Shared caches must not store | Browser may store even if not otherwise cacheable |
| `public` | May store even if otherwise prohibited | Rarely needed |
| `must-revalidate` | Once stale, must not reuse without validation; disconnected cache returns 504 | Allows shared caching of `Authorization` responses |
| `proxy-revalidate` | Like `must-revalidate`, shared caches only | |
| `immutable` (RFC 8246) | Won't change during freshness; skip conditional reloads | Firefox 49+, Safari 11+; Chrome never implemented it (skips subresource revalidation on reload instead) |
| `stale-while-revalidate=N` (RFC 5861) | Serve stale up to N s past expiry while revalidating in background | Browsers: Chrome 75, Firefox 68, Safari 14; CDN support varies |
| `stale-if-error=N` (RFC 5861) | Serve stale up to N s on 500/502/503/504 | Treat as a CDN/proxy feature; browser support unconfirmed |
| `no-transform` | Intermediaries must not modify the body | |
| `must-understand` | Store only if the cache understands the status code | Send as `must-understand, no-store` |

`Expires` is redundant when `max-age` is present; `Expires: 0` or an invalid date means already expired. `Pragma` is deprecated; `Warning` is obsolete.

## Request directives and reloads

- Normal reload: `Cache-Control: max-age=0` + validators (Chrome, Edge, Firefox). Safari reload sends `no-cache` + `Pragma: no-cache`.
- Force reload: `Cache-Control: no-cache` + `Pragma: no-cache`, no validators, for the document and every subresource (including `immutable`).
- `only-if-cached` returns the stored response or 504. `max-stale`/`min-fresh` aren't supported by major browsers.
- Fetch cache modes: `default`, `no-store`, `reload`, `no-cache` (always conditional), `force-cache` (any stored response, even stale), `only-if-cached` (same-origin only).

## Freshness and heuristic caching

Freshness lifetime, first match: `s-maxage` (shared only) → `max-age` → `Expires − Date` → heuristic.

Heuristic: with `Last-Modified` and no explicit freshness, caches may reuse a response for a fraction of its age (typically 10%). A page last modified a year ago can be reused for about 5 weeks without any `Cache-Control`. Heuristically cacheable statuses: 200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501. Not: 302, 303, 307. A headerless 301 can stick in browsers for a very long time, and a transient 404 during a deploy can be cached.

## Validators and conditional requests

- Send a strong `ETag` and `Last-Modified` on every cacheable 200. `If-None-Match` wins over `If-Modified-Since` and uses weak comparison, so weak ETags work for revalidation. `If-Match` (lost-update protection, 412) needs strong comparison.
- A 304 must repeat `Cache-Control`, `Expires`, `ETag`, `Vary`, `Date`, `Content-Location` that a 200 would carry.
- Derive ETags from content (build hash, body hash, row version), never per-machine inode/mtime, or every server behind the load balancer reports a different tag and 304s never happen.
- Compute ETags after the encoding decision, or tag per encoding (`"123-gzip"` vs `"123-br"`) with `Vary: Accept-Encoding`.
- nginx downgrades strong ETags to weak when it gzips on the fly, and drops unquoted upstream ETags (`ETag: abc`) entirely. Always send quoted ETags.
- Express generates weak ETags by default.
- If browser JavaScript adds `If-None-Match`/`If-Modified-Since` to `fetch()`, the request switches to cache mode `no-store` and bypasses the HTTP cache. Let the browser add validators itself.
- Weak ETags prevent caching of byte-range responses; strong ETags keep range requests cacheable.

## Vary and the cache key

- `Vary` lists request headers that changed the response. Each value multiplies stored variants.
- Send the same `Vary` on every response for a URL, including 304s. `Vary: *` makes the response unusable from cache.
- Good: `Accept-Encoding` (usually automatic); `Accept` for image format negotiation (normalize to a few buckets at the CDN); `Accept-Language` only when the language is negotiated (prefer locale in the URL); `Origin` when `Access-Control-Allow-Origin` is computed per request.
- Never: `Vary: Cookie` (with analytics cookies it's effectively `Vary: *`), `Vary: User-Agent` (huge cardinality), `Vary: Authorization` on shared-cacheable content. Use `private` instead, or strip cookies at the edge for public paths.
- If `Access-Control-Allow-Origin` is `*` or static, send it on every response, including non-CORS ones.
- Client hints that select the response belong in `Vary`; high-variance hints make the response effectively uncacheable. `Accept-CH`/`Critical-CH` are Chromium-only.
- Dictionary-compressed responses need `Vary: accept-encoding, available-dictionary`. Navigation-preload responses that differ need `Vary: Service-Worker-Navigation-Preload`.

## Targeted headers (CDN-Cache-Control)

RFC 9213 lets one response carry different policies per cache tier. A cache with a target list picks the first valid targeted field and ignores `Cache-Control`/`Expires` for itself.

```http
Cache-Control: no-cache
CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400
```

- Browsers get `no-cache`; the CDN caches 300 s with SWR and SIE. This is the portable edge header.
- Vendor-only variants are stripped before forwarding: `Cloudflare-CDN-Cache-Control`, `Vercel-CDN-Cache-Control`, `Netlify-CDN-Cache-Control`. Fastly uses `Surrogate-Control`. Akamai needs its Caching behavior set to honor origin headers.
- Targeted fields are Structured Field dictionaries; a value that fails to parse is ignored and the cache falls back to `Cache-Control`.
- `CDN-Cache-Control: max-age=600` with `Cache-Control: no-store` means "CDN only".
- On Cloudflare, `s-maxage`, `must-revalidate`, `proxy-revalidate` or `no-cache` in the same header as `stale-while-revalidate` disables stale serving. Use the targeted header without them.

## Cache-Status

RFC 9211 `Cache-Status` is a list with one member per cache, origin-side first: `hit`, `fwd=bypass|method|uri-miss|vary-miss|miss|request|stale|partial`, `fwd-status`, `ttl`, `stored`, `collapsed`, `key`, `detail`. Example: `Cache-Status: OriginCache; hit; ttl=1100, "CDN Company"; fwd=stale; fwd-status=304`. Prefer it over vendor headers when present; see `references/core/observability-testing.md` for the vendor vocabulary.

## Version notes

- RFC 9111 (2022) obsoletes RFC 7234: `Pragma` deprecated, `Warning` obsolete, `must-understand` added.
- Compression Dictionary Transport is RFC 9842 (browser support: `references/layers/browser-platform.md`).
- `No-Vary-Search` and Cache Groups are still IETF drafts at last review; treat as progressive enhancement.

<details><summary>Old patterns</summary>

- `Expires` + `Pragma: no-cache` instead of `Cache-Control`.
- `max-age=0, must-revalidate` instead of `no-cache`.
- Kitchen-sink `no-store, no-cache, max-age=0, must-revalidate, proxy-revalidate`.
- Query-string cache busting (`app.js?v=123`).

</details>

## Verify

```bash
curl -sI https://example.com/ | grep -iE 'cache-control|cdn-cache-control|age|etag|last-modified|vary|cache-status|set-cookie'
ETAG=$(curl -sI https://example.com/ | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" https://example.com/   # expect 304
curl -sI -H 'Accept-Encoding: br' https://example.com/app.js   # check Vary / ETag per encoding
```

Or `python scripts/probe_headers.py <url>` for the full matrix.

## Sources

- [RFC 9111 HTTP Caching](https://httpwg.org/specs/rfc9111.html)
- [RFC 9110 HTTP Semantics](https://httpwg.org/specs/rfc9110.html)
- [RFC 5861 stale-while-revalidate / stale-if-error](https://httpwg.org/specs/rfc5861.html)
- [RFC 8246 immutable](https://httpwg.org/specs/rfc8246.html)
- [RFC 9213 Targeted Cache-Control](https://httpwg.org/specs/rfc9213.html)
- [RFC 9211 Cache-Status](https://httpwg.org/specs/rfc9211.html)
- [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [Fetch Standard: cache mode and CORS/HTTP caches](https://fetch.spec.whatwg.org/#concept-request-cache-mode)
- [nginx trac #377 (ETag weakening)](https://trac.nginx.org/nginx/ticket/377)
