# Cloudflare

Last reviewed: 2026-10-27 · Applies to: Cloudflare CDN (Cache Rules, Cache Response Rules, Tiered Cache, Cache Reserve), Workers (Workers Caching, Cache API, KV), all plans unless noted

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Default behavior
- Configuration surface
- Cache keys
- Purge and invalidate
- Tiering, stale serving, Cache Reserve
- Workers caching options
- Status headers
- Version notes
- Verify
- Sources

## When to read this

When the zone is proxied by Cloudflare (orange cloud), the app runs on Workers/Pages, or `cf-cache-status` appears in responses. Vendor-neutral concepts: `references/layers/cdn-concepts.md`. Workers KV and edge data: `references/layers/serverless-edge-data.md`.

## How to detect

`wrangler.toml`/`wrangler.json(c)`, `@cloudflare/*` or `@opennextjs/cloudflare` deps, Terraform `cloudflare_ruleset`/`cloudflare_zone`, response headers `cf-cache-status`, `cf-ray`, `server: cloudflare`.

## Default recipe

Origin headers (preferred control):

```http
# Public HTML/API
Cache-Control: no-cache
Cloudflare-CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400
Cache-Tag: page:home,section:news,all
ETag: "<hash>"

# Personalized
Cache-Control: private, no-cache
```

Cache Rules (dashboard, API or Terraform; full examples in `assets/snippets/cdn/cloudflare-cache-rules.md`):

1. Rule "bypass private": `http.cookie contains "session=" or starts_with(http.request.uri.path, "/account") or starts_with(http.request.uri.path, "/api/private")` → Bypass cache.
2. Rule "cache public HTML": `http.host eq "www.example.com" and http.request.method eq "GET"` → Eligible for cache; Edge TTL "use cache-control header if present"; cache key: ignore query string order, Cache Deception Armor on.

Then enable Smart Tiered Cache (free) and, for cloud origins, the cloud region hint.

## Rules and gotchas

1. HTML and JSON are never cached by default; caching is by file extension, not MIME type. You need a Cache Rule ("Eligible for cache") to cache HTML.
2. Migrating from Page Rules: "Eligible for cache" means Cache Everything by default. Matching Cache Rules stack; order bypass rules deliberately.
3. Stale serving needs `stale-while-revalidate` from the origin and is disabled when the same header also carries `s-maxage`, `must-revalidate`, `proxy-revalidate` or `no-cache` (you get `EXPIRED` instead of `UPDATING`). Use `Cloudflare-CDN-Cache-Control: max-age=…, stale-while-revalidate=…` and keep `Cache-Control` for browsers. Always Online also disables SWR/SIE.
4. `Set-Cookie` on the response → `BYPASS` by default. `Cache-Control: private="Set-Cookie"` keeps the response cacheable and drops only that header. Better: don't send cookies on cacheable routes.
5. A request with `Authorization` is cached only if the response has `public`, `s-maxage` or `must-revalidate`. Setting `Cloudflare-CDN-Cache-Control` turns Origin Cache Control on, so this rule applies.
6. An Edge TTL rule "ignore cache-control and use this TTL" overrides `no-store`/`private` and strips `Set-Cookie`: it will cache personalized pages unless a bypass rule runs first.
7. Response Header Transform Rules that change `Cache-Control` don't affect caching (the decision happens first). Use Cache Response Rules.
8. Cache Deception Armor only activates when freshness is heuristic (no explicit `Cache-Control`). Correct origin headers are the real protection.
9. Use integer values in cache directives (docs disagree on whether floats are ignored or rounded).
10. Purge rate limits (hostname/tag/prefix/everything): Free 5 requests/min (bucket 25), Pro 5/s, Business 10/s, Enterprise 50/s; 100 items per request. Batch and debounce webhook purges.
11. Sort query string is off by default and can break order-dependent endpoints.

## Default behavior

- Cached extensions include css, js, images, fonts, media, archives, pdf (not html/json). `robots.txt` is cached by default.
- Without `Cache-Control`/`Expires`: 200/206/301 cached 120 min; 302/303 20 min; 404/410 3 min; others not cached.
- Max object: 512 MB Free/Pro/Business; 5 GB Enterprise default. Over the limit → `BYPASS`.
- `BYPASS` when: over size; `no-store` or bare `private` in any of the three cache headers; `Set-Cookie`; `Vary: *`; request `Authorization` without an allowing directive.
- `no-cache`/`max-age=0` with Origin Cache Control on (always on for Free/Pro/Business): stored and revalidated (`REVALIDATED`/`EXPIRED`); with OCC off (Enterprise default) → `BYPASS`.
- Header precedence: `Cloudflare-CDN-Cache-Control` (Cloudflare only, stripped) > `CDN-Cache-Control` (passed downstream) > `Cache-Control`. A Cache Response Rule `set_cache_control` beats all of them.

## Configuration surface

- **Cache Rules** decide eligibility, edge/browser TTL, cache key, serve-stale, Cache Reserve eligibility. Fields include `http.request.uri.path`, `http.request.uri.query`, `http.cookie`, `http.host`, `http.request.headers`, `http.request.uri.path.extension`.
- **Cache Response Rules** (March 2026, phase `http_response_cache_settings`) act on the origin response before caching: set or override `Cache-Control` (optionally Cloudflare-only), manage cache tags (including converting another CDN's tag header), strip `Set-Cookie`. They win over Cache Rules on conflict; last match wins. They can make content `no-store` but can't make it eligible.
- **Workers `fetch()`** can override cache settings per request via the `cf` object.
- Terraform `cloudflare_ruleset` with `set_cache_settings`: `edge_ttl { mode = "override_origin" | "respect_origin" ... }`, `browser_ttl`, `serve_stale { disable_stale_while_updating }`, `respect_strong_etags`, `cache_key`.

## Cache keys

| Option | Plans |
|---|---|
| Cache Deception Armor, cache by device type, ignore query string, sort query string | All |
| Custom query string include/exclude, headers, cookies, host, user features (device/geo/lang) | Enterprise |
| `Vary` honored in Cache Rules with per-header `normalize`/`passthrough`/`bypass` (July 2026) | All |

- `Vary` support: origin `Vary` header names join the key. `normalize` collapses `Accept-Language: en-US, fr;q=0.8` and `fr;q=0.8, en-GB` to `en,fr`; limits: ≤ 10 `Accept` media types, ≤ 20 languages, ≤ 50 header entries.
- Non-Enterprise plans can't exclude individual params: strip `utm_*` with a URL rewrite (Transform Rule/Snippet) or move variants into the path.
- Prefetch URLs always use the default key (incompatible with custom keys). Cloudflare Trace shows the computed key.

## Purge and invalidate

- All purge methods on all plans (since April 2025): URL, hostname, tag, prefix, everything. Instant Purge ≈ 150 ms globally.
- **Invalidate (soft purge)**, September 2026: `POST /zones/{zone_id}/invalidate_cache`, same body as purge. Marks stale; next request revalidates (304 reuses the stored body, needs origin `ETag`/`Last-Modified`); can serve stale meanwhile or on origin errors. Shares purge rate limits. Use hard purge only when content must never be served again.

```bash
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/invalidate_cache" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
  --data '{"tags":["product:123"]}'
```

- `Cache-Tag`: comma-separated, ≤ 16 KB total (~1,000 tags), case-insensitive, stripped before visitors; API tag ≤ 1,024 chars.
- URL purge on keys that include headers must pass those header values. Cache Rules matching only `GET` don't match purge requests: add `http.request.method eq "PURGE"` if rules depend on method.
- Purging a redirect URL purges the redirect, not its destination. With Tiered Cache, the first post-purge status may be `EXPIRED`.

## Tiering, stale serving, Cache Reserve

- Smart Tiered Cache: free, all plans; falls back to Generic when the origin location is unknown; cloud region hint (April 2026, e.g. `aws/us-east-1`); R2 origins get an upper tier near the bucket. Packaged with Regional Tiered Cache and Cache Reserve as "Smart Shield". Not compatible with Regional Services (data localization).
- Async SWR (February 2026): first request after expiry gets stale with `UPDATING`, revalidation runs in the background.
- Cache Reserve: R2-backed persistent upper tier, paid; eligible objects need a freshness TTL ≥ 10 h and `Content-Length`; 30-day retention reset on access; image-transformation variants aren't eligible (originals are); no Origin Range Requests. Purge forces a full miss; invalidate allows 304 reuse.

## Workers caching options

| Need | Use |
|---|---|
| Cache whole Worker responses | **Workers Caching** (`"cache": { "enabled": true }` in wrangler config): read-through, tiered, collapses requests, purge via `ctx.cache.purge()`/`ctx.cache.invalidate()` |
| Cache a subrequest or fragment | Cache API (`caches.default`): explicit `put`, data-center local, no tiering, no collapsing, `cache.delete` only local |
| Read-mostly config/data | Workers KV (eventually consistent, up to 60 s; min `cacheTtl` 30 s) |
| Strong consistency | Durable Objects/D1, with outputs behind Workers Caching |

Workers Caching traps: the host is not in the key (same cache for all domains); the Worker version is in the key by default, so every deploy starts cold (`cache.cross_version_cache` shares across versions); zone Cache Rules/Cache Response Rules don't apply; purges always use Free-tier rate limits; no pre-warm API. For tenants on the same path, pass tenant (or user) ID via `ctx.props`, which is part of the key.

Authenticated gateway pattern: an uncached entrypoint authenticates, strips `Authorization`, and calls a cached entrypoint that returns `Cache-Control: public, max-age=60`.

Also see Hyperdrive (DB query caching) in `references/layers/database-orm.md` and APO for WordPress in `references/cms/wordpress.md`.

## Status headers

`cf-cache-status`: `HIT`, `MISS` (cacheable, not stored yet), `EXPIRED`, `STALE`, `UPDATING` (stale served during async revalidation), `REVALIDATED`, `BYPASS` (uncacheable), `DYNAMIC` (not eligible, no lookup). Compute hit ratio over cacheable requests without `BYPASS`/`DYNAMIC`. Logpush fields: `CacheTieredFill`, `CacheLockWaitedMs`.

## Version notes

- 2025-04: all purge methods on all plans. 2026-01: KV minimum `cacheTtl` 30 s. 2026-02: async SWR. 2026-03: Cache Response Rules. 2026-04: Smart Tiered Cache cloud region hint. 2026-05: cache on Pingora; consistent `BYPASS`. 2026-06: `cf.vary` for Workers subrequests. 2026-07: `Vary` in Cache Rules. 2026-09: invalidate (soft purge) for zones and Workers Caching.

<details><summary>Old patterns</summary>

- Page Rules with "Cache Level: Cache Everything" (replaced by Cache Rules).
- Transform Rules to change `Cache-Control` for caching purposes (never affected caching).
- Expecting `MISS` to mean "uncacheable" (before May 2026 oversize objects showed `MISS` forever).

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://www.example.com/ | grep -iE 'cf-cache-status|age|cache-control'      # MISS then HIT
curl -s -o /dev/null -D - -H 'Cookie: session=x' https://www.example.com/ | grep -i cf-cache-status   # BYPASS or DYNAMIC
curl -s -o /dev/null -D - https://www.example.com/account/x.css | grep -iE 'cf-cache-status|cache-control'   # never HIT
```

## Sources

- [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior)
- [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
- [Cache Response Rules](https://developers.cloudflare.com/cache/how-to/cache-response-rules/)
- [Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/)
- [Revalidation and SWR](https://developers.cloudflare.com/cache/concepts/revalidation/)
- [Cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/)
- [Vary in Cache Rules](https://developers.cloudflare.com/cache/concepts/vary/)
- [Purge cache](https://developers.cloudflare.com/cache/how-to/purge-cache/)
- [Invalidate cache](https://developers.cloudflare.com/cache/guides/invalidate-cache/)
- [Tiered Cache](https://developers.cloudflare.com/cache/how-to/tiered-cache/)
- [Workers Cache](https://developers.cloudflare.com/workers/cache/)
- [Cache changelog](https://developers.cloudflare.com/changelog/product/cache/)
