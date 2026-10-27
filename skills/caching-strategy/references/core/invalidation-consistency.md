# Invalidation and consistency

Last reviewed: 2026-10-27 · Applies to: all layers (browser, CDN, proxy, app cache, DB-derived caches)

## Contents

- When to read this
- Default recipe
- Rules and gotchas
- Choosing an invalidation strategy
- The stale-set race and its fixes
- Write ordering and dual writes
- Replicas, read-your-writes, multi-region
- TTL design
- Tag schemes and purge pipelines
- Measuring consistency
- Verify
- Sources

## When to read this

Whenever the plan adds an app cache, a CDN purge, a tag scheme, or any cache that must reflect writes. Stampede and failure handling: `references/core/stampede-failure.md`.

## Default recipe

Layer several mechanisms; no single one is enough:

1. **TTL backstop** on every cached item (jittered).
2. **Delete on write** for object caches (never set-on-write by default).
3. **Versioned/generational keys** for bulk invalidation (schema changes, tenant-wide resets).
4. **Tags / surrogate keys** at the HTTP tier, soft-purged on change.
5. **Commit-log-driven invalidation** (transactional outbox + CDC) where correctness matters or many code paths write the DB.

Order on every write: **commit the database → delete the app-cache key(s) → purge inner HTTP layers (origin proxy) → soft-purge the CDN tags**. Assets use content-hashed URLs and are never purged.

## Rules and gotchas

1. Delete, don't set. Deletes are idempotent and commutative, so duplicate or reordered invalidations converge to "miss". Concurrent sets don't converge: the last arrival wins regardless of version.
2. Set-on-write only with a version-conditional write (CAS/Lua compare) or a single serialized writer per key.
3. Never delete before commit: a reader can refill the old row before the commit lands.
4. Invalidating from application code "after commit, best effort" is lost if the process crashes between the two steps. Use a transactional outbox (or CDC) for anything that must not be missed.
5. CDC catches writes that bypass the app (batch jobs, admin tools, migrations, manual SQL). Consumers must be idempotent and should ignore events older than the last applied version.
6. Fills must read value and version atomically (one row, one snapshot). Meta's TAO bug came from reading them separately, which let a stale value persist indefinitely.
7. Bump a key prefix (`v{schema}`) on format changes instead of flushing; a flush is a cold-start stampede. Roll prefix changes out gradually or pre-warm.
8. Webhooks (CMS) are at-least-once and unordered: idempotent handler, debounce/batch purges, TTL backstop.
9. Keep a global purge runbook and test that purging everything doesn't itself stampede the origin (soft purge, constant `all` tag).

## Choosing an invalidation strategy

| Strategy | Use when | Trade-off |
|---|---|---|
| TTL only | Staleness up to the TTL is acceptable; writes are untracked (third-party data, rates, config) | Cheapest; staleness bounded by TTL; always jitter |
| Delete on write | Default for app object caches | Needs the write path; stale-set race remains (below) |
| Update on write (write-through) | Single writer per key, cheap value, read-after-write needed | Concurrent writers can leave the older value |
| Versioned / generational keys | Invalidate a large or unknown key set at once (tenant, schema) | Extra read of the version counter (cache it ~1 s locally); orphans until evicted |
| Key-based expiration (Rails Russian doll, `cache_key_with_version`) | Rendered fragments whose key derives from input versions | Needs touch cascades (`touch: true`); parent row must be read |
| Tags / surrogate keys | One entity appears in many URLs (product on PDP, category, search, sitemap) | Tag limits per vendor; purge rate limits |
| Event bus (outbox) | Several services derive from the same entity | Infra; at-least-once delivery |
| CDC (Debezium, binlog, Postgres logical replication, DynamoDB Streams) | Correctness matters; many writers | Infra; ordering per partition only |
| CMS webhook | CMS is the source of truth | At-least-once, unordered |
| Deploy-time | Asset/format changes | Hash URLs; prefix bumps, not flushes |

## The stale-set race and its fixes

The canonical bug: reader misses and reads the old row → writer commits and deletes the (still empty) key → reader's delayed `set` writes the old value back, where it stays until the TTL expires.

Fixes, weakest to strongest:

| Fix | How | Notes |
|---|---|---|
| Short TTL backstop | Bounds the damage | Always on |
| Delayed double delete | Delete, commit, then delete again after `delay > p99(read DB + set cache)` (+ replica lag) | Heuristic timing |
| **Leases** | On miss, issue a token (`SET lease:{key} token NX PX 10000`); the fill succeeds only if the token is still present; a delete removes key and lease | Deterministic; also limits herds (one filler per key per lease period). Script: `assets/snippets/app/redis-lease.lua` |
| **Version-conditional set** | Store `{v, data}`; write only if the new version is greater | Value and version from the same read. Script: `assets/snippets/app/redis-version-set.lua` |
| Commit-log-ordered invalidation | Invalidate from the (replica's) change stream | Delete arrives only after the data is visible |

```python
# Lease-protected cache-aside (Redis); LEASE_SET is the loaded redis-lease.lua
def get(key, loader, ttl_ms):
    v = r.get(key)
    if v is not None:
        return v
    token = uuid4().hex
    if r.set(f"lease:{key}", token, nx=True, px=10_000):        # I am the filler
        value = loader()
        r.evalsha(LEASE_SET, 2, key, f"lease:{key}", token, value, ttl_ms)
        return value
    for delay in (0.005, 0.01, 0.02, 0.05, 0.1):                  # someone else is filling
        time.sleep(delay)
        if (v := r.get(key)) is not None:
            return v
    return loader()

def invalidate(key):
    r.delete(key, f"lease:{key}")    # revokes any in-flight filler's right to set
```

## Write ordering and dual writes

- Application code writing DB + cache + search index is a "dual write": concurrent writers in opposite orders leave stores permanently disagreeing, and small divergences accumulate.
- Fix: write once to the database; derive caches from its change log (Kleppmann). Facebook's mcsqueal tails the MySQL commit log and broadcasts memcache deletes.
- Transactional outbox: insert an event row in the same transaction as the change; Debezium (or a poller) publishes it; an idempotent consumer deletes keys and soft-purges tags.

```python
def on_invalidation_event(evt):        # at-least-once, possibly reordered across partitions
    cache.delete(f"product:{evt.aggregate_id}")
    cdn.soft_purge(tags=[f"product:{evt.aggregate_id}"])
```

## Replicas, read-your-writes, multi-region

- If fills read a lagging replica, the stale-set window is the full replication lag (seconds). Fill from the primary for a short window after writing a key (`recently_written:{key}` with TTL ≥ p99 lag), drive invalidations from the replica's own change stream, or use versioned/leased fills.
- Read-your-writes for the writer: pin their reads to the primary or bypass the cache for N seconds (session flag), or write-through into a per-session cache. Fixes the most visible symptom ("I saved and it didn't change").
- Multi-region, weakest to strongest: per-region TTL only → broadcast deletes to every region from the commit log → "remote markers" (read from the primary region if recently written) → measure convergence per region with a sampler. Treat invalidation lag per region as an SLO.

## TTL design

1. Hard TTL = the business answer to "how stale may anyone ever see this?". With reliable invalidation, the TTL is only a safety net (long); without it, the TTL is the consistency bound (short).
2. Soft TTL / refresh point at 50–80% of the hard TTL, or XFetch, for hot, expensive keys.
3. Jitter: `ttl = base × uniform(0.9, 1.1)` (e.g. 55–65 min for 1 h).
4. Negative entries get a separate, much shorter TTL (30–120 s), deleted on create.
5. Per tier: browser short or `no-cache` (can't purge) → CDN long with tag purge + SWR + SIE → app cache soft/hard + jitter + delete on write → DB-adjacent query caches shortest or CDC-driven.

Example ladder for a product page: browser `no-cache` (or `max-age=60`); CDN `max-age=86400, stale-while-revalidate=60, stale-if-error=86400` + tag `product:42`; app cache soft 5 min / hard 1 h ±10%; stock not cached beyond 5–10 s and re-checked at checkout.

## Tag schemes and purge pipelines

- Tags: lowercase `entity:id` plus a constant `all`; ≤ 50 per response (CloudFront's per-object cap); hash long IDs if you might change CDNs.
- One entity change maps to a fixed tag set (`product:42`, `category:9`, `search`, `sitemap`). Document the map in the plan's invalidation map.
- Soft purge by default (Cloudflare `invalidate_cache`, Fastly `Fastly-Soft-Purge: 1`, Vercel `invalidateByTag`, Akamai invalidate). Hard purge for legal takedowns and leaked data. Fastly purge-all can't be soft: soft-purge the `all` tag.
- Purge rate limits: Cloudflare Free 5 tag-purge requests/min (100 tags each); Netlify each tag twice per 5 s; CloudFront bills per tag beyond 1,000/month. Batch and debounce (e.g. collect tags for 2–5 s, then one request).
- Purge order: inner layer before outer (app cache → origin proxy → CDN), after the DB commit.
- Set a purge-to-visible target (e.g. < 30 s for news) and probe it synthetically.

## Measuring consistency

A minimal Polaris-style checker (Meta used this approach to go from six to ten nines on TAO):

1. Sample 1 in N writes from the change stream.
2. After T seconds (several × p99 invalidation latency), read the key from each cache replica/region and from the DB.
3. Count samples where cache ≠ DB and cache ≠ miss. Re-check mismatches at 2T and 5T to separate "slow" from "stuck".
4. Alert on the ratio (e.g. 99.99% of sampled writes consistent within 1 min). Trace invalidations for sampled writes to diagnose.

## Verify

- Unit test the stale-set race: interleave a slow reader and a writer (fake clock, injected delays) and assert the cache ends empty or fresh, never old.
- Staging: edit a record, measure time until every layer serves the new value; confirm the TTL backstop exists on every key (`redis-cli TTL key` ≠ -1).
- Replay duplicate and out-of-order invalidation events; state must converge.

## Sources

- [Kleppmann: why dual writes are a bad idea](https://martin.kleppmann.com/2015/05/27/logs-for-data-infrastructure.html)
- [Kleppmann: turning the database inside-out](https://martin.kleppmann.com/2015/03/04/turning-the-database-inside-out.html)
- [Scaling Memcache at Facebook (NSDI 2013)](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf)
- [Meta Engineering: Cache made consistent](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/)
- [Debezium: outbox pattern](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)
- [Rails Guides: caching (Russian doll, touch)](https://guides.rubyonrails.org/caching_with_rails.html)
- [Fastly soft purges](https://www.fastly.com/documentation/guides/full-site-delivery/purging/soft-purges/)
- [AWS Builders' Library: caching challenges and strategies](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/)
- [RFC 5861](https://httpwg.org/specs/rfc5861.html)
