# Node.js backends

Last reviewed: 2026-10-27 · Applies to: Express 4/5, Fastify, NestJS 11 (`@nestjs/cache-manager` v3, Keyv stores), Hono, Koa

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Hono and Koa
- Version notes
- Verify
- Sources

## When to read this

When the backend is Node (`express`, `fastify`, `@nestjs/core`, `hono`, `koa`). Node frameworks have no built-in data cache: you set HTTP headers yourself and add cache-aside with Redis/Valkey (`references/layers/distributed-cache.md`).

## How to detect

`package.json` deps: `express`, `fastify` (+ `@fastify/caching`, `@fastify/etag`), `@nestjs/core` + `@nestjs/cache-manager`, `cache-manager`, `keyv`/`@keyv/redis`, `hono`, `koa`, `apicache`, `ioredis`/`redis`, `lru-cache`, `dataloader`.

## Default recipe

1. A default-headers middleware so every response has an explicit `Cache-Control` (default `no-store`; routes opt in): `assets/snippets/headers/express-default-headers.js`.
2. Version-based ETags (not body hashes) on cacheable GETs.
3. Cache-aside helper with jitter, single-flight and SWR for hot reads: `assets/snippets/app/cache-aside.ts`.
4. DataLoader per request for N+1.

```js
// Express
app.set('etag', false)                                    // emit your own version-based ETag
app.get('/products/:id', async (req, res) => {
  const p = await getProduct(req.params.id)               // cache-aside helper
  res.set('Cache-Control', 'no-cache')
  res.set('CDN-Cache-Control', 'max-age=300, stale-while-revalidate=3600, stale-if-error=86400')
  res.set('ETag', `"p-${p.id}-v${p.version}"`)
  if (req.fresh) return res.status(304).end()             // compares If-None-Match / If-Modified-Since
  res.json(p)
})
```

```ts
// NestJS 11 + @nestjs/cache-manager v3 (Keyv stores; TTL in milliseconds)
import { CacheModule } from '@nestjs/cache-manager'
import { createKeyv } from '@keyv/redis'

@Module({
  imports: [CacheModule.registerAsync({
    isGlobal: true,
    useFactory: async () => ({ stores: [createKeyv(process.env.REDIS_URL)], ttl: 60_000 }),
  })],
})
export class AppModule {}

@Injectable()
export class ProductsService {
  constructor(@Inject(CACHE_MANAGER) private cache: Cache) {}
  async find(id: string) {
    const key = `shop:v3:product:${id}`
    return (await this.cache.get(key)) ?? this.load(id, key)
  }
  async update(id: string, dto: UpdateDto) {
    await this.repo.update(id, dto)
    await this.cache.del(`shop:v3:product:${id}`)         // delete after commit
  }
}
```

## Rules and gotchas

1. Express generates weak ETags from the body by default; bodies with per-request data (timestamps, nonces) never produce 304s, and weak ETags can collide for small bodies. Disable (`app.set('etag', false)`) and emit content- or version-based ETags, or use `'strong'`.
2. NestJS `CacheInterceptor` keys by URL and ignores auth: don't apply it globally to authenticated routes; give it a custom `trackBy` or use it only on public GETs.
3. cache-manager TTL units changed (seconds in v4, milliseconds in v5+). Older `cache-manager-redis-store` + `store: redisStore` examples are outdated since NestJS 11 moved to Keyv. One source says cached value shape changed; flush the store after upgrading from NestJS 10.
4. `apicache` is effectively legacy; prefer explicit Redis cache-aside or a CDN/reverse proxy.
5. Fastify: use `@fastify/etag` for ETags and set headers per route; plugin details weren't verified in this skill's research.
6. Never share a DataLoader across requests (cross-user leak). Never cache in module-level `Map`s without bounds (`lru-cache` requires `max`/`maxSize`/`ttl`).
7. In serverless deployments (Vercel/Netlify/Lambda) module scope is an opportunistic L1 only (`references/layers/serverless-edge-data.md`).

## Hono and Koa

Set headers per route (`c.header('Cache-Control', ...)` in Hono; `ctx.set(...)` in Koa) and use the same cache-aside helper. On Cloudflare Workers, Hono apps can use the Workers cache options (`references/platforms/cloudflare.md`).

## Version notes

- NestJS 11: cache-manager on Keyv (`@keyv/redis`, `createKeyv`).

<details><summary>Old patterns</summary>

- `cache-manager-redis-store` with `CacheModule.register({ store: redisStore })`.
- `apicache` middleware for API caching.

</details>

## Verify

```bash
curl -s -o /dev/null -D - http://localhost:3000/products/1 | grep -iE 'cache-control|etag'
ETAG=$(curl -sI http://localhost:3000/products/1 | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" http://localhost:3000/products/1   # 304
```

## Sources

- [NestJS caching](https://docs.nestjs.com/techniques/caching)
- [expressjs/express#2667 (weak ETags)](https://github.com/expressjs/express/issues/2667)
- [Express API: req.fresh](https://expressjs.com/en/api.html#req.fresh)
- [jaredwray/cacheable (cache-manager, Keyv)](https://github.com/jaredwray/cacheable)
- [graphql/dataloader](https://github.com/graphql/dataloader)
