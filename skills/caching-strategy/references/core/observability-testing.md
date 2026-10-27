# Observability, debugging and testing

Last reviewed: 2026-10-27 · Applies to: CDN status headers, RFC 9211 Cache-Status, browser RUM, Redis/Valkey/Memcached metrics, OpenTelemetry, CI testing

## Contents

- When to read this
- Status vocabulary
- Metrics per layer
- Alerts
- Debugging recipes
- Testing
- Rollout verification checklist
- Sources

## When to read this

At the verification step of every plan, and when diagnosing "is this cached?", "why is the hit ratio low?" or "why is stale content showing?". Nothing is done until headers, HIT/Age behavior and a two-user leak test pass.

## Status vocabulary

Normalize every vendor's header to one taxonomy: **hit**, **miss** (cacheable, not stored), **stale** (served stale: SWR/SIE/grace), **revalidated** (304 from origin), **bypass** (uncacheable).

| Source | Values → taxonomy |
|---|---|
| RFC 9211 `Cache-Status` (prefer when present) | `hit` → hit; `fwd=uri-miss`/`vary-miss`/`miss` → miss; `fwd=stale` → revalidated or stale (see `fwd-status`); `fwd=bypass`/`method`/`request` → bypass. Also `ttl`, `stored`, `collapsed`, `key` |
| Cloudflare `cf-cache-status` | `HIT`; `MISS` (cacheable, not yet stored); `EXPIRED`; `STALE` (origin unreachable); `UPDATING` (stale during async revalidation); `REVALIDATED`; `BYPASS` (uncacheable since 2026-05-26); `DYNAMIC` (not eligible); `NONE` (generated before cache, e.g. Worker/WAF) |
| Vercel `x-vercel-cache` | `HIT`; `MISS`; `STALE` (SWR/ISR background refresh); `PRERENDER` (build output); `REVALIDATED` (foreground regenerate after delete); `BYPASS` |
| Next.js `x-nextjs-cache` | `HIT`, `STALE`, `MISS`, `REVALIDATED` |
| Fastly `X-Cache` (+ `X-Served-By`, `X-Cache-Hits`) | `HIT`/`MISS` per node (`MISS, HIT` with shielding; PASS reports as MISS). `Fastly-Debug: 1` request header adds `Fastly-Debug-Path`, `Fastly-Debug-TTL` |
| CloudFront `X-Cache` | `Hit from cloudfront`; `Miss from cloudfront`; `RefreshHit from cloudfront` (revalidated); `Error from cloudfront` |
| Akamai (Pragma debug or `Akamai-Debug: cache`) | `X-Cache: TCP_HIT` / `TCP_MISS` / `TCP_REFRESH_HIT`; `X-Cache-Key`, `X-True-Cache-Key` |
| nginx `$upstream_cache_status` | `HIT`, `MISS`, `EXPIRED`, `STALE`, `UPDATING`, `REVALIDATED`, `BYPASS` |
| Netlify | RFC 9211 `Cache-Status` (`"Netlify Edge"`, `"Netlify Durable"`) |
| `Age` | Seconds since stored at the cache; rising across requests = hits |

## Metrics per layer

| Layer | Metric | How |
|---|---|---|
| CDN | Request hit ratio over cacheable requests | HIT / (HIT + MISS + EXPIRED + STALE/UPDATING); exclude BYPASS/DYNAMIC and track them separately as the opportunity |
| CDN | Byte hit ratio, origin offload (bytes), origin RPS/egress | CDN analytics/logs; large objects dominate bytes |
| CDN | Purge-to-visible latency | Synthetic probe after publish |
| Proxy | `$upstream_cache_status` counts; Varnish `varnishstat` hit/miss/hfp | Access logs, exporters |
| App (Redis/Valkey) | Hit ratio from **deltas** of `keyspace_hits`/`keyspace_misses`; `evicted_keys` (memory pressure) vs `expired_keys` (TTL working); `used_memory`, `mem_fragmentation_ratio`; `connected_clients` vs `maxclients`; latency | `INFO stats`, `INFO memory`; low ratio right after restart (uptime < ~30 min) can just be a cold cache |
| App (Memcached) | `get_hits`/`cmd_get`; `get_expired`; `evictions`; `curr_items`; `bytes` vs `limit_maxbytes` | `stats` |
| In-process | Hits, misses, evictions, load time per cache name | Caffeine `recordStats()`, library counters |
| Browser (RUM) | Cache hit when `transferSize === 0 && decodedBodySize > 0`; revalidation when `0 < transferSize < encodedBodySize`; `deliveryType` (`cache`, Chromium 117+) | `PerformanceObserver` on resource/navigation entries; raise `setResourceTimingBufferSize` (default ~250). Safari doesn't support the heuristic |
| Browser (field) | TTFB p75 (≤ 0.8 s good), LCP p75; CrUX navigation types; bfcache hit rate = bfcache / (bfcache + back-forward); `notRestoredReasons` (Chrome 125+) | CrUX, RUM |
| LLM | Cached-token share, cost per task | Provider `usage` fields (`references/layers/ai-llm.md`) |
| Traces | OpenTelemetry has no standard cache-hit attribute: set a custom `cache.hit` (bool) and `cache.layer` on spans | Redis spans use `db.system.name = "redis"`, `db.operation.name` |

Measure per key class/route class, not just globally.

## Alerts

- Hit ratio drop per path class (delta-based to avoid cold-start noise).
- Eviction spike (`evicted_keys`/min rising) = undersized cache.
- Stale-served spike = origin health problem.
- A route that flipped from BYPASS to HIT (possible leak) or HIT to BYPASS (lost caching, e.g. a new `Set-Cookie`).
- Purge API errors; purge-to-visible above target.
- Byte hit ratio diverging from request hit ratio (large-object misses).
- Redis `connected_clients` near `maxclients`.

## Debugging recipes

```bash
URL=https://example.com/page
H='^(cache-control|cdn-cache-control|surrogate-control|age|etag|last-modified|vary|set-cookie|cache-status|cf-cache-status|x-cache|x-vercel-cache|x-nextjs-cache|x-served-by|cache-tag|surrogate-key):'

curl -s -o /dev/null -D - "$URL" | grep -iE "$H"                          # 1. what headers?
for i in 1 2 3; do curl -s -o /dev/null -D - "$URL" | grep -iE '^(age|cf-cache-status|x-cache|x-vercel-cache|cache-status):'; done   # 2. MISS→HIT, Age rising?
curl -s -o /dev/null -D - "$URL?cb=$RANDOM" | grep -iE "$H"                # 3. bypass the shared cache without purging
ETAG=$(curl -sI "$URL" | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" "$URL"   # 4. expect 304
curl -s -o /dev/null -D - -H 'Cookie: session=test' "$URL" | grep -iE "$H" # 5. with a session: never HIT
curl -sI -H 'Fastly-Debug: 1' "$URL"                                       # Fastly extras
curl -sI -H 'Pragma: akamai-x-cache-on, akamai-x-get-cache-key, akamai-x-get-true-cache-key' "$URL"   # Akamai
```

Or run `python scripts/probe_headers.py "$URL"` for the whole matrix.

Other tools:

- Chrome DevTools Network: Size column shows `(memory cache)`, `(disk cache)`, `(ServiceWorker)`, `(prefetch cache)`; "Disable cache" only for cold-load tests. Keep cold, warm and cache-disabled runs separate, and record the browser version.
- REDbot: lints caching/validation headers. The public site forbids scripted use; for CI run your own (`pipx install redbot`).
- Lighthouse "Use efficient cache lifetimes" insight skips `no-cache`/`no-store`/`must-revalidate`/`private` responses and TTLs ≥ 30 days; a pass says nothing about HTML or API policy.
- Redis: `redis-cli --bigkeys`/`--memkeys` (full scan; off-peak), `--hotkeys` (needs an LFU policy), `OBJECT FREQ`, `SLOWLOG`, `INFO commandstats`. `MONITOR` only briefly on non-production or a replica (`timeout 5 redis-cli MONITOR`).
- Cloudflare Trace shows the computed cache key.

## Testing

| Test | What it proves | How |
|---|---|---|
| Unit: TTL logic | Fresh → hit; past soft TTL → stale + refresh; past hard TTL → miss; errors → stale, not delete | Inject a fake clock; no real sleeps |
| Unit: race | Stale-set race is closed (lease/version) | Interleave slow reader and writer deterministically |
| Integration: header snapshots | Each route class keeps its exact `Cache-Control`, `Vary`, no `Set-Cookie` on cacheable responses | `assets/snippets/tests/header-snapshot.test.ts`; fails when caching posture changes (would have caught the missing-`Vary` CVE) |
| E2E: two-user leak | Personalized content is never served to another user via the real CDN | `assets/snippets/tests/leak-test.sh` or `scripts/probe_headers.py --cookie-a … --cookie-b …` |
| E2E: deception probes | `/account.css`-style URLs never cached | `scripts/probe_headers.py --deception`; WCVS in CI against staging |
| E2E: tenant canary | Tenant A never sees tenant B's data | Plant unique canaries in two tenants |
| Load: cold cache + spike | Single-flight/SWR/collapsing hold; origin load bounded | k6/Locust from a cold cache, hammer one hot key |
| Chaos: cache down | Bounded latency, DB concurrency limit holds, graceful 503s | Kill/partition Redis or the shield |
| Synthetic: purge-to-visible | Invalidation pipeline meets its target | Edit a canary record, poll until visible, record seconds |
| Post-deploy synthetic | Status headers and hit ratio on key URLs unchanged | Scheduled probe; alert on flips |

## Rollout verification checklist

1. Baseline captured (date range, sources).
2. Headers match the plan for every route class (snapshot tests green).
3. No `Set-Cookie` on publicly cached responses; `Vary` minimal and correct.
4. Second request shows HIT with rising `Age`; conditional request returns 304; query variants map to intended keys.
5. Two-user leak test, deception probes and tenant canary pass.
6. Invalidation tested in staging: purge-to-visible within target; SWR serves stale while refreshing; SIE serves when origin is down.
7. Load test from cold cache and chaos test pass.
8. Canary rollout per route class; watch error rate, hit ratio, origin RPS, staleness reports.
9. Dashboards and alerts live; synthetic freshness probe scheduled.
10. Rollback ready: CDN bypass rule, header revert, cache-namespace version bump.
11. Post-rollout before/after report; adjust TTLs where staleness incidents or low hit ratios appear.

## Sources

- [RFC 9211 Cache-Status](https://www.rfc-editor.org/rfc/rfc9211)
- [Cloudflare cache responses](https://developers.cloudflare.com/cache/concepts/cache-responses/)
- [Vercel cache status](https://vercel.com/docs/caching/cache-status)
- [Fastly: checking cache](https://www.fastly.com/documentation/guides/full-site-delivery/caching/checking-cache/)
- [Akamai Pragma debug headers](https://techdocs.akamai.com/edge-diagnostics/docs/pragma-headers)
- [MDN PerformanceResourceTiming.transferSize](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/transferSize)
- [OpenTelemetry Redis semantic conventions](https://opentelemetry.io/docs/specs/semconv/database/redis)
- [REDbot](https://redbot.org/about/)
- [Hackmanit Web Cache Vulnerability Scanner](https://github.com/Hackmanit/Web-Cache-Vulnerability-Scanner)
- [devtools-frontend Cache insight](https://github.com/ChromeDevTools/devtools-frontend/blob/main/front_end/models/trace/insights/Cache.ts)
