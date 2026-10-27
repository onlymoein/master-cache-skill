# Cache Invalidation, Consistency, and Failure Modes (stampedes, avalanches, penetration, hot keys) Across All Caching Layers — state as of October 2026

> Research-method note for the report writer: the session's egress proxy blocked direct fetches of several primary sources (engineering.fb.com, usenix.org, aws.amazon.com, wikipedia.org, blog.railway.com, mit.edu mirrors, redis.antirez.com). Where a primary source could not be opened, findings come from search-engine extracts of that primary page or from secondary write-ups, and are labelled as such. Code sketches are the researcher's own syntheses of the cited algorithms, so they sit under "Inferences". They are not quoted from the sources.

---

## 1. Invalidation strategies and their tradeoffs (TTL-only, delete-on-write, update-on-write, versioned keys, tags/surrogate keys/Russian doll, event-driven, CDC, CMS webhooks, deploy-time)

### Takeaway
No single invalidation strategy is enough. Production systems layer them: a TTL as the backstop, explicit invalidation on write (delete, not set), versioned or generational keys where bulk invalidation is needed, tags or surrogate keys for fan-out at the HTTP/CDN tier, and log- or CDC-driven invalidation when correctness matters. CDC replaces application-side dual writes. The strongest pattern is "write once to the DB, derive cache invalidations from the DB's commit log".

### Cited Findings
- **Dual writes are the root problem.** Kleppmann argues that when an application writes to several stores (DB + cache + search index), concurrent writers can leave them permanently disagreeing. His example has two processes updating the DB and the cache in opposite orders. He calls dual writes "a bad idea" mainly because of race conditions, and notes that small divergences accumulate into drift that is hard to recover from. — [Kleppmann, "Using logs to build a solid data infrastructure (or: why dual writes are a bad idea)"](https://martin.kleppmann.com/2015/05/27/logs-for-data-infrastructure.html); [Kleppmann, "Turning the database inside-out"](https://martin.kleppmann.com/2015/03/04/turning-the-database-inside-out.html)
- **Log-based alternative.** Write once to the primary DB, then derive the other stores (caches, indexes, materialized views) by consuming its change stream. Kleppmann frames caches and materialized views as derived data maintained from a log, which moves invalidation out of application code. — [Kleppmann, Bottled Water (Postgres → Kafka)](https://martin.kleppmann.com/2015/04/23/bottled-water-real-time-postgresql-kafka.html); [Turning the database inside-out](https://martin.kleppmann.com/2015/03/04/turning-the-database-inside-out.html)
- **Facebook's production instance of commit-log invalidation (mcsqueal).** Facebook runs a daemon called mcsqueal on each database node. It watches the MySQL commit log and broadcasts invalidations (deletes) to memcache, so web servers do not have to fan the invalidations out themselves (secondary summaries of the NSDI 2013 paper). — [Hemant Gupta, Insights from "Scaling Memcache at Facebook"](https://hemantkgupta.medium.com/insights-from-paper-scaling-memcache-at-facebook-1386a5956859); [Distributed Computing Musings, paper notes](https://distributed-computing-musings.com/2022/03/paper-notes-scaling-memcache-at-facebook/); original paper: [Nishtala et al., NSDI 2013](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf) (could not be fetched this session)
- **Transactional outbox + Debezium.** The application writes an event row to an outbox table in the same DB transaction as the business change. Debezium tails the transaction log and publishes the outbox rows to Kafka, using an "outbox event router" transform. This gives atomic "change + invalidation intent" without 2PC. — [Debezium blog, "Reliable Microservices Data Exchange With the Outbox Pattern"](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)
- Practitioner write-ups describe the tradeoff: a polling outbox relay is simpler but adds latency, log-tailing (CDC) is near-real-time, and consumers must be idempotent because duplicates can be delivered. — [Decodable, "Revisiting the Outbox Pattern"](https://www.decodable.co/blog/revisiting-the-outbox-pattern); [SeatGeek, Transactional Outbox Pattern](https://chairnerd.seatgeek.com/transactional-outbox-pattern/) (search extracts; which write-up made which point was not fully attributable)
- **TTL as backstop.** Even with explicit invalidation, cache-aside designs keep a TTL so that any stale entry left by a race eventually expires. — [Redisson glossary: Cache Invalidation](https://redisson.pro/glossary/cache-invalidation.html)
- **Key-based expiration / Russian doll caching (Rails).** Cache keys embed the record's `updated_at` (cache version). A changed record therefore gets a new key and is never "invalidated" in place, and old entries simply age out of an LRU store. Nested fragments are "Russian doll caching". A change to an inner record does NOT expire the outer fragment unless the association uses `touch: true` (e.g., `belongs_to :product, touch: true`), which cascades `updated_at` up the tree. — [Rails Guides: Caching with Rails](https://guides.rubyonrails.org/caching_with_rails.html)
- Secondary write-ups warn that Russian doll caching "fails silently and confusingly" when `touch: true` is missing. For collections, `render ..., cached: true` fetches cached partials in bulk (multi-get). — [DEV: Performance and Caching in Rails](https://dev.to/agentq/performance-and-caching-in-rails-russian-doll-caching-fragment-caching-and-redis-for-ai-apps-5ehk); [AppSignal on DEV: Russian Doll Caching in Rails](https://dev.to/appsignal/russian-doll-caching-in-rails--3j8o)
- **Surrogate keys / cache tags (CDN tier).** Fastly lets origins tag responses with surrogate keys and purge every object carrying a key in one call. Single-URL, surrogate-key, and bulk surrogate-key purges all support "soft purge", enabled with the `Fastly-Soft-Purge: 1` header. Soft purge marks objects stale rather than removing them, so they can still be served while a fresh copy is fetched. Surrogate keys are case-sensitive. — [Fastly docs: Purging with surrogate keys](https://www.fastly.com/documentation/guides/full-site-delivery/purging/purging-with-surrogate-keys/); [Fastly docs: Soft purges](https://www.fastly.com/documentation/guides/full-site-delivery/purging/soft-purges/)
- **Purge-all cannot be soft** on Fastly: it always hard-invalidates everything. Fastly's suggested workaround is to put a constant key (e.g., `all`) on every object and soft-purge that key instead. Fastly states that soft purges "protect backend servers from being overloaded by an inrush of traffic following a purge". — [Fastly docs: Soft purges](https://www.fastly.com/documentation/guides/full-site-delivery/purging/soft-purges/); [Fastly blog: Introducing Soft Purge](https://www.fastly.com/blog/introducing-soft-purge-more-efficient-way-mark-outdated-content)
- Fastly's guidance for soft purge is to also configure `stale-if-error`. Its DEV post gives an example header for purge-driven content: `Cache-Control: public, max-age=31536000, stale-while-revalidate=60, stale-if-error=31536000`. — [Fastly on DEV: "Is purging still the hardest problem in computer science?"](https://dev.to/fastly/is-purging-still-the-hardest-problem-in-computer-science-339i)
- **Surrogate-key features carry blast radius.** Railway's March 30, 2026 CDN incident was triggered by a configuration change tied to rolling out a Surrogate Keys feature. It enabled caching on domains that had CDN turned off (see Q7). — [Railway incident report, March 30 2026](https://blog.railway.com/p/incident-report-march-30-2026-authenticated-user-data-cached) (via search extract)

### Inferences

#### Decision rules (synthesized)
- **TTL-only**: use it when staleness up to TTL is acceptable, writes are rare or untracked (third-party API responses, exchange rates, config), or you cannot hook the write path. It is the cheapest option with zero coupling, and staleness is bounded by the TTL. Always add jitter (Q5).
- **Delete-on-write (cache-aside invalidation)**: the default for app-tier object caches. Prefer delete over set (Q2), and still keep a TTL backstop.
- **Update-on-write (write-through set)**: only use it when a single writer per key is guaranteed (or writes are serialized/versioned), and the value is cheap to compute on the write path. Otherwise concurrent writers can leave the older value last (Kleppmann's opposite-order race).
- **Versioned / generational keys** (`user:42:v17`, or `ns:{gen}:...` with a namespace generation counter): use them when you need to invalidate a large or unknown set of keys at once (all of a tenant's keys, all of a schema's keys after a deploy) and your store has LRU eviction to reap orphans. The tradeoffs are an extra round-trip to read the version/generation counter (cache it locally for a short time), and orphaned entries using memory until evicted.
- **Key-based expiration (Rails-style)**: use it for rendered fragments and derived views where the key can be computed from the inputs' versions. You never have to "find what to delete", but you need touch cascades and the parent row must be read to compute the key.
- **Tags / surrogate keys**: use them at the CDN and full-page tier, where one entity (a product) appears in many URLs (PDP, category pages, search results, sitemaps). Purge by tag on entity change. Prefer a soft purge plus `stale-while-revalidate`/`stale-if-error` to avoid an origin inrush.
- **Event-driven (message bus)**: use it when multiple services or caches derive from the same entity. Emit the invalidation from an outbox, never "after commit, best effort" in application code.
- **CDC-driven (Debezium/MySQL binlog/Postgres logical replication/DynamoDB Streams)**: use it when correctness matters and multiple code paths (batch jobs, admin tools, migrations, manual SQL) write the DB. CDC catches writes that bypass application code. Consumers must be idempotent and should compare versions/LSNs to avoid applying older events after newer ones.
- **CMS webhooks**: these are a special case of event-driven invalidation where the CMS is the source of truth. Map the webhook payload → affected surrogate keys/tags → soft purge. Webhooks are typically at-least-once with no ordering guarantee, so make the handler idempotent and keep a TTL backstop. (Inference; webhook delivery semantics vary by CMS and were not researched.)
- **Deploy-time invalidation**: prefer content-hashed (fingerprinted) asset URLs with very long TTLs over purges. For app caches whose serialized format or semantics changed, bump a global key prefix/generation (`v{schema_version}:`) rather than flushing the cache. Flushing creates a cold-cache stampede (Q5); a prefix bump does the same unless it is rolled out gradually or the cache is pre-warmed.

#### Code sketch: versioned/generational keys (namespace version bump)
```python
# Namespace generation: invalidate *everything* under a namespace in O(1).
def ns_key(cache, ns: str, key: str) -> str:
    gen = cache.get(f"gen:{ns}")
    if gen is None:
        cache.add(f"gen:{ns}", 1)          # add = set-if-absent
        gen = cache.get(f"gen:{ns}")
    return f"{ns}:g{gen}:{key}"

def invalidate_namespace(cache, ns: str):
    cache.incr(f"gen:{ns}")                # old keys become unreachable; LRU reaps them

# Per-entity version embedded in key (Rails-style key-based expiration):
def product_fragment_key(product) -> str:
    return f"views/product/{product.id}-{product.updated_at_epoch_ms}"  # new version => new key
```
Notes: cache `gen:{ns}` in-process for ~1s to avoid a hot key on the generation counter (Q5, hot keys), and accept up to ~1s of cross-node lag after a bump.

#### Code sketch: CDC/outbox-driven invalidation consumer
```python
# Outbox row written in the SAME transaction as the business update:
#   INSERT INTO outbox(aggregate_type, aggregate_id, version, event) VALUES ('product', 42, 17, 'updated')
# Debezium (or a poller) publishes it to Kafka topic 'outbox.product'.

def on_invalidation_event(evt):            # at-least-once, possibly re-ordered across partitions
    key = f"product:{evt.aggregate_id}"
    cache.delete(key)                      # delete is idempotent => safe under duplicates
    cdn.soft_purge(surrogate_key=f"product-{evt.aggregate_id}")
    # Optional: record high-water version to reject stale fills (see lease/version sketch in Q2)
    cache.set(f"minver:{key}", evt.version, ttl=3600)
```

### Gaps
- Could not retrieve Debezium's current (2026) docs on delivery guarantees. "At-least-once, consumers must be idempotent" is from practitioner write-ups and general Kafka semantics, not a fetched Debezium spec page.
- No sources were retrieved on Postgres logical replication or DynamoDB Streams used specifically for cache invalidation (ordering guarantees per partition/shard, retention windows). The guidance above is inferred from general CDC properties.
- No source retrieved for Cloudflare cache-tag purge semantics or measured purge-propagation latency for any CDN in 2026.
- No source retrieved for CMS webhook delivery semantics (Contentful, Sanity, Strapi, etc.).

---

## 2. Consistency problems and their fixes (DB-write vs cache-delete races, delete vs set, double delete, leases, read-your-writes, replica lag, dual writes, outbox, multi-region)

### Takeaway
The canonical bug is the **stale set**: a reader misses, reads the old DB value, and is delayed. A writer then commits and deletes the key. The reader's late `set` then writes the stale value back, and it sticks until the TTL expires. The fixes, from weakest to strongest, are: a short TTL backstop; delayed double delete (probabilistic, timing-based); **leases / versioned conditional sets** (Facebook-style, deterministic); and CDC/commit-log-ordered invalidation, with monitoring (Meta's Polaris) to measure what is left. Meta's experience shows the residual bugs live in error-handling paths and cross-region replication, so you must **measure** consistency, not just design for it.

### Cited Findings
- **The cache-aside race.** A reader fetches the old value on a miss. A writer then updates the DB and deletes the (still empty) cache entry, so the delete has nothing to remove. The reader finishes and populates the stale value, which persists until the TTL expires. This is why a TTL is kept as a backstop. — [Redisson glossary: Cache Invalidation](https://redisson.pro/glossary/cache-invalidation.html); also described in [JonasBorgesLM/cistern ADR-0011 "cache-aside race — accepted risk and mitigations"](https://github.com/JonasBorgesLM/cistern/issues/50)
- **Opposite-order dual-write race (set-on-write).** Two processes update DB and cache in opposite orders, leaving the cache permanently holding the older value. — [Kleppmann, Turning the database inside-out](https://martin.kleppmann.com/2015/03/04/turning-the-database-inside-out.html)
- **Delayed double delete.** The steps are delete cache → update DB → sleep → delete cache again. Per the Alibaba Cloud write-up, the sleep "needs to be greater than the time of reading data from the database + writing cache" for a concurrent reader, so that the second delete removes any stale value that reader re-populated. Sources note it is heuristic and give no rigorous way to pick the delay. — [Alibaba Cloud Community, "Exploring Cache Data Consistency"](https://www.alibabacloud.com/blog/exploring-cache-data-consistency_600308) (search extract)
- **Leases (Facebook memcache, NSDI 2013).** On a miss, memcached gives the client a 64-bit lease token bound to the key. The client must present the token on its subsequent `set`. A `delete` (invalidation) arriving in between invalidates the token, so the stale set is rejected. — [Meena K., summary of "Scaling Memcache at Facebook"](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce); [Distributed Computing Musings](https://distributed-computing-musings.com/2022/03/paper-notes-scaling-memcache-at-facebook/) (secondary; paper not fetchable)
- **Leases also fix thundering herds.** The memcache server issues a token for a given key at most once every 10 seconds. Other clients requesting the key in that window are told to wait briefly and retry, since the filler usually completes within milliseconds. — [Meena K. summary](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce); [MIT 6.824 lecture notes](https://people.csail.mit.edu/alinush/6.824-spring-2015/l16-memcached.html)
- A secondary blog reports that leases cut Facebook's peak DB query rate from **17K/s to 1.3K/s**. This could not be verified against the paper text in this session. — [Engineer's Codex, "How Facebook served billions of requests per second using Memcached"](https://read.engineerscodex.com/p/how-facebook-scaled-memcached) (search extract, unverified)
- **Cross-region read-your-writes: remote markers.** When a web server in a replica (non-master) region writes, it (1) sets a "remote marker" for the key in its regional cache, (2) performs the write on the master with a trigger to delete the marker afterwards, and (3) deletes the key from its local cache. A later miss that sees the marker reads from the master region instead of the (possibly lagging) local replica. — [Meena K. summary](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce); [Distributed Computing Musings](https://distributed-computing-musings.com/2022/03/paper-notes-scaling-memcache-at-facebook/)
- **Meta "Cache made consistent" (June 2022).** Meta improved TAO's cache consistency by one measure from **six nines (99.9999%) to ten nines (99.99999999%)**. — [Meta Engineering, "Cache made consistent"](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/) (via search extract)
- **Polaris** measures consistency from the client side. It acts as a client of the stateful service and checks client-observable invariants, e.g., "the cache should eventually equal the database" after an invalidation event. It uses a multi-timescale design to cut false positives, and delays DB checks to avoid hammering the DB. Per a secondary recreation of the blog, it reports inconsistency at timescales such as 1, 5, and 10 minutes. — [Meta Engineering](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/); [HN discussion](https://news.ycombinator.com/item?id=31673006); [Mayank-Sharma-27/meta-cache-made-consistent (recreation)](https://github.com/Mayank-Sharma-27/meta-cache-made-consistent)
- **Consistency tracing** is a library that runs in every cache host and logs every cache state mutation for traced writes, so that when Polaris flags an inconsistency engineers can see why. A commenter (apparently a Meta engineer) notes this is cheap because in an invalidation-based cache, inconsistency can only arise in a short window after a write. — [HN discussion of "Cache made consistent"](https://news.ycombinator.com/item?id=31671252) (community commentary, not an official Meta statement)
- **The bug class Meta found.** The recreation of the Meta example works as follows. A cache fill reads data (v=42) and version separately, and a write (→43, version 4→5) lands in between, so the cache holds data 42 tagged with version 5. The write's invalidation hits an error. The error-handling path then calls "drop cache if version > cached version", which is 5 > 5 = false, so the stale 42 stays **indefinitely**. Lessons: fills must read value and version atomically; version-based conflict resolution must never let an older version overwrite a newer one; and bugs hide in error handling. With tracing, on-call located the bug in under 30 minutes. — [Mayank-Sharma-27/meta-cache-made-consistent](https://github.com/Mayank-Sharma-27/meta-cache-made-consistent) (secondary recreation; the real bug also involved DB replication and cross-region traffic)
- **Outbox closes the dual-write gap for invalidation messages**: the outbox row commits atomically with the data change, and CDC delivers it. — [Debezium outbox blog](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)

### Inferences

#### Delete vs set on write: decision rule
- **Delete** on write (then let the next reader fill) is the safe default. Deletes are idempotent and commutative, so duplicates and reordering of invalidations converge to "miss". Concurrent `set`s do not converge: the last arrival wins regardless of version. (Facebook's paper is widely cited as choosing delete for idempotency; see Gaps.)
- **Set** on write only when the cache supports a version-conditional write (CAS / Lua compare of version), or when each key has a single serialized writer.
- **Always order it as: commit the DB transaction first, then invalidate** (ideally from the commit log). Deleting before commit lets a reader re-fill the old value from the DB before the commit lands. Invalidating from application code after commit is lost if the process crashes between the two steps. The outbox/CDC fixes the crash gap.

#### Replica-lag interaction (important for read-replica setups)
- If cache fills read from a lagging read replica, then "commit on primary → delete cache → reader misses → reads *old* row from replica → sets stale value" happens. This is the stale-set race with a window of the full replication lag (seconds), not milliseconds. Fixes:
  1. Fill from the primary for a short window after a write to that key (a remote-marker-like flag: `recently_written:{key}` with TTL ≥ p99 replica lag).
  2. Drive invalidations from the **replica's** own replication stream / commit log, so the delete arrives only after the replica has the new row. (Recall from the Facebook paper: replica-region mcsqueal runs against replica DBs for this reason. Unverified this session.)
  3. Use leases/versioned sets so that a fill carrying an older version than the last invalidation is rejected.
- **Read-your-writes for the writing user** (cheap, common): after a user writes, pin their reads to the primary (or bypass cache) for N seconds via a session flag/cookie, or write-through the new value into a per-user/session cache. This does not fix other users' staleness, but removes the most visible symptom ("I saved and it didn't change").

#### Code sketch: lease-protected cache-aside on Redis (memcache-lease emulation)
```lua
-- KEYS[1]=value key, KEYS[2]=lease key ; ARGV[1]=token, ARGV[2]=value, ARGV[3]=ttl_ms
-- lease_set.lua : only the current lease holder may fill, and only if no delete happened since
if redis.call('GET', KEYS[2]) == ARGV[1] then
  redis.call('SET', KEYS[1], ARGV[2], 'PX', ARGV[3])
  redis.call('DEL', KEYS[2])
  return 1
end
return 0   -- lease was revoked by an invalidation (or expired): drop the fill
```
```python
LEASE_MS = 10_000   # FB issued at most one lease per key per 10s

def get(key, loader, ttl_ms):
    v = r.get(key)
    if v is not None:
        return v
    token = uuid4().hex
    if r.set(f"lease:{key}", token, nx=True, px=LEASE_MS):   # I am the filler
        value = loader()                                      # read DB (primary if recently written)
        r.evalsha(LEASE_SET, 2, key, f"lease:{key}", token, value, ttl_ms)
        return value
    # Someone else holds the lease: wait-and-retry briefly (or serve stale copy if you keep one)
    for delay in (0.005, 0.01, 0.02, 0.05, 0.1):
        time.sleep(delay)
        v = r.get(key)
        if v is not None:
            return v
    return loader()   # fall through; bounded by lease rate so herd is limited

def invalidate(key):
    r.delete(key, f"lease:{key}")    # deleting the lease revokes any in-flight filler's right to set
```

#### Code sketch: version-conditional fill (Meta lesson: never let older overwrite newer)
```lua
-- KEYS[1]=key ; ARGV[1]=version, ARGV[2]=payload, ARGV[3]=ttl_ms
local cur = redis.call('HGET', KEYS[1], 'v')
if (not cur) or tonumber(ARGV[1]) > tonumber(cur) then
  redis.call('HSET', KEYS[1], 'v', ARGV[1], 'd', ARGV[2])
  redis.call('PEXPIRE', KEYS[1], ARGV[3])
  return 1
end
return 0
```
The value and version must come from the **same** DB read (one row, one snapshot). Meta's bug came from reading them separately.

#### Code sketch: delayed double delete (heuristic; prefer leases/CDC)
```python
def update(entity):
    cache.delete(key(entity.id))
    db.commit(entity)
    # delay > p99(reader DB read + cache set) [+ replica lag if fills read replicas]
    scheduler.run_after(seconds=1.0, fn=lambda: cache.delete(key(entity.id)))
```

#### Multi-region
- Options in order of strength: (a) per-region TTL-only (accept staleness = TTL); (b) broadcast deletes to all regions from the commit log (each region's invalidator tails its local replica, as with FB mcsqueal); (c) remote markers / "read from primary region if recently written" for read-your-writes; (d) measure with a Polaris-style checker that samples invalidation events and verifies every regional cache replica converges within N minutes.
- Treat "invalidation lag per region" as an SLO, and alert on the consistency ratio (e.g., "99.99% of sampled writes consistent within 1 min").

#### Polaris-style checker (minimal version any team can build)
- Sample 1 in N writes (from the CDC stream). After a delay of T seconds (several times p99 invalidation latency), read the key from each cache replica/region and from the DB. Report the share of samples where cache ≠ DB and cache ≠ miss. Re-check mismatches after 2T and 5T to separate "slow" from "stuck" (the multi-timescale idea).

### Gaps
- The NSDI 2013 paper PDF and the Meta 2022 blog could not be opened directly. Lease token size, the 10-second lease rate, remote markers, and the 17K/s→1.3K/s figure come from secondary summaries (the last from one blog only).
- I recall, but could not verify this session, that the Facebook paper explicitly justifies delete-over-set by idempotency, and that replica regions run invalidation daemons against replica DBs to avoid racing replication. Treat both as unverified.
- No 2025–2026 sources were found on new consistency techniques beyond Meta's 2022 work (e.g., Redis client-side caching tracking or managed-service features).
- Nothing was retrieved on distributed transactions (2PC/XA) used with caches. Outbox + CDC is the standard recommendation in what was found.

---

## 3. How to choose TTLs (volatility vs staleness tolerance, jitter, per-tier TTLs, soft vs hard TTL)

### Takeaway
Pick a TTL from the **business tolerance for staleness**, not from how often the data changes. Then decouple "freshness" from "availability" with **two TTLs**: a soft TTL (refresh after this) and a hard TTL (never serve after this, or serve only on error). Add **random jitter** so keys created together do not expire together. Different tiers get different TTLs because they differ in purgeability. A browser cache cannot be purged, a CDN can (by tag), and an app cache can be deleted directly.

### Cited Findings
- **Soft TTL / hard TTL pattern** (AWS Builders' Library). Serve the last cached good value when the downstream fails, using soft/hard TTLs, or alternatively cache the error response ("negative cache") with a *different* TTL from positive entries and propagate the error. — [AWS Builders' Library, "Caching challenges and strategies" (Brinkley & Chhabra)](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/) (search extract); [PDF](https://d1.awsstatic.com/builderslibrary/pdfs/caching-challenges-and-strategies.pdf)
- **Caffeine (Java) refresh vs expiry.** `refreshAfterWrite` makes an entry eligible for asynchronous refresh after the duration, but the refresh starts only when the entry is queried. The old value is returned while the refresh runs. The documented pattern pairs it with `expireAfterWrite` as the hard limit, so an entry not queried after it becomes refresh-eligible is allowed to expire. Redundant refreshes are deduplicated. — [Caffeine wiki: Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh); [Caffeine discussion #1935](https://github.com/ben-manes/caffeine/discussions/1935)
- **FusionCache (.NET).** *Eager refresh* is configured as a percentage of the entry duration. A request after that threshold but before expiry triggers a non-blocking background refresh. *Fail-safe* lets an expired entry be used as a fallback when the factory fails, bounded by a max fail-safe duration. *Soft timeouts* apply only when a stale fallback exists, *hard timeouts* always apply, and a timed-out factory keeps running in the background by default so the cache still gets updated. — [FusionCache docs: EagerRefresh.md](https://github.com/ZiggyCreatures/FusionCache/blob/main/docs/EagerRefresh.md); [Timeouts.md](https://github.com/ZiggyCreatures/FusionCache/blob/main/docs/Timeouts.md); [FusionCache README](https://github.com/ZiggyCreatures/FusionCache); [DeepWiki summary (secondary)](https://deepwiki.com/ZiggyCreatures/FusionCache/4-resilience-features)
- **Rails `race_condition_ttl`.** Used with `expires_in`, it is "the number of seconds during which an expired value can be reused while a new value is being generated". The first process to see a recently-expired entry bumps its expiry and regenerates, while others keep serving the old value. — [Rails API: ActiveSupport::Cache::Store](https://api.rubyonrails.org/classes/ActiveSupport/Cache/Store.html)
- **HTTP tier soft/hard TTLs (RFC 5861).** `stale-while-revalidate=N` lets a cache serve a stale response for N seconds while revalidating in the background. If the window is too small or traffic too sparse, requests fall outside it and block on revalidation. `stale-if-error=N` allows serving stale when revalidation hits an error, defined as a situation that would produce a 500, 502, 503 or 504. — [RFC 5861 (httpwg.org)](https://httpwg.org/specs/rfc5861.html); [RFC 5861 text](https://www.ietf.org/rfc/rfc5861.txt)
- **Varnish grace** (default 10 seconds) is Varnish's soft-TTL equivalent: it serves stale while a coalesced background fetch runs. — [Varnish docs: Achieving a high hitrate](https://www.varnish.org/docs/users-guide/increasing-your-hitrate/)
- **TTL jitter.** Randomize each key's TTL, e.g., a random TTL between 55 and 65 minutes for a nominal 1-hour expiry, so that keys written together do not expire together (avalanche prevention). — [Redis blog: How to tame the thundering herd problem](https://redis.io/blog/how-to-tame-the-thundering-herd-problem/) (search extract)
- **CDN support for RFC 5861 varies** by vendor. A 2020 comparison found some vendors' behavior non-compliant, and Cloudflare honoring it only with Origin Cache Control enabled. Verify current vendor docs. — [ctrl.blog, "Which CDN providers support stale-while-revalidate?"](https://www.ctrl.blog/entry/cdn-rfc5861-support.html)
- **Purge-driven long TTLs.** Fastly's example for content that is purged on change uses a 1-year `max-age` with `stale-while-revalidate=60` and `stale-if-error=31536000`. — [Fastly on DEV](https://dev.to/fastly/is-purging-still-the-hardest-problem-in-computer-science-339i)

### Inferences

#### TTL selection rules (synthesized)
1. Ask "how stale may a user ever see this?" (business answer) → that is the **hard TTL** (or, with explicit invalidation, the backstop TTL).
2. Ask "how expensive or slow is a refresh, and how hot is the key?" → set the **soft TTL / refresh-ahead point** (e.g., 50–80% of the hard TTL, or use XFetch). Hot, expensive keys get earlier refresh.
3. If you have reliable invalidation (purge by tag, CDC deletes), the TTL is only a safety net: make it long (hours to days at the CDN, minutes to hours in the app cache).
4. If you have no invalidation, the TTL *is* your consistency bound: keep it as short as the hit-rate math allows.
5. Always jitter: `ttl = base * uniform(0.9, 1.1)`, or `base + rand(0, 0.1*base)`.
6. Set a separate, shorter TTL for negative entries (404 / empty) and error entries (Q6).
7. **Per tier**:
   - *Browser*: cannot be purged → short `max-age` (0–300s) for HTML/API, or `no-cache` + ETag revalidation. Use `immutable` + 1-year TTL only for content-hashed asset URLs. Use `private`/`no-store` for anything personalized.
   - *CDN/shared cache*: long `s-maxage` (or a CDN-targeted header) + purge by surrogate key/tag + `stale-while-revalidate` (seconds to minutes) + `stale-if-error` (hours to days).
   - *App/object cache*: soft TTL + hard TTL, jitter, explicit delete on write.
   - *DB-adjacent / query result cache*: shortest TTLs or none. Prefer invalidation from CDC.
8. Example ladder for a product page: browser `max-age=60`; CDN `s-maxage=86400, stale-while-revalidate=60, stale-if-error=86400` + surrogate key `product-42`; app cache soft 5 min / hard 1 h ± 10% jitter; inventory count not cached beyond 5–10 s (or computed per request).

#### Code sketch: soft/hard TTL with background refresh and stale-on-error
```python
@dataclass
class Entry:
    value: Any
    soft_exp: float   # refresh after
    hard_exp: float   # never serve after (except fail-safe window)

def get(key, loader, soft=300, hard=3600, failsafe=86400):
    e = local.get(key) or remote.get(key)
    now = time.time()
    if e and now < e.soft_exp:
        return e.value                                  # fresh
    if e and now < e.hard_exp:
        refresh_in_background_once(key, loader, soft, hard)   # single-flight per key
        return e.value                                  # stale-while-revalidate
    try:
        v = singleflight.do(key, lambda: loader_with_timeout(loader, timeout=0.5))
        j = random.uniform(0.9, 1.1)
        remote.set(key, Entry(v, now + soft*j, now + hard*j), ttl=failsafe)
        return v
    except Exception:
        if e and now < e.hard_exp + failsafe:
            return e.value                              # stale-if-error / fail-safe
        raise
```

### Gaps
- No authoritative quantitative guidance was found (e.g., "TTL = X × change interval"). TTL choice is a judgment call in all sources found.
- RFC 9213 (`CDN-Cache-Control`, Targeted HTTP Cache Control) and RFC 9111 were not fetched. The per-tier header guidance relies on training knowledge plus one remediation PR using `CDN-Cache-Control: no-store` ([GitHub PR example](https://github.com/Etherealmber/atlas-commerce/pull/59)).
- No 2026-current matrix of CDN support for `stale-while-revalidate`/`stale-if-error` was found (the cited comparison dates from 2020).

---

## 4. Cache stampede / thundering herd / dogpile (lock-on-miss, single-flight, XFetch, stale-while-revalidate, refresh-ahead, CDN request collapsing)

### Takeaway
A stampede happens when many concurrent requests miss the same key and all recompute it. There are four families of fixes, which combine:
- **Coalesce** concurrent misses into one load: in-process single-flight/promise memoization, distributed lock or lease, or CDN/proxy request collapsing.
- **Refresh before expiry**: refresh-ahead, eager refresh, or XFetch probabilistic early expiration.
- **Serve stale while refreshing**: stale-while-revalidate, grace, `race_condition_ttl`.
- **Route the same key to the same node** so that coalescing works at all (Discord).

Default stack: single-flight in-process + soft TTL/SWR + jitter, with a distributed lease added only when per-node coalescing still leaves N_nodes × loads too high.

### Cited Findings
- **Go `singleflight`**: `Group` "represents a class of work and forms a namespace in which units of work can be executed with duplicate suppression". `Do(key, fn)` "executes and returns the results of the given function, making sure that only one execution is in-flight for a given key at a time. If a duplicate comes in, the duplicate caller waits for the original to complete and receives the same results". It returns `shared bool` to say whether the value was given to multiple callers. `DoChan` returns a channel instead. `Forget(key)` makes future calls run the function rather than wait for the earlier call. — [pkg.go.dev: golang.org/x/sync/singleflight](https://pkg.go.dev/golang.org/x/sync/singleflight)
- **XFetch (probabilistic early expiration)**, from Vattani, Chierichetti & Lowenstein, "Optimal Probabilistic Cache Stampede Prevention" (VLDB 2015). Each reader independently decides to recompute early with a probability that rises as expiry approaches. The rule is: recompute if the value is missing or `now − delta·beta·ln(rand()) ≥ expiry`, where `delta` is the measured recompute time, `beta` defaults to 1.0 (>1 favors earlier recomputation), and `rand()` ∈ (0,1]. Expensive-to-rebuild entries get refreshed earlier. — [docs.rs: xfetch crate (credits the VLDB paper)](https://docs.rs/xfetch/); [Redis docs: Cache stampede prevention](https://redis.antirez.com/fundamental/cache-stampede-prevention.html) (search extract)
- XFetch is probabilistic: under heavy concurrency two nodes can still recompute at the same time. — [Redisson glossary: Thundering herd problem](https://redisson.pro/glossary/thundering-herd-problem.html)
- One unverified secondary page suggests `beta ≥ 2.0` for high-concurrency workloads. This is not in the primary sources found. — [OpenSkillIndex page](https://openskillindex.com/skills/intense-visions-harness-engineering-perf-cache-invalidation) (low-confidence)
- **Facebook leases as herd control**: at most one lease per key per 10 seconds, with others told to wait and retry. — [Meena K. summary](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce)
- **Varnish request coalescing**: "Concurrent backend requests for the same object are coalesced – only one fetch is executed at a time, and the other pending fetches wait for the result." With grace, stale content is served while the coalesced fetch runs asynchronously. A `pass` is not coalesced, since the response won't be cached. This is the root of the "hit-for-pass" mechanism, which keeps uncacheable URLs from serializing behind one fetch. — [Varnish docs: Achieving a high hitrate](https://www.varnish.org/docs/users-guide/increasing-your-hitrate/)
- A third-party CDN glossary states Fastly and Cloudflare enable request coalescing by default (not verified against vendor docs). — [cdncertified.com glossary: Request Coalescing](https://cdncertified.com/glossary/request-coalescing/)
- HN practitioner caveat: coalescing in a shared cache reduces propagation to backends, but the cache tier itself can still be overwhelmed by the herd. — [HN comment](https://news.ycombinator.com/item?id=28053723)
- **Discord**: Discord's Rust "data services" layer does request coalescing. The first request for a message spawns a worker task, later identical requests subscribe to it, and one DB query answers all subscribers. Discord added **consistent-hash routing by channel ID** so identical requests land on the same instance, which is what makes coalescing effective. Together with the ScyllaDB migration, p99 read latency is reported at ~15 ms vs 40–125 ms on Cassandra. — [InfoQ, Discord Cassandra→ScyllaDB (2023)](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/); [The New Stack](https://thenewstack.io/how-discord-migrated-trillions-of-messages-to-scylladb/)
- **AWS**: request coalescing ensures "only one pending request is out for uncached resources". — [AWS Builders' Library](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/) (search extract)
- **Rails `race_condition_ttl`** reduces dogpiles on expiry, but Kit's engineering team found it does not prevent stampedes during *cold* population, since there is no lock between the expiry check and the write. They built their own gem. — [Kit Engineering, "What is a cache stampede and how we solved it"](https://engineering.kit.com/2019/10/29/we-built-our-own-cache/); [Rails API](https://api.rubyonrails.org/classes/ActiveSupport/Cache/Store.html)
- **Caffeine** deduplicates redundant refreshes, and **FusionCache** provides eager refresh and protects factories from concurrent execution. — [Caffeine discussion #1935](https://github.com/ben-manes/caffeine/discussions/1935); [FusionCache README](https://github.com/ZiggyCreatures/FusionCache)
- Instagram published "Thundering Herds & Promises" on caching *promises* (in-flight futures) rather than values. Only the HN discussion was retrieved, not the post. — [HN: Thundering Herds and Promises](https://news.ycombinator.com/item?id=19683410)

### Inferences

#### Decision rules
- **Always** do in-process single-flight / promise memoization for any cache-miss loader. It is cheap, has no network cost, and caps concurrent loads at one per key per process.
- **Add soft TTL / SWR** when the key is hot (≥ several requests during one recompute time) and staleness of a few seconds is acceptable. This removes user-visible latency on refresh.
- **Add XFetch** when you can't keep stale copies (hard TTL only, e.g., memcached without a stale store) and recompute is expensive. It needs `delta` stored alongside the value.
- **Add a distributed lock/lease** when the fleet is large (N processes × 1 load each is still too much for the DB) or the load is very expensive (seconds, or a paid API). Always give the lock a TTL slightly longer than the p99 load time, and have waiters serve stale or poll the key. Never let them block unboundedly.
- **Route by key** (consistent hashing to a service instance, or a CDN shield/tiered cache) to make coalescing global rather than per-node.
- **Refresh-ahead (scheduled)** for a small, known set of very hot keys (home page, top-N products, config). A background job refreshes them before expiry, so user traffic never triggers recompute.
- At the CDN: enable request collapsing + origin shielding/tiered caching, and send `stale-while-revalidate`. Make sure uncacheable responses are marked (`private`/`no-store`) so the CDN doesn't serialize requests behind them (the Varnish hit-for-pass lesson).

#### Code sketch: single-flight (Go)
```go
var g singleflight.Group

func GetUser(ctx context.Context, id string) (*User, error) {
    if u, ok := cache.Get(id); ok { return u, nil }
    v, err, _ := g.Do("user:"+id, func() (any, error) {
        // Re-check cache inside the flight to avoid a redundant load after a just-finished flight.
        if u, ok := cache.Get(id); ok { return u, nil }
        u, err := db.LoadUser(ctx, id)
        if err != nil { return nil, err }       // do NOT cache errors here (see Q6)
        cache.Set(id, u, jitter(5*time.Minute))
        return u, nil
    })
    if err != nil { return nil, err }
    return v.(*User), nil
}
// Caveat: one slow/hung loader blocks all waiters -> use DoChan + select with ctx timeout,
// and consider g.Forget(key) on timeout so the next caller retries.
```

#### Code sketch: promise memoization (Node/TypeScript)
```ts
const inflight = new Map<string, Promise<unknown>>();

async function cached<T>(key: string, ttlMs: number, load: () => Promise<T>): Promise<T> {
  const hit = await cache.get<T>(key);
  if (hit !== undefined) return hit;
  let p = inflight.get(key) as Promise<T> | undefined;
  if (!p) {
    p = load()
      .then(async v => { await cache.set(key, v, Math.round(ttlMs * (0.9 + Math.random() * 0.2))); return v; })
      .finally(() => inflight.delete(key));       // remove on success AND failure (don't memoize rejections forever)
    inflight.set(key, p);
  }
  return p;
}
```

#### Code sketch: XFetch
```python
import math, random, time

def xfetch(key, recompute, ttl, beta=1.0):
    entry = cache.get(key)               # stores (value, delta, expiry)
    now = time.time()
    if entry is None or now - entry.delta * beta * math.log(random.random() or 1e-12) >= entry.expiry:
        start = time.time()
        value = recompute()
        delta = time.time() - start      # measured recompute cost (seconds)
        cache.set(key, Entry(value, delta, now + ttl), ttl=ttl)
        return value
    return entry.value
# -log(rand) is Exp(1)-distributed: on average a reader refreshes ~delta*beta before expiry,
# and the probability that *any* reader refreshes rises sharply as expiry nears.
```

#### Code sketch: distributed lock-on-miss with stale fallback (Redis)
```python
def get_with_lock(key, loader, ttl, lock_ms=5000):
    v = r.get(key)
    if v is not None:
        return v
    token = uuid4().hex
    if r.set(f"lock:{key}", token, nx=True, px=lock_ms):
        try:
            v = loader()
            r.set(key, v, ex=jitter(ttl))
            r.set(f"stale:{key}", v, ex=ttl * 24)     # long-lived stale copy for waiters/errors
            return v
        finally:
            release_if_owner(f"lock:{key}", token)     # Lua compare-and-delete
    stale = r.get(f"stale:{key}")
    if stale is not None:
        return stale                                   # serve stale while the lock holder refills
    return poll_until(key, timeout_ms=lock_ms) or loader()   # bounded wait, then degrade
```

### Gaps
- The VLDB 2015 paper itself could not be opened. The optimality claim and the exact recommended beta values come from secondary implementations (docs.rs, Redis docs extract).
- Instagram's promise-caching post content and Fastly/Cloudflare first-party request-collapsing docs were not retrieved.
- No 2026-specific developments were found (e.g., new built-in stampede protection in Redis 8.x / Valkey clients). Not covered.

---

## 5. Avalanche, penetration, breakdown/hot-key expiry, hot keys & big keys, cold start/warming, cache-down (fail-open vs fail-closed, circuit breakers, timeouts), retry storms

### Takeaway
These are mostly **capacity** failures disguised as cache problems. The backing store is sized for the cache hit rate, so anything that drops the hit rate suddenly overloads the DB. That includes mass expiry, a flushed or replaced cache node, a cold deploy, junk keys that never hit, or a dead cache cluster. Defenses: jittered TTLs; negative caching + Bloom filters for nonexistent keys; stale-serving and single-flight for hot keys; local L1 replicas or key splitting for hot and big keys; a gutter/failover pool; gradual warm-up; and a load-shedding or circuit-breaking path to the DB. Design the cache client to **fail open to a protected DB path**, with tight timeouts and no blind retries.

### Cited Findings
- **Avalanche (mass simultaneous expiry)**: the standard fix is TTL jitter (e.g., 55–65 min for a 1 h TTL). Additional mitigations are replicas, circuit breakers and rate limiters on the DB path, and multi-level caching (local + Redis) so a Redis failure doesn't flood the DB. — [Redis blog: How to tame the thundering herd problem](https://redis.io/blog/how-to-tame-the-thundering-herd-problem/); [tanzhuo.xyz, Redis cache penetration, breakdown and avalanche](https://www.tanzhuo.xyz/en/2022/08/11/redis-huan-cun-chuan-tou-ji-chuan-xue-beng) (search extracts)
- **Penetration (requests for keys that don't exist)**: cache the null/empty result with a short TTL (negative caching), and/or check a **Bloom filter of known keys** before touching the cache or DB, rejecting IDs that definitely don't exist. Bloom filters have false positives (some nonexistent keys still pass) and do not support deletion (use counting/cuckoo filters, or rebuild periodically). — [Redis blog](https://redis.io/blog/how-to-tame-the-thundering-herd-problem/); [tanzhuo.xyz](https://www.tanzhuo.xyz/en/2022/08/11/redis-huan-cun-chuan-tou-ji-chuan-xue-beng); [DEV: "The 6-Hour Ghost: … cache avalanche … Bloom filter"](https://dev.to/bigboss6797976/the-6-hour-ghost-how-i-exorcised-a-cache-avalanche-with-async-reconnection-and-a-bloom-filter-4dfb)
- **Hot keys**: remedies are a local in-process L1 copy and key splitting (replicate the key as `key#0..N-1`, read from a random shard), plus read replicas. Hot keys are distinct from stampedes (fixed by locking/SWR) and penetration (fixed by Bloom filter/validation). — [Interview reference: Redis cache penetration/breakdown/avalanche](https://interviewasssistant.com/en/interview-questions/redis-cache-penetration-breakdown-avalanche); [Greenroom caching Q&A (2026)](https://usegreenroom.app/blog/caching-strategies-interview-questions) (secondary, low authority)
- **Discord hot partitions**: unbounded concurrency on a hot partition caused cascading latency. The fix was request coalescing + consistent-hash routing in a data-service layer in front of the DB. — [InfoQ](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)
- **Gutter pool (Facebook)**: when a memcached server fails or stops responding, clients send its traffic to a small dedicated "gutter" pool, about 1% of memcached servers, whose entries have short TTLs. This avoids rehashing the failed server's keys onto healthy servers, which could cascade. — [Distributed Computing Musings](https://distributed-computing-musings.com/2022/03/paper-notes-scaling-memcache-at-facebook/); [Hemant Gupta summary](https://hemantkgupta.medium.com/insights-from-paper-scaling-memcache-at-facebook-1386a5956859)
- **Cold cluster warm-up (Facebook)**: a new or cold memcache cluster serves its misses from a *warm* cluster's cache rather than from the databases, until its hit rate recovers. — [Meena K. summary](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce)
- **Cache non-availability must be survivable** (AWS best practice), and request coalescing is recommended for uncached resources. — [AWS Builders' Library](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/) (search extract)
- **Slack 2-22-22**: a cache control plane that replaced memcached nodes with **empty** spares whenever a node dropped out of the service-discovery catalog (during a Consul agent rolling restart) collapsed the cache hit rate during peak, overloading the Vitess databases and causing a cascading failure (details in Q7). — [Slack Engineering, "Slack's Incident on 2-22-22"](https://slack.engineering/slacks-incident-on-2-22-22/)
- **Facebook 2010 feedback loop**: DB errors were treated as "invalid value → delete cache key → re-query DB", so failures generated more load on the failing DB (details in Q7). — [Facebook Engineering, "More details on today's outage" (2010)](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/)
- **FusionCache timeouts** illustrate the graceful-degradation pattern: a soft timeout returns stale data quickly if any exists, a hard timeout bounds the wait regardless, and the slow factory keeps running in the background to refill the cache. — [FusionCache Timeouts.md](https://github.com/ZiggyCreatures/FusionCache/blob/main/docs/Timeouts.md)

### Inferences

#### Failure-mode → defense table (synthesized)
| Failure mode | Trigger | Primary defenses |
|---|---|---|
| Avalanche | Many keys share an expiry (bulk load, deploy warm-up, fixed TTL); cache node/cluster loss | TTL jitter; soft TTL + SWR; staggered warm-up; gutter pool; DB-side concurrency limits |
| Penetration | Requests for nonexistent IDs (bots, enumeration, bugs) | Negative cache (short TTL); Bloom filter of valid IDs; input validation; rate limit per client |
| Breakdown (hot key expiry) | One very hot key expires | Single-flight + SWR/grace; XFetch; refresh-ahead; never-expire + async refresh for top-N keys |
| Hot key (steady) | One key gets a large share of reads, saturating one cache shard | L1 in-process cache (1–5 s TTL); key splitting `k#0..N`; read replicas; CDN for public data |
| Big key | Multi-MB value / huge hash/list | Split into chunks or a paged structure; compress; cache projections not whole objects; avoid `DEL` of huge keys on Redis (use `UNLINK`, async) — the last point is training knowledge, not verified this session |
| Cold start | Deploy with a new key prefix, new region/cluster, cache flush, failover | Warm from a warm peer (FB cold cluster); pre-warm top-N keys; ramp traffic gradually; don't flush, prefix-bump gradually |
| Cache down | Cache cluster unreachable/slow | Tight client timeouts (single-digit ms for in-DC), circuit breaker, fail open to a **rate-limited/coalesced** DB path, serve stale from L1, shed non-critical traffic |
| Retry storm | Clients retry cache/DB failures, multiplying load | Retry budgets/token buckets, exponential backoff + jitter, no retries on the hot path for cache reads; treat errors ≠ misses |

#### Fail-open vs fail-closed rule
- **Fail open** (treat a cache failure as a miss and go to the source) only if the source can survive the full miss rate, or the fail-open path is guarded by coalescing + a concurrency limiter/circuit breaker. Otherwise fail-open just moves the outage to the DB (Slack 2022, FB 2010).
- **Fail closed / degrade** (return stale L1 data, a static fallback, or a 503 with `Retry-After`) for expensive or non-critical data when the DB cannot absorb the load.
- **Security-sensitive caches** (sessions, authz decisions, rate-limit counters): decide explicitly. Failing open on a rate limiter or permission cache can be a security bug, while failing closed can be an availability bug.
- **Never interpret an error as "value invalid → delete"** (the FB 2010 lesson). On error keep the existing value, and if needed mark it stale.

#### Code sketch: negative caching + Bloom filter guard
```python
NEG = b"__NEG__"

def get_product(pid):
    if not bloom.might_contain(pid):          # definitely not a real ID
        return None
    v = cache.get(f"p:{pid}")
    if v == NEG:
        return None                            # cached "not found"
    if v is not None:
        return v
    row = singleflight(f"p:{pid}", lambda: db.get_product(pid))
    if row is None:
        cache.set(f"p:{pid}", NEG, ttl=jitter(60))      # short negative TTL
    else:
        cache.set(f"p:{pid}", row, ttl=jitter(3600))
    return row
# On create: bloom.add(pid) and cache.delete(f"p:{pid}") so a cached NEG doesn't hide the new row.
```

#### Code sketch: hot-key split + L1
```python
SPLIT = 8
def hot_get(key):
    v = l1.get(key)                                   # in-process, TTL 1-5s
    if v is not None: return v
    v = redis.get(f"{key}#{random.randrange(SPLIT)}") # spread reads across shards
    if v is None:
        v = load_and_fill_all_replicas(key)           # single-flight; writes key#0..key#7
    l1.set(key, v, ttl=2)
    return v
def hot_invalidate(key):
    redis.delete(*[f"{key}#{i}" for i in range(SPLIT)]); broadcast_l1_evict(key)
```

#### Code sketch: cache client with timeout + circuit breaker + guarded fallback
```python
def read(key, loader):
    if breaker.open():
        return guarded_db(key, loader)               # skip cache entirely
    try:
        v = cache.get(key, timeout_ms=5)
        breaker.record_success()
        if v is not None:
            return v
    except (Timeout, ConnectionError):
        breaker.record_failure()                     # do NOT retry inline
    return guarded_db(key, loader)

def guarded_db(key, loader):
    stale = l1.get_stale(key)
    if not db_limiter.try_acquire():                 # bounded concurrency to the DB
        if stale is not None: return stale
        raise Overloaded()                           # 503 + Retry-After; don't cascade
    try:
        return singleflight(key, loader)
    finally:
        db_limiter.release()
```

#### Cache warming after deploys/failovers
- Prefer **no global cold start**: roll out key-format changes per host or per percentage, or read-through from the old prefix and copy forward on miss.
- For a new cluster or region: warm it from a warm peer (FB pattern), replay the top-N keys from access logs, then shift traffic gradually (1% → 10% → 50% → 100%) while watching DB load.
- Capacity-plan the DB for a **degraded** hit rate (e.g., what happens at 80% instead of 98%), not the steady-state one.

### Gaps
- Big-key guidance has no sourced material from this session. The search returned nothing on big keys, and the `UNLINK`/chunking advice is from training knowledge.
- No authoritative sources were retrieved on circuit-breaker or retry-budget parameters specific to caches (AWS's "Timeouts, retries and backoff with jitter" article was not fetched).
- The Facebook gutter/cold-cluster details (including a "two-second hold-off" on deletes during cold warm-up, which I recall from the paper) could not be verified against the paper. The hold-off figure is unverified.
- No 2026-specific hot-key tooling was retrieved (e.g., `redis-cli --hotkeys`, managed-service hot-key detection).

---

## 6. Negative caching (404s, empty results) and error caching (stale-if-error, not caching 5xx)

### Takeaway
Cache "not found" and "empty" results deliberately, with **short, separate TTLs**, and invalidate them on create. Never cache transient errors as if they were data. Instead, keep serving the last good value (`stale-if-error`, fail-safe, soft/hard TTL). If you do cache errors (to protect a struggling dependency), use a very short TTL and keep error entries separate from positive entries. Make every response's cacheability **explicit** at the HTTP layer so that a 5xx or a personalized response never gets stored by a shared cache by default.

### Cited Findings
- **AWS**: two options when the downstream returns errors. (1) Reply with the last cached good value via soft/hard TTL. (2) Cache the error response ("negative cache") with a TTL different from positive entries, and propagate the error to the client. — [AWS Builders' Library](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/) (search extract)
- **RFC 5861 `stale-if-error`** covers errors that "would result in a 500, 502, 503 or 504 HTTP response status code". It does **not** cover 404. — [RFC 5861](https://httpwg.org/specs/rfc5861.html)
- **Fastly**: pair soft purge with `stale_if_error`. Example: `stale-if-error=31536000` on purge-driven content. — [Fastly docs: Soft purges](https://www.fastly.com/documentation/guides/full-site-delivery/purging/soft-purges/); [Fastly on DEV](https://dev.to/fastly/is-purging-still-the-hardest-problem-in-computer-science-339i)
- **FusionCache fail-safe**: on factory failure, reuse the expired entry as a fallback for up to a configured max duration. — [FusionCache README](https://github.com/ZiggyCreatures/FusionCache); [AGentleIntroduction.md](https://github.com/ZiggyCreatures/FusionCache/blob/main/docs/AGentleIntroduction.md)
- **Negative caching for penetration**: cache null with a short TTL. — [Redis blog](https://redis.io/blog/how-to-tame-the-thundering-herd-problem/)
- **Default-caching of headerless responses is dangerous**: during Railway's 2026 incident, "most GET responses without explicit cache headers were cached by default", while origin `Cache-Control` directives were respected where present and `Set-Cookie` headers were not cached. — [Penligent write-up of Railway incident](https://www.penligent.ai/hackinglabs/railway-cdn-caching-incident-how-an-edge-cache-misfire-exposed-authenticated-content/); [Railway status page](https://status.railway.com/incident/X0Q39H56)
- **Web cache deception**: crafted URLs (e.g., `/account/settings/x.css`) can make a CDN cache a logged-in page for anyone. This was demonstrated against PayPal at Black Hat 2017, and still applies to APIs whose backends serve private data without explicit no-store headers. — [DEV: Web Cache Deception Against APIs](https://dev.to/rxkov/web-cache-deception-against-apis-cdns-cache-what-backends-serve-privately-339c)

### Inferences

#### Rules
1. **Negative TTL ≪ positive TTL** (e.g., 30–120 s vs 1 h), jittered. On entity *create*, delete the negative entry (and add it to the Bloom filter).
2. **Distinguish "not found" (cacheable fact) from "lookup failed" (transient error, not cacheable as data)**. The FB 2010 outage was ultimately caused by conflating the two.
3. **HTTP tier**:
   - 200 public: `Cache-Control: public, s-maxage=…, stale-while-revalidate=…, stale-if-error=…`.
   - 404/410: cache briefly at the CDN (`s-maxage=60`) if crawlers or bots hammer missing URLs. 410 can be cached longer. Purge on creation of the URL.
   - 5xx: `Cache-Control: no-store` (or rely on the CDN not caching 5xx by default). Let `stale-if-error` serve the previous 200 instead. Some CDNs cache certain error statuses briefly by default. Check vendor defaults (not researched here).
   - 429/503: send `Retry-After`, never cache as content.
   - Authenticated/personalized: `Cache-Control: private, no-store` (+ `Vary: Cookie`/`Authorization` only if deliberately caching per-user at the edge). Emit these headers on **every** response, including errors and redirects, so a CDN config change can't silently start caching them (Steam 2015, Railway 2026).
4. **App tier**: store a sentinel for "not found" (`__NEG__`), never `None`/`null` (which is indistinguishable from a miss in many clients). Keep error entries in a separate namespace with a very short TTL, if at all.
5. **Empty collections** (`[]` search results): cacheable like positive results, but use a shorter TTL if new items commonly appear (e.g., a "new arrivals" query).

#### Code sketch: error-aware HTTP caching middleware (pseudo-Express)
```ts
app.use((req, res, next) => {
  res.on('header', () => {
    if (!res.getHeader('Cache-Control')) {
      // Secure default: nothing is shared-cacheable unless a route opts in.
      res.setHeader('Cache-Control', req.user ? 'private, no-store' : 'no-store');
    }
    if (res.statusCode >= 500) res.setHeader('Cache-Control', 'no-store');
  });
  next();
});
// Opt-in per route:
// res.set('Cache-Control', 'public, max-age=60, s-maxage=86400, stale-while-revalidate=60, stale-if-error=86400');
// res.set('Surrogate-Key', `product-${id} category-${catId}`);
```

### Gaps
- Default CDN behavior for caching 404/5xx in 2026 (Cloudflare, Fastly, CloudFront, Akamai, Vercel, Netlify) was not researched. Vendor defaults differ and change.
- No primary-source postmortem was found where caching a 5xx itself caused a major outage (the cited incidents involve caching private 200s, not errors).

---

## 7. Real-world incidents and postmortems caused by caching, and their lessons

### Takeaway
Caching incidents fall into four classes:
1. **Feedback loops / herds** where the cache-miss path overloads the source: Facebook 2010, Slack 2022.
2. **Privacy leaks** from caching personalized responses at a shared tier: Steam 2015, Railway 2026, web cache deception.
3. **Silent staleness bugs** in invalidation and error paths: Meta TAO, found only by measurement.
4. **The cache/CDN tier itself as a single point of failure**: Fastly 2021.

The recurring lessons: separate errors from misses; make cacheability explicit on every response; never replace warm cache nodes with empty ones at scale; rate-limit automated "corrective" actions; size the source for a degraded hit rate; and measure cache consistency continuously.

### Cited Findings

#### Facebook, September 23, 2010 (~2.5 h, "worst outage in over four years")
- An automated system checked cached configuration values for validity and replaced invalid ones with values from the persistent store. That works for transient cache corruption, but this time the **persistent store itself** held a value the checker considered invalid. Every client saw the bad value and tried to "fix" it by querying a DB cluster, which was quickly overwhelmed by "hundreds of thousands of queries a second". Clients treated DB errors as invalid values and **deleted the cache keys**, so the query flood continued even after the original value was fixed: a self-sustaining feedback loop. Recovery required stopping all traffic to the DB cluster (taking the site down), reintroducing users gradually, and disabling the auto-correction system. — [Facebook Engineering, Robert Johnson, "More details on today's outage"](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/) (via search extract); [TechCrunch coverage](https://techcrunch.com/2010/09/23/facebook-downtime)
- **Lessons**: an error is not a miss and not an invalid value; never delete cache entries in response to backend errors; rate-limit and kill-switch automated remediation; keep the ability to shed load and readmit traffic gradually.

#### Steam (Valve), December 25, 2015 (~90 min)
- During a DoS attack, Valve deployed a caching configuration through its web caching partner, and a subsequent configuration change "incorrectly enabled caching for authenticated users". Between 11:50 and 13:20 PST, store page requests for about **34,000 users**, containing personal information (billing address, last four digits of the Steam Guard phone number, purchase history, last two digits of the card number, email), may have been served to other users. Valve shut down the store and deployed a new caching configuration. — [SteamDB: Recent caching issues on Steam (quotes Valve's statement)](https://steamdb.info/blog/recent-caching-issues-on-steam); [Security Affairs](https://securityaffairs.com/43189/security/steam-users-data-exposed.html)
- **Lessons**: emergency CDN or caching changes made under attack are high-risk; authenticated responses must carry `private`/`no-store` at the origin regardless of CDN rules; the cache key must include identity, or the response must never be shared.

#### Slack, February 22, 2022 (multi-hour degradation)
- A routine rolling upgrade of Consul agents removed memcached nodes from the service catalog while each agent restarted. Slack's cache control plane (Mcrib) responded by assigning **empty** spare memcached instances. Repeated emptying collapsed cache hit rates at peak, and read load overwhelmed the Vitess databases, causing a cascading failure. The official postmortem attributes the root cause to complex interactions between the application, Vitess, the caching system, and service discovery. — [Slack Engineering, "Slack's Incident on 2-22-22"](https://slack.engineering/slacks-incident-on-2-22-22/)
- Secondary accounts disagree on the rollout step (25% vs the third 25% step bringing the total to 75%). HN commenters argued that Mcrib equated "Consul agent down" with "memcached unhealthy" and evicted still-warm caches, and suggested application-level health checks. — [Recap Tech summary](https://recaptech.substack.com/p/recap-slacks-incident-on-2-22-22); [HN discussion](https://news.ycombinator.com/item?id=31170370)
- **Lessons**: control planes must not replace warm cache nodes en masse (rate-limit replacements); health-check the cache service itself, not a sidecar; rolling maintenance must account for cache warmth, not just process liveness; the DB must be protected (rate limits/load shedding) for hit-rate dips.

#### Meta TAO (2022 "Cache made consistent")
- Residual inconsistencies came from rare interleavings involving versioned fills, failed invalidations, and error-handling code, with real cases also involving replication and cross-region traffic. Meta built Polaris (measurement) and consistency tracing (diagnosis), and moved from six to ten nines of consistency by its measure. — [Meta Engineering](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/); [recreation repo](https://github.com/Mayank-Sharma-27/meta-cache-made-consistent)
- **Lessons**: you can't test your way to cache consistency, you have to measure it in production; fills must be atomic (value + version); error paths need the same rigor as happy paths.

#### Fastly, June 8, 2021 (global CDN outage)
- A software deployment from May 12 contained a latent bug. On June 8 a customer's **valid** configuration change triggered it, and about 85% of Fastly's network returned errors. Fastly detected it within a minute and had 95% of the network normal within 49 minutes. Major sites (NYT, Guardian, Reddit, gov.uk) were briefly unreachable. Some customers, including one in the top ten, had not returned traffic by August 2021. — [Fastly, "Summary of June 8 outage"](https://www.fastly.com/blog/summary-of-june-8-outage); [The Register](https://www.theregister.com/2021/08/05/fastly_ceo_outage/)
- **Lessons**: the CDN is a dependency with its own failure modes. Decide whether the origin can take direct traffic (a capacity fail-open) or whether multi-CDN / DNS failover is needed, and keep origin shielding and caching rules in version control so you can fail over quickly.

#### Railway, March 30, 2026 (52 min, ~0.05% of domains)
- A configuration change tied to a CDN Surrogate Keys feature enabled caching for domains that had CDN turned off. During the window, cached responses could be served to users other than the original requester. Origin `Cache-Control` directives were respected where present and `Set-Cookie` headers were not cached, but most GET responses **without explicit cache headers were cached by default**. Railway reverted the change and purged all cached assets globally at 11:34 UTC. Community reports that authenticated POSTs might also have been cached were unconfirmed. — [Railway incident report](https://blog.railway.com/p/incident-report-march-30-2026-authenticated-user-data-cached); [Railway status page](https://status.railway.com/incident/X0Q39H56); [Penligent analysis](https://www.penligent.ai/hackinglabs/railway-cdn-caching-incident-how-an-edge-cache-misfire-exposed-authenticated-content/); [Railway community thread](https://station.railway.com/feedback/cdn-caching-incident-on-30-march-2026-5f870fd7)
- **Lessons**: the same as Steam's, eleven years later. Apps must send explicit `Cache-Control` on every response (secure default `no-store`/`private`), because platform or CDN defaults can change underneath you, and a global purge capability is a required incident tool.

#### Web cache deception (class of vulnerability)
- Path-confusion URLs make CDNs cache private pages (PayPal, Black Hat 2017), and the technique extends to APIs. — [DEV: Web Cache Deception Against APIs](https://dev.to/rxkov/web-cache-deception-against-apis-cdns-cache-what-backends-serve-privately-339c)

#### Discord (hot partitions, not an outage postmortem)
- Hot channels caused unbounded concurrent reads to the same partition. Request coalescing with consistent-hash routing was the fix. — [InfoQ](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)

### Inferences

#### Cross-incident checklist for the skill (synthesized)
1. **Classify every response** as public-cacheable, private, or no-store at the origin. Default to `no-store` and opt in per route (Steam, Railway).
2. **Treat backend errors as errors**: do not delete or overwrite cache entries on error, serve stale instead (FB 2010; RFC 5861 `stale-if-error`).
3. **Automations that mutate cache state** (auto-correctors, node replacers, purgers) need rate limits, blast-radius caps, and kill switches (FB 2010, Slack 2022).
4. **Plan DB capacity and load shedding for a degraded hit rate** (Slack 2022), and rehearse "cache cluster lost" in game days (AWS: "resilient in face of cache non-availability").
5. **Measure consistency** with a Polaris-style sampler and **trace invalidations** for a sample of writes (Meta 2022).
6. **Have a global purge runbook**, and test that purging everything doesn't itself cause an origin stampede (use soft purge or a constant surrogate key such as `all` on Fastly).
7. **Know your CDN failure plan**: origin direct-serve capacity, multi-CDN, or accept downtime (Fastly 2021).

### Gaps
- GitHub caching-related postmortems: none retrieved. (GitHub's notable incidents in search results were DB/network rather than cache-invalidation.)
- Cloudflare cache-specific incidents (e.g., cache-related parts of Cloudflare's 2023–2025 outages, or Cloudbleed 2017, where leaked memory was cached by search engines) were not retrieved this session.
- Discord outage postmortems involving caches, Shopify, Stripe, Pinterest, Netflix (EVCache) and Uber cache-consistency blog posts were not retrieved, because of the tool-call budget and egress blocks on several engineering blogs.
- The primary texts of the Facebook 2010 postmortem and the Railway 2026 report could not be opened directly. Details come from search-engine extracts of those pages plus secondary coverage.
