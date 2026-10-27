# Next.js

Last reviewed: 2026-10-27 · Applies to: Next.js 16.x (stable 16.4.3; docs track 16.5 canary) and 15.x; App Router and Pages Router

## Contents

- When to read this
- How to detect
- Pick the model first
- Default recipe: Cache Components model
- Default recipe: previous model
- Rules and gotchas
- Invalidation APIs
- HTTP and CDN mapping
- Self-hosting and multi-instance
- Hosting platforms
- Client router cache
- Security patches
- Version notes
- Verify
- Sources

## When to read this

When `next` is a dependency. Prefer the project's bundled docs when present: Next.js 16.3+ ships docs in `node_modules/next/dist/docs`. Never suggest an API outside the detected version.

## How to detect

`next` in `package.json`/lockfile; `next.config.{js,mjs,ts}`. Check `cacheComponents: true` (top-level since 16.0), `cacheHandler`, `cacheHandlers`, `cacheLife` profiles, `output: 'export'|'standalone'`, `expireTime`, `images`. App Router = `app/`; Pages Router = `pages/`. Deploy target: `vercel.json`, `netlify.toml`, `open-next.config.ts`, `wrangler.jsonc`, Dockerfile.

## Pick the model first

| `cacheComponents: true` in next.config? | Model | Caching APIs |
|---|---|---|
| Yes | **Cache Components** (everything dynamic until opted in; Partial Prerendering is the default rendering) | `'use cache'`, `'use cache: remote'`, `'use cache: private'`, `cacheLife`, `cacheTag` |
| No | **Previous model** | `fetch` cache options, `unstable_cache`, segment `revalidate`/`dynamic`/`fetchCache`, ISR, `React.cache` |

Never add `'use cache'` to an app without the flag. Enabling `cacheComponents` is a migration: it surfaces build errors for uncached data outside `<Suspense>`. Recommend it as its own phase, not a side effect. Current docs say new `create-next-app` apps have it on by default (with `partialPrefetching`, introduced in 16.3); which minor made that the default wasn't confirmed.

## Default recipe: Cache Components model

```ts
// lib/products.ts
import { cacheLife, cacheTag } from 'next/cache'

export async function getProduct(id: string) {
  'use cache'
  cacheLife('hours')               // always pair a directive with cacheLife
  cacheTag(`product:${id}`, 'products')
  return db.product.findUnique({ where: { id } })
}
```

```tsx
// Read runtime data outside the cached scope and pass it in (it becomes part of the key)
import { cookies } from 'next/headers'
import { Suspense } from 'react'

export default function Page() {
  return <Suspense fallback={<Skeleton />}><Prices /></Suspense>
}
async function Prices() {
  const currency = (await cookies()).get('currency')?.value ?? 'USD'
  return <PriceList currency={currency} />    // PriceList uses 'use cache' with currency as an arg
}
```

```ts
'use server'
import { updateTag, revalidateTag } from 'next/cache'
export async function saveProduct(id: string, data: FormData) {
  await db.product.update({ where: { id }, data: parse(data) })
  updateTag(`product:${id}`)           // read-your-writes for the editor
  revalidateTag('products', 'max')     // everyone else: stale-while-revalidate
}
```

`cacheLife` presets (stale / revalidate / expire): `default` 5m/15m/never · `seconds` 30s/1s/1m · `minutes` 5m/1m/1h · `hours` 5m/1h/1d · `days` 5m/1d/1w · `weeks` 5m/1w/30d · `max` 5m/30d/1y. Custom profiles in `next.config` `cacheLife`; `expire` must exceed `revalidate`.

Directive variants:

| Directive | Stored | Use for |
|---|---|---|
| `'use cache'` | Default handler (in-memory LRU; self-hosted persists per instance; serverless rarely persists) | Shared, non-personalized data and UI |
| `'use cache: remote'` | Durable shared handler (Vercel Runtime Cache, or your `cacheHandlers.remote`) | Expensive upstreams with a high hit rate (it costs a network round trip) |
| `'use cache: private'` | Browser only, as part of prefetch; not configurable | Per-user data that may read cookies/headers/searchParams |

## Default recipe: previous model

```ts
export const revalidate = 3600                                     // route-level ISR (static literal only)
const res = await fetch(url, { cache: 'force-cache', next: { revalidate: 60, tags: ['posts'] } })
export const getUser = unstable_cache(async (id: string) => db.user(id), ['user'], { tags: ['user'], revalidate: 3600 })
import { cache } from 'react'
export const getSession = cache(async () => readSession())          // per-request dedupe for non-fetch calls
```

Pages Router: `getStaticProps` returns `{ props, revalidate: 60 }`; on-demand `await res.revalidate('/posts/1')`; `getServerSideProps` can set `res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=600')` for public pages only.

## Rules and gotchas

1. Cached scopes can't call `cookies()`, `headers()` or read `searchParams`; this follows the call stack, and on dynamic routes it can pass `next build` and fail under `next start`. Read runtime data outside and pass values as arguments.
2. The `'use cache'` key = build ID (or `deploymentId`) + function ID + serializable args, including closed-over variables. Entries never survive a new deploy. For data that must persist across deploys use `unstable_cache` or the `fetch` cache.
3. Arguments and return values must be serializable (no class instances, `URL`, symbols).
4. Draft Mode re-executes cached functions and skips writes. Preview/draft traffic must bypass every cache, including the CDN.
5. Next 15 flipped defaults: `fetch` and GET Route Handlers aren't cached unless opted in (`cache: 'force-cache'`, `dynamic = 'force-static'`); the client router's dynamic `staleTime` is 0.
6. `force-cache` caches whatever you fetch, including requests with `authorization`/`cookie` headers and POSTs. Never `force-cache` user-specific fetches.
7. Conflicting `fetch` options (`{ revalidate: 3600, cache: 'no-store' }`) are both ignored. The lowest `revalidate` across a route's layouts and pages wins. Segment config values must be literals (`600`, not `60*10`).
8. Request memoization applies to GET `fetch` within one render pass, not in Route Handlers; use `React.cache` for ORM calls.
9. Tags are case-sensitive, ≤ 256 chars (longer tags are silently never assigned), ≤ 128 per `fetch`.
10. Bots detected by user agent skip the static shell and render dynamically; if build-time data sources are unavailable at runtime they get 500s.
11. `revalidateTag`/`revalidatePath` don't purge a CDN you run yourself. "Revalidation works locally but not in production" almost always means a CDN copy is still being served.

## Invalidation APIs

| API | Where | Behavior |
|---|---|---|
| `revalidateTag(tag, 'max')` | Server Actions, Route Handlers | Marks stale; next request gets stale while it regenerates (SWR). Recommended for content |
| `revalidateTag(tag, { expire: 0 })` | Same | Immediate expiry; next request blocks. Use in webhooks when freshness must be immediate |
| `revalidateTag(tag)` (one arg) | — | **Deprecated in 16** (TypeScript error); behaves like `{ expire: 0 }`. Audit after upgrading |
| `updateTag(tag)` | **Server Actions only** (throws in Route Handlers) | Immediate expiry, read-your-writes for the user who acted |
| `revalidatePath(path)` | Server Actions, Route Handlers | Tag for that page; regeneration on next request |
| `refresh()` | Server Actions only | Refreshes the client router |

CMS webhooks run in Route Handlers, so they use `revalidateTag`, never `updateTag`. Template: `assets/snippets/frameworks/nextjs-cms-webhook-route.ts`.

## HTTP and CDN mapping

| Page type | `Cache-Control` Next emits |
|---|---|
| Static | `s-maxage=31536000` |
| ISR | `s-maxage={revalidate}, stale-while-revalidate={expire − revalidate}` (default expire 1 year; tune with `expireTime`) |
| Dynamic / Draft Mode | `private, no-cache, no-store, max-age=0, must-revalidate` |
| `/_next/static/*` | `public, max-age=31536000, immutable` (can't be overridden) |

CDN in front of Next (self-hosted or a second CDN):

- App Router responses `Vary` on `rsc`, `next-router-state-tree`, `next-router-prefetch`, `next-router-segment-prefetch`, `next-url`. Forward the `rsc` header and include the `_rsc` query param in the cache key; otherwise RSC payloads and HTML collide (that's the CVE class below).
- Purge the CDN alongside every `revalidateTag`/`revalidatePath` (both HTML and RSC variants), or keep CDN TTLs short.
- Run `proxy.js` (formerly `middleware`) before the CDN so auth, redirects and rewrites stay authoritative.
- `cacheLife()` does not emit CDN `Cache-Control` headers by itself; check actual responses.

Images: `images.minimumCacheTTL` default is 4 h in 16 (60 s in 15); default `qualities` `[75]`. Variants multiply across widths × qualities × formats; restrict them.

## Self-hosting and multi-instance

- One instance with persistent disk works out of the box (filesystem + 50 MB memory).
- Several instances (Kubernetes, autoscaling) or ephemeral disks need **both**:
  - `cacheHandler` (singular): ISR, Route Handlers, `fetch`/`unstable_cache`, image optimization (16.2+). Implements `get`, `set`, `revalidateTag`, `resetRequestCache`. Must use shared storage (Redis/S3), bound size, serialize `Buffer` (`rscData`) and `Map` (`segmentData`), index by tag, and survive storage errors. Disable the in-memory cache (`cacheMaxMemorySize: 0`).
  - `cacheHandlers` (plural): backends for `'use cache'` / `'use cache: remote'`. Interface `get(cacheKey, softTags)`, `set(cacheKey, pendingEntry)`, `refreshTags()`, `getExpiration(tags)`, `updateTags(tags, { expire })`. The entry `value` is a single-read stream; return `undefined` from `get` on errors (exceptions become render errors).
  - Stub: `assets/snippets/frameworks/nextjs-cache-handler.mjs`. Community handlers exist (`@fortedigital/nextjs-cache-handler` is active; `@neshca/cache-handler` hasn't released since 2024-11).
- Use one build across containers (`generateBuildId`) or set `deploymentId`.
- Time-based ISR works per instance; on-demand ISR and `'use cache'` need the shared cache.

## Hosting platforms

| Platform | What to do |
|---|---|
| Vercel | Use framework APIs; tags purge Vercel's CDN and data caches; `'use cache: remote'` = Runtime Cache. See `references/platforms/vercel.md` |
| Netlify | `@netlify/plugin-nextjs` v5 supports the route and data caches with tag/path revalidation (durable cache from 5.5.0). See `references/platforms/netlify.md` |
| Cloudflare | `@opennextjs/cloudflare`: R2 incremental cache, D1 or sharded Durable Object tag cache, DO queue, `enableCacheInterception`; large sites add regional cache and `cachePurge: purgeCache({ type: 'direct' })`. KV-backed caches take up to 60 s to update. `next.config` `headers` don't apply to static assets there |
| AWS | `@opennextjs/aws`: S3 incremental cache, DynamoDB tag cache, SQS queue; still invalidate CloudFront after revalidation. Docs claim Next 15 feature support; confirm Next 16 Cache Components before relying on it |
| Docker/Kubernetes | Shared `cacheHandler` + `cacheHandlers` (Redis), plus a CDN purge hook |

## Client router cache

- Previous model: `experimental.staleTimes = { dynamic, static }` (dynamic 0 s since 15, static 5 min). Back/forward and shared layouts still reuse segments.
- Cache Components: `cacheLife` `stale` controls client freshness; the App Shell is prefetched per route; `<Link prefetch={true}>` also prefetches param-dependent cached content (a server invocation per link).
- 16.3 stabilized segment exports `instant` and `prefetch`.

## Security patches

Several Next.js advisories share one root cause: a shared cache keyed on the URL that doesn't distinguish the response variant (HTML vs RSC, image variants).

| CVE | Issue | Fixed in |
|---|---|---|
| CVE-2024-46982 | Pages Router SSR cache poisoning (`x-now-route-matches`) | 13.5.7 / 14.2.10 |
| CVE-2025-49005 | Missing `Vary`: RSC payload cached in place of HTML | 15.3.3 |
| CVE-2025-57752 | Image Optimization cache-key confusion | 14.2.31 / 15.4.5 |
| CVE-2026-44576 | Shared caches confuse HTML and RSC for the same URL | 15.5.16 / 16.2.5 |

The September 2026 security release fixed further cache-poisoning issues (including self-hosted Pages Router and a Draft Mode + `'use cache'` leak) and told users to move to 16.3.8 or 15.5.27. Upgrade to the latest patch of the app's release line and check GitHub advisories for anything newer. Vercel-hosted apps were often unaffected because Vercel's edge keys variants correctly; self-hosted apps behind a generic CDN are the exposed case.

## Version notes

- 16.0: `cacheComponents` top-level (replaces `experimental.dynamicIO`/`useCache`/`ppr`); `'use cache'`, `cacheLife`, `cacheTag` stable (`unstable_cacheLife`/`unstable_cacheTag` deprecated); `revalidateTag` second argument; `updateTag`, `refresh`; `middleware` renamed `proxy`; image `minimumCacheTTL` 4 h; Node 20.9+.
- 16.2: `cacheHandler` covers image optimization; Deployment Adapter API (`adapterPath`) stable.
- 16.3: `partialPrefetching`; `instant`/`prefetch` segment exports stable.
- 15.0: `fetch`/GET Route Handlers uncached by default; router dynamic `staleTime` 0.

<details><summary>Old patterns</summary>

- `experimental.dynamicIO`, `experimental.useCache`, `experimental.ppr`, route-level `experimental_ppr` (removed in 16).
- `unstable_cacheLife`, `unstable_cacheTag`, `unstable_expireTag`.
- One-argument `revalidateTag(tag)`.
- Relying on implicit `fetch` caching (pre-15 default).

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/products/1 | grep -iE 'cache-control|x-nextjs-cache|x-vercel-cache|age|vary'
curl -s -o /dev/null -D - -H 'RSC: 1' https://example.com/products/1 | grep -iE 'content-type|vary|cache'   # RSC variant must not share the HTML entry
grep -rnE "revalidateTag\([^,)]+\)" app lib src 2>/dev/null   # one-argument calls to fix in 16
python scripts/find_cache_primitives.py .
```

## Sources

- [Next.js caching (Cache Components)](https://nextjs.org/docs/app/getting-started/caching)
- [use cache](https://nextjs.org/docs/app/api-reference/directives/use-cache)
- [revalidateTag](https://nextjs.org/docs/app/api-reference/functions/revalidateTag)
- [updateTag](https://nextjs.org/docs/app/api-reference/functions/updateTag)
- [Caching without Cache Components](https://nextjs.org/docs/app/guides/caching-without-cache-components)
- [CDN caching guide](https://nextjs.org/docs/app/guides/cdn-caching)
- [Self-hosting](https://nextjs.org/docs/app/guides/self-hosting)
- [cacheHandlers](https://nextjs.org/docs/app/api-reference/config/next-config-js/cacheHandlers)
- [Upgrading to 16](https://nextjs.org/docs/app/guides/upgrading/version-16)
- [OpenNext Cloudflare caching](https://opennext.js.org/cloudflare/caching)
- [OpenNext AWS caching](https://opennext.js.org/aws/inner_workings/caching)
- [Next.js September 2026 security release](https://nextjs.org/blog/september-2026-security-release)
