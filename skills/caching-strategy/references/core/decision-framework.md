# Decision framework: audit, classify, plan

Last reviewed: 2026-10-27 · Applies to: any web app, API or mobile backend, any stack

## Contents

- When to read this
- Audit procedure (six passes)
- Probing traps
- Decision tree (steps 0–9)
- Data-class matrix
- TTL ladder across tiers
- Hit-ratio and ROI math
- Rollout order by ROI
- When not to cache
- Anti-pattern catalog
- Plan row requirements
- Sources

## When to read this

Always, before proposing any cache. Every route or data type in the plan goes through the decision tree. Each plan row records the step that decided it.

## Audit procedure (six passes)

Run the passes in order. Write down what each pass finds; the plan cites it.

| Pass | Do | Output |
|---|---|---|
| 1. Fingerprint | `python scripts/detect_stack.py <repo>`. Read exact versions from lockfiles; versions decide which APIs exist. Note hosting, CDN, proxies, data stores and replica count (more than one instance means in-process caches drift). | App profile and the list of references to read |
| 2. Inventory | List every route or endpoint: method, auth required, cookies/headers/session read, query params, data sources, write side effects, traffic share if known. Use the framework's route tree (see the framework reference) or `rails routes`, `php artisan route:list`, `urls.py`, `@GetMapping`, `app.get(`. | Resource inventory |
| 3. Live probe (optional, only on URLs the user gives you) | `python scripts/probe_headers.py <url>... [--cookie-a ... --cookie-b ...] [--deception]`. Repeat GETs (expect MISS then HIT with rising `Age`), a conditional GET (expect 304), with and without a session cookie, plus deception paths. | Header table, leak findings |
| 4. Existing caches | `python scripts/find_cache_primitives.py <repo>`. Also read CDN rules in IaC and dashboards the user can export. | Existing caches with key, TTL, invalidation |
| 5. Baseline | Collect the metrics below with date range and source. Ask the user for what you can't read from the repo. | Dated baseline |
| 6. Classify | Run the decision tree per inventory row. | Plan rows |

Baseline metrics:

| Metric | Source | Why |
|---|---|---|
| CDN request and byte hit ratio per path class, over cacheable requests | CDN analytics/logs; exclude `BYPASS` and track it separately | Offload headroom |
| Origin RPS, p50/p95/p99 per route | APM, access logs | Finds hot, expensive routes |
| Popularity distribution (top-N URL share) | Logs | A Zipf head means a high achievable hit ratio |
| Read:write ratio per entity, top repeated queries | `pg_stat_statements`, slow log, ORM logs | Cache candidates vs queries to fix |
| Redis/Memcached `keyspace_hits`, `keyspace_misses`, `evicted_keys`, memory | `INFO stats` deltas | Existing cache health |
| TTFB p75 (good ≤ 0.8 s, poor > 1.8 s), LCP p75 | RUM / CrUX | User impact |
| CrUX navigation types (bfcache, back-forward, prerender, cache) | CrUX | bfcache hit rate = bfcache / (bfcache + back-forward) |
| Traffic shape: peak/mean, spikes | Analytics | Stampede risk |
| Egress and compute cost per 1M requests | Billing | ROI |

## Probing traps

1. A missing `Cache-Control` does not mean "not cached". Caches apply heuristic freshness (typically 10% of the time since `Last-Modified`) to 200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414 and 501. Every headerless response is a finding.
2. Cloudflare since 2026-05-26: `BYPASS` = uncacheable (size, `private`/`no-store`/`no-cache`/`max-age=0`, `Set-Cookie`, request `Authorization`); `MISS` = cacheable but not stored yet. Compute hit ratio as HIT / (HIT + MISS + EXPIRED + …) without BYPASS.
3. Reloads lie. Chrome reload sends `max-age=0` plus validators; Safari reload sends `no-cache` + `Pragma` and always gets 200; a hard reload revalidates everything including `immutable`. Never mix cold, warm and cache-disabled runs; record browser version and DevTools state.
4. `No-Vary-Search` on a page can make a throwaway query string stop busting the cache.
5. Shared caches collapse concurrent identical requests even for `max-age=0`/`no-cache` responses. Personalized responses need `private`, not just `no-cache`.

## Decision tree (steps 0–9)

Run per route or data type. Stop at the first step that ends the decision. Record the step number in the plan row (`decision_step`).

| Step | Question | Outcome |
|---|---|---|
| 0 | Method other than GET/HEAD? | `Cache-Control: no-store`. On success, run invalidation for every read it affects (tags, keys, events). **Stop.** |
| 1 | Contains secrets or regulated data (tokens, OTPs, payment data, health data, balances, statements)? | `no-store`. No shared cache. App cache only if scoped to tenant/user, encrypted, minimal TTL. **Stop.** |
| 2 | Body depends on who asks (cookie, session, `Authorization`, tenant, entitlement, A/B bucket, geo price)? | **Wholly:** `private, no-cache` + `ETag`; app-cache keys scoped `t:{tenant}:` / user; never `s-maxage`, never a CDN TTL. **Stop.** **Partly:** split a public shell (continue at step 3) from a private island (client fetch, PPR, `'use cache: private'`, ESI). Strip `Set-Cookie` from the shell. **No:** public, continue. |
| 3 | Can the URL change whenever the content changes (content hash, version id, immutable upload id)? | `max-age=31536000, immutable`. Add `public` only if requests never carry `Authorization`. No invalidation needed. **Stop.** |
| 4 | Staleness budget S? | **S = 0** (price at payment, stock at checkout, permissions): browser `no-cache`; shared cache only if event-purged and the commit path re-reads the source of truth. **Seconds–minutes** (fronts, listings, scores): browser `no-cache`/`max-age=0`; shared `max-age=S, stale-while-revalidate≈10·S, stale-if-error=86400` via the CDN-targeted header; 1–10 s micro-cache on hot dynamic routes. **Hours–days** (articles, docs, product copy): long shared TTL plus tag purge on publish; browser `no-cache`. |
| 5 | Event-driven invalidation available (tag purge, `revalidateTag`, CMS webhook, CDC)? | **Yes:** long shared TTL + purge on change; prefer soft purge with an `ETag` so revalidation returns 304. **No:** shared TTL ≤ S, plus SWR and SIE. |
| 6 | How many variants per URL? | Allow-list query params, strip `utm_*`/`fbclid`/`gclid`, sort params; normalize `Accept-Language` and image `Accept` to a few buckets; never `Vary: Cookie` or `Vary: User-Agent`. If variants per URL far exceed requests per TTL window, cache a lower layer (data, fragments) instead. |
| 7 | Read is both hot (Zipf head) and expensive (slow query, fan-out, third-party or LLM call)? | Cache-aside in L2 with jittered TTL ≤ S, single-flight, SWR; add L1 (1–5 s) for the hottest keys. Cold tail or cheap: don't cache; fix the query or index. |
| 8 | Does the writer need to read their own write? | Write-through, or delete-on-write plus "bypass cache / read primary for N seconds after write" for that session. |
| 9 | What happens when the cache or the origin fails? | Cache is optional behind timeouts and a circuit breaker; serve SIE at the CDN; define degraded behavior; size the DB for a degraded hit ratio. |

Steps 1 and 2 are the safety gate. If a route is uncertain at step 2, treat it as personalized until the code proves otherwise.

## Data-class matrix

Starting points. Check every TTL against the route's staleness budget. Identifiers match `data_class` in `assets/plan.schema.json` and the rows of `assets/policy-defaults.csv`.

| Data class | Browser `Cache-Control` | Shared cache (CDN/proxy) | App cache | Invalidation | Main risk |
|---|---|---|---|---|---|
| `fingerprinted-asset` | `public, max-age=31536000, immutable` | Same | — | New URL per build; keep old builds deployed | `immutable` on an unhashed file |
| `fixed-url-asset` (favicon, manifest, robots, `/.well-known/*`) | `no-cache` + `ETag` | `max-age` 1 h–1 day | — | Purge on deploy | Long browser TTL can't be recalled |
| `service-worker-script` | `no-cache` | Short or none | — | Deploy | Stale SW pins old app versions |
| `public-html-stable` (docs, posts, marketing) | `no-cache` + `ETag` | 1 day–1 year, SWR 1 day, SIE 1 week | Framework data cache with tags | Publish webhook → tag purge | `Set-Cookie` on public pages kills caching |
| `public-html-volatile` (home, fronts, listings) | `no-cache` or `max-age=0` | 30–300 s, SWR 300–3600 s, SIE 1 day; micro-cache 1–10 s | Fragment cache with tags | Event purge + short TTL backstop | Stampede at expiry |
| `personalized` (dashboards, account, cart, user APIs) | `private, no-cache` + `ETag` | Bypass | Cache-aside keyed by tenant/user | Delete on write | Request collapse without `private`; cross-tenant keys |
| `sensitive` (payment, auth, tokens, PHI) | `no-store` | Bypass | None (or encrypted, per user, minimal TTL) | — | Disk persistence, logs |
| `public-api-reference` (catalog, config, countries) | `no-cache` + `ETag`, or `public, max-age=60–300` | Hours, with tags | Preload at startup or cache-aside | Purge on admin publish; versioned keys | Clients hard-coding long TTLs |
| `public-api-volatile` (price, stock, scores) | `no-cache` | 1–30 s, or none | Short TTL + events | Event-driven; re-check at commit | Overselling from cache |
| `search-listing` (search, faceted lists) | `no-cache` or `max-age=60` | Normalized popular queries only | Result cache for head queries | TTL + index-update events | Cardinality explosion |
| `mutation` | `no-store` | Never | Triggers invalidation | Emit tags/events | Missing invalidation |
| `realtime` (WebSocket/SSE, presence, live odds) | `no-store` | Never; cache only the bootstrap snapshot | In-memory state on sharded servers | Ops/CRDT updates | Treating live data as cacheable |
| `llm-output` (completions, embeddings, retrievals) | `private` or `no-store` | None | Exact-match, embedding, retrieval caches; semantic only for public FAQs | Model/prompt version in key | Semantic false positives, cross-user leaks |
| `media-segment` (VOD segments, uploads) | `max-age=31536000, immutable` | Same, behind shield; live manifests ≈ half a segment | — | New ID per change; purge on takedown | Max object size; private media needs signed URLs |
| `redirect` | 301/308: explicit `max-age=86400` first, raise later; 302/307: `no-store` | Same as browser | — | Change the rule; can't recall browser copies | Headerless 301 cached for a very long time |
| `error-response` | 404: `max-age=60`; 410: long; 5xx: `no-store` | 404 short; 5xx at most 5–10 s | Negative cache with short TTL | TTL | Cached 5xx; heuristic 404 caching during deploys |

## TTL ladder across tiers

- Browser TTL is the shortest, because browsers can't be purged. HTML and other fixed URLs get `no-cache` with a validator.
- Shared TTL can be the longest, but only when it's purgeable (tag purge, `revalidateTag`). Without purge, shared TTL ≤ S.
- App cache: L1 TTL < L2 TTL. L1 is per instance and drifts; keep it 1–60 s unless invalidated by pub/sub.
- Origin proxy behind a tag-purging CDN: 1–10 s micro-cache only, or it becomes a second invalidation problem.
- Jitter every app-cache TTL by about ±10% (e.g. 55–65 min for 1 h). Jitter fixes synchronized expiry, not a single hot key; see `references/core/stampede-failure.md`.
- Soft TTL (refresh after) and hard TTL (never serve after, except on error) map to SWR and SIE.
- Use `cacheLife` profile names as shared vocabulary when the app is Next.js (`seconds`, `minutes`, `hours`, `days`, `weeks`, `max`).

## Hit-ratio and ROI math

With hit ratio h, hit latency L_hit, miss latency L_miss (source fetch) and request rate R:

```text
effective_latency = h·L_hit + (1 − h)·(L_hit + L_miss)
origin_load      = (1 − h)·R
benefit/sec      ≈ R · h · (L_miss − L_hit)
```

Example: 1 ms Redis hit, 50 ms DB miss, h = 0.90 → 6 ms average and 10× fewer DB reads. Going from 0.90 to 0.99 cuts DB reads another 10×. Run `python scripts/size_cache.py --rps R --hit-ratio h --hit-ms A --miss-ms B` instead of doing it by hand.

Cache only when the benefit is material, the TTL fits S, and a safe key exists. If the miss is slow because of a missing index or N+1, fix that first.

## Rollout order by ROI

Default order; reorder by the audit's findings. Every phase gets a canary and a load test, because adding a cache can move the bottleneck (Azure saw front ends return 503s).

| Phase | Work | Risk |
|---|---|---|
| 0 | Safety: remove shared caching of personalized/sensitive responses; strip `Set-Cookie` from public cached responses | Low |
| 1 | Hashed static assets with `immutable`; keep previous builds' assets | Low |
| 2 | Explicit `Cache-Control` on every response (default `no-store`, routes opt in) plus validators | Low |
| 3 | CDN for public HTML/API: targeted headers with SWR and SIE, tag purge, key normalization | Medium |
| 4 | bfcache (drop needless `no-store`, remove `unload`) and speculation rules | Low |
| 5 | App caching for measured hot, expensive reads (cache-aside, jitter, single-flight, L1+L2) | Medium |
| 6 | API ETags/304s and client query caches | Low |
| 7 | Origin shield, `No-Vary-Search`, service workers, edge KV, micro-caching | Medium |
| ∥ | Build/CI caching (parallel track; see `references/layers/build-ci-network.md`) | Low |

## When not to cache

Mutations; one-time tokens and OTPs; payment and auth flows; data with legal freshness requirements; truly unique per-request responses; low-traffic internal tools where cost and complexity outweigh benefit; anything the team cannot invalidate or observe; workloads where most requests would miss; and any cache that would become the only copy of critical data.

## Anti-pattern catalog

| Anti-pattern | Detection signal | Fix |
|---|---|---|
| Personalized HTML/API at the CDN | Shared HIT on routes reading cookies/session; `s-maxage` on authenticated routes; `Set-Cookie` on a cached response | `private`; split shell/island; CDN bypass on session cookie |
| Web cache deception/poisoning | CDN caches by extension; reflected unkeyed headers | See `references/core/security.md` |
| One TTL for everything | Single global `expires`/`max-age` | Per-class matrix |
| Short `max-age` on unhashed, interdependent assets | `max-age=600` on `app.js` | Fingerprint + `immutable`; HTML `no-cache` |
| Caching to hide slow queries | Low hit ratio, p95 unchanged on misses | Index/batch first |
| Premature caching | No metrics, no hit/miss instrumentation | Measure first |
| Cache as source of truth | Data only in Redis | Persist to the DB |
| No stampede protection | Latency/DB spikes at TTL boundaries | Jitter, single-flight, SWR |
| Key without tenant/user scope | Keys like `report:42` in multi-tenant code | `t:{tenant}:` prefix |
| `Vary: Cookie` / `Vary: User-Agent` | Response headers | `private`, or bucketed variants |
| `no-store` on every page | Global middleware | `no-cache, private`; regain bfcache |
| Unbounded growth | No TTL; Redis `noeviction` OOM errors | TTL + `allkeys-*` policy |
| Purge-everything on deploy | Origin spike after each deploy | Hashed assets need no purge; tag or soft purge |
| Cached errors | 5xx/404 with long TTL | Short negative TTLs; SIE instead |
| Query-string chaos | Keys differing only by `utm_*` | Key normalization; `No-Vary-Search` |

## Plan row requirements

Every row in the plan states: route pattern and methods, data class, audience, staleness budget, browser `Cache-Control`, shared-cache layer and header, `Vary` and cache key, app-cache mechanism and key pattern, tags, invalidation trigger → mechanism → expected propagation time, decision step, owner, and a verification command. Rows whose answer is `no-store` still appear; they document the decision.

Fill `assets/caching-plan.template.md` for the human-readable plan and `plan.json` per `assets/plan.schema.json`, then run `python scripts/validate_plan.py plan.json` until it passes.

## Sources

- [RFC 9111 HTTP Caching](https://httpwg.org/specs/rfc9111.html)
- [MDN HTTP caching guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- [Jake Archibald, Caching best practices](https://jakearchibald.com/2016/caching-best-practices/)
- [Harry Roberts, Cache-Control for Civilians](https://csswizardry.com/2019/03/cache-control-for-civilians/)
- [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- [Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)
- [Azure Cache-Aside pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
- [Cloudflare BYPASS status change (2026-05-26)](https://developers.cloudflare.com/changelog/post/2026-05-26-bypass-status-for-uncacheable-responses/)
- [web.dev TTFB](https://web.dev/articles/ttfb)
- [csswizardry, Cache Grab (CrUX navigation types)](https://csswizardry.com/2024/08/cache-grab-how-much-are-you-leaving-on-the-table/)
- [Vercel vercel-optimize CDN cache safety rules](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md)
