# Astro

Last reviewed: 2026-10-27 · Applies to: Astro 7.4 (route caching stable since 7.0; experimental in 6.x); adapters `@astrojs/node` 11, `@astrojs/vercel` 11, `@astrojs/netlify` 8, `@astrojs/cloudflare` 14

## When to read this

When `astro` is a dependency. Astro prerenders everything by default; caching questions are about on-demand pages, endpoints and server islands.

## How to detect

`astro` in `package.json`; `astro.config.mjs` (`output`, `adapter`, top-level `cache` and `routeRules` in 7.x, `experimental.cache` in 6.x); pages with `export const prerender = false`.

## Default recipe

```js
// astro.config.mjs (Astro 7)
import { defineConfig, memoryCache } from 'astro/config'
import node from '@astrojs/node'

export default defineConfig({
  adapter: node({ mode: 'standalone' }),
  cache: { provider: memoryCache() },              // single instance; use a CDN provider or custom provider for many
  routeRules: {
    '/api/[...path]':      { swr: 600 },
    '/products/[...slug]': { maxAge: 3600, tags: ['products'] },
  },
})
```

```astro
---
// src/pages/index.astro (on-demand)
export const prerender = false
if (Astro.cache.enabled) Astro.cache.set({ maxAge: 120, swr: 60, tags: ['home'] })
---
```

```ts
// src/pages/api/revalidate.ts
export async function POST(context) {
  if (context.cache.enabled) await context.cache.invalidate({ tags: ['products'] })
  return new Response(null, { status: 204 })
}
```

Opt a page out with `Astro.cache.set(false)`. Personalized pages: don't call `cache.set`; send `private, no-cache`.

## Rules and gotchas

1. Without a provider, `cache.set` warns and `cache.invalidate` **throws**. Guard with `Astro.cache.enabled`. In dev, caching is disabled and calls are no-ops.
2. Merging across calls (middleware, layouts, loaders, page): `maxAge`, `swr`, `etag` last-write-wins; `lastModified` most recent; `tags` accumulate.
3. Path invalidation is exact-match (no globs). `routeRules` use file-route syntax (`[...rest]`, not `*`).
4. `memoryCache()` is per instance; on multi-instance deployments use a CDN provider or a custom provider.
5. CDN providers are **experimental**: `cacheVercel()` (sets `Vercel-CDN-Cache-Control` + `Vercel-Cache-Tag`; tag invalidation is soft), `cacheNetlify()` (`Netlify-CDN-Cache-Control` + `Netlify-Cache-Tag`, durable cache), `cacheCloudflare()` (`Cloudflare-CDN-Cache-Control` + `Cache-Tag`, Workers Cache). Each auto-tags responses with the request path so path invalidation works. Flag them as experimental in plans.
6. Server islands load via GET with encrypted props in the query string (cacheable). Props over 2048 bytes switch to POST, which isn't cacheable. The encryption key is random per build: set `ASTRO_KEY` for rolling deploys, multiple regions, or CDN-cached pages containing islands.
7. Vercel adapter `isr`: caches on-demand pages for the deployment by default; without `expiration`, app `Cache-Control` headers are ignored; ISR drops search params; middleware runs only on misses unless `middlewareMode: 'edge'`.

## By version

| Astro | Caching API |
|---|---|
| 7.x | Top-level `cache` + `routeRules`; `Astro.cache` / `context.cache` |
| 6.x | Same under `experimental.cache` |
| ≤ 5 | Manual `Astro.response.headers.set('Cache-Control', …)` and adapter ISR only |

Static output: hashed `/_astro/*` assets `public, max-age=31536000, immutable`; HTML `no-cache` at the browser with CDN TTL + purge on deploy.

## Version notes

- 7.0: route caching stable (moved out of `experimental`).

<details><summary>Old patterns</summary>

- `experimental.cache` (Astro 6).
- Setting `Cache-Control` by hand on every on-demand page instead of `routeRules`.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/products/a | grep -iE 'cache-control|cdn-cache-control|age|cache-tag'
curl -s 'https://example.com/_server-islands/Avatar?p=...' -o /dev/null -D - | grep -i cache-control
```

## Sources

- [Astro route caching](https://docs.astro.build/en/guides/caching/)
- [Astro v7 upgrade guide](https://docs.astro.build/en/guides/upgrade-to/v7/)
- [Astro server islands](https://docs.astro.build/en/guides/server-islands/)
- [@astrojs/vercel](https://docs.astro.build/en/guides/integrations-guide/vercel/)
- [Astro on-demand rendering](https://docs.astro.build/en/guides/on-demand-rendering/)
