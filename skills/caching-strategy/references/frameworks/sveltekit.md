# SvelteKit

Last reviewed: 2026-10-27 · Applies to: SvelteKit 3.1 (notes for 2.x where they differ)

## When to read this

When `@sveltejs/kit` is a dependency. SvelteKit has **no built-in server data cache**: caching is HTTP headers (`setHeaders`), prerendering, adapter features (Vercel ISR) and your own server-side cache.

## How to detect

`@sveltejs/kit` in `package.json`. Major ≥ 3: config lives in the `sveltekit({...})` Vite plugin in `vite.config.js` (`svelte.config.js` is no longer supported). Major 2: `svelte.config.js`. Adapters: `@sveltejs/adapter-vercel`, `-netlify`, `-cloudflare`, `-node`.

## Default recipe

```js
// src/routes/products/[id]/+page.server.js — shared page cached at the edge
export async function load({ params, setHeaders }) {
  const product = await getProduct(params.id)          // your own cache-aside helper in $lib/server
  setHeaders({ 'cache-control': 'public, max-age=0, s-maxage=300, stale-while-revalidate=3600' })
  return { product }
}
```

```js
// src/routes/blog/[slug]/+page.server.js — Vercel ISR (adapter-vercel)
export const config = { isr: { expiration: 600, bypassToken: process.env.ISR_BYPASS_TOKEN } }
```

```js
export const prerender = true      // or 'auto': prerender, but keep it in the SSR manifest for the long tail
```

For personalized pages set `private, no-cache` (or nothing shared at all) and keep `s-maxage` off.

## Rules and gotchas

1. Setting the same header twice, even from different `load` functions (layout and page), is an error. Set `cache-control` in one place, usually the leaf page.
2. `setHeaders` can't set `set-cookie` (use `cookies`), doesn't work inside streamed promises, and is a no-op in the browser.
3. `fetch` in `load` inherits the user's cookies/auth. Responses fetched during SSR are inlined into the HTML and reused at hydration (headers aren't serialized unless listed in `filterSerializedResponseHeaders`). Don't put personalized SSR fetches on pages cached with `s-maxage`.
4. Vercel ISR: `expiration` is required; use ISR only on routes where every visitor sees the same content; ISR on a `prerender = true` route does nothing; `allowQuery` lists query params that create separate entries.
5. Server data caching is yours to build: an LRU/Redis cache-aside helper in `$lib/server` (`references/layers/in-process.md`, `references/layers/distributed-cache.md`).
6. Client reruns: `load` reruns when the params/url/parent it used change. Use `depends('app:key')` + `invalidate('app:key')`; `refreshAll()` reruns everything (SvelteKit 3; `invalidateAll` is deprecated). Server `load` never automatically depends on a fetched URL.

## Adapters

- adapter-node (3.x): serves static assets with content-hash `ETag`s and no `Last-Modified`; GET/HEAD only. Put a CDN in front with explicit headers.
- adapter-cloudflare (3.x): `caches` is a global; `env`/`waitUntil` from `cloudflare:workers`; wrangler ≥ 4.67. Use `setHeaders` + the Cache API or Workers Caching (`references/platforms/cloudflare.md`).
- adapter-netlify uses the Netlify Frameworks API; Netlify ISR-equivalents for SvelteKit 3 weren't documented in this skill's research. Use `Netlify-CDN-Cache-Control` headers.
- adapter-vercel 3.x drops the `edge` runtime.

## Remote functions (experimental)

`experimental.remoteFunctions` + `compilerOptions.experimental.async`. `query` args form a cache key (object keys sorted); request-scoped dedupe on the server; identical calls share one instance on the client while in use. Refresh with `getPosts().refresh()`, set with `getPost(id).set(v)` from `form`/`command` handlers, `requested(getPosts, n)` for client-requested refreshes, `query.batch` for n+1. Don't cache live query responses in a service worker. Flag as experimental in any plan.

## Version notes

- 3.0: config moved to `vite.config.js`; `$lib` → `#lib`; `$app/environment` → `$app/env`; `$service-worker` and `$app/stores` removed (use `$app/manifest` for offline lists); `version.pollInterval` default one hour; `output.linkHeaderPreload` defaults to `<link>` elements; Node 22.17, Vite 8.

<details><summary>Old patterns</summary>

- `invalidateAll()` (deprecated in 3; use `refreshAll()`).
- `kit.prerender`/`kit.version` in `svelte.config.js` (move into `vite.config.js` in 3).
- `$service-worker` module.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/products/1 | grep -iE 'cache-control|age|x-vercel-cache|cf-cache-status'
curl -s -o /dev/null -D - -H 'Cookie: session=x' https://example.com/account | grep -i cache-control   # private/no-store
```

## Sources

- [SvelteKit loading data](https://svelte.dev/docs/kit/load)
- [SvelteKit page options (prerender)](https://svelte.dev/docs/kit/page-options)
- [adapter-vercel (ISR)](https://svelte.dev/docs/kit/adapter-vercel)
- [Migrating to SvelteKit 3](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)
- [Remote functions](https://svelte.dev/docs/kit/remote-functions)
