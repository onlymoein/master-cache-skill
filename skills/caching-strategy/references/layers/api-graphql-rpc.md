# APIs: REST, GraphQL, gRPC/Connect, tRPC and gateways

Last reviewed: 2026-10-27 · Applies to: REST/JSON APIs; API gateways (AWS API Gateway, Kong, Azure APIM, Apigee); Apollo Server 5, GraphQL Yoga, Hive Gateway, Grafbase; Connect RPC, gRPC, tRPC

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- REST
- API gateway caches
- GraphQL
- gRPC and Connect
- tRPC
- Idempotency keys are not a cache
- Version notes
- Verify
- Sources

## When to read this

For any API (public, partner, mobile backend, or BFF). Read with `references/core/http-semantics.md`. For the CDN layer in front of the API see `references/layers/cdn-concepts.md`.

## How to detect

- REST: route definitions (`app.get(`, `@GetMapping`, `[HttpGet]`, `urls.py`), OpenAPI specs (`openapi.yaml`, `swagger.json`).
- Gateways: `serverless.yml`/SAM/CDK/Terraform with `aws_api_gateway_*` (`cache_cluster_enabled`, `caching_enabled`), Kong `kong.yml`/`deck` files with `proxy-cache`, APIM policy XML with `cache-lookup`, Apigee bundles with `ResponseCache`.
- GraphQL: `@apollo/server` (v5), `apollo-server` (legacy), `graphql-yoga`, `@envelop/response-cache`, `@graphql-hive/gateway`, Apollo Router `router.yaml`, `mercurius`, `@grafbase/*`, `dataloader`; persisted-query manifests.
- RPC: `*.proto`, `@grpc/grpc-js`, `google.golang.org/grpc`, `@connectrpc/connect`, `connectrpc.com/connect`, `@trpc/server`.

## Default recipe

1. Reads are GETs with stable, normalized URLs; writes are never cached.
2. Every response has an explicit `Cache-Control`: `public, max-age=…, stale-while-revalidate=…` for public data; `private, no-cache` for user data; `no-store` for secrets, PII and errors like 401/403/429.
3. Validators (ETag from a version column, or Last-Modified) on every cacheable GET so clients get cheap 304s; `If-Match` for optimistic concurrency on writes.
4. Shared caches (CDN, gateway) only for public responses, or with tenant/user identity in the key.
5. App-level cache-aside for expensive reads behind the API (`references/layers/distributed-cache.md`).

```http
GET /v1/products?category=shoes&limit=20&page=2
Cache-Control: public, max-age=60, stale-while-revalidate=300
ETag: "p-c3f9-v17"
Vary: Accept, Accept-Encoding

GET /v1/products/123
If-None-Match: "p-c3f9-v17"
→ 304 Not Modified

GET /v1/me/orders
Cache-Control: private, no-cache

PUT /v1/products/123
If-Match: "p-c3f9-v17"          → 412 if changed

HTTP/1.1 429 Too Many Requests
Cache-Control: no-store
```

## Rules and gotchas

1. Never put credentials or tokens in query strings: they end up in cache keys and logs.
2. Normalize query parameters (sorted, defaults omitted) and allowlist them in CDN/gateway keys; unknown params fragment the cache and enable poisoning.
3. Version in the path (`/v1/`) or media type (`Vary: Accept`), never in a header the cache ignores.
4. Revalidation (304) still counts as a request at the gateway/origin and against rate limits; cache hits at the edge usually don't.
5. Error responses (`4xx`/`5xx`) get `no-store` or a very short TTL; negative caching of `404` is fine with a short TTL and purge on create.
6. Mobile clients and SDKs live for months: send server-driven TTLs, keep cached response shapes backward compatible (`references/layers/mobile-native.md`).

## REST

- **Pagination:** cursor pages are more cache-stable than offset pages (offsets shift on insert). First page short TTL; deeper pages longer. Include `limit` in the key. Don't cache "total count" fields for long.
- **Lists vs items:** tag list responses with the collection (`products`) and item responses with `product:{id}`; purge both on writes.
- **Field selection/sparse fieldsets** (`?fields=`) multiply variants; allowlist common sets.
- **Clients:** browsers, URLSession, OkHttp and dio's cache interceptor handle 304s transparently; a custom `fetch` wrapper that sets `If-None-Match` itself must handle the 304 (empty body) itself.

## API gateway caches

| Gateway | Cache | Key facts |
|---|---|---|
| AWS API Gateway (REST APIs) | Per-stage cache instance, 0.5–237 GB | TTL default 300 s, max 3600 s, 0 disables. GET only by default. Keys can include headers, path, query. Changing capacity deletes the cache |
| Kong | Proxy Cache plugin (OSS: in-memory per node); Proxy Caching Advanced (Enterprise) adds Redis | `cache_control: true` honors headers; `X-Cache-Status` Hit/Miss/Refresh/Bypass; purge via Admin API. Sources conflict on edition details |
| Azure APIM | `cache-lookup` (inbound) + `cache-store` (outbound) policies | GET only; `vary-by-developer`, `vary-by-developer-groups`, `vary-by-header`, `vary-by-query-parameter`; `duration` in seconds; only 200 cached by default; built-in cache is volatile, shared per region |
| Apigee | `ResponseCache` policy | `CacheKey`, `ExpirySettings`, `SkipCacheLookup`, `SkipCachePopulation` (from knowledge; verify) |

AWS API Gateway invalidation trap: a client can invalidate an entry by sending `Cache-Control: max-age=0`. Unless **Require authorization** is on (`requireAuthorizationForCacheControl: true`, with `unauthorizedCacheControlHeaderStrategy: FAIL_WITH_403`), any client can force cache misses (a DoS vector). Turn it on.

Never cache authenticated responses at a gateway unless the key includes the identity (`Authorization` header or a claim) or tenant.

## GraphQL

POST to one URL defeats URL-keyed HTTP caches. In order of impact:

1. **Cache hints:** `@cacheControl(maxAge, scope)` (Apollo) or `ttl`/`ttlPerType` (Yoga). Default `maxAge` 0 so one uncached field makes the response uncacheable (the safe direction); `scope: PRIVATE` / `session` for user data.
2. **Persisted queries over GET** so a CDN can cache public operations: Apollo APQ with `useGETForHashedQueries: true`, or trusted documents (persisted-only in production, which also stops arbitrary queries from blowing up the key space).
3. **Server or gateway response cache** with entity/mutation-based invalidation (Yoga `useResponseCache`, Apollo `responseCachePlugin`, Hive Gateway `responseCaching`, Grafbase entity caching).
4. **DataLoader per request** for N+1 (never global: a shared DataLoader leaks data across users).
5. **Normalized client cache** (Apollo Client, urql Graphcache, Relay): `references/frameworks/client-data-caches.md`.

```graphql
enum CacheControlScope { PUBLIC PRIVATE }
directive @cacheControl(maxAge: Int, scope: CacheControlScope, inheritMaxAge: Boolean) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION

type Product @cacheControl(maxAge: 300) { id: ID!  name: String!  price: Money @cacheControl(maxAge: 30) }
type Query { me: User @cacheControl(maxAge: 0, scope: PRIVATE) }
```

```ts
// Apollo Server 5: shared store + per-session response cache
import responseCachePlugin from '@apollo/server-plugin-response-cache'
import { KeyvAdapter } from '@apollo/utils.keyvadapter'
import Keyv from 'keyv'

const server = new ApolloServer({
  typeDefs, resolvers,
  cache: new KeyvAdapter(new Keyv(process.env.REDIS_URL)),
  plugins: [responseCachePlugin({
    sessionId: async ({ request }) => request.http?.headers.get('authorization') ?? null,
  })],
})
```

```ts
// GraphQL Yoga: session-partitioned response cache with entity invalidation
import { createYoga } from 'graphql-yoga'
import { useResponseCache, createInMemoryCache } from '@graphql-yoga/plugin-response-cache'

const cache = createInMemoryCache()
const yoga = createYoga({ schema, plugins: [useResponseCache({
  session: (req) => req.headers.get('authorization') ?? null,
  ttl: 2_000, ttlPerType: { User: 500 }, cache,
})] })
cache.invalidate([{ typename: 'Product', id: '42' }])
```

GraphQL gotchas:

- Apollo emits `Cache-Control` from the most restrictive hint (`max-age` or `no-store`). With a CDN, `scope: PRIVATE` must still produce `Cache-Control: private`; set `calculateHttpHeaders: false` only if you emit correct headers yourself (e.g. `s-maxage` for public operations).
- A response cache without `session`/`sessionId` on an authenticated API leaks data.
- Yoga prefers ETags over `max-age` so clients revalidate and mutation invalidation stays effective; Apollo subgraphs with TTLs can't be invalidated early by a gateway.
- Responses with errors aren't cached by default in Apollo/Yoga (verify for your version); keep it that way.
- Grafbase entity caching scopes entries by all headers sent to the subgraph (default TTL 60 s, memory or Redis).
- Stellate (GraphQL edge cache: ~150 ms purge, 10 MB response limit) docs were 1–1.5 years old at review; confirm it's still offered before recommending.

## gRPC and Connect

Native gRPC runs over HTTP/2 POST; CDNs and HTTP caches don't cache it. Cache in the server (cache-aside inside handlers) and in clients. For CDN-cacheable reads, mark methods side-effect free and serve them over GET with Connect, or expose REST via grpc-gateway/transcoding.

```protobuf
service ProductService {
  rpc GetProduct(GetProductRequest) returns (Product) { option idempotency_level = NO_SIDE_EFFECTS; }
}
```

Connect sends `NO_SIDE_EFFECTS` methods as GET when the client opts in (connect-go 1.7.0+); GET alone doesn't make proxies cache, so handlers still set `Cache-Control`.

## tRPC

```ts
// fetch adapter: cache only public, error-free queries
responseMeta({ type, errors, ctx }) {
  if (type === 'query' && errors.length === 0 && !ctx?.user)
    return { headers: new Headers([['cache-control', 's-maxage=60, stale-while-revalidate=300']]) }
  return {}
}
```

- `httpBatchLink` combines procedures into one URL, fragmenting cache keys; use a non-batched link for cacheable public queries.
- Next.js App Router can override headers set this way (community reports); check real responses.
- Never set shared-cache headers on authenticated queries.

## Idempotency keys are not a cache

`Idempotency-Key` makes retried POST/PATCH safe: store the request fingerprint and response (about 24 h in Redis or the DB) and replay the stored response for the same key. Never serve reads from the idempotency store. The IETF draft (draft-07) expired on 2026-04-18 without becoming an RFC; the pattern (Stripe-style) is still common.

## Version notes

- Apollo Server 4 reached end of life on 2026-01-26; Apollo Server 5 needs Node 20+ (small migration; v3 can jump straight to v5).
- Yoga v5 `cache.invalidate([{ typename, id }])`; v4 docs used `type`.

<details><summary>Old patterns</summary>

- `apollo-server` v2/v3 packages and `apollo-server-plugin-response-cache`.
- GraphQL over POST with no persisted queries behind a CDN (uncacheable).
- Global DataLoader instances.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://api.example.com/v1/products/1 | grep -iE 'cache-control|etag|vary|age|x-cache'
ETAG=$(curl -sI https://api.example.com/v1/products/1 | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" https://api.example.com/v1/products/1   # 304
curl -s -o /dev/null -D - -H 'Cache-Control: max-age=0' https://api.example.com/v1/products/1 | head -1     # AWS: expect 403 with Require authorization
curl -s -D - -o /dev/null 'https://api.example.com/graphql?extensions=%7B%22persistedQuery%22%3A%7B%22version%22%3A1%2C%22sha256Hash%22%3A%22<hash>%22%7D%7D' | grep -iE 'cache-control|age'
```

## Sources

- [AWS: API Gateway caching](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html)
- [Kong: API gateway cache](https://konghq.com/blog/engineering/api-gateway-cache)
- [Azure APIM: caching overview](https://learn.microsoft.com/en-us/azure/api-management/caching-overview)
- [IETF: Idempotency-Key header draft](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)
- [Apollo Server: server-side caching](https://www.apollographql.com/docs/apollo-server/performance/caching)
- [Apollo Server: APQ](https://www.apollographql.com/docs/apollo-server/performance/apq)
- [GraphQL Yoga: response caching](https://the-guild.dev/graphql/yoga-server/docs/features/response-caching)
- [Hive Gateway: response caching](https://the-guild.dev/graphql/hive/docs/gateway/other-features/performance/response-caching)
- [Grafbase: entity caching](https://grafbase.com/docs/gateway/performance/entity-caching)
- [graphql/dataloader](https://github.com/graphql/dataloader)
- [Buf: cacheable RPCs in Connect](https://buf.build/blog/introducing-connect-cacheable-rpcs)
- [tRPC: caching](https://trpc.io/docs/server/caching)
