# Database and ORM caching

Last reviewed: 2026-10-27 · Applies to: PostgreSQL, MySQL 8+, ProxySQL, Readyset, Cloudflare Hyperdrive, Prisma Accelerate, Hibernate, PgBouncer/Supavisor

## Contents

- When to read this
- Decision ladder
- Rules and gotchas
- Buffer caches
- Materialized views and summary tables
- Read replicas
- Transparent query caches
- ORM caches
- Poolers and plan caches
- Verify
- Sources

## When to read this

When the app has a relational database (it almost always does) and the plan considers caching reads, or when queries are the bottleneck. The database already caches pages; tune that first.

## Decision ladder

Cheapest and safest first:

1. Fix queries and indexes (N+1, missing indexes, full scans). Check the buffer-cache hit ratio.
2. Size the buffer pool to the hot working set.
3. Materialized views or summary tables for expensive aggregates.
4. Read replicas for read scale, with read-your-writes routing.
5. A transparent query cache when app code can't change (Readyset for replication-consistent caching; ProxySQL or Hyperdrive for TTL caching).
6. App or ORM cache (Redis cache-aside, Hibernate L2, Prisma Accelerate) when you need cross-service sharing, tags or business-level keys.

## Rules and gotchas

1. MySQL's query cache was removed in 8.0 (global mutex, table-wide invalidation, fragmentation). Don't recommend it.
2. Every transparent cache has its own staleness model; write it in the plan. Hyperdrive caches reads for 60 s with 15 s SWR by default (max 1 h) and does **not** invalidate on your writes; for read-after-write use a second Hyperdrive config with caching off.
3. Replicas are a stale cache tier: the stale-set window widens to the full replication lag (`references/core/invalidation-consistency.md`).
4. Hibernate's query cache stores only IDs resolved against the entity (L2) cache; mismatched expirations can **increase** query count. Any update to a table invalidates its cached queries; avoid the query cache on frequently updated tables. Data written by other apps goes stale.
5. Connection poolers are not caches. They reduce connection setup and backend count; they interact with prepared-statement/plan caches.
6. SQL-level `PREPARE` is invisible to PgBouncer and breaks in transaction mode.
7. Prisma Migrate needs a direct connection, not a pooler.

## Buffer caches

- Postgres `shared_buffers`: start around 25% of RAM on a dedicated server; above ~40% rarely helps; very large machines may cap at 128–256 GB and leave the rest to the OS page cache (pages can be double-buffered). Changing it needs a restart. `effective_cache_size` (50–75% of RAM) is a planner hint, not an allocation.
- MySQL InnoDB buffer pool: commonly 50–75% of RAM on a dedicated host.
- Don't starve the OS page cache with large in-process caches in the same container.

## Materialized views and summary tables

```sql
CREATE MATERIALIZED VIEW daily_revenue AS
  SELECT date_trunc('day', created_at) AS d, sum(amount) AS total FROM orders GROUP BY 1;
CREATE UNIQUE INDEX ON daily_revenue (d);                -- required for CONCURRENTLY
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_revenue;    -- doesn't block readers; schedule with pg_cron
```

pg_ivm offers incremental view maintenance (PG 13–17), but `refresh_immv` takes an AccessExclusiveLock. Show "as of" timestamps on screens backed by refreshed views.

## Read replicas

Read-your-writes options:

- Pin the writing user to the primary for N seconds after a write (≥ worst-case lag):

```ts
await db.primary.update(/* ... */)
await redis.set(`ryw:${userId}`, '1', { PX: 2000 })
const conn = (await redis.exists(`ryw:${userId}`)) ? db.primary : db.replica
```

- Causal tokens (LSN/version): read from a replica only at or past that position.
- Read the user's own data from the primary; keep transaction reads on the primary.
- Pull lagging replicas out of the pool.

## Transparent query caches

| Tool | Model | Notes |
|---|---|---|
| Readyset | Wire-compatible Postgres/MySQL proxy; "deep" caches kept current from the replication stream; "shallow" TTL caches | Change the connection string; choose queries with `CREATE CACHE FROM SELECT …` (verify syntax) |
| ProxySQL (MySQL) | Query rules with `cache_ttl` (ms) per digest; `cache_empty_result` | TTL only |
| Cloudflare Hyperdrive | Pools connections; caches read queries from Workers | 60 s / 15 s SWR default; no write invalidation |

## ORM caches

| ORM | Cache | Notes |
|---|---|---|
| Hibernate / JPA | Second-level (entity, "dehydrated") + query cache | Best for reference data and rarely updated entities with a single writer app; choose `READ_ONLY` / `NONSTRICT_READ_WRITE` / `READ_WRITE`; queries opt in with `setCacheable(true)` |
| Prisma Accelerate | Per-query `cacheStrategy: { ttl, swr, tags }` | Tags ≤ 64 chars, alphanumeric/underscore; `$accelerate.invalidate({ tags })` (≤ 5 tags per call; paid plans; daily limits); not for writes |
| ActiveRecord, Django ORM, EF Core, GORM, Ecto, SQLAlchemy | No transparent result cache | Use the framework cache API (see framework references) |
| Drizzle | Not covered by this skill's research | Check current docs |

```ts
const posts = await prisma.post.findMany({
  where: { published: true },
  cacheStrategy: { ttl: 60, swr: 60, tags: ['posts_list'] },
})
await prisma.$accelerate.invalidate({ tags: ['posts_list'] })
```

## Poolers and plan caches

- PgBouncer 1.21+ supports protocol-level prepared statements in transaction mode via `max_prepared_statements` (default value differs by version/provider; check it). Supavisor offers transaction (6543) and session (5432) modes.
- Postgres caches plans only for prepared statements, per session (`plan_cache_mode`). MySQL 8 caches prepared statements per session. Drivers keep statement caches (e.g. JDBC `prepStmtCacheSize`).
- Serverless: route through a pooler/accelerator (Hyperdrive, Prisma Accelerate, RDS Proxy, Supavisor); budget `max_concurrency × pool_size ≤ max_connections − headroom`.

## Verify

```sql
-- Postgres buffer hit ratio (aim high on OLTP)
SELECT sum(blks_hit) * 100.0 / nullif(sum(blks_hit) + sum(blks_read), 0) AS hit_pct FROM pg_stat_database;
-- Top repeated queries (needs pg_stat_statements)
SELECT calls, mean_exec_time, query FROM pg_stat_statements ORDER BY calls DESC LIMIT 20;
-- Replica lag
SELECT now() - pg_last_xact_replay_timestamp() AS replica_lag;
```

## Sources

- [CYBERTEC: shared_buffers](https://pgconfigurator.cybertec-postgresql.com/docs/parameters/shared_buffers)
- [PostgreSQL: REFRESH MATERIALIZED VIEW](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html)
- [pg_ivm](https://github.com/sraoss/pg_ivm)
- [Readyset docs](https://readyset.io/docs/)
- [Readyset: end of MySQL query cache](https://readyset.io/blog/mysql-5-7-eol-the-end-of-mysql-query-cache)
- [Cloudflare Hyperdrive query caching](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/)
- [Prisma Accelerate API](https://prisma.io/docs/accelerate/api-reference)
- [DZone: Hibernate cache pitfalls](https://dzone.com/articles/pitfalls-hibernate-second-0)
- [Crunchy Data: PgBouncer prepared statements](https://www.crunchydata.com/blog/prepared-statements-in-transaction-mode-for-pgbouncer)
