# Server-Side Application & Data-Layer Caching (state as of October 2026)

> Scope note: cache invalidation strategy and stampede protection are covered in depth by another researcher. They appear here only where a library or pattern bundles them.
> Research method note: in this session WebFetch could reach github.com but not redis.io, docs.aws.amazon.com or developers.openai.com (DNS/proxy failures). Facts about those sites come from search-result summaries of the official pages. Anthropic prompt-caching facts come from the bundled `claude-api` skill reference (`shared/prompt-caching.md`, cached 2026-10-06), which mirrors platform.claude.com docs. Code sketches are the researcher's illustrations, not quotations. Verify API signatures before copying them.

---

## 1. Caching patterns and when to use each (cache-aside, read-through, write-through, write-behind, write-around, refresh-ahead, request-scoped memoization, computed caches, page/fragment/object/query caching)

### Takeaway
Use cache-aside with a TTL as the default. Add write-through, or better "write then delete", only for data that is read right after it is written. Use refresh-ahead (Caffeine `refreshAfterWrite`, lru-cache `fetchMethod`, FusionCache eager refresh) for hot keys where a miss is expensive. Write-behind is the only pattern here that risks losing data, so reserve it for counters and analytics-style writes. Request-scoped memoization (DataLoader) complements a shared cache and does not replace it. Cache the highest level that is still reusable: a page or fragment beats an object, and an object beats a query result. The trade-off is that higher levels are harder to invalidate.

### Cited Findings
- AWS's whitepaper "Database Caching Strategies Using Redis" names two core approaches. Cache-aside / lazy loading is the reactive one: on a miss the app reads the database and populates the cache, so the cache holds only data that was requested. Write-through is the proactive one: the cache is updated when the primary database is updated. — [AWS whitepaper: Caching patterns](https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-using-redis/caching-patterns.html)
- The AWS whitepaper is marked "for historical reference only" (published March 8, 2021), so it is a sound conceptual base but not current product guidance. — [AWS whitepaper PDF](https://docs.aws.amazon.com/pdfs/whitepapers/latest/database-caching-strategies-using-redis/database-caching-strategies-using-redis.pdf)
- Write-through fills memory with data that is never read. The usual fix is a TTL on every write, which combines the benefits of both patterns. AWS typically pairs write-through with lazy loading, which adds churn because rarely requested data also gets written. — [Upstash: Redis Caching Patterns 2026](https://upstash.com/blog/redis-caching-patterns-2026.md); [AWS whitepaper](https://docs.aws.amazon.com/whitepapers/latest/database-caching-strategies-using-redis/caching-patterns.html)
- AWS recommends setting TTLs on keys and adding randomness (jitter) to TTLs so keys don't all expire in the same window. — [AWS ElastiCache: Managing reserved memory / best practices](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html)
- **Write-behind in the Redis ecosystem.** Redis's write-behind "captures any changes to a selected set of key patterns in a Redis keyspace and asynchronously writes them in small batches to the downstream database". Its install docs (updated April 2026) still require the RedisGears module, yet RedisGears v1 docs now sit under a "deprecated-features" path. Flag this as an uncertain support timeline. — [Redis write-behind architecture](https://redis.io/docs/latest/integrate/write-behind/architecture/); [Install RedisGears for RDI](https://redis.io/docs/latest/integrate/write-behind/installation/install-redis-gears/); [RedisGears v1 deprecated path](https://redis.io/docs/latest/operate/oss_and_stack/stack-with-enterprise/deprecated-features/gears-v1/index.json)
- The older rgsync write-behind recipe used a synchronous function to capture writes in order and an asynchronous one to push them to the target, "so changes events are recorded in order and to eliminate the possibility of losing events in case of failure". — [rgsync on PyPI](https://pypi.org/project/rgsync)
- **Refresh-ahead (Caffeine).** `expireAfterWrite` removes the entry, so the next read blocks on a load. `refreshAfterWrite` only makes the entry *eligible* for refresh. The refresh starts when the entry is next queried, runs asynchronously on an Executor (default `ForkJoinPool.commonPool()`), and "the old value (if any) is still returned while the key is being refreshed". If the refresh fails, "the old value is kept and the exception is logged". The recommended setup combines both settings, for example `maximumSize(10_000)`, `expireAfterWrite(5 min)` and `refreshAfterWrite(1 min)`, so hot entries stay fresh and cold ones expire. — [Caffeine wiki: Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh)
- **Refresh-ahead (Node lru-cache).** `fetchMethod` is an async method used by `cache.fetch()` for "stale-while-revalidate type of behavior". — [isaacs/node-lru-cache README](https://github.com/isaacs/node-lru-cache)
- **Request-scoped memoization (DataLoader).** DataLoader "will coalesce all individual loads which occur within a single frame of execution" into one batch call. The batch function must return an array "the same length as the Array of keys", in key order, with `null` or an `Error` for missing items. "DataLoader caching does not replace Redis, Memcache, or any other shared application-level cache." Instances "are created when a Request begins, and are not used once the Request ends". Avoid sharing one instance across users. Call `clear(key)` after mutations. `prime(key, value)` seeds the cache, and `cacheKeyFn` normalizes object keys. — [graphql/dataloader README](https://github.com/graphql/dataloader)
- **Computed or derived caches at the database layer.** Postgres `REFRESH MATERIALIZED VIEW CONCURRENTLY` refreshes "without locking out concurrent selects" and needs at least one unique index on the matview. pg_ivm provides incremental view maintenance ("only incremental changes are computed and applied") for PG 13–17, but its `refresh_immv` takes an AccessExclusiveLock. — [pgEdge PG17 docs: REFRESH MATERIALIZED VIEW](https://docs.pgedge.com/postgresql/v17/reference/sql-commands/refresh-materialized-view/); [pg_ivm GitHub](https://github.com/sraoss/pg_ivm); [Tantor pg_ivm docs](https://docs.tantorlabs.ru/tdb/en/17_9/se/pg_ivm.html)
- **Query-result caching at a proxy.** Readyset keeps cached query results current from the database's replication stream ("deep", dataflow-based caches) and also offers "shallow" TTL-based caches. Apps switch by changing the connection string, and only the queries you choose are cached. — [Readyset Docs](https://readyset.io/docs/)
- **Framework-level fragment and data caching (Next.js 16 / Vercel).** `'use cache'` is in-memory by default ("ephemeral, and disappears when the instance that served the request is shut down"). `'use cache: remote'` stores output in a remote cache such as Vercel Runtime Cache and requires `cacheComponents`. `cacheTag` and `cacheLife` come from `next/cache`. — [Vercel docs: Runtime Cache](https://vercel.com/docs/runtime-cache)
- **Stampede protection is built into several libraries** (detail belongs to the other researcher). Facebook's memcache "leases" let "only the first client that misses … ask MySQL for the latest data", with leases issued at most once every 10 seconds per key. Peak DB query rate reportedly fell from 17K/s to 1.3K/s. — [MIT 6.824 memcache FAQ](https://pdos.csail.mit.edu/6.824/papers/memcache-faq.txt); [Engineer's Codex summary](https://read.engineerscodex.com/p/how-facebook-scaled-memcached)

### Inferences
**Decision rules (synthesized):**

| Situation | Pattern |
|---|---|
| Read-heavy, tolerant of seconds to minutes of staleness, unknown access set | Cache-aside + TTL + jitter (default) |
| Must read your own write immediately after mutation | Write-through, or more simply "write DB, then DELETE cache key" (write-around + invalidate). Deleting is safer than setting because it avoids racing stale writes. |
| Bulk-written data that is rarely re-read (logs, imports) | Write-around: write the DB only and let reads populate |
| Hot key, expensive recompute, staleness OK for one refresh interval | Refresh-ahead / stale-while-revalidate (`refreshAfterWrite` < `expireAfterWrite`) |
| High-rate counters, likes, view counts where losing a few seconds is OK | Write-behind (INCR in Redis, periodic flush) with an idempotent, batched flusher |
| Same entity fetched many times in one request (GraphQL, N+1) | Request-scoped DataLoader / memo, then shared cache underneath |
| Expensive aggregate over many rows | Computed cache: materialized view, precomputed Redis ZSET/HASH, or a summary table updated by job or CDC |
| Mostly anonymous traffic, identical HTML | Full-page cache at CDN/reverse proxy (HTTP caching researcher covers this) |
| Personalized page with shared parts | Fragment cache for the shared parts, object cache for per-user data |
| Many different views over the same rows | Object cache (entity by ID) rather than query-result cache, because invalidation is per-entity |
| Query results that are expensive and stable (reports, search facets) | Query-result cache keyed by normalized query + params hash + schema version |

- Write-behind turns the cache into the system of record for a window of time. Apply it only to data where the cache is configured durable (AOF) or loss is acceptable. Given the RedisGears deprecation signal, prefer an app-owned queue or stream (Redis Streams, Kafka, SQS) to vendor write-behind.
- Prefer "delete on write" to "set on write" in cache-aside. Two concurrent writers that each SET can leave the older value in cache. DELETE converges on the next read. Remaining read/write races are what leases solve (other researcher).
- Cache negative results ("not found") with a short TTL to stop repeated misses for nonexistent IDs from hammering the DB (prior knowledge; no source retrieved this session).

#### Code sketches
```ts
// Cache-aside with jittered TTL + negative caching (node-redis v4+/ioredis style)
async function getUser(id: string): Promise<User | null> {
  const key = `app:v3:user:${id}`;                 // namespace + schema version
  const hit = await redis.get(key);
  if (hit !== null) return hit === "__nil__" ? null : JSON.parse(hit);
  const row = await db.user.findUnique({ where: { id } });
  const ttl = row ? 300 : 30;                       // short TTL for negatives
  const jitter = Math.floor(Math.random() * ttl * 0.1);
  await redis.set(key, row ? JSON.stringify(row) : "__nil__", { EX: ttl + jitter });
  return row;
}
// Write path: write DB, then delete (not set) the key
async function updateUser(id: string, patch: Partial<User>) {
  await db.user.update({ where: { id }, data: patch });
  await redis.del(`app:v3:user:${id}`);
}
```
```java
// Read-through + refresh-ahead (Caffeine LoadingCache)
LoadingCache<String, Product> products = Caffeine.newBuilder()
    .maximumSize(10_000)
    .expireAfterWrite(Duration.ofMinutes(5))   // hard staleness bound
    .refreshAfterWrite(Duration.ofMinutes(1))  // async reload on next access; old value served meanwhile
    .recordStats()
    .build(id -> productRepo.load(id));
```
```python
# Write-through (sync): DB is the source of truth; cache updated in the same request
def save_price(sku: str, price: int):
    with db.transaction():
        db.execute("UPDATE prices SET price=%s WHERE sku=%s", (price, sku))
    r.set(f"app:v1:price:{sku}", price, ex=3600)   # after commit; TTL guards against drift
```
```python
# Write-behind for counters: INCR in Redis, flush periodically (idempotent upsert)
r.hincrby("app:views:pending", post_id, 1)
def flush():                                       # cron/worker every N seconds
    pending = r.hgetall("app:views:pending"); r.delete("app:views:pending")  # use RENAME/Lua for atomic swap in prod
    db.executemany("UPDATE posts SET views = views + %s WHERE id=%s",
                   [(int(v), k) for k, v in pending.items()])
```
```ts
// Request-scoped memoization: new DataLoader per request
app.use((req, _res, next) => {
  req.loaders = {
    user: new DataLoader<string, User | null>(async (ids) => {
      const rows = await db.user.findMany({ where: { id: { in: [...ids] } } });
      const byId = new Map(rows.map(r => [r.id, r]));
      return ids.map(id => byId.get(id) ?? null);   // same length, same order
    }),
  };
  next();
});
```
```sql
-- Computed cache: materialized view refreshed without blocking readers
CREATE MATERIALIZED VIEW daily_revenue AS
  SELECT date_trunc('day', created_at) d, sum(amount) total FROM orders GROUP BY 1;
CREATE UNIQUE INDEX ON daily_revenue (d);          -- required for CONCURRENTLY
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_revenue;  -- schedule via cron/pg_cron
```

### Gaps
- I could not retrieve the AWS whitepaper's own TTL guidance text (fetch blocked).
- I found no authoritative 2026 source comparing refresh-ahead implementations across ecosystems, or one on write-behind durability guarantees outside Redis.
- The engineering blogs from Discord, Shopify, Stripe and Uber suggested in the brief were not retrieved. No citable 2025–2026 architecture details from them are included.

---

## 2. In-process caches (libraries, eviction algorithms, memory bounds, per-instance inconsistency)

### Takeaway
Use a bounded, frequency-aware local cache for each runtime: Caffeine (JVM), Otter v2 (Go), Moka (Rust), lru-cache v11 (Node), cachetools or a bounded `functools.lru_cache` (Python). Modern admission and eviction (W-TinyLFU, S3-FIFO, SIEVE) beats plain LRU on real traces because most objects are one-hit wonders. Always bound by count *and* bytes where possible. Treat each instance's cache as a separate, possibly divergent copy: keep TTLs short or add a pub/sub invalidation backplane once you run more than one instance.

### Cited Findings
- **Caffeine / W-TinyLFU design.** A small LRU "admission window" feeds a large Segmented LRU main space. TinyLFU admits a candidate only if its estimated frequency beats the victim's. Frequency comes from a 4-bit CountMinSketch costing about 8 bytes per cache entry, with no ghost entries kept. Hill climbing adapts the window/main split as the workload shifts. W-TinyLFU "provides a near optimal hit rate", is "competitive with ARC and LIRS", and gives a "substantial improvement to LRU". ARC needs the cache size doubled for ghost keys and LIRS needs it tripled. — [Caffeine wiki: Efficiency](https://github.com/ben-manes/caffeine/wiki/Efficiency)
- **S3-FIFO (SOSP 2023,** "FIFO Queues are All You Need for Cache Eviction"). A small FIFO queue filters most objects out of the main cache, giving "guaranteed demotion speed and high demotion precision". It uses only FIFO queues and is reported as adopted by Google and VMware, among others. — [S3-FIFO paper (Yang et al.)](https://junchengyang.com/publication/sosp23-s3fifo.pdf); [slides](https://junchengyang.com/slides/sosp23-s3fifo.pdf)
- **SIEVE (NSDI 2024,** "SIEVE is Simpler than LRU", community award). It uses one FIFO list, a "hand" pointer scanning tail to head, and one visited bit per object, giving lazy promotion and quick demotion. Motivation: short request sequences hold more one-hit wonders than expected. — [SIEVE slides](https://junchengyang.com/slides/nsdi24-SIEVE.pdf); [USENIX NSDI'24 page](https://usenix.org/node/299212)
- **Node: lru-cache.** v11 is described as "one of the most performant LRU cache implementations" (April 2026). At least one of `max`, `ttl` or `maxSize` is required to prevent "unsafe unbounded storage". With `max`, storage is preallocated. With `maxSize`, every item needs a positive-integer size via `sizeCalculation`. "This is not primarily a TTL cache, and does not make strong TTL guarantees": expired items are purged lazily on next access unless `ttlAutopurge` is set. With only `ttl`, the cache can grow unbounded and prints a warning. The README advises avoiding `dispose`, size tracking and "especially ttl behavior" unless needed. For TTL-only caching it suggests `@isaacs/ttlcache`. — [isaacs/node-lru-cache](https://github.com/isaacs/node-lru-cache)
- **Node multi-tier.** The `cacheable` monorepo ("Caching for Nodejs based on Keyv") includes `cacheable` ("built from the ground up with layer 1 / layer 2 caching"), `cache-manager` (used by NestJS, with `wrap`) and `@cacheable/memory` (in-memory LRU). — [jaredwray/cacheable](https://github.com/jaredwray/cacheable)
- **Go: Otter v2** (`github.com/maypok86/otter/v2`, Go 1.24+). It offers "High hit rates across all workload types via adaptive W-TinyLFU", size-based eviction, expire-after-access or after-write, loaders whose concurrent `Get` calls "deduplicate loader calls", async refresh triggered by the first stale request, stats, and save/load to file. — [maypok86/otter](https://github.com/maypok86/otter)
- **Go: Ristretto v2** (`github.com/dgraph-io/ristretto/v2`, Go 1.21+, generics) uses TinyLFU admission (12 bits per counter), SampledLFU eviction and cost-based eviction. Gotcha: "a Set call for a new item (updates are guaranteed) isn't guaranteed to make it into the cache". Writes are buffered asynchronously, so call `cache.Wait()` if you need read-after-set. — [hypermodeinc/ristretto](https://github.com/hypermodeinc/ristretto)
- **Rust: Moka** ("inspired by Caffeine"). It uses TinyLFU (LFU admission plus LRU eviction); "Upgrade TinyLFU to Window-TinyLFU" is still listed on the roadmap. It provides `sync::Cache` and `future::Cache` (Tokio, async-std), TTL and TTI, per-entry variable expiry (v0.11+) and a `u32` weigher. "Weighted sizes are not used when making eviction selections." `get_with` / `try_get_with` give atomic per-key initialization. v0.12 removed background threads. `get` returns a clone, so wrap large values in `Arc`. — [moka-rs/moka](https://github.com/moka-rs/moka)
- **Python: cachetools** "provides various memoizing collections and decorators", including `LRUCache` and `TTLCache` used with `@cached(cache=...)`. — [tkem/cachetools](https://github.com/tkem/cachetools)
- **Per-instance inconsistency.** In Spring multi-level setups, a missed invalidation message (for example during pod startup) can leave stale L1 data. A short L1 TTL of about 30–60 s bounds this. Spring's `@Cacheable` and `@CacheEvict` don't coordinate by default (a race). — [DEV: When caches lie (Spring multi-instance)](https://dev.to/prasadmk/when-caches-lie-the-hidden-invalidation-traps-in-a-multi-instance-spring-boot-microservice-44pl)
- Next.js `'use cache'` (default) is per-instance in-memory and ephemeral, a concrete example of per-instance caches in serverless. — [Vercel docs: Runtime Cache](https://vercel.com/docs/runtime-cache)

### Inferences
**Algorithm cheat-sheet (synthesized from the papers above plus prior knowledge):**

| Algorithm | Strength | Weakness | Where you get it |
|---|---|---|---|
| LRU | Simple; good for recency-skewed workloads | Scan or one-hit-wonder pollution; lock on every hit | lru-cache (Node), `functools.lru_cache`, Guava legacy |
| LFU | Keeps long-term popular items | Slow to adapt; stale popularity | cachetools `LFUCache`, Redis `allkeys-lfu` (approximate) |
| ARC | Adapts recency/frequency | Ghost lists cost about 2x metadata; patent history | Some DBs (ZFS ARC) |
| W-TinyLFU | Near-optimal hit rate on many traces, low metadata (sketch) | More complex | Caffeine, Otter v2, Moka (TinyLFU), Ristretto (TinyLFU + SampledLFU) |
| S3-FIFO | FIFO-only (lock-free friendly), quick demotion of one-hit wonders | Newer; fewer mature app-level libraries | Research implementations; adopted internally at some companies |
| SIEVE | Simplest high performer: one queue + visited bit | Less adaptive on some recency-heavy traces (paper-dependent) | Small libraries; easy to hand-roll |

- **Default library picks for 2026:** JVM Caffeine; Go Otter v2 (Ristretto v2 if you need cost-based admission and can tolerate dropped Sets); Rust Moka; Node lru-cache v11 for a single process or `cacheable` for L1/L2; Python `cachetools` with an explicit lock, or `functools.lru_cache(maxsize=N)` for pure functions. .NET users get L1 from `HybridCache` (see §4).
- **Memory bounds:** count-based limits (`maximumSize`, `max`) are unsafe for variable-size values. Use weight or byte bounds (`maximumWeight` + weigher, lru-cache `maxSize` + `sizeCalculation`, Moka weigher). Estimate serialized size, not object graph size. JVM, V8 and CPython object overhead is often 2–5x the payload (prior knowledge; not measured this session).
- **Per-instance inconsistency rules:**
  1. L1 TTL should be far shorter than the L2/DB staleness budget (seconds to about 1 min).
  2. Only cache immutable or versioned data in L1 indefinitely.
  3. With N instances, the effective miss rate on cold start is N times higher. Expect a cold-start burst after deploys.
  4. In serverless, the L1 hit rate depends on instance reuse and can be near zero at low traffic.
- **Python gotchas (prior knowledge, not re-verified this session):**
  - `functools.lru_cache` on instance methods keeps `self` alive (a leak). Use `functools.cached_property` or a module-level cache keyed by ID.
  - `cachetools` caches are not thread-safe; pass `lock=threading.Lock()` to `@cached`.
  - `lru_cache(maxsize=None)` is unbounded.

#### Code sketches
```ts
// Node lru-cache v11: bounded by bytes + SWR fetch
import { LRUCache } from "lru-cache";
const cache = new LRUCache<string, Buffer>({
  max: 50_000,                      // count bound (preallocates)
  maxSize: 256 * 1024 * 1024,       // 256 MB byte bound
  sizeCalculation: (v) => v.byteLength || 1,
  ttl: 60_000, allowStale: true,    // serve stale while fetchMethod refreshes
  fetchMethod: async (key, stale, { signal }) => loadFromL2orDB(key, signal),
});
const v = await cache.fetch("product:42");
```
```go
// Go Otter v2: W-TinyLFU, loader dedupe, refresh-ahead
c := otter.Must(&otter.Options[string, Product]{
    MaximumSize:       100_000,
    ExpiryCalculator:  otter.ExpiryWriting[string, Product](5 * time.Minute),
    RefreshCalculator: otter.RefreshWriting[string, Product](1 * time.Minute),
})
p, err := c.Get(ctx, "p:42", otter.LoaderFunc[string, Product](func(ctx context.Context, k string) (Product, error) {
    return repo.Load(ctx, k)   // concurrent Gets for same key share one load
}))
```
```rust
// Rust Moka (future feature): TTL + weigher + single-flight init
let cache: moka::future::Cache<String, Arc<Vec<u8>>> = moka::future::Cache::builder()
    .max_capacity(512 * 1024 * 1024)
    .weigher(|_k, v: &Arc<Vec<u8>>| v.len().try_into().unwrap_or(u32::MAX))
    .time_to_live(Duration::from_secs(300))
    .build();
let v = cache.get_with(key.clone(), async { Arc::new(load(&key).await) }).await;
```
```python
# Python cachetools with lock (thread-safe) and TTL
from cachetools import TTLCache, cached
import threading
@cached(cache=TTLCache(maxsize=10_000, ttl=60), lock=threading.Lock())
def get_rates(currency: str) -> dict: ...
```

### Gaps
- I found no head-to-head 2025–2026 miss-ratio numbers comparing S3-FIFO and SIEVE with W-TinyLFU on app (not CDN) traces. The Caffeine efficiency page's charts are images without quoted numbers.
- I could not confirm whether Moka has shipped W-TinyLFU as of Oct 2026 (README roadmap still lists it).
- No official doc on cachetools thread-safety or `getsizeof` was retrieved (the README excerpt was minimal). The Python gotchas above are from prior knowledge.
- I found no production-grade S3-FIFO or SIEVE library for Node, Python or JVM application caching to recommend with citations.

---

## 3. Distributed caches (Redis vs Valkey and others, managed options, data structures, eviction, persistence, clustering, hot keys, serialization, key naming, TTLs, big values)

### Takeaway
As of Oct 2026, Valkey (BSD-3, Linux Foundation) is the default "open" Redis-compatible engine on AWS and GCP and is cheaper on ElastiCache. Redis 8.x is again OSI open source via an AGPLv3 option (tri-license RSALv2/SSPLv1/AGPLv3), bundles JSON, Search, time series, probabilistic structures and beta vector sets, and has new eviction policies. Many enterprises ban AGPL, which pushes them to Valkey. Azure is retiring Azure Cache for Redis in favor of Azure Managed Redis (Redis Enterprise based). Dragonfly is BSL (source-available). KeyDB has been quiet since v6.3.0. Garnet (MIT) is real but its cluster control plane is passive. For a cache, configure `maxmemory` plus an `allkeys-*` policy, keep values small (KBs, not MBs), namespace and version keys, jitter TTLs, and size against usable memory after reserved overhead.

### Cited Findings
**Licensing and project status**
- Redis license timeline: 7.2.x and prior are BSDv3. 7.4.x–7.8.x are RSALv2 or SSPLv1. "Version 8.0.x and subsequent releases are subject to the tri-license RSALv2/SSPLv1/AGPLv3 at your option." Redis CE was renamed "Redis Open Source" with v8.0. A full build includes JSON, time series, Bloom, cuckoo, count-min, top-k, t-digest and the Query Engine. Vector sets are a beta data type. The repo references 8.10.0 and 8.10.2 releases. — [redis/redis GitHub](https://github.com/redis/redis)
- License gotcha: Intel SVS-VAMANA optimizations (LeanVec/LVQ) for vector search "are only available with Redis Open Source under RSALv2". AGPLv3/SSPLv1 users cannot use them. — [redis/redis GitHub](https://github.com/redis/redis)
- Redis 8 (May 2025) added AGPLv3 as a third option, so Redis can again be called open source. Many companies keep blanket AGPL bans, which pushes them to Valkey. Blogs disagree on current version numbers (Redis 8.2/8.8/8.10.x; Valkey 9.1.1/9.1.2). — [Tacnode: Valkey vs Redis 2026](https://tacnode.io/post/valkey-vs-redis); [The Stack: Redis reverts to open source](https://www.thestack.technology/redis-reverts-to-open-source/); [Redis License Timeline](https://redisvsmemcached.com/redis-license-timeline/)
- One vendor-sourced claim says Valkey Docker Hub pulls passed 100M in May 2026, a 17x YoY jump (unverified). — [DEV: Valkey vs Redis in 2026](https://dev.to/jamilxt/valkey-vs-redis-in-2026-the-fork-quietly-won-most-of-the-market-2g0d)
- Valkey: BSD-3-Clause, "an open community project under LF Projects", forked just before Redis's relicensing. It has optional Zstandard compression for RDB streaming and replication, experimental RDMA, and a plugin system. — [valkey-io/valkey GitHub](https://github.com/valkey-io/valkey)
- **Valkey 9.0 (GA Oct 21, 2025):**
  - Features: multiple databases in cluster mode, atomic slot migration, hash field expiration.
  - Performance: up to 40% more throughput than 8.1, and 2,000 nodes / >1B requests/s.
  - Sources of the gains: memory prefetch for pipelining, zero-copy large responses, MPTCP, AVX-512.
  - Security: Lua RCE fixes and certificate-based TLS client auth.

  — [Linux Foundation press release](https://www.linuxfoundation.org/press/valkey-9.0-delivers-performance-and-resiliency-for-real-time-workloads); [Phoronix](https://phoronix.com/news/Valkey-9.0-Released); [The New Stack](https://thenewstack.io/valkey-9-0-debuts-multidatabase-clustering-for-massive-scale-workloads/)
- **Valkey 9.1:** redesigned I/O threading (up to 17% throughput), database-level ACLs, and a Lua engine moved to a separate module that can be disabled. Up to 2.1M req/s on a single server under specific benchmarks (vendor figure). — [Techstrong: Valkey 9.1](https://techstrong.it/featured/valkey-9-1-sharpens-performance-and-security-controls/)
- **Valkey 8.1** new hash table: about 20 bytes saved per key-value pair (up to 30 with TTL), and about 10% higher pipeline throughput vs 8.0. A 50M-ZSET test used 3.77 GB vs 4.83 GB (about 22% less). AWS cites >20% lower footprint for common key-value patterns on ElastiCache 8.1. — [Valkey blog: A new hash table](https://valkey.io/blog/new-hash-table/); [Valkey 8.1 GA](https://valkey.io/blog/valkey-8-1-0-ga/); [Valkey: 50M ZSETs](https://valkey.io/blog/50-million-zsets/); [AWS: Year one of Valkey](https://aws.amazon.com/blogs/database/year-one-of-valkey-open-source-innovations-and-elasticache-version-8-1-for-valkey)
- **Dragonfly:** BSL 1.1. Free to use in production "as long as you do not provide dragonfly as a managed service". A single secondary source says it converts to Apache 2.0 on June 1, 2027. Architecture: multi-threaded, shared-nothing (keyspace partitioned across thread shards). It claims about 30% better idle memory efficiency than Redis, and Redis peaking at about 3x Dragonfly's memory during snapshots (vendor benchmark). `--cache_mode` uses a "unified, adaptive caching algorithm" that evicts only near `maxmemory`. The README states "~185 Redis commands (roughly equivalent to Redis 5.0 API)", which is possibly outdated text. — [Dragonfly license FAQ](https://dragonflydb.io/docs/about/faq); [Dragonfly license](https://dragonflydb.io/docs/about/license); [dragonflydb/dragonfly GitHub](https://github.com/dragonflydb/dragonfly); [linuxadictos](https://www.linuxadictos.com/en/dragonfly-a-project-that-pretends-to-be-the-replacement-for-being-faster-for-redis-and-memcached.html)
- **KeyDB:** latest release v6.3.0, which merged open source and enterprise into one BSD-3 project. It is maintained by Snap with no paid support. Commit recency was not visible. — [Snapchat/KeyDB GitHub](https://github.com/Snapchat/KeyDB)
- **Microsoft Garnet:**
  - License and protocol: MIT; RESP-compatible with unmodified Redis clients.
  - Storage: Tsavorite engine with tiered storage (memory/SSD/cloud).
  - Cluster mode: has sharding, replication and key migration, but is "*passive*" and "does not implement leader election". It needs an external control plane.
  - Preview features and managed offer: Vector Sets and Range Index are in preview; offered as the managed "Azure Cosmos DB Garnet Cache".

  — [microsoft/garnet GitHub](https://github.com/microsoft/garnet)

**Managed options**
- **ElastiCache for Valkey:** serverless priced 33% lower than Serverless Redis OSS, with a 100 MB minimum (vs 1 GB) from about $6/month. Node-based is 20% lower than other node-based engines. Reserved-node discounts carry over when switching. — [AWS Database Blog: ElastiCache & MemoryDB support Valkey](https://aws.amazon.com/blogs/database/amazon-elasticache-and-amazon-memorydb-announce-support-for-valkey/); [AWS: reduce costs up to 60% with Valkey](https://aws.amazon.com/blogs/database/reduce-your-amazon-elasticache-costs-by-up-to-60-with-valkey-and-cudos)
- A secondary source describes Valkey as the default engine on ElastiCache and MemoryDB. — [Tacnode: Valkey vs Redis 2026](https://tacnode.io/post/valkey-vs-redis)
- **Memorystore for Valkey:**
  - GA in April 2025 with a 99.99% SLA, PSC support and 1–250 nodes.
  - Later GA additions: multi-VPC, cross-region replication, backups, vector search.
  - Version and mode milestones: 7.2→8.0 upgrades GA June 25, 2025; cluster-enabled and cluster-disabled modes GA July 7, 2025.
  - Memorystore for Valkey 9.0 is GA per a Google Cloud blog.

  — [Google Cloud blog: Memorystore for Valkey GA](https://cloud.google.com/blog/products/databases/announcing-general-availability-of-memorystore-for-valkey/); [Memorystore for Valkey release notes](https://docs.cloud.google.com/memorystore/docs/valkey/release-notes); [Memorystore for Valkey 9.0 GA](https://cloud.google.com/blog/products/databases/memorystore-for-valkey-9-0-is-now-ga)
- **Azure retirement (deprecation flag):**
  - Enterprise and Enterprise Flash tiers: creation blocked April 1, 2026; retire March 31, 2027 (Azure pages also say March 30); instances migrate to Azure Managed Redis from April 1, 2027.
  - Basic, Standard and Premium tiers: creation blocked for new customers April 1, 2026 and for existing customers Oct 1, 2026; retire Sept 30, 2028.

  Azure Managed Redis is built on Redis Enterprise. — [Azure Cache for Redis retired features](https://docs.azure.cn/en-us/azure-cache-for-redis/cache-retired-features); [Microsoft Tech Community](https://techcommunity.microsoft.com/blog/azure-managed-redis/-/4458721)
- **Upstash:**
  - Pay-as-you-go is about $0.20 per 100K commands; replicated writes to read regions count as extra commands; idle databases cost nothing.
  - Free tier: 256 MB and 500K commands/month. Fixed plans run $10–$1,500/month.
  - Access is over the Redis protocol and an HTTPS REST endpoint, so it works from edge runtimes.

  These figures come mostly from Upstash's own blog; check the pricing page. — [Upstash: Redis pricing compared 2026](https://upstash.com/blog/redis-pricing-comparison-every-major-provider-in-2026-with-numbers); [Upstash vs ElastiCache Serverless 2026](https://upstash.com/blog/upstash-vs-aws-elasticache-serverless-redis-pricing-and-performance-2026)
- **Momento:** the official page lists $0.50/GB transferred (1 KB metering) with the first 5 GB/month free, and no storage, replication or instance charges. A Japanese docs page shows different provisional pricing (conflict). — [Momento pricing docs](https://docs.momentohq.com/cache/manage/pricing); [Momento JP pricing](https://docs.momentohq.com/ja/product/cache/pricing)

**Eviction, memory and keys**
- Redis eviction policies are set with `maxmemory-policy` and only apply once `maxmemory` is set (default 0 means no limit). Open-source default is `noeviction`. New `allkeys-lrm` / `volatile-lrm` evict the least recently *modified* keys (by write time, not read). One glossary ties these to Redis 8.6+ and says Redis has 10 policy values vs Valkey's 8 (not confirmed from release notes). — [Redis docs: Key eviction](https://redis.io/docs/latest/develop/reference/eviction/); [Redisson glossary](https://redisson.pro/glossary/redis-eviction-policy.html); [fast.io: Redis memory limit](https://fast.io/resources/redis-memory-limit/)
- Redis Software (Enterprise) defaults to `volatile-lru` for most databases, which differs from OSS. — [Redis Software 8.0: eviction policy](https://redis.io/docs/latest/operate/rs/8.0/databases/memory-performance/eviction-policy/)
- ElastiCache: `reserved-memory-percent` defaults to 25% (for failover, backup and other non-data usage). Raise it to 30% on small and up to 50% on micro instance types, and up to 50% for write-heavy data-tiering clusters. Default `maxmemory-policy` is `volatile-lru`. If nothing is evictable, writes fail with OOM. — [AWS ElastiCache: Managing reserved memory](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html); [AWS re:Post: high memory usage](https://repost.aws/knowledge-center/elasticache-cluster-high-memory-usage)
- Per-key overhead in Redis is roughly 50–110+ bytes (blog estimates). For small values the overhead can be "5-10x the actual data". Bucketing small items into hashes (for example 1,000 fields per hash) keeps compact encodings. Listpack thresholds are disputed (128 vs 512 entries; ≤64-byte values), so check your version's config. Measure with `MEMORY USAGE` and `OBJECT ENCODING`. — [OneUptime: Redis memory overhead per key](https://oneuptime.com/blog/post/2026-03-31-redis-memory-overhead-per-key/markdown); [antirez: memory optimization](https://redis.antirez.com/fundamental/memory-optimization.md)
- Hot keys and big keys:
  - Impact: a single hot key can overwhelm a node, raising latency for all clients.
  - Detection: `redis-cli --bigkeys` scans all keys (run off-peak); `--hotkeys` is offered too. A hot-key node shows much higher CPU and bandwidth than its peers.
  - Mitigation: local caching, key splitting or replication, read replicas, and splitting big objects into buckets with size limits at write time.

  — [OneUptime: Redis hot keys](https://oneuptime.com/blog/post/2026-01-21-redis-hot-keys/markdown); [T-Systems DCS FAQ](https://docs.otc.t-systems.com/distributed-cache-service/umn/faqs/big_hot_key_analysis_and_expired_key_scan/how_do_i_detect_big_keys_and_hot_keys_in_advance.html); [besthub: big key splitting](https://www.besthub.dev/articles/redis-object-storage-best-practices-string-vs-hash-big-key-splitting-hot-key-handling-and-thread-model-explained-9c8074337859)
- Facebook memcache: pools separate keys with cheap misses from the default pool. Gutter pools (idle spare servers) absorb a failed server's traffic instead of rehashing. mcrouter routes and batches. — [Utah CS6963 lecture notes](https://users.cs.utah.edu/~stutsman/cs6963/lecture/11/); [Engineer's Codex](https://read.engineerscodex.com/p/how-facebook-scaled-memcached)
- Netflix EVCache: writes replicate to all zones and reads stay local, favoring availability and latency over strict consistency. Sharding uses Ketama consistent hashing. Cache warming uses a sidecar dumper/populator from a healthy replica. Later "Moneta" tiering puts hot data in RAM and cold on SSD. — [Netflix EVCache wiki](https://github.com/netflix/evcache/wiki); [ByteByteGo: How Netflix warms petabytes of cache](https://blog.bytebytego.com/p/how-netflix-warms-petabytes-of-cache); [InfoQ: Netflix global cache](https://infoq.com/articles/netflix-global-cache)

### Inferences
**Engine choice (decision rules):**
- **Default in AWS or GCP:** managed Valkey (ElastiCache/MemoryDB, Memorystore). It is cheaper on AWS and has no license questions.
- **Choose Redis 8 (Redis Cloud, Azure Managed Redis or self-hosted)** when you need Redis Query Engine/Search, JSON, time series, probabilistic structures or vector sets with first-party support, or Redis Enterprise features (Active-Active). Run AGPL past legal if you self-host and modify it.
- **On Azure:** plan migration to Azure Managed Redis. Don't create new Azure Cache for Redis instances; creation is blocked for all customers from Oct 1, 2026.
- **Serverless or edge:** Upstash (HTTP), Momento, or ElastiCache Serverless (VPC-only).
- **Memcached** is still fine for pure string caches with multithreaded simplicity. It has no persistence, replication or data structures. Most new projects pick Valkey or Redis for structures and TTL-per-field.
- **Dragonfly:** consider it for vertical scale on one big box. Avoid it if you resell it as a service (BSL).
- **Avoid KeyDB for new builds** (stagnant).
- **Garnet:** viable on Azure or .NET-heavy stacks via the Cosmos DB Garnet Cache; self-hosted cluster needs your own failover orchestration.

**Configuration defaults for a pure cache (prior knowledge; verify against your engine version):**
- Set `maxmemory`, and size usable memory to about 75% of the node (ElastiCache reserves 25% by default).
- Set `maxmemory-policy allkeys-lfu` (skewed popularity) or `allkeys-lru` (recency). `volatile-*` only applies when *every* cacheable key has a TTL and non-TTL keys must never be evicted. Never run a cache on `noeviction`, which causes OOM write errors.
- Persistence: for a pure cache, disable RDB snapshots (`save ""`) and AOF (`appendonly no`) to avoid fork and copy-on-write memory spikes and disk I/O. Rely on replicas for availability and accept a cold cache after full loss. Enable persistence only if a cold restart would stampede the DB (or use warm-up as Netflix does).
- Hot-key detection: `redis-cli --hotkeys` requires an LFU `maxmemory-policy` (prior knowledge).

**Data structures useful for caching:**
- STRING: serialized object. Use `SET k v EX ttl NX` for lock-ish semantics.
- HASH: partial-field objects; bucketing small items.
- Field-level TTL: hash field expiration (Redis 7.4+/8 `HEXPIRE`, `HGETEX`/`HSETEX`; Valkey 9.0) gives per-field TTL without one key per field.
- ZSET: leaderboards and top-N computed caches.
- SET: tag-to-key indexes for tag invalidation.
- Bloom/Cuckoo: negative caching ("definitely not present").
- STREAM: write-behind queues.

**Key naming and versioning:**
- Use the shape `{app}:{env?}:{schemaVersion}:{entity}:{id}[:{variant}]`, for example `shop:v7:product:42:en-US`.
- Bump `schemaVersion` on any serialization or shape change to invalidate everything at once without SCAN+DEL. Old keys age out by TTL.
- In Redis Cluster, use hash tags `{user:42}:profile` / `{user:42}:cart` only when multi-key ops or Lua need co-location. Overusing one tag creates a hot slot.
- Keep keys short but readable. Key bytes count toward the per-key overhead.

**TTL design:**
- TTL equals the staleness budget for that data class, plus 5–15% jitter.
- Typical classes: config and feature flags 30–60 s; catalog and content 5–60 min; user session or profile 15–60 min with explicit delete on write; immutable or content-addressed data days or no TTL (LRU will evict).
- Negative caching: 10–60 s.
- Always set *some* TTL as a backstop even when using explicit invalidation.

**Serialization and compression:**
- Formats: JSON is debuggable and cross-language. MessagePack or CBOR are about 20–50% smaller and faster. Protobuf or Avro need a schema but are best for evolution. Avoid language-native pickling (Java serialization, Python pickle) for security and cross-version fragility.
- Compression: compress values over about 1 KB with zstd or LZ4. Store a 1-byte header (format + codec + version) so you can change codecs without a flag day.

**Big values:**
- Keep values below about 100 KB, and ideally single-digit KB. Large values block Redis's single-threaded command execution and saturate NIC bandwidth.
- Split large lists or sets into buckets.
- Never `KEYS *` in production; use `SCAN`. Delete big keys with `UNLINK` (async).
- These size numbers are common practitioner heuristics, not from a retrieved source.

**Clustering:**
- Scale reads with replicas (stale by replication lag) and writes and memory with shards.
- For extreme hot keys, use a local L1 (seconds of TTL), replicate the key N ways (`k#0..k#7`, read from a random copy, write to all), or Redis client-side caching (§4).

#### Code sketches
```bash
# Pure-cache Valkey/Redis config (redis.conf / valkey.conf)
maxmemory 12gb                 # ≈75% of a 16 GB node (leave headroom for fragmentation, replication buffers)
maxmemory-policy allkeys-lfu   # or allkeys-lru
save ""                        # no RDB snapshots for a pure cache
appendonly no
lazyfree-lazy-eviction yes     # async free on eviction (prior knowledge)
```
```python
# Versioned, namespaced keys + compressed msgpack with header byte
import msgpack, zstandard as zstd
SCHEMA_V = 7
def k(entity, id, variant=""): return f"shop:v{SCHEMA_V}:{entity}:{id}" + (f":{variant}" if variant else "")
def enc(obj):
    raw = msgpack.packb(obj)
    return (b"\x02" + zstd.compress(raw)) if len(raw) > 1024 else (b"\x01" + raw)
def dec(b):
    return msgpack.unpackb(zstd.decompress(b[1:]) if b[0] == 2 else b[1:])
```

### Gaps
- I could not confirm the exact current GA versions of Redis Open Source (8.10.x appears on GitHub) and Valkey (9.1.x per blogs) from official release pages; fetches were blocked.
- I could not confirm the exact Redis version that introduced `allkeys-lrm`/`volatile-lrm`. One source says 8.6.
- I found no current (2026) maintenance activity data for KeyDB or Garnet. No Garnet release number was visible.
- I could not verify Dragonfly's BSL change date (June 1, 2027) from the license file itself.
- I found no authoritative source on serialization-format benchmarks or compression thresholds for caches; the guidance above is practitioner heuristics.
- I found no current Memcached-specific (memcached.org) 2026 release info; not researched due to tool limits.

---

## 4. Multi-tier caching (L1 in-process + L2 distributed), near-cache invalidation, Redis client-side caching, hybrid-cache libraries

### Takeaway
L1+L2 gives roughly microsecond hits for hot keys and protects the L2 from hot-key load. The cost is a second consistency problem: L1 copies on N instances. Bound it with a short L1 TTL (seconds to about 1 min, always shorter than L2) and, if needed, a pub/sub backplane or Redis server-assisted client-side caching (RESP3 + `CLIENT TRACKING`). Prefer a library that already does this: .NET `HybridCache` or FusionCache, Node `cacheable`, Jedis/redis-py client-side caching. Spring's `CompositeCacheManager` does not tier caches.

### Cited Findings
- **.NET HybridCache** (Microsoft.Extensions.Caching.Hybrid) shipped with .NET 9 and pairs an in-memory L1 with an optional `IDistributedCache` L2 (Redis, SQL Server). It has built-in stampede protection and configurable serialization. Tags are set via `GetOrCreateAsync` and cleared with `RemoveByTagAsync`, which also accepts a collection of tags. Removal clears both L1 and L2. Global defaults set `MaximumPayloadBytes`, `MaximumKeyLength` and `DefaultEntryOptions`; the docs sample uses 1 MB and 5-minute `Expiration`/`LocalCacheExpiration`, and per-call `HybridCacheEntryOptions` override them. — [Microsoft Learn: HybridCache library in ASP.NET Core](https://learn.microsoft.com/aspnet/core/performance/caching/hybrid); [Milan Jovanović: HybridCache](https://www.milanjovanovic.tech/blog/hybrid-cache-in-aspnetcore-new-caching-library)
- Community guidance (not official): keep `LocalCacheExpiration` shorter than `Expiration`, so one server's stale window is small while the cluster still avoids the DB. One author's test had 100 concurrent cold-cache requests issue 100 DB queries with IMemoryCache vs 1 with HybridCache. — [Start Debugging: HybridCache with Redis L2 (ASP.NET Core 11)](https://startdebugging.net/2026/06/how-to-use-hybridcache-in-aspnetcore-11-with-redis-as-the-l2-cache/); [codewithmukesh: HybridCache](https://codewithmukesh.com/blog/hybridcache-in-aspnet-core/)
- **FusionCache features:**
  - Tiering: optional `IDistributedCache` L2 "all transparently"; a backplane notifies other nodes of changes.
  - Resilience: fail-safe (reuse an expired entry on transient failures); soft/hard timeouts on slow factories; local and distributed stampede protection; auto-recovery.
  - Freshness and grouping: eager refresh (background refresh before expiry); tagging.
  - It can serve as an implementation of Microsoft's HybridCache abstraction.

  — [ZiggyCreatures/FusionCache](https://github.com/ZiggyCreatures/FusionCache)
- **Node:** `cacheable` provides L1/L2 on top of Keyv stores. `cache-manager` (NestJS) provides `wrap`. — [jaredwray/cacheable](https://github.com/jaredwray/cacheable)
- **Spring:**
  - Common pattern: Caffeine L1 → Redis L2 → DB, with refill on the way back and pub/sub messages on put/evict/clear that each instance uses to drop its Caffeine entry.
  - Alternative: one starter randomizes L1 TTLs below L2 instead of using pub/sub, wraps Redis in a Resilience4j circuit breaker, and says it suits immutable entities.
  - `CompositeCacheManager` returns the first manager that has the named cache, so it does not give a true L1→L2 read path; you need a custom `Cache`.

  — [OneUptime: multi-level caching Spring Boot](https://oneuptime.com/blog/post/2026-01-29-multi-level-caching-spring-boot/markdown); [apispace: Spring Cache multi-level](https://apispace.com/news/post/51533.html); [SuppieRK multilevel cache starter](https://github.com/SuppieRK/spring-boot-multilevel-cache-starter/)
- **Redis server-assisted client-side caching:**
  - Protocol: it needs RESP3 for same-connection push invalidations. Under RESP2, invalidations go to a separate connection via `REDIRECT`, subscribed to `__redis__:invalidate`.
  - Modes: default tracking with `OPTIN`/`OPTOUT`, or `BCAST` with key prefixes.
  - Client support: official client libraries added support in Oct 2024. Jedis 5.2.0 GA supports it "exclusively with RESP3 and Redis 7.4 or later" across UnifiedJedis, JedisPooled and JedisCluster. redis-py support is reported as v5.1.0+ with Redis 7.4+ (secondary source). node-redis support was not confirmed.

  — [Redis blog: client library support for client-side caching](https://redis.io/blog/faster-redis-client-library-support-for-client-side-caching/); [Jedis releases](https://github.com/redis/jedis/releases/latest); [OneUptime: CLIENT TRACKING](https://oneuptime.com/blog/post/2026-03-31-redis-client-tracking-client-side-caching/markdown); [Stanza: client-side caching impl](https://www.stanza.dev/courses/redis-caching/client-side-caching/redis-caching-client-side-impl)
- Missed invalidations happen, for example a pod subscribing after a message was published. That is why a short L1 TTL is the safety net even with a backplane. — [DEV: When caches lie](https://dev.to/prasadmk/when-caches-lie-the-hidden-invalidation-traps-in-a-multi-instance-spring-boot-microservice-44pl)

### Inferences
**When to add L1:**
- Add it when you have hot keys with a high read:write ratio, L2 round-trip latency matters (Caffeine at about 1 ms vs Redis at about 5–10 ms in the Spring guide's table), or you see hot-key CPU or bandwidth spikes on one Redis shard.
- Skip it for per-user data with low reuse per instance. L1 hit rate is roughly (requests per key per instance per L1-TTL); with many instances and a long tail it approaches zero.

**Invalidation choices (cheapest first):**
1. Short L1 TTL only (bounded staleness, no infrastructure).
2. Versioned keys: L1 caches `entity:id@version` and a tiny "current version" lookup in L2.
3. Pub/sub backplane: publish key or tag on write; subscribers evict. Delivery is at-most-once, so keep the TTL as a backstop.
4. Redis client-side caching via RESP3 tracking: the server tracks which keys each connection read and pushes invalidations. It costs server memory for the tracking table. Use `BCAST` + prefix for small hot namespaces and `OPTIN` to track only chosen keys.

**General rules:**
- L1 serialization: store deserialized immutable objects in L1 to save CPU, but never hand out mutable references. Copy them or use immutable types; HybridCache's docs discuss reuse of immutable instances (prior knowledge).
- Always set L1 TTL < L2 TTL. Otherwise L1 can serve values older than anything in L2 after an L2 invalidation.

#### Code sketches
```csharp
// .NET 9+ HybridCache with Redis L2 and tags
builder.Services.AddStackExchangeRedisCache(o => o.Configuration = redisConn);
builder.Services.AddHybridCache(o => {
    o.MaximumPayloadBytes = 1024 * 1024;
    o.DefaultEntryOptions = new HybridCacheEntryOptions {
        Expiration = TimeSpan.FromMinutes(10),          // L2
        LocalCacheExpiration = TimeSpan.FromMinutes(1)  // L1 (shorter)
    };
});
// usage
var product = await cache.GetOrCreateAsync($"product:{id}",
    async ct => await db.Products.FindAsync([id], ct),
    tags: new[] { $"category:{catId}" }, cancellationToken: ct);
await cache.RemoveByTagAsync($"category:{catId}");     // invalidate group
```
```ts
// Hand-rolled L1 (lru-cache) + L2 (Redis) + pub/sub invalidation (Node)
const l1 = new LRUCache<string, any>({ max: 10_000, ttl: 30_000 });
const sub = redis.duplicate(); await sub.connect();
await sub.subscribe("cache:invalidate", (key) => l1.delete(key));
async function get(key: string, load: () => Promise<any>) {
  const a = l1.get(key); if (a !== undefined) return a;
  const b = await redis.get(key); if (b) { const v = JSON.parse(b); l1.set(key, v); return v; }
  const v = await load(); await redis.set(key, JSON.stringify(v), { EX: 600 }); l1.set(key, v); return v;
}
async function invalidate(key: string) { await redis.del(key); await redis.publish("cache:invalidate", key); }
```
```python
# redis-py server-assisted client-side caching (RESP3; verify API for your redis-py version)
import redis
from redis.cache import CacheConfig
r = redis.Redis(host="cache", port=6379, protocol=3, cache_config=CacheConfig(max_size=10_000))
r.get("shop:v7:config:flags")   # served locally after first read; server pushes invalidations
```

### Gaps
- I could not fetch the redis.io client-side caching reference to confirm tracking-table memory costs (`tracking-table-max-keys`) and RESP3 race-condition guidance. The redis-py snippet's exact class names (`redis.cache.CacheConfig`) are from prior knowledge and should be verified.
- node-redis built-in client-side caching status was not confirmed.
- Official Spring Framework docs on tiered caching were not retrieved.

---

## 5. Database-level caching (buffer caches, MySQL query cache removal, proxies, materialized views, read replicas, ORM second-level caches, plan caches, connection pooling)

### Takeaway
The database already caches pages: Postgres `shared_buffers` plus the OS page cache, MySQL's InnoDB buffer pool. Tune those before adding an app cache, and remember MySQL's query cache is gone since 8.0. For query-result caching without app changes, use a proxy (ProxySQL TTL rules, Readyset's replication-maintained caches, Cloudflare Hyperdrive) or an ORM-level cache (Hibernate L2, Prisma Accelerate). Each has staleness semantics you must design for. Read replicas act as a stale cache tier; handle read-your-writes explicitly. Connection poolers (PgBouncer, Supavisor) are not caches, though they interact with prepared-statement caching.

### Cited Findings
- **Postgres buffers:** a page can sit in both `shared_buffers` and the OS cache (double buffering). The usual start is about 25% of RAM on a dedicated server; going above about 40% rarely helps, and very large machines may cap at 128–256 GB and leave the rest to the OS. `effective_cache_size` is a planner hint, not an allocation (commonly 50–75% of RAM), and influences index-scan choice. Changing `shared_buffers` needs a restart. — [CYBERTEC pgconfigurator: shared_buffers](https://pgconfigurator.cybertec-postgresql.com/docs/parameters/shared_buffers); [Netdata: shared_buffers tuning](https://www.netdata.cloud/guides/postgres/postgres-shared-buffers-tuning/); [Tiger Data: OS RAM vs Postgres buffer cache](https://www.tigerdata.com/blog/understanding-why-os-ram-postgres-buffer-cache-compete)
- **MySQL query cache (removed):**
  - History: deprecated in MySQL 5.7.20 and removed entirely in 8.0.
  - Why: a global mutex caused contention on multi-core machines, any write invalidated all cached results for the table, and memory fragmented.
  - Replacements suggested: ProxySQL or server-side query rewrite.
  - `SQL_NO_CACHE` behavior in 8.0 is described inconsistently across sources.

  — [OneUptime: How MySQL query cache worked and why it was removed](https://oneuptime.com/blog/post/2026-03-31-mysql-how-mysql-query-cache-worked-and-why-it-was-removed/markdown); [Readyset: MySQL 5.7 EOL, end of query cache](https://readyset.io/blog/mysql-5-7-eol-the-end-of-mysql-query-cache)
- **ProxySQL:** query rules take `cache_ttl` in milliseconds (seconds in ProxySQL 1.1). `cache_empty_result` controls caching of empty result sets. Rules match by digest. — [Ansible community.proxysql query rules docs](https://docs.ansible.com/projects/ansible/14/collections/community/proxysql/proxysql_query_rules_module.html)
- **Readyset:**
  - Compatibility and adoption: wire-compatible with Postgres and MySQL; apps change only the connection string; you choose which queries to cache.
  - Cache types: deep caches are refreshed from the replication stream (no TTL); shallow caches are TTL-based.
  - Product surface: the platform includes QueryPilot (automatic caching for AI-generated workloads) and the `rdst` CLI; explicit caching uses `CREATE CACHE`.
  - Performance: the "100x" claims are vendor marketing.

  — [Readyset Docs](https://readyset.io/docs/); [Readyset blog](https://readyset.io/blog/readyset-scale-postgresql-and-mysql-performance-by-100x-without-code-changes)
- **Cloudflare Hyperdrive:** caches cacheable read queries from Workers (on by default) and never caches writes. Defaults are `max_age` 60 s and `stale_while_revalidate` 15 s, with `max_age` up to 1 h. It "does not invalidate cached read query results when your application writes". For read-after-write, use a second Hyperdrive config with caching disabled. — [Cloudflare Hyperdrive: Query caching](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/)
- **Materialized views:** `REFRESH … CONCURRENTLY` does not block readers and needs a unique index. pg_ivm does incremental maintenance (PG 13–17) but `refresh_immv` takes an AccessExclusiveLock. — [pgEdge docs](https://docs.pgedge.com/postgresql/v17/reference/sql-commands/refresh-materialized-view/); [pg_ivm](https://github.com/sraoss/pg_ivm)
- **Read replicas and read-your-writes. Strategies:**
  - Route a user's reads to the primary until last-write time plus worst-case lag; a Redis flag with about 1 s TTL is one implementation.
  - Use causal tokens (LSN or version): only read from replicas at or past that position.
  - Pull lagging replicas out of the pool.
  - Read only the user's *own* data from the primary.
  - Pin by node ID rather than role, which survives failover.
  - Keep transaction reads on the primary.

  — [Codemia: Read-your-writes consistency](https://codemia.io/archive/read-your-writes-consistency); [Codemia: Read after write](https://codemia.io/archive/read-after-write-consistency); [OneUptime: Redis replication lag](https://oneuptime.com/blog/post/2026-03-31-redis-handle-replication-lag-applications/view)
- **Hibernate second-level and query cache:**
  - Storage model: L2 stores entities in "dehydrated" form (ID → array of primitive values). The query cache stores only result IDs that are resolved against L2, so the two caches belong together.
  - Pitfall 1: if query-cache entries outlive or underlive the entity entries differently, especially when queries expire *less* frequently than entities, you get *more* queries. Queries must opt in (`setCacheable(true)` / `org.hibernate.cacheable`).
  - Pitfall 2: data goes stale if other applications write the DB.

  — [DZone: Pitfalls of the Hibernate second-level / query caches](https://dzone.com/articles/pitfalls-hibernate-second-0); [Packt/O'Reilly: Mastering Hibernate ch.5](https://www.oreilly.com/library/view/mastering-hibernate/9781782175339/ch05.html)
- **Prisma Accelerate:**
  - Options: per-query `cacheStrategy: { ttl, swr, tags }`. With `ttl: 60, swr: 60` it serves cache for 60 s, then serves stale for another 60 s while revalidating.
  - Tags: alphanumeric/underscore, ≤64 chars.
  - Invalidation: `$accelerate.invalidate({ tags })` takes up to 5 tags per call; `invalidateAll()` clears the whole environment. On-demand invalidation needs paid plans and has daily tag-invalidation limits.
  - Scope: not supported on writes.

  — [Prisma Accelerate API reference](https://prisma.io/docs/accelerate/api-reference); [Prisma blog: on-demand cache invalidation](https://blog.prisma.io/blog/announcing-on-demand-cache-invalidation-for-prisma-accelerate)
- **PgBouncer:** 1.21 added protocol-level prepared statements in transaction mode via `max_prepared_statements`. One guide says it is enabled by default at 200 since 1.24; Azure lists 0, so check your version. SQL-level `PREPARE` is invisible to PgBouncer and breaks. Prisma Migrate needs a direct connection, not a pooler. **Supavisor** supports transaction mode (port 6543) and session mode (5432) with named prepared statements in transaction mode (secondary source). — [Crunchy Data: prepared statements in PgBouncer transaction mode](https://www.crunchydata.com/blog/prepared-statements-in-transaction-mode-for-pgbouncer); [Netdata: PgBouncer transaction vs session](https://www.netdata.cloud/guides/pgbouncer/pgbouncer-transaction-vs-session-pooling/); [Prisma docs: PgBouncer](https://www.prisma.io/docs/orm/v7/prisma-client/setup-and-configuration/databases-connections/pgbouncer); [chat2db: PgCat vs PgBouncer vs Supavisor](https://chat2db.ai/resources/blog/pgcat-vs-pgbouncer-vs-supavisor)

### Inferences
**DB-level decision ladder (cheapest and safest first):**
1. Fix queries and indexes, and check the buffer-cache hit ratio. Size `shared_buffers` (about 25%) or the InnoDB buffer pool (MySQL commonly 50–75% of RAM on a dedicated host; prior knowledge) to the hot working set.
2. Materialized views or summary tables for expensive aggregates, refreshed `CONCURRENTLY` on a schedule or incrementally via pg_ivm or triggers.
3. Read replicas for read scale, with read-your-writes routing.
4. A transparent query cache (Readyset for replication-consistent caching; ProxySQL or Hyperdrive for TTL caching) when you can't change app code.
5. An app or ORM cache (Hibernate L2, Prisma Accelerate, Redis cache-aside) when you need cross-service sharing, tag invalidation or business-level keys.

**Gotchas and clarifications:**
- **Pooling is not caching.** PgBouncer and Supavisor reduce connection setup cost and backend count; they don't store results. They interact with the *statement and plan* cache: Postgres prepared statements and their cached plans live per backend connection, which is why transaction pooling broke them before PgBouncer 1.21.
- **Plan caches:** Postgres caches plans only for prepared statements, per session (`plan_cache_mode` chooses generic vs custom; prior knowledge). MySQL 8 has no query-result cache but still caches parsed and prepared statements per session. ORMs often keep their own statement caches (for example JDBC `prepStmtCacheSize`).
- **Hibernate L2** suits reference data and rarely updated entities with a single writer application. Use `READ_ONLY`/`NONSTRICT_READ_WRITE`/`READ_WRITE` concurrency strategies appropriately (prior knowledge). Avoid the query cache for queries over frequently updated tables, since any update to the table invalidates its cached queries (prior knowledge).
- **Drizzle ORM:** no retrieved source on Drizzle's caching features (see Gaps).

#### Code sketches
```ts
// Prisma Accelerate per-query cache with SWR and tag invalidation
const posts = await prisma.post.findMany({
  where: { published: true },
  cacheStrategy: { ttl: 60, swr: 60, tags: ["posts_list"] },
});
await prisma.$accelerate.invalidate({ tags: ["posts_list"] }); // after a publish
```
```sql
-- Readyset: cache one query explicitly (syntax per Readyset docs; verify)
CREATE CACHE FROM SELECT id, title FROM posts WHERE author_id = $1;
-- ProxySQL: 30s TTL for one digest
INSERT INTO mysql_query_rules (rule_id, active, digest, cache_ttl, apply)
VALUES (10, 1, '0x1A2B3C...', 30000, 1);  -- cache_ttl in ms
LOAD MYSQL QUERY RULES TO RUNTIME;
```
```ts
// Read-your-writes: pin a user to primary briefly after a write
await db.primary.update(...);
await redis.set(`ryw:${userId}`, "1", { PX: 2000 });       // >= worst-case replica lag
const usePrimary = (await redis.exists(`ryw:${userId}`)) === 1;
const conn = usePrimary ? db.primary : db.replica;
```

### Gaps
- Official PostgreSQL and MySQL docs pages were not retrieved (fetch blocked). The tuning numbers come from reputable secondary sources (CYBERTEC, Tiger Data, Netdata).
- I found no source on Drizzle ORM caching (Drizzle has added a cache API in 2025 per prior knowledge, which is unverified) or other ORM-level caches beyond Hibernate and Prisma.
- I found no authoritative 2026 status for Readyset as a company or product beyond vendor pages.
- I found no source confirming PgBouncer's exact current default for `max_prepared_statements`; sources conflict between 200 and 0.

---

## 6. Serverless / edge runtime constraints (cold starts, ephemeral memory, connection limits, HTTP Redis, platform data caches)

### Takeaway
In serverless, in-memory caches are per execution environment and disappear unpredictably, so treat them as an opportunistic L1. TCP connection fan-out (concurrency × pool size) against Redis or the DB is the main failure mode. Create clients outside the handler, cap pools, and prefer HTTP-based Redis (Upstash) or platform caches (Vercel Runtime Cache, Cloudflare KV, Hyperdrive) on edge runtimes. Cloudflare KV is eventually consistent (about 60 s), so it is not suitable for read-after-write.

### Cited Findings
- **Lambda practices:**
  - Client reuse: create the Redis client at module scope, outside the handler, so warm invocations reuse it, and reset it on connection error.
  - Connection fan-out: each concurrent execution environment holds its own connection (1,000 concurrent invocations means 1,000 connections), while managed services may cap `maxclients` below Redis's default of 10,000. Use small capped pools (for example 5).
  - Cold-start cost: a fresh TCP+TLS+AUTH connection adds roughly 20–80 ms (vendor-blog estimate). VPC-attached cold starts add 200–500 ms. ElastiCache is VPC-only.
  - Mitigations: provisioned concurrency, pre-warming, or HTTP Redis.

  — [OneUptime: Redis connections in short-lived functions](https://oneuptime.com/blog/post/2026-03-31-redis-connection-short-lived-functions/markdown); [OneUptime: Redis cold start in serverless](https://oneuptime.com/blog/post/2026-03-31-redis-cold-start-serverless-functions/markdown); [OneUptime: ElastiCache with Lambda](https://oneuptime.com/blog/post/2026-03-31-redis-elasticache-redis-with-lambda/markdown); [Upstash redis-js AWS Lambda example](https://www.mintlify.com/upstash/redis-js/examples/aws-lambda)
- **Upstash:** an HTTPS REST endpoint in addition to the Redis protocol, so the same DB works from edge runtimes and browsers; per-command pricing; idle databases cost nothing. — [Upstash pricing comparison 2026](https://upstash.com/blog/redis-pricing-comparison-every-major-provider-in-2026-with-numbers)
- **Vercel Runtime Cache:**
  - What it is: "a regional, ephemeral cache" usable across Vercel Functions, Routing Middleware and builds within a region.
  - Next.js 16 integration: `'use cache: remote'` (with `cacheComponents`) or `fetch` with `force-cache` uses it; plain `'use cache'` is in-memory per instance.
  - Invalidation (per a docs mirror): `updateTag` works in Server Actions only, and `revalidateTag(tag, 'max')` gives SWR. Runtime Cache tags do not apply to ISR pages.

  — [Vercel docs: Runtime Cache](https://vercel.com/docs/runtime-cache); [mcpservers.org mirror of Vercel runtime-cache skill](https://mcpservers.org/es/agent-skills/vercel/vercel-plugin/runtime-cache)
- **Cloudflare Workers KV:** writes can take up to about 60 s to propagate globally, so reads may be stale. KV does not accept expirations shorter than 60 s. These figures are from third-party docs. — [Upstash: Cloudflare Workers KV vs Upstash Redis](https://upstash.com/blog/cloudflare-workers-redis.md); [OneUptime: Cloudflare Workers KV](https://oneuptime.com/blog/post/2026-01-27-cloudflare-workers-kv/markdown)
- **Cloudflare Hyperdrive:** pools connections to regional DBs and caches read queries (default 60 s max_age, 15 s SWR, max 1 h, no write-triggered invalidation). — [Cloudflare Hyperdrive: How it works](https://developers.cloudflare.com/hyperdrive/concepts/how-hyperdrive-works/); [Hyperdrive query caching](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/)
- **Prisma Accelerate** pairs a global cache with a connection pool, aimed at serverless and edge clients. — [Prisma blog: Accelerate preview](https://blog.prisma.io/blog/accelerate-preview-release-ab229e69ed2)

### Inferences
**Serverless caching rules:**
1. Module-scope L1 (lru-cache, small, TTL of seconds to minutes). It is a bonus, not a design assumption.
2. Shared L2 must be reachable without long-lived TCP from edge runtimes: Upstash REST, Vercel Runtime Cache, Cloudflare KV for read-mostly config, or Momento.
3. DB access goes through a pooler or accelerator (Hyperdrive, Prisma Accelerate, RDS Proxy, Supavisor transaction mode). Never open a raw connection per invocation.
4. Budget connections as `max_concurrency × pool_size ≤ maxclients − headroom`.
5. For read-after-write on edge, bypass eventually consistent caches (KV, Hyperdrive cache) on the request that just wrote. Use a no-cache config or the origin.

**Cold-start trade-off:** HTTP Redis costs a few ms more per call than a warm TCP connection (prior knowledge), but avoids the connection storm and the TLS/AUTH setup on cold start. Pipeline or batch multiple commands per HTTP request.

#### Code sketches
```ts
// Edge/serverless: HTTP Redis (Upstash) client at module scope
import { Redis } from "@upstash/redis";
const redis = Redis.fromEnv();                 // REST, no TCP pool to exhaust
const local = new Map<string, { v: unknown; exp: number }>();  // opportunistic L1
export default async function handler(req: Request) {
  const key = "cfg:v2:flags";
  const l = local.get(key); if (l && l.exp > Date.now()) return Response.json(l.v);
  let v = await redis.get(key);
  if (v === null) { v = await loadFlags(); await redis.set(key, v, { ex: 60 }); }
  local.set(key, { v, exp: Date.now() + 5_000 });
  return Response.json(v);
}
```
```ts
// Next.js 16 remote data cache (Vercel Runtime Cache)
import { cacheTag, cacheLife } from "next/cache";
export async function getProduct(id: string) {
  "use cache: remote";
  cacheTag(`product:${id}`);
  cacheLife({ expire: 3600 });
  return db.product.findUnique({ where: { id } });
}
```

### Gaps
- I found no official AWS documentation in this session on Lambda execution-environment lifetime, or official ElastiCache `maxclients` limits per node type.
- Cloudflare KV's 60 s propagation figure came from third-party pages, not Cloudflare's own KV docs.
- I found no measured latency comparison of HTTP Redis vs TCP Redis from a neutral source.
- Netlify, Deno Deploy and Fly.io platform data caches were not researched.

---

## 7. Caching for AI/LLM features (provider prompt caching, semantic caching, caching embeddings and RAG results)

### Takeaway
Provider prompt caching (Anthropic, OpenAI, Gemini) is a prefix-match KV-cache reuse feature, not a response cache. It is the biggest, safest LLM cost and latency lever: design prompts with stable content first and volatile content last. The economics differ by provider:
- Anthropic: explicit `cache_control` breakpoints, write premium (1.25x for 5 min, 2x for 1 h) and reads at about 0.1x or less.
- OpenAI: automatic at ≥1024 tokens with discounts up to about 90%. Writes are free before GPT-5.6 and 1.25x from GPT-5.6 on. Retention is `in_memory` or `24h`.
- Gemini: implicit caching on 2.5+ at a 90% discount, plus explicit caches with storage billing.

Semantic (similarity) caching returns *someone else's answer* to a different prompt. It has real false-positive and security risks and needs conservative thresholds, scoping and evaluation. Caching embeddings is safe and cheap if keys include model and version.

### Cited Findings
**Anthropic (Claude API)** — source: platform.claude.com prompt-caching docs as mirrored in the bundled claude-api skill reference (cached 2026-10-06). — [Anthropic: Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- It is a prefix match: "Any change anywhere in the prefix invalidates everything after it". Render order is `tools` → `system` → `messages`. A breakpoint on the last system block caches tools and system together.
- `cache_control: {type: "ephemeral"}` gives a 5-minute TTL (default); `{"type": "ephemeral", "ttl": "1h"}` gives 1 hour. Max **4** breakpoints per request. Top-level automatic caching (`cache_control` on the request) places the breakpoint on the last cacheable block and uses one of the 4 slots.
- Pricing: writes cost **1.25x** base input (5 min) or **2x** (1 h). Reads cost about **0.1x**, 0.05x on Claude Opus 5.5 ($0.20/MTok) and 0.025x on Claude Fable 5.1 ($0.25/MTok). Break-even is 2 requests for a 5-minute TTL (1.25 + 0.1 = 1.35 vs 2.0) and 3 requests for 1 h (2 + 0.2 = 2.2 vs 3.0).
- A cache read refreshes the TTL at no extra cost. Lifetime is measured from the *start* of the request, so long generations eat into the TTL.
- Minimum cacheable prefix is model-dependent: 512 tokens on the newest models (Opus 5.5, Opus 5, Fable 5/5.1, Sonnet 5.5, Haiku 5.5), 1024 on Opus 4.8 / Sonnet 5 / Sonnet 4.x, 2048 on Opus 4.7, 4096 on Opus 4.6/4.5 / Haiku 4.5. Shorter prefixes silently don't cache (`cache_creation_input_tokens: 0`).
- Caches are isolated per workspace (Claude API, Claude Platform on AWS, Foundry) or per org (Bedrock, Google Cloud), are model-scoped, and are never shared across organizations.
- Silent invalidators: timestamps in the system prompt, unsorted JSON, varying tool sets, and switching models. Changing tools invalidates everything. Changing thinking or effort settings invalidates the messages cache (and on some models more).
- Each breakpoint looks back at most **20 positions** for a prior entry. Long turns can miss the cache, so add intermediate breakpoints.
- Verify with `usage.cache_read_input_tokens` / `cache_creation_input_tokens`. A cache-diagnostics beta (`cache-diagnosis-2026-04-07`) reports where two requests diverged. Pre-warm with `max_tokens: 0`.

**OpenAI**
- Caching is automatic for prompts ≥1024 tokens, with hits in 128-token increments on an exact prefix match. Requests are routed by a hash of the initial prefix (typically the first ~256 tokens). `prompt_cache_key` is combined into that hash to improve hit rates. — [OpenAI: Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching); [OpenAI Cookbook: Prompt Caching 201](https://developers.openai.com/cookbook/examples/prompt_caching_201)
- Retention is set per request with `prompt_cache_retention`: `in_memory` (default) or `24h`. Pricing is the same for both policies. GPT-5.5 / GPT-5.5-pro support only `24h`. For older dual-support models, orgs without ZDR default to `24h` (reported via search summary). — [OpenAI: Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- Cache writes have no extra fee before the GPT-5.6 family. From GPT-5.6 on, writes cost **1.25x** the uncached input rate, and Azure docs say the same. — [OpenAI: Prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching); [Microsoft Learn: Azure OpenAI prompt caching](https://learn.microsoft.com/en-my/Azure/foundry/openai/how-to/prompt-caching)
- Discounts vary by model: up to 90%. GPT-5 is listed at $1.25 vs $0.125/MTok cached and GPT-5.5 at $5.00 vs $0.50 (third-party table). GPT-4o was 50% at launch ($2.50 vs $1.25). — [OpenAI: API prompt caching announcement](https://openai.com/index/api-prompt-caching); [MorphLLM: OpenAI API pricing 2026](https://www.morphllm.com/openai-api-pricing)

**Google Gemini**
- Implicit caching is automatic on Gemini 2.5+. The launch post (May 2025) promised a 75% discount. Current Vertex docs give **90%** on 2.5+ and 75% on 2.0. Implicit caching has no storage fee. Hits need a shared prefix, so put stable content first. Cached tokens are reported as `cached_content_token_count`. — [Google Developers Blog: implicit caching](https://developers.googleblog.com/en/gemini-2-5-models-now-support-implicit-caching/); [Vertex AI: Context cache overview](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview); [Gemini API: optimization](https://ai.google.dev/gemini-api/docs/optimization.md.txt)
- Explicit context caching: TTL defaults to 1 hour with no min or max bounds. Storage is billed by cached tokens × TTL. Model minimums per one docs version: 1,024 (2.5 Flash), 4,096 (2.5 Pro), 2,048 (3 Pro Preview); older versions differ. — [Gemini API: Context caching](https://ai.google.dev/gemini-api/docs/caching?lang=node)
- One forum user reported the implicit-cache discount on gemini-3.1-flash-lite stopped applying around June 30, 2026, though cached tokens were still reported (anecdotal, unconfirmed). A reseller advises budgeting at uncached prices because implicit hit rates trail OpenAI and Claude (vendor opinion). — [Google AI forum thread](https://discuss.ai.google.dev/t/gemini-3-1-flash-lite-implicit-cache-stopped-applying-cost-savings-june-30-2026/173779); [APIYI: Gemini prompt caching](https://docs.apiyi.com/en/api-capabilities/gemini/prompt-caching)

**Semantic caching**
- Redis LangCache: the default similarity threshold is 0.85, with 0.8–0.9 recommended as a start. Tighter thresholds cut wrong answers and hit rate; looser ones raise both. Start conservative and loosen while spot-checking. A support FAQ bot tolerates looser matching than account-specific financial Q&A. LangCache is in preview on Redis Cloud. RedisVL uses a *distance* threshold (strict about 0.05, loose about 0.3), a different scale. — [Redis: LangCache concepts](https://redis.io/docs/latest/develop/ai/context-engine/langcache/concepts/); [RedisVL extensions](https://redis.io/docs/latest/develop/ai/redisvl/0.26.0/concepts/extensions/); [Redis AI Research: Evaluating LangCache on your data](https://redis-ai-research-redis.static.hf.space/posts/evaluating-langcache-on-your-data.html)
- vCache (arXiv 2502.03771): correct and incorrect hits have "highly overlapping similarity distributions", so any single global threshold either lets errors through or rarely hits. Existing caches lack error-rate guarantees. vCache learns per-embedding thresholds with a bounded error rate. — [vCache: Verified Semantic Prompt Caching](https://arxiv.org/html/2502.03771v5)
- Security (arXiv 2601.23088): adversarial prompts can be crafted to collide with a benign prompt's semantic key and retrieve or poison cached responses. Agent pipelines amplify the impact. — [arXiv 2601.23088](https://arxiv.org/pdf/2601.23088)
- Practitioner anecdotes:
  - Banking: a card-cancellation query got account-closure steps at 88.7% similarity, and a 0.7 threshold produced near-99% false positives in some cases.
  - Threshold trade-off from another guide: 0.97 gives about a 5% hit rate, while 0.88 gives higher hits with real correctness risk.

  Both are vendor-reported. — [InfoQ: Reducing false positives in RAG](https://www.infoq.com/articles/reducing-false-positives-retrieval-augmented-generation/); [Respan: semantic cache LLM](https://respan.ai/articles/semantic-cache-llm)
- GPTCache's README says "we no longer add support for new API or models" and "the API may be subject to change at any time". Line-count-based eviction "may cause out-of-memory (OOM) errors", and in-memory mode can't scale horizontally. — [zilliztech/GPTCache](https://github.com/zilliztech/GPTCache)

**Embeddings and RAG**
- LangChain `CacheBackedEmbeddings` keys are `namespace` + hash(text). Set the namespace to the embedding model name to avoid cross-model collisions; the Python default namespace is empty. The default SHA-1 is flagged as not collision-resistant (blake2b/sha256/sha512 available). Only document embeddings are cached unless you pass a `query_embedding_store`. — [LangChain: caching embeddings](https://python.langchain.com/docs/how_to/caching_embeddings); [LangChain source: embeddings/cache](https://reference.langchain.com/v0.3/python/_modules/langchain/embeddings/cache.html)

### Inferences
**Prompt-caching design rules (all providers):**
1. Order the prompt as frozen system prompt and tool list (sorted, deterministic serialization), then long reference docs or few-shot examples, then conversation history, then the volatile user turn.
2. Never interpolate timestamps, request IDs or user names into the prefix.
3. On Anthropic, put an explicit breakpoint at the end of the shared static prefix and use automatic caching for the growing tail. Choose the 1 h TTL only when same-prefix requests are 5–60 min apart.
4. On OpenAI, set `prompt_cache_key` per tenant or conversation family so traffic with the same prefix lands on the same machines. Use `24h` retention for bursty, long-gap traffic, which is free on most models.
5. Monitor cached-token fields as a KPI and alert on hit-rate drops after deploys; the usual cause is a prompt change.
6. Caches are per workspace or org and per model. Model cascades and A/B tests split cache namespaces.

**Prompt-caching cost math example (Anthropic, 5-minute TTL):** a 20K-token static prefix reused 50 times in 5 minutes costs 1.25 + 49×0.1 = 6.15 prefix-units vs 50 uncached, about 88% savings on that portion. With the 1 h TTL at 2x write, the break-even is 3 requests.

**Semantic caching rules:**
- Scope by namespace: cache key = (tenant, user scope if personalized, model, system-prompt version, tool or RAG corpus version, locale) plus the embedding.
- Never semantically cache responses that depend on user-specific data, real-time data or tool side effects.
- Start strict (LangCache ≥0.9 similarity), measure precision on a labeled sample, and add a cheap verifier (cross-encoder or LLM judge) for borderline hits.
- Set a TTL tied to content freshness.
- Log every hit with its similarity score for auditing.
- Prefer *exact-match* response caching (hash of the normalized prompt and params) first; it is safe and often catches a lot (templated prompts, retries, identical FAQs).

**RAG caching:**
- Embeddings: cache by `sha256(model_id + model_version + dims + normalized_text)`. Cache chunk embeddings permanently (they are content-addressed) and query embeddings with a TTL.
- Retrieval results: cache by (normalized query embedding or query text hash, index version, filters, k) with a TTL, and invalidate by bumping the index version on re-index.
- Reranker scores: cache by (query hash, doc ID, reranker version).

#### Code sketches
```python
# Anthropic: explicit breakpoint on the static prefix + automatic caching for the tail
resp = client.messages.create(
    model="claude-opus-5-5", max_tokens=16000,
    cache_control={"type": "ephemeral"},                 # top-level automatic caching (tail)
    system=[{"type": "text", "text": BIG_STATIC_SYSTEM,
             "cache_control": {"type": "ephemeral"}}],   # guaranteed read point
    messages=history + [{"role": "user", "content": question}],
)
u = resp.usage; log(u.cache_read_input_tokens, u.cache_creation_input_tokens)
```
```python
# OpenAI: stable prefix + cache routing key + 24h retention
resp = client.responses.create(
    model="gpt-5.5", input=[{"role": "system", "content": STATIC_PROMPT},
                            {"role": "user", "content": question}],
    prompt_cache_key=f"tenant:{tenant_id}:support-bot:v12",
    prompt_cache_retention="24h",
)
```
```python
# Guarded semantic cache (sketch)
def answer(q, ctx):
    if ctx.personalized or ctx.realtime: return llm(q, ctx)
    exact = r.get(f"llm:exact:{ctx.ns}:{sha256(normalize(q))}")
    if exact: return exact
    hit = vec.search(embed(q), namespace=ctx.ns, k=1)     # ns = tenant+model+prompt_ver+corpus_ver
    if hit and hit.similarity >= 0.92 and verifier(q, hit.prompt):
        metrics.inc("semantic_hit"); return hit.response
    out = llm(q, ctx)
    vec.upsert(embed(q), {"prompt": q, "response": out}, namespace=ctx.ns, ttl=86400)
    return out
```
```python
# Embedding cache key (content-addressed, model-scoped)
key = f"emb:{MODEL_ID}:{MODEL_VER}:{DIMS}:{hashlib.sha256(text.encode()).hexdigest()}"
```

### Gaps
- I could not fetch OpenAI's docs directly to confirm exact per-model cached-input discounts for Oct 2026, the in-memory retention duration (historically about 5–10 min idle, up to 1 h), or the per-prefix request-rate overflow behavior. These come from search summaries.
- I found no official Gemini explicit-cache storage price per MTok-hour.
- I found no official GA date or pricing for Redis LangCache; the sources say preview.
- I found no peer-reviewed measurement of production semantic-cache hit rates or precision across domains beyond vCache's benchmarks.
- Anthropic prompt-caching facts are from the bundled skill reference (cached 2026-10-06), not a live fetch of platform.claude.com.

---

## 8. Sizing and capacity (working-set estimation, per-key memory overhead, hit-ratio math, when caching won't help)

### Takeaway
Size the cache to the *hot working set*, not the dataset. Per-key overhead (roughly 50–100+ bytes in Redis; Valkey 8.1 saved about 20–30 B/key) dominates for small values, and managed services reserve about 25% of node memory. Use effective-latency math to decide whether a cache pays off. Caching won't help when reuse is low (long-tail or unique keys), writes dominate reads, or the miss path is already cheap.

### Cited Findings
- Redis per-key overhead is roughly 88–112 bytes minimum per key (blog estimate; its own examples give about 56 B for a short embstr). For small values overhead can be "5-10x the actual data". Bucket small items into hashes (for example 1,000 per hash) to use compact encodings. Measure with `MEMORY USAGE` and `OBJECT ENCODING`. — [OneUptime: Redis memory overhead per key](https://oneuptime.com/blog/post/2026-03-31-redis-memory-overhead-per-key/markdown); [antirez: memory optimization](https://redis.antirez.com/fundamental/memory-optimization.md)
- Valkey 8.1 cut about 20 B per key-value (about 30 B with TTL) and about 10–20 B per element in large hashes, sets and sorted sets. AWS claims >20% lower footprint. — [Valkey blog: A new hash table](https://valkey.io/blog/new-hash-table/); [AWS: ElastiCache 8.1 for Valkey](https://aws.amazon.com/blogs/database/year-one-of-valkey-open-source-innovations-and-elasticache-version-8-1-for-valkey)
- ElastiCache reserves 25% by default (more on small or micro nodes and write-heavy data tiering). Size usable data against about 75% of node memory; for example `cache.r5.large` maxmemory is about 10.5 GB of 14.0 GB after the reserve (third-party note). — [AWS: Managing reserved memory](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html); [scrapbox note: ElastiCache metrics](https://scrapbox.io/bobstrange-note/ElastiCache_%E3%81%AE_metrics)
- High eviction counts mean memory pressure. Set TTLs and jitter them. — [AWS: Managing reserved memory](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html)
- Most cached objects are never reused ("one-hit wonders"). That is why S3-FIFO and SIEVE use quick demotion, and why admission filters (TinyLFU) improve hit rates at a fixed size. — [S3-FIFO paper](https://junchengyang.com/publication/sosp23-s3fifo.pdf); [Caffeine Efficiency](https://github.com/ben-manes/caffeine/wiki/Efficiency)
- The W-TinyLFU frequency sketch costs about 8 bytes per entry; ARC and LIRS need 2x and 3x metadata for ghost entries. Include this when sizing in-process caches. — [Caffeine Efficiency](https://github.com/ben-manes/caffeine/wiki/Efficiency)
- Facebook's leases cut peak DB query rate from 17K/s to 1.3K/s. Misses under concurrency, not average hit rate, often set DB capacity needs. — [Engineer's Codex](https://read.engineerscodex.com/p/how-facebook-scaled-memcached)
- Hibernate pitfall: mismatched expirations between the query cache and entity cache can make caching *increase* query count. — [DZone: Hibernate cache pitfalls](https://dzone.com/articles/pitfalls-hibernate-second-0)

### Inferences
**Working-set estimation (synthesized formula):**
```
hot_keys          = distinct keys accessed within one TTL window (from logs/metrics; or DAU × keys_per_user × reuse fraction)
bytes_per_entry   = avg_key_bytes + avg_serialized_value_bytes + engine_overhead (~50–100 B Redis/Valkey; more with TTL)
raw_memory        = hot_keys × bytes_per_entry
provisioned       = raw_memory × fragmentation/headroom (≈1.2–1.5) ÷ (1 − reserved_fraction (0.25 on ElastiCache))
# + replicas: multiply node count, not per-node memory
```
- Example: 5M hot keys × (40 B key + 600 B value + 80 B overhead) ≈ 3.6 GB raw → ×1.3 ÷ 0.75 ≈ 6.2 GB per shard group. Choose a 13 GB-class node for growth headroom.
- Validate with a sampling run: load 1% of keys, read `INFO memory` (`used_memory`, `mem_fragmentation_ratio`) and `MEMORY USAGE` on samples, then extrapolate. The fragmentation multiplier of 1.2–1.5 is a practitioner heuristic, not from a retrieved source.

**Hit-ratio math:**
```
effective_latency = h × L_hit + (1 − h) × (L_hit_check + L_miss)      # cache-aside: a miss pays the lookup too
DB_load           = (1 − h) × request_rate   (+ write rate)
speedup           = L_miss / effective_latency
```
- Example: L_hit = 1 ms (Redis), L_miss = 50 ms (DB), h = 0.9 gives 0.9×1 + 0.1×(1+50) = 6.0 ms (8.3x faster). DB load drops 10x.
- At h = 0.5: 0.5 + 0.5×51 = 26 ms. That is still about 2x better, but DB load only halves.
- L1 at 0.01 ms with 60% L1 hits on top of the above gives 0.6×0.01 + 0.4×6.0 ≈ 2.4 ms.
- DB capacity is set by `(1 − h)`: going from 90% to 99% hit rate cuts DB reads 10x. Small hit-rate gains at the top end matter more than they look.

**When caching won't help (decision rules):**
- **Low reuse:** if a key is read about once per TTL window (long-tail search queries, unique IDs), h is about 0 and you pay the lookup plus write overhead. Check the reuse distribution first. A rule of thumb is to cache when expected reads per write per TTL window are at least 2–3.
- **Write-heavy:** if writes per read on a key approach 1, invalidation churn eats the benefit and risks stale reads. Cache derived or aggregate data instead, or use write-behind for counters.
- **Cheap misses:** if the source is fast (a primary-key lookup in a warm buffer cache, about 1 ms), a network cache at about 0.5–1 ms adds complexity for little gain. Use in-process L1 or nothing.
- **Strong consistency required** (balances, inventory decrements, auth revocation): don't cache, or cache with versioned reads and short TTLs, and validate on the write path.
- **Personalized and unbounded key spaces** (per-user × per-filter × per-page): consider caching building blocks (objects) instead of combinations.

**Monitoring KPIs:**
- Hit ratio per key class (not global).
- Eviction rate. Evictions of keys with TTL remaining indicate undersizing.
- p99 latency of hits and misses.
- Memory fragmentation.
- Hot-key and big-key reports.
- Connection count vs `maxclients`.
- For LLM caches: cached-token ratio and semantic-cache precision.

### Gaps
- I found no authoritative engine documentation in this session giving exact per-key overhead by type and version for Redis 8 or Valkey 9; the figures are blog estimates plus Valkey's own delta claims.
- I found no published, sourced rule of thumb for the fragmentation multiplier or the "reads per write" break-even; both are synthesized heuristics.
- I found no source for Memcached slab-allocator overhead and sizing (not researched).
