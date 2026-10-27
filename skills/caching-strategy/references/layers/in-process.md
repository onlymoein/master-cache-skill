# In-process caches and caching patterns

Last reviewed: 2026-10-27 · Applies to: Caffeine (JVM), Otter v2 / Ristretto v2 (Go), Moka (Rust), lru-cache v11 / cacheable (Node), cachetools / functools (Python), .NET IMemoryCache / HybridCache L1, Cachex (Elixir)

## Contents

- When to read this
- Pattern selection
- Default recipe per runtime
- Rules and gotchas
- Eviction algorithms
- Multi-tier (L1 + L2)
- Version notes
- Verify
- Sources

## When to read this

When the plan adds or reviews a server-side cache (decision tree step 7). Distributed L2 caches: `references/layers/distributed-cache.md`. Invalidation races: `references/core/invalidation-consistency.md`. Stampedes: `references/core/stampede-failure.md`.

## Pattern selection

| Situation | Pattern |
|---|---|
| Read-heavy, tolerates seconds–minutes of staleness | **Cache-aside** + TTL + jitter (default) |
| Writer must read its own write | Write DB, then **delete** the key (or write-through for read-heavy hot paths) |
| Bulk writes rarely re-read (imports, logs) | Write-around (write DB only; reads populate) |
| Hot key, expensive recompute | **Refresh-ahead** / SWR (`refreshAfterWrite` < `expireAfterWrite`, lru-cache `fetchMethod`) |
| High-rate counters (views, likes) where losing seconds is fine | Write-behind: `INCR` in Redis, idempotent batched flush |
| Same entity fetched many times in one request (GraphQL, N+1) | Request-scoped memoization (DataLoader per request), shared cache underneath |
| Expensive aggregate | Computed cache: materialized view, Redis ZSET/HASH, summary table (`references/layers/database-orm.md`) |
| Many views over the same rows | Object cache by ID (per-entity invalidation) over query-result caching |
| Personalized page with shared parts | Fragment cache for shared parts, object cache for per-user data |

Cache the highest reusable level (page > fragment > object > query result); higher levels are harder to invalidate. Write-behind makes the cache the system of record for a window: use it only where loss is acceptable, and prefer an app-owned queue/stream to vendor write-behind (Redis write-behind still depends on RedisGears, whose docs sit under a deprecated path).

## Default recipe per runtime

| Runtime | Default | Key config |
|---|---|---|
| JVM | Caffeine | `maximumSize`/`maximumWeight`, `expireAfterWrite`, `refreshAfterWrite`, `recordStats()` |
| Go | Otter v2 (`github.com/maypok86/otter/v2`, Go 1.24+) | `MaximumSize`, `ExpiryCalculator`, `RefreshCalculator`, loader (dedupes concurrent loads) |
| Go (alt) | Ristretto v2 | Cost-based admission; a `Set` of a new item may be dropped; `Wait()` for read-after-set |
| Rust | Moka | `max_capacity` + `weigher`, `time_to_live`, `get_with` (single-flight init); wrap large values in `Arc` |
| Node | lru-cache v11 (single process) or `cacheable` (L1/L2 on Keyv) | Must set `max`, `maxSize` (+ `sizeCalculation`) or `ttl`; `fetchMethod` + `allowStale` for SWR |
| Python | `cachetools` (`TTLCache`, `LRUCache`) with a lock; `functools.lru_cache(maxsize=N)` for pure functions | Thread safety via `lock=` |
| .NET | `HybridCache` (L1 + optional L2) | `LocalCacheExpiration` < `Expiration` |
| Elixir | Cachex or Nebulex | See `references/frameworks/elixir.md` |

```java
LoadingCache<String, Product> products = Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(Duration.ofMinutes(5))     // hard bound
    .refreshAfterWrite(Duration.ofMinutes(1))    // async reload on next access; old value served meanwhile
    .recordStats()
    .build(productRepo::load);
```

```ts
import { LRUCache } from 'lru-cache'
const cache = new LRUCache<string, Buffer>({
  max: 50_000,
  maxSize: 256 * 1024 * 1024,
  sizeCalculation: (v) => v.byteLength || 1,
  ttl: 60_000,
  allowStale: true,
  fetchMethod: async (key, _stale, { signal }) => loadFromL2orDb(key, signal),
})
const v = await cache.fetch('product:42')
```

```go
c := otter.Must(&otter.Options[string, Product]{
    MaximumSize:       100_000,
    ExpiryCalculator:  otter.ExpiryWriting[string, Product](5 * time.Minute),
    RefreshCalculator: otter.RefreshWriting[string, Product](1 * time.Minute),
})
p, err := c.Get(ctx, "p:42", otter.LoaderFunc[string, Product](func(ctx context.Context, k string) (Product, error) {
    return repo.Load(ctx, k)
}))
```

```python
from cachetools import TTLCache, cached
import threading

@cached(cache=TTLCache(maxsize=10_000, ttl=60), lock=threading.Lock())
def get_rates(currency: str) -> dict: ...
```

Verify option names against the installed version (Otter v2 and Moka APIs have changed across majors).

## Rules and gotchas

1. Bound every cache by count and, for variable-size values, by bytes (`maximumWeight`, `maxSize` + `sizeCalculation`, Moka weigher). Count bounds alone are unsafe; object overhead is often 2–5× the payload.
2. lru-cache refuses to run unbounded without `max`, `maxSize` or `ttl`; TTL-only can still grow (warning) and expiry is lazy unless `ttlAutopurge`.
3. `functools.lru_cache(maxsize=None)` is unbounded; on instance methods it keeps `self` alive. cachetools caches aren't thread-safe without `lock=`.
4. Ristretto may silently drop a `Set`; never treat it as a store.
5. Each instance's L1 is a separate copy that drifts. Keep L1 TTL far below the L2/DB staleness budget (seconds to ~1 min); cache only immutable/versioned data indefinitely.
6. With N instances, cold-start misses are N× higher after deploys. In serverless, L1 hit ratio depends on instance reuse and can be near zero.
7. Never hand out mutable references from an in-process cache: copy, or use immutable types.
8. DataLoader instances are per request; never share one across users. Its batch function must return results in key order, same length (null/Error for missing). `clear(key)` after mutations.
9. Prefer delete-on-write over set-on-write; two concurrent setters can leave the older value.
10. Cache negative results ("not found") with a short TTL (10–60 s).

## Eviction algorithms

| Algorithm | Use | Notes |
|---|---|---|
| W-TinyLFU | Default when available | Near-optimal hit ratio; ~8 bytes/entry sketch; Caffeine, Otter v2 (adaptive), Moka (TinyLFU), Ristretto (TinyLFU + SampledLFU) |
| LRU | Recency-skewed workloads, simplicity | Polluted by scans and one-hit wonders |
| LFU | Stable long-term popularity | Slow to adapt |
| ARC | Mixed recency/frequency | 2× metadata for ghost entries |
| S3-FIFO | FIFO-only, lock-friendly, quick demotion | Few mature app-level libraries |
| SIEVE | Simplest strong performer (one queue + visited bit) | Easy to hand-roll |

Most cached objects are never reused; admission filters (TinyLFU) and quick demotion (S3-FIFO, SIEVE) beat plain LRU on real traces.

## Multi-tier (L1 + L2)

- Add L1 when hot keys have a high read:write ratio, L2 round-trip latency matters, or one Redis shard shows hot-key CPU/bandwidth spikes. Skip it for low-reuse per-user data.
- Always L1 TTL < L2 TTL, or L1 serves values older than anything in L2 after an invalidation.
- L1 invalidation options, cheapest first: short TTL only → versioned keys (`entity:id@version` with a tiny version lookup in L2) → pub/sub backplane (at-most-once, keep the TTL backstop) → Redis client-side caching (RESP3 tracking; `references/layers/distributed-cache.md`).
- Libraries that already do it: .NET HybridCache, FusionCache (backplane, fail-safe, eager refresh), Node `cacheable`, Jedis/redis-py client-side caching. Spring's `CompositeCacheManager` doesn't tier (it returns the first manager that has the named cache).

```ts
// Hand-rolled L1 + L2 with pub/sub invalidation (Node)
const l1 = new LRUCache<string, unknown>({ max: 10_000, ttl: 30_000 })
const sub = redis.duplicate(); await sub.connect()
await sub.subscribe('cache:invalidate', (key) => l1.delete(key))

export async function invalidate(key: string) {
  await redis.del(key)
  await redis.publish('cache:invalidate', key)
}
```

Full cache-aside helper with jitter, single-flight, SWR and negative caching: `assets/snippets/app/cache-aside.ts` and `assets/snippets/app/cache_aside.py`.

## Version notes

- lru-cache v11, Otter v2, Ristretto v2 (generics), Moka 0.12 (no background threads) are current. Moka's roadmap still lists W-TinyLFU.

<details><summary>Old patterns</summary>

- Guava `CacheBuilder` (use Caffeine).
- `node-cache`/`memory-cache` without size bounds.
- Unbounded module-level `dict`/`Map` caches.

</details>

## Verify

- Expose hit/miss/eviction stats (`recordStats()`, `cache.stats()`, lru-cache counters) as metrics per cache name.
- Load test: memory stays within the bound; hit ratio per key class matches the estimate from `scripts/size_cache.py`.
- Multi-instance: update an entity, then read it from every instance within the L1 TTL; staleness never exceeds the TTL.

## Sources

- [Caffeine wiki: Efficiency](https://github.com/ben-manes/caffeine/wiki/Efficiency)
- [Caffeine wiki: Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh)
- [maypok86/otter](https://github.com/maypok86/otter)
- [Ristretto](https://github.com/hypermodeinc/ristretto)
- [moka-rs/moka](https://github.com/moka-rs/moka)
- [isaacs/node-lru-cache](https://github.com/isaacs/node-lru-cache)
- [jaredwray/cacheable](https://github.com/jaredwray/cacheable)
- [tkem/cachetools](https://github.com/tkem/cachetools)
- [graphql/dataloader](https://github.com/graphql/dataloader)
- [S3-FIFO (SOSP 2023)](https://junchengyang.com/publication/sosp23-s3fifo.pdf)
- [SIEVE (NSDI 2024)](https://junchengyang.com/slides/nsdi24-SIEVE.pdf)
