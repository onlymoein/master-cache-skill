# Stampedes and failure modes

Last reviewed: 2026-10-27 · Applies to: app caches, CDNs and proxies; Go singleflight, Caffeine, FusionCache, Rails, Varnish, nginx

## Contents

- When to read this
- Default recipe
- Rules and gotchas
- Stampede defenses
- Failure-mode table
- Negative caching and errors
- Cache down: fail open vs closed
- Warming and cold starts
- Incident lessons
- Verify
- Sources

## When to read this

Whenever the plan adds a cache that protects an expensive source, or the app shows latency/DB spikes at TTL boundaries, after deploys, or when the cache is unavailable. Most of these are capacity failures: the database is sized for the healthy hit ratio, and anything that drops it overloads the database.

## Default recipe

For every cache-miss loader:

1. In-process **single-flight** (one load per key per process).
2. **Soft TTL + SWR** (serve stale while one request refreshes) and **SIE** (serve stale on errors).
3. **TTL jitter** (±10%).
4. **Timeouts + circuit breaker** on the cache client; the fallback path to the DB is concurrency-limited.
5. Add a **distributed lease/lock** only when N processes × one load each is still too much, or a load is very expensive (seconds, paid API).

Ready-made helpers: `assets/snippets/app/cache-aside.ts`, `assets/snippets/app/cache_aside.py`, `assets/snippets/app/singleflight.go`, `assets/snippets/app/xfetch.py`.

## Rules and gotchas

1. **An error is not a miss.** Never delete or overwrite cache entries because a backend failed (Facebook 2010). Keep the old value, mark it stale, serve it.
2. Never cache errors as data. If you cache errors to protect a dependency, use a separate namespace and a very short TTL.
3. `stale-if-error` covers 500, 502, 503 and 504 only (not 404).
4. Single-flight: remove the in-flight promise on success **and** failure, or a rejection is memoized forever. A hung loader blocks all waiters: add a timeout (`DoChan` + context in Go) and `Forget` the key on timeout.
5. Locks always expire (TTL slightly above p99 load time); waiters serve stale or poll briefly, never block unboundedly; release only if you own the lock (compare-and-delete).
6. Rails `race_condition_ttl` reduces dogpiles at expiry but doesn't stop cold-cache stampedes (no lock before the write).
7. Coalescing only works if identical requests reach the same place: route by key (consistent hashing, CDN shield/tiered cache).
8. At the CDN/proxy, mark uncacheable responses explicitly (`private`/`no-store`, Varnish hit-for-pass/hit-for-miss) so requests don't queue behind a fetch that won't be cached.
9. Automations that mutate cache state (node replacement, auto-correction, purgers) need rate limits, blast-radius caps and kill switches (Slack 2022, Facebook 2010).
10. Retries multiply load: retry budgets, exponential backoff with jitter, no inline retries on the cache read hot path.

## Stampede defenses

| Defense | Use when | Implementation |
|---|---|---|
| Single-flight / promise memoization | Always | Go `golang.org/x/sync/singleflight`; JS in-flight `Map`; Caffeine/Otter/Moka loaders dedupe; .NET HybridCache, FusionCache |
| Soft TTL + SWR / refresh-ahead | Hot key, staleness of seconds acceptable | Caffeine `refreshAfterWrite` < `expireAfterWrite`; FusionCache eager refresh; lru-cache `fetchMethod` + `allowStale`; HTTP `stale-while-revalidate`; Varnish grace |
| XFetch (probabilistic early expiration) | Can't keep stale copies; recompute is expensive | Recompute if `now − delta·beta·ln(rand()) ≥ expiry`; `delta` = measured recompute time, `beta` = 1.0 (> 1 refreshes earlier) |
| Distributed lease/lock | Large fleets or very expensive loads | `SET lock:{key} token NX PX …`, stale fallback for waiters; Facebook leases (one per key per 10 s) |
| Request collapsing at the edge | Public content | On by default at Cloudflare zone cache, Fastly, Varnish; `proxy_cache_lock` in nginx; `requestCoalescing` on Google Cloud CDN; not on the Cloudflare Workers Cache API |
| Route by key | Coalescing must be global | Consistent hashing to an instance (Discord: p99 reads ≈ 15 ms vs 40–125 ms before) |
| Scheduled refresh | Small set of very hot keys (home page, top-N, config) | Background job refreshes before expiry |

```ts
// Promise memoization (TypeScript)
const inflight = new Map<string, Promise<unknown>>()

export async function cached<T>(key: string, ttlMs: number, load: () => Promise<T>): Promise<T> {
  const hit = await cache.get<T>(key)
  if (hit !== undefined) return hit
  let p = inflight.get(key) as Promise<T> | undefined
  if (!p) {
    p = load()
      .then(async (v) => { await cache.set(key, v, Math.round(ttlMs * (0.9 + Math.random() * 0.2))); return v })
      .finally(() => inflight.delete(key))
    inflight.set(key, p)
  }
  return p
}
```

```python
# XFetch
import math, random, time

def xfetch(key, recompute, ttl, beta=1.0):
    entry = cache.get(key)                       # (value, delta, expiry)
    now = time.time()
    if entry is None or now - entry.delta * beta * math.log(random.random() or 1e-12) >= entry.expiry:
        start = time.time()
        value = recompute()
        cache.set(key, Entry(value, time.time() - start, now + ttl), ttl=ttl)
        return value
    return entry.value
```

## Failure-mode table

| Failure | Trigger | Defenses |
|---|---|---|
| Avalanche | Many keys share an expiry (bulk load, deploy, fixed TTL); node or cluster lost | TTL jitter; soft TTL + SWR; staggered warm-up; DB concurrency limits; gutter pool |
| Penetration | Requests for IDs that don't exist (bots, enumeration, bugs) | Short-TTL negative cache with a sentinel; Bloom filter of valid IDs; input validation; per-client rate limits |
| Breakdown | One very hot key expires | Single-flight + SWR; XFetch; scheduled refresh for top-N keys |
| Hot key | One key saturates one shard | In-process L1 (1–5 s TTL); key splitting `k#0..N`; replicas; CDN for public data |
| Big key | Multi-MB values, huge collections | Chunk/page; cache projections; compress; delete with `UNLINK` |
| Cold start | New key prefix, new region/cluster, flush, failover | Warm from a warm peer; pre-warm top-N from access logs; ramp traffic 1% → 10% → 50% → 100%; prefix-bump gradually, never flush |
| Cache down | Cluster unreachable or slow | Millisecond timeouts; circuit breaker; fail open only into a coalesced, concurrency-limited DB path; serve stale L1; shed non-critical traffic |
| Retry storm | Clients retry cache/DB failures | Retry budgets; backoff + jitter; errors ≠ misses |
| CDN outage | The CDN itself fails (Fastly 2021: ~85% of network, 49 min to recover) | Know whether the origin can take direct traffic; multi-CDN or DNS failover; CDN config in version control |

## Negative caching and errors

| Response | Policy |
|---|---|
| Not found (app cache) | Store a sentinel (`__NEG__`), not `null`; TTL 10–120 s jittered; delete on create (and add to the Bloom filter) |
| Empty collections | Cache like positive results, shorter TTL if new items appear often |
| 404 (HTTP) | `max-age=60` at the CDN if bots hammer missing URLs; purge on creation |
| 410 | Can be cached longer |
| 5xx | `no-store`; let SIE serve the previous 200 |
| 429/503 | `Retry-After`; never cached as content |

## Cache down: fail open vs closed

- **Fail open** (treat as miss, go to source) only if the source survives the full miss rate, or the path is guarded by single-flight plus a concurrency limiter/circuit breaker. Otherwise you move the outage to the database.
- **Fail closed / degrade** (stale L1, static fallback, 503 + `Retry-After`) for expensive or non-critical data.
- Security caches (sessions, authorization decisions, rate-limit counters): decide explicitly. Failing open on a rate limiter or permission cache can be a security bug.
- Facebook's "gutter pool" (~1% of servers, short TTLs) absorbs a failed node's traffic instead of rehashing it onto healthy nodes.

```python
def read(key, loader):
    if breaker.is_open():
        return guarded_db(key, loader)
    try:
        v = cache.get(key, timeout_ms=5)
        breaker.record_success()
        if v is not None:
            return v
    except (TimeoutError, ConnectionError):
        breaker.record_failure()                 # no inline retry
    return guarded_db(key, loader)

def guarded_db(key, loader):
    if not db_limiter.try_acquire():
        stale = l1.get_stale(key)
        if stale is not None:
            return stale
        raise Overloaded()                       # 503 + Retry-After
    try:
        return singleflight(key, loader)
    finally:
        db_limiter.release()
```

## Warming and cold starts

- Avoid global cold starts: roll key-format changes per host or percentage, or read through from the old prefix and copy forward on miss.
- New cluster/region: warm from a warm peer (Netflix EVCache and Facebook do this), replay top-N keys, shift traffic gradually while watching DB load.
- Capacity-plan the database for a degraded hit ratio (e.g. 80% instead of 98%), and rehearse "cache cluster lost" in game days.
- Per-deploy caches (Next.js `'use cache'`, Cloudflare Workers Caching by version) start cold on every deploy: pre-warm critical routes or share across versions.

## Incident lessons

| Incident | What happened | Rule |
|---|---|---|
| Facebook, 2010-09-23 | Clients treated DB errors as invalid values and deleted cache keys; a feedback loop kept the DB down ~2.5 h | Errors aren't misses; never delete on backend failure; kill switches on automation |
| Steam, 2015-12-25 | A CDN config change under DoS enabled caching for authenticated users; ~34,000 users' pages may have been served to others | Authenticated responses carry `private`/`no-store` at the origin, whatever the CDN rules |
| Slack, 2022-02-22 | Control plane replaced warm memcached nodes with empty spares during a Consul restart; hit ratio collapsed at peak; databases overloaded | Rate-limit node replacement; health-check the cache itself; size DB for degraded hit ratio |
| Meta TAO, 2022 | Rare races in versioned fills and error handlers left stale values indefinitely | Atomic value+version fills; measure consistency in production |
| Fastly, 2021-06-08 | Latent bug triggered by a valid config; ~85% of the network down | Plan for CDN failure |
| Railway, 2026-03-30 | Caching enabled on CDN-off domains for 52 min; headerless GET responses cached by default | Explicit `Cache-Control` on every response; global purge runbook |

## Verify

- Load test from a cold cache with a spike on one hot key: origin requests per key stay at ~1 per process (single-flight) or ~1 globally (lease/collapsing).
- Chaos test: kill Redis/Valkey; latency stays bounded, DB concurrency stays under its limit, errors are 503 with `Retry-After` rather than timeouts.
- Expire 10,000 keys at once in staging; DB load stays flat thanks to jitter.
- Request a nonexistent ID 1,000 times; the DB sees one query per negative TTL window.

## Sources

- [Go singleflight](https://pkg.go.dev/golang.org/x/sync/singleflight)
- [XFetch (Vattani et al., VLDB 2015) — xfetch crate](https://docs.rs/xfetch/)
- [Caffeine: Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh)
- [FusionCache timeouts and fail-safe](https://github.com/ZiggyCreatures/FusionCache/blob/main/docs/Timeouts.md)
- [Varnish: increasing your hit rate](https://www.varnish.org/docs/users-guide/increasing-your-hitrate/)
- [Kit Engineering: cache stampede](https://engineering.kit.com/2019/10/29/we-built-our-own-cache/)
- [Facebook: more details on today's outage (2010)](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/)
- [SteamDB: caching issues on Steam (2015)](https://steamdb.info/blog/recent-caching-issues-on-steam)
- [Slack: incident on 2-22-22](https://slack.engineering/slacks-incident-on-2-22-22/)
- [Fastly: summary of June 8 outage](https://www.fastly.com/blog/summary-of-june-8-outage)
- [Railway incident report (2026-03-30)](https://blog.railway.com/p/incident-report-march-30-2026-authenticated-user-data-cached)
- [InfoQ: Discord request coalescing](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)
