# Distributed caches (Redis, Valkey, Memcached and others)

Last reviewed: 2026-10-27 · Applies to: Valkey 8.1–9.x, Redis Open Source 8.x, Memcached, Dragonfly, Garnet; managed ElastiCache/MemoryDB, Memorystore, Azure Managed Redis, Upstash, Momento

## Contents

- When to read this
- Default recipe
- Rules and gotchas
- Choosing an engine
- Managed options
- Keys, TTLs and serialization
- Data structures for caching
- Hot keys, big keys, clustering
- Client-side caching (near cache)
- Sizing
- Version notes
- Verify
- Sources

## When to read this

When the plan uses or adds a shared L2 cache. Patterns: `references/layers/in-process.md`. Invalidation and races: `references/core/invalidation-consistency.md`. Security hardening: `references/core/security.md`.

## Default recipe

```conf
# valkey.conf / redis.conf for a pure cache
maxmemory 12gb                 # ≈ 75% of a 16 GB node; leave room for fragmentation and replication buffers
maxmemory-policy allkeys-lfu   # or allkeys-lru for recency-driven workloads
save ""                        # no RDB snapshots for a pure cache
appendonly no
lazyfree-lazy-eviction yes
```

```ts
// Key shape: {app}:{env}:v{schema}:[t:{tenant}:]{entity}:{id}
const key = `shop:prod:v3:t:${tenantId}:product:${id}`
await redis.set(key, payload, { EX: ttlWithJitter(300) })   // TTL = staleness budget ± ~10%
```

Pick managed Valkey on AWS/GCP unless you need Redis-only modules.

## Rules and gotchas

1. Open-source Redis/Valkey defaults to `maxmemory 0` (no limit) and `noeviction`: a full cache rejects writes with OOM errors. Always set `maxmemory` and an `allkeys-*` policy for caches. `volatile-*` only works if every evictable key has a TTL.
2. ElastiCache reserves 25% of node memory by default (more on small/micro nodes) and defaults `maxmemory-policy` to `volatile-lru`. Redis Software (Enterprise) also defaults to `volatile-lru`. Check the effective policy.
3. Every key gets a TTL, even with explicit invalidation (backstop). Jitter it.
4. Version keys (`v{schema}`) and bump the version on serialization/shape changes instead of `SCAN`+`DEL` or `FLUSHALL`.
5. Never `KEYS *` in production (use `SCAN`); delete big keys with `UNLINK`.
6. Keep values small (single-digit KB ideally, < ~100 KB). Large values block command execution and saturate the NIC.
7. Don't use language-native serialization (Java serialization, Python pickle) for cached values: security and cross-version fragility.
8. Persistence on a pure cache costs fork/copy-on-write memory spikes and disk I/O. Disable it unless a cold restart would stampede the database (then prefer warm-up from a replica).
9. Reuse one long-lived client per process; never connect per operation. Co-locate cache and app in the same region.
10. Never expose Redis/Valkey to the internet; require auth/ACLs and TLS (see `references/core/security.md`; the 2025 RediShell RCE found ~60,000 exposed unauthenticated instances).

## Choosing an engine

| Engine | License (Oct 2026) | Choose when | Avoid when |
|---|---|---|---|
| **Valkey** 8.1/9.x | BSD-3 (Linux Foundation) | Default open engine on AWS/GCP; 9.0 adds multiple DBs in cluster mode, atomic slot migration, hash field expiration; 9.1 adds DB-level ACLs | You need Redis Query Engine/JSON modules with first-party support |
| **Redis Open Source** 8.x | Tri-license RSALv2 / SSPLv1 / AGPLv3 (7.4–7.8 RSAL/SSPL; ≤ 7.2 BSD) | You need bundled JSON, Search, time series, probabilistic structures, vector sets (beta), or Redis Enterprise features | Your org bans AGPL/SSPL; Intel SVS vector optimizations are RSALv2-only |
| **Memcached** | BSD | Pure string cache, simple multithreaded scaling | You need structures, per-field TTL, replication |
| **Dragonfly** | BSL 1.1 (no reselling as a managed service) | Vertical scale on one big box | You offer it as a service |
| **Garnet** | MIT | Azure/.NET stacks (Cosmos DB Garnet Cache) | Self-hosted clusters: cluster mode is passive, no leader election |
| **KeyDB** | BSD-3 | — | New builds (stalled at 6.3.0) |

## Managed options

| Service | Notes |
|---|---|
| ElastiCache / MemoryDB for Valkey | Serverless 33% cheaper than Serverless Redis OSS, 100 MB minimum (~$6/month); node-based 20% cheaper; VPC-only |
| Memorystore for Valkey | GA 2025 (99.99% SLA); 9.0 GA |
| Azure Managed Redis | Replacement for Azure Cache for Redis. **Azure Cache for Redis:** creation blocked for all customers from 2026-10-01; Enterprise tiers retire 2027-03-31; Basic/Standard/Premium retire 2028-09-30. Plan migrations |
| Upstash | Per-command pricing (~$0.20 per 100K), REST endpoint for edge runtimes, idle databases free (check current pricing) |
| Momento | Serverless, priced per GB transferred (check current pricing; docs conflict) |

## Keys, TTLs and serialization

- Key shape `{app}:{env}:v{schema}:[t:{tenant}:]{entity}:{id}[:{variant}]`. Short but readable; key bytes count toward overhead.
- Multi-tenant: the tenant prefix is mandatory in every code path; wrap key construction in one helper.
- TTL = staleness budget + 5–15% jitter. Typical: config/flags 30–60 s; catalog/content 5–60 min; sessions/profiles 15–60 min with delete on write; content-addressed data long; negative results 10–60 s.
- Serialization: JSON (debuggable) or MessagePack/CBOR (20–50% smaller); Protobuf/Avro when schemas evolve. Compress values > ~1 KB with zstd or LZ4, and prefix a 1-byte header (format + codec) so you can change codecs without a flag day.

## Data structures for caching

| Structure | Use |
|---|---|
| STRING | Serialized object; `SET k v EX ttl NX` for lock-ish fills |
| HASH | Partial-field objects; bucketing many small items (compact encoding) |
| Hash field expiration (`HEXPIRE`, `HGETEX`/`HSETEX` in Redis 7.4+/8; Valkey 9.0) | Per-field TTL without a key per field |
| ZSET | Leaderboards, top-N computed caches |
| SET | Tag → keys index for tag invalidation |
| Bloom/Cuckoo | Negative caching ("definitely not present") |
| STREAM | Write-behind queues |

## Hot keys, big keys, clustering

- Detect: `redis-cli --bigkeys` (scans everything; off-peak), `--hotkeys` (needs an LFU policy), per-node CPU/bandwidth skew.
- Hot keys: local L1 with 1–5 s TTL; replicate the key N ways (`k#0..k#7`, read a random copy, write all); read replicas; CDN for public data.
- Big keys: split into buckets, cache projections, compress, cap sizes at write time.
- Cluster hash tags (`{user:42}:profile`) only when multi-key ops or Lua need co-location; overusing one tag creates a hot slot.
- Scale reads with replicas (stale by replication lag), writes and memory with shards.

## Client-side caching (near cache)

Redis/Valkey server-assisted client-side caching (`CLIENT TRACKING`): the server remembers which keys a connection read and pushes invalidations.

- Needs RESP3 for same-connection pushes (RESP2 uses `REDIRECT` + `__redis__:invalidate`). Modes: default, `OPTIN`/`OPTOUT`, `BCAST` with prefixes.
- Jedis 5.2+ supports it with RESP3 and Redis 7.4+; redis-py reportedly 5.1+ (verify class names such as `CacheConfig`); node-redis support unconfirmed.
- Costs server memory for the tracking table. Use `BCAST` + prefix for small hot namespaces.

## Sizing

```text
bytes_per_entry = key_bytes + serialized_value_bytes + engine_overhead (≈ 50–110 B per key; Valkey 8.1 saves ≈ 20–30 B)
raw_memory      = hot_keys_per_TTL_window × bytes_per_entry
provisioned     = raw_memory × 1.2–1.5 (fragmentation, heuristic) ÷ (1 − reserved_fraction, 0.25 on ElastiCache)
```

Example: 5 M hot keys × (40 + 600 + 80) B ≈ 3.6 GB raw → ≈ 6.2 GB provisioned → a 13 GB-class node for headroom. Validate by loading 1% of keys and reading `INFO memory` and `MEMORY USAGE`. Use `python scripts/size_cache.py --keys K --avg-bytes V` for the arithmetic. For small values, bucket into hashes; overhead can be 5–10× the data.

## Version notes

- Redis 8.0 (May 2025): renamed Redis Open Source, AGPLv3 option added, modules bundled. Newer policies `allkeys-lrm`/`volatile-lrm` (least recently modified) exist; the introducing version is unconfirmed (one source says 8.6).
- Valkey 8.1 new hash table; 9.0 GA 2025-10-21; 9.1 I/O threading redesign.
- Exact latest versions conflict across sources; check release pages before pinning.

<details><summary>Old patterns</summary>

- Redis with `noeviction` used as a cache.
- `KEYS pattern` + `DEL` for invalidation.
- Creating new Azure Cache for Redis instances (blocked from 2026-10-01).
- KeyDB for new deployments.

</details>

## Verify

```bash
redis-cli INFO stats | grep -E 'keyspace_hits|keyspace_misses|evicted_keys|expired_keys'   # take deltas over time
redis-cli CONFIG GET maxmemory-policy
redis-cli INFO memory | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation_ratio'
redis-cli --bigkeys
redis-cli MEMORY USAGE shop:prod:v3:product:42
```

Rising `evicted_keys` with keys still inside their TTL means the cache is undersized.

## Sources

- [redis/redis (license, Redis Open Source)](https://github.com/redis/redis)
- [Redis key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis client-side caching libraries](https://redis.io/blog/faster-redis-client-library-support-for-client-side-caching/)
- [valkey-io/valkey](https://github.com/valkey-io/valkey)
- [Valkey 9.0 (Linux Foundation)](https://www.linuxfoundation.org/press/valkey-9.0-delivers-performance-and-resiliency-for-real-time-workloads)
- [Valkey: a new hash table](https://valkey.io/blog/new-hash-table/)
- [ElastiCache reserved memory](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html)
- [ElastiCache and MemoryDB support Valkey](https://aws.amazon.com/blogs/database/amazon-elasticache-and-amazon-memorydb-announce-support-for-valkey/)
- [Azure Cache for Redis retirement](https://docs.azure.cn/en-us/azure-cache-for-redis/cache-retired-features)
- [Dragonfly license](https://dragonflydb.io/docs/about/license)
- [microsoft/garnet](https://github.com/microsoft/garnet)
- [Netflix EVCache](https://github.com/netflix/evcache/wiki)
