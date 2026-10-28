# Nuxt and Nitro

Last reviewed: 2026-10-27 · Applies to: Nuxt 4.6.x (and 3.21.x) on nitropack 2.13; Nitro 3 / Nuxt 5 are pre-release

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Cached handlers and functions
- Client data: useFetch and useAsyncData
- Hosting
- Version notes
- Verify
- Sources

## When to read this

When `nuxt`, `nitropack` or `nitro` is a dependency. Stable Nuxt 4.6 runs on nitropack 2.13, so Nitro v2 caching docs apply.

## How to detect

`nuxt` in `package.json`; `nuxt.config.ts` (`routeRules`, `nitro.storage`, `nitro.preset`); standalone Nitro: `nitro.config.ts` (`defineNitroConfig`). `nitro` 3.x beta or Nuxt 5.0.0-x means pre-release APIs.

## Default recipe

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  routeRules: {
    '/':            { prerender: true },
    '/products/**': { swr: 3600 },                 // shared, server/proxy cached, SWR
    '/blog/**':     { isr: 600 },                  // CDN-cached on Vercel/Netlify
    '/account/**':  { headers: { 'cache-control': 'private, no-cache' } },
    '/_nuxt/**':    { headers: { 'cache-control': 'public, max-age=31536000, immutable' } },
  },
  nitro: {
    storage: { cache: { driver: 'redis', url: process.env.REDIS_URL } },   // shared across instances
  },
})
```

```ts
// server/api/stars/[repo].get.ts
export default defineCachedEventHandler(async (event) => {
  const repo = getRouterParam(event, 'repo')
  return (await $fetch(`https://api.github.com/repos/${repo}`)).stargazers_count
}, { maxAge: 3600, staleMaxAge: 86400, name: 'ghStars', getKey: (event) => getRouterParam(event, 'repo')! })
```

## Rules and gotchas

1. `defineCachedEventHandler`/`defineCachedFunction` default `maxAge` is **1 second**. Always set `maxAge` (and `staleMaxAge` for bounded staleness; `-1` = always serve stale).
2. Cached handlers **drop all incoming request headers** unless listed in `varies`. Anything depending on auth, cookies or locale must use `varies`/`getKey`, or must not be cached. For multi-tenant hosts use `varies: ['host', 'x-forwarded-host']`.
3. The `cache:` storage mount is **in-memory per instance in production** (fs in dev). Multi-instance or serverless deployments need a shared driver (Redis, Cloudflare KV, Upstash) or invalidation will be inconsistent.
4. Treat `swr`/`isr` routes as shared: never use them for per-user pages.
5. `isr` gets CDN behavior only on the Vercel and Netlify presets; elsewhere it degrades to `swr`-style server caching.
6. Routes with `isr`/`swr` also generate `_payload.json`. Nuxt CVE-2025-27415 let a CDN that ignores the query string cache `/?/_payload.json` JSON as the page (fixed in 3.16.0); keep Nuxt patched and keep query strings in the CDN key for payload URLs.
7. Cache keys are normalized (non-word chars stripped: `/api/products/sale-items` → `api/productssaleitems.json`). Use `escapeKey()` when building keys to invalidate.
8. `defineCachedFunction` results are JSON-serialized (no Map/Set/Symbol). On edge workers pass `event` first so Nitro can `waitUntil` the background refresh.
9. Hybrid rendering (`routeRules`) doesn't work with `nuxt generate`.

## Cached handlers and functions

Options: `base` (storage mount, default `cache`), `name`, `group` (`nitro/handlers` | `nitro/functions`), `getKey`, `integrity`, `maxAge` (default 1), `staleMaxAge` (default 0), `swr` (default true), `shouldInvalidateCache`, `shouldBypassCache`, `varies`.

Invalidate by removing the storage key:

```ts
// key = `${group}:${name}:${getKey(...)}.json`; handlers use group nitro/handlers, functions nitro/functions
await useStorage('cache').removeItem('nitro:handlers:ghStars:nuxt.json')
```

Route rules can select a custom mount: `{ cache: { maxAge: 60, base: 'redis' } }`.

## Client data: useFetch and useAsyncData

- Calls with the same key share `data`, `error`, `status`; handler, `transform`, `pick`, `getCachedData` and `default` must match across them. Without a key, Nuxt generates one from file and line.
- Server data travels in the payload (`devalue`), so hydration doesn't refetch. Shrink it with `pick`/`transform`. `serialize: false` (4.6) keeps data out of the payload (client refetches).
- Default `getCachedData` returns payload/static data only during hydration (and only caches across navigations with `experimental.payloadExtraction`). Write a custom `getCachedData(key, nuxtApp, ctx)` with a timestamp check for client-side SWR across navigations.
- Invalidate with `refresh()`/`clear()` per call, or `refreshNuxtData(keys)`/`clearNuxtData(keys)` globally. Clear on logout.
- `dedupe` defaults to `'cancel'`; `enabled` (4.5) and `middleware` (4.6) options exist.

## Hosting

| Target | Behavior |
|---|---|
| Vercel / Netlify presets | `isr`/`swr` map to the platform CDN; see platform references |
| Node server preset | `swr` caches full responses in Nitro storage; put a CDN in front with explicit headers |
| Cloudflare | Use `nitro.storage.cache` on KV (eventual, up to 60 s) |
| Docker/Kubernetes | Redis storage driver; CDN purge hook on content change |

## Version notes

- Nuxt 4.5: `useAsyncData` `enabled`. Nuxt 4.6: `serialize`, `middleware` options.
- Nitro 3 (beta) and Nuxt 5 (pre-release) move to h3 v2; cached-handler names may change (unverified). Don't recommend Nitro 3 APIs for stable apps.
- `defineRouteRules()` in pages is experimental (`experimental.inlineRouteRules`).

<details><summary>Old patterns</summary>

- Nuxt 2 `serverMiddleware` + `nuxt-ssr-cache`.
- Relying on the default memory cache driver in multi-instance production.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/products/1 | grep -iE 'cache-control|age|x-nitro|cache-status'
curl -s -o /dev/null -D - 'https://example.com/?/_payload.json' | grep -iE 'content-type|cache-control'   # must not be cached as the page
```

Check that two instances return the same cached value after an invalidation (shared storage working).

## Sources

- [Nuxt rendering and route rules](https://nuxt.com/docs/guide/concepts/rendering)
- [Nitro v2 cache guide](https://nitro.build/guide/cache)
- [Nuxt useAsyncData](https://nuxt.com/docs/api/composables/use-async-data)
- [Nuxt data fetching](https://nuxt.com/docs/getting-started/data-fetching)
- [Nuxt CVE-2025-27415 advisory](https://advisories.gitlab.com/npm/nuxt/CVE-2025-27415/)
