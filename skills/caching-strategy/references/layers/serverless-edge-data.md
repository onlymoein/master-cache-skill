# Serverless and edge data caching

Last reviewed: 2026-10-27 · Applies to: AWS Lambda, Vercel Functions, Netlify Functions, Cloudflare Workers (KV, Cache API, Workers Caching, Durable Objects, D1, Hyperdrive), Fastly Compute (KV/Config Store), Upstash

## When to read this

When code runs in serverless functions or at the edge. In-memory caches there are per execution environment and vanish unpredictably; connection fan-out is the main failure mode.

## Default recipe

```ts
// Module scope: one client per execution environment, opportunistic L1
import { Redis } from '@upstash/redis'
const redis = Redis.fromEnv()                       // HTTP/REST: no TCP pool to exhaust
const local = new Map<string, { v: unknown; exp: number }>()

export default async function handler(req: Request) {
  const key = 'cfg:v2:flags'
  const hit = local.get(key)
  if (hit && hit.exp > Date.now()) return Response.json(hit.v)
  let v = await redis.get(key)
  if (v === null) { v = await loadFlags(); await redis.set(key, v, { ex: 60 }) }
  local.set(key, { v, exp: Date.now() + 5_000 })
  return Response.json(v)
}
```

## Rules and gotchas

1. Module-scope L1 is a bonus, never a design assumption. Hit ratio depends on instance reuse and can be near zero at low traffic. Bound it.
2. Create clients outside the handler; reset on connection errors. Budget connections: `max_concurrency × pool_size ≤ maxclients − headroom`. 1,000 concurrent invocations hold 1,000 connections.
3. Edge runtimes can't hold long-lived TCP: use HTTP Redis (Upstash), platform caches, or KV. HTTP costs a few ms per call; pipeline/batch commands.
4. TCP+TLS+AUTH on cold start adds roughly 20–80 ms; VPC-attached Lambda cold starts add more; ElastiCache is VPC-only.
5. Eventually consistent stores (Workers KV, Fastly KV, Hyperdrive's query cache) don't give read-your-writes. On the request that just wrote, bypass them (origin or a no-cache config).
6. Never use KV for counters or anything needing atomic read-modify-write; use Durable Objects, D1 or the origin DB.
7. Many platform caches are per deploy or per region: expect cold caches after each deploy.

## Choosing an edge store

| Need | Cloudflare | Vercel | Netlify | Fastly |
|---|---|---|---|---|
| Cache whole responses from compute | Workers Caching (read-through, tiered, collapsing) | CDN via headers | `durable` cache via headers | CDN via headers |
| Cache a fragment/subrequest | Cache API (data-center local, explicit `put`, no collapsing/tiering) | Runtime Cache (`getCache()`, regional, ≤ 2 MB items, ≤ 128 tags) | Cache API / `@netlify/cache` `fetchWithCache` (per region) | Core cache (not covered here) |
| Read-mostly config, flags, redirects | Workers KV (≈ 60 s propagation; `cacheTtl` min 30 s) | Edge Config (most reads < 15 ms P99) | — | Config Store (Compute, read-only at edge, ~1 ms) |
| Durable, eventually consistent KV | Workers KV | Marketplace Redis (Upstash) | — | KV Store (recent writes may take ~300 ms to read) |
| Strong consistency, per-user state | Durable Objects, D1 | Origin DB | Origin DB | Origin DB |
| DB access with pooling/caching | Hyperdrive (60 s / 15 s SWR default; no write invalidation) | Prisma Accelerate or a pooler | Pooler | Origin |

## Platform notes

- **Cloudflare Workers Caching:** cache key = entrypoint + path + query (order-sensitive) + Worker version (default) + `ctx.props`; host not included; zone Cache Rules don't apply; purge via `ctx.cache.purge()`/`invalidate()` with Free-tier rate limits. Wrap Durable Objects behind a cached entrypoint (e.g. leaderboard `max-age=30`, purge on write). Details: `references/platforms/cloudflare.md`.
- **Vercel Runtime Cache:** `'use cache: remote'` or `fetch` with `force-cache` in Next.js 16 uses it; plain `'use cache'` is in-memory per instance. Runtime Cache tags don't apply to ISR pages.
- **Netlify:** Cache API limits per invocation (100 lookups, 20 writes), invalidated on redeploy.
- **Lambda/SST:** provisioned concurrency or pre-warming for latency-critical cold starts; HTTP Redis avoids VPC attachment.

## Verify

- Log cache hit/miss per invocation with the instance ID; confirm the L1 isn't relied on for correctness.
- Load test at peak concurrency and watch Redis `connected_clients` vs `maxclients` and DB connections.
- After a write, read through the edge path immediately and confirm the writer sees fresh data.

## Sources

- [Upstash: Redis pricing and REST](https://upstash.com/blog/redis-pricing-comparison-every-major-provider-in-2026-with-numbers)
- [Vercel Runtime Cache](https://vercel.com/docs/caching/runtime-cache)
- [Vercel Edge Config](https://vercel.com/docs/edge-config)
- [Cloudflare storage options](https://developers.cloudflare.com/workers/platform/storage-options/)
- [Cloudflare KV write propagation](https://developers.cloudflare.com/kv/api/write-key-value-pairs/)
- [Cloudflare Workers Cache](https://developers.cloudflare.com/workers/cache/)
- [Cloudflare Hyperdrive query caching](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/)
- [Fastly edge data stores](https://www.fastly.com/documentation/guides/compute/edge-data-storage/about-edge-data-stores/)
