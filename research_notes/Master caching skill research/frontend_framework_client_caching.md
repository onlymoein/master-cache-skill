# Frontend Meta-Frameworks & Client-Side Data Caching (state as of 2026-10-27)

> Method note for the report writer: nextjs.org, docs.astro.build, vercel.com, docs.netlify.com and developers.cloudflare.com were blocked by the session's egress proxy. Primary sources were therefore read directly from each project's **docs source in its GitHub repo** (default branch, cloned 2026-10-27) and from the **npm registry** (versions and release dates). Each GitHub docs file maps one-to-one to the public docs page (for example `vercel/next.js/docs/01-app/01-getting-started/08-caching.mdx` is `nextjs.org/docs/app/getting-started/caching`). Vercel docs were read through Vercel's documentation-search tool (a Context7 index of vercel.com/docs). One caution: Next.js docs on `canary` track **16.5.0-canary.28**, while npm `latest` is **16.4.3**. Where a feature's version table says it shipped in 16.3.0 or earlier, it is in stable. Anything without a version table may be canary-only, and is flagged below.

## Q0. Current versions and how to detect each framework and version from a repo

### Takeaway
Many majors have shipped since mid-2025. Current stable lines are Next 16.4, Nuxt 4.6 (on nitropack 2.13), SvelteKit 3.1, React Router 8.5, Astro 7.4, Angular 22.2, SolidStart 2.1, TanStack Start 1.169, Vite 8.3, React 19.3, TanStack Query 5.105, SWR 2.5, Apollo Client 4.3, RTK 2.13, urql 5 / Graphcache 9, and Relay 21. A detection step must read the **resolved version** from the lockfile or `package.json`, because SvelteKit 3 and React Router 8 changed config-file and package conventions.

### Cited Findings
**Latest stable versions on npm (dist-tag `latest`, with publish date):**
- `next` 16.4.3 (2026-10-23). Other tags still exist for older lines. The canary repo is at 16.5.0-canary.28 — [npm](https://registry.npmjs.org/next); [next package.json on canary](https://github.com/vercel/next.js/blob/canary/packages/next/package.json)
- Next.js 16.3 was announced 2026-08-03 with "Instant Navigations". A Sept 2026 security release targeted 16.3.7 and 15.5.27, so 15.5.x is still patched. No Next 17 announcement was found — [Next.js blog (via search)](https://nextjs.org/blog); [Upcoming security release Sept 2026](https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026)
- `nuxt` 4.6.3 (2026-10-27). Tags `3x`=3.21.11 and `4x`=4.6.3. It depends on `@nuxt/nitro-server` 4.6.3, which depends on `nitropack ^2.13.5` and `h3 ^1.15.11` — [npm nuxt](https://registry.npmjs.org/nuxt); [npm @nuxt/nitro-server](https://registry.npmjs.org/@nuxt%2fnitro-server)
- `nitropack` 2.13.5 (2026-10-19) is the stable Nitro. The new `nitro` package is 3.0.260903-beta (2026-09-03, **beta**). Nuxt `main` is 5.0.0-0, and a `release/v5.0.0-1` branch exists. Nuxt 5 "upgrades to Nitro v3 … built on srvx and h3 v2" and "we are still working on Nitro v3 integration" — [npm nitropack](https://registry.npmjs.org/nitropack); [npm nitro](https://registry.npmjs.org/nitro); [Nuxt main upgrade guide](https://github.com/nuxt/nuxt/blob/main/docs/1.getting-started/18.upgrade.md)
- `@sveltejs/kit` 3.1.0 (2026-10-14); `@sveltejs/adapter-vercel` 7.0.1 — [npm](https://registry.npmjs.org/@sveltejs%2fkit)
- `react-router` 8.5.0 (2026-10-19), with `version-7` tag at 7.18.4. `@remix-run/react` is frozen at 2.17.5 (2026-06-01). A separate `remix` package is at 3.1.0 (2026-10-23) — [npm react-router](https://registry.npmjs.org/react-router); [npm @react-router/dev](https://registry.npmjs.org/@react-router%2fdev); [npm remix](https://registry.npmjs.org/remix)
- `astro` 7.4.2 (2026-10-21). Adapters: `@astrojs/vercel` 11.0.16, `@astrojs/netlify` 8.2.10, `@astrojs/cloudflare` 14.4.2, `@astrojs/node` 11.1.9 — [npm astro](https://registry.npmjs.org/astro)
- `@angular/core` 22.2.3 (2026-10-14); `@angular/ssr` 22.2.4 — [npm](https://registry.npmjs.org/@angular%2fcore)
- `gatsby` 5.16.1 (2026-02-10; no newer release through Oct 2026) — [npm](https://registry.npmjs.org/gatsby)
- `@builder.io/qwik-city` 1.20.3 is stable. The Qwik v2 router `@qwik.dev/router` is 2.0.0-rc.4 (**RC**) — [npm](https://registry.npmjs.org/@qwik.dev%2frouter)
- `@solidjs/start` 2.1.0 (2026-10-22), Vite-based (`vite ^8 || ^9`, `h3 ^2.0.1-rc`, no vinxi). `@solidjs/router` 1.0.0 (2026-07-28) — [npm @solidjs/start 2.1.0](https://registry.npmjs.org/@solidjs%2fstart/2.1.0); [solid-start package.json](https://github.com/solidjs/solid-start/blob/main/packages/start/package.json)
- `@tanstack/react-start` 1.169.4, `@tanstack/react-router` 1.170.46, `@tanstack/react-query` 5.105.0, `swr` 2.5.1 (2.6.0-beta.0 exists), `@apollo/client` 4.3.5, `relay-runtime` 21.0.1, `urql` 5.0.4, `@urql/exchange-graphcache` 9.0.2, `@reduxjs/toolkit` 2.13.0, `react` 19.3.1, `vite` 8.3.5, `webpack` 5.112.2 — [npm registry](https://registry.npmjs.org/)
- Next.js self-hosting adapters: `@opennextjs/aws` 4.1.12, `@opennextjs/cloudflare` 1.20.13, `@netlify/plugin-nextjs` 5.16.4. The community handler `@neshca/cache-handler` was last published 2024-11 (1.9.0); `@fortedigital/nextjs-cache-handler` 3.4.0 (2026-10-16) is active — [npm](https://registry.npmjs.org/@neshca%2fcache-handler); [npm](https://registry.npmjs.org/@fortedigital%2fnextjs-cache-handler)

**Detection signals (config files and deps):**
- **SvelteKit 3:** "`svelte.config.js` is no longer supported." Config moves into the `sveltekit({...})` Vite plugin in `vite.config.js`. `$lib` becomes `#lib` via package.json `imports`, `$app/environment` becomes `$app/env`, and `$service-worker` / `$app/stores` are removed. Requires Node 22.17, TS 6, Svelte 5.57.1, and Vite 8.0.12 — [Migrating to SvelteKit 3](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)
- **React Router 8:** "Remove `react-router-dom` package", ESM-only, Node ≥22.22.0, React ≥19.2.7, middleware always on. Framework mode uses `react-router.config.ts` (`ssr`, `prerender`) — [react-router CHANGELOG v8.0.0](https://github.com/remix-run/react-router/blob/main/packages/react-router/CHANGELOG.md); [SPA mode](https://github.com/remix-run/react-router/blob/main/docs/how-to/spa.md)
- **Next.js:** `next.config.ts|js|mjs`. Cache Components is the top-level `cacheComponents: true` (since 16.0.0); the old `experimental.dynamicIO` / `experimental.useCache` / `experimental.ppr` flags were removed in 16 — [cacheComponents](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheComponents.mdx); [Next 16 upgrade guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-16.mdx)
- **Nuxt / Nitro:** `nuxt.config.ts` with `routeRules` and `nitro.storage`; standalone Nitro uses `nitro.config.ts` (`defineNitroConfig`) — [Nitro v2 cache guide](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)
- **Astro 7:** `astro.config.mjs` with top-level `cache: { provider }` and `routeRules`. These moved out of `experimental` in v7 — [Astro v7 upgrade guide](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/upgrade-to/v7.mdx)
- **TanStack Start:** `tanstackStart()` plugin in `vite.config.ts` (or `rsbuild.config.ts`) — [TanStack Start ISR guide](https://github.com/TanStack/router/blob/main/docs/start/framework/react/guide/isr.md)

### Inferences
- A detector should key on: `next`; `nuxt` (plus `nitropack` vs `nitro`); `@sveltejs/kit` (major ≥3 means look in `vite.config.*`, not `svelte.config.js`); `react-router` + `@react-router/dev` (framework mode) vs legacy `@remix-run/*` (Remix v2); `astro`; `@angular/ssr`; `gatsby`; `@builder.io/qwik-city` / `@qwik.dev/router`; `@solidjs/start` (v1 used vinxi `app.config.ts`, v2 uses Vite); and `@tanstack/react-start` / `@tanstack/solid-start`. Client caches: `@tanstack/*-query`, `swr`, `@apollo/client`, `react-relay`/`relay-runtime`, `urql`/`@urql/*`, and `@reduxjs/toolkit` (look for `createApi`).
- Deployment target signals: `@opennextjs/aws` / `open-next.config.ts`, `@opennextjs/cloudflare` / `wrangler.jsonc`, `@netlify/plugin-nextjs` / `netlify.toml`, `vercel.json`, Astro/SvelteKit `adapter-*` packages, and Nitro `preset`.
- The `react-router` package version alone does not show framework mode vs data/declarative mode. Check for `@react-router/dev` and `react-router.config.ts`.

### Gaps
- Exact release dates of Next 16.4.0 and SvelteKit 3.0.0, and the Astro 7.0 and React Router 8.0 announcement posts, were not retrieved (blog sites blocked).
- Remix 3 (`remix@3.1.0`) caching model was not researched. It is a different framework from React Router v7/v8 and was out of scope.
- Gatsby (`gatsby-config.*`) and Angular (`angular.json`, `app.routes.server.ts`) detection filenames come from background knowledge, not from a source read in this session.

---

## Q1. Next.js: full caching model in 16.x (latest stable 16.4.3), defaults, APIs, invalidation, HTTP/CDN mapping, self-hosting, pitfalls

### Takeaway
Next.js 16 has **two caching models**. The **Cache Components model** (`cacheComponents: true`, stable since 16.0.0, the default for new `create-next-app` apps per current docs) makes everything dynamic by default, and you opt in with `'use cache'` + `cacheLife` + `cacheTag`. Partial Prerendering is the default rendering in this model. The **previous model** (no flag) keeps `fetch` cache options, `unstable_cache`, route segment config (`dynamic`, `revalidate`, `fetchCache`) and ISR. Invalidation is unified: `revalidateTag(tag, profile)` gives SWR-style revalidation, `updateTag` (Server Actions only) gives read-your-writes, `revalidatePath`, and `refresh()` refreshes the client router. Multi-instance self-hosting needs **two handlers**: `cacheHandler` (singular, for ISR, route handlers, `fetch`, `unstable_cache` and images) and `cacheHandlers` (plural, for `'use cache'` backends).

### Cited Findings

**The two models and how to enable Cache Components**
- "New App Router apps created with the recommended `create-next-app` defaults already have Cache Components and Partial Prefetching enabled." To enable manually, set `cacheComponents: true` and `partialPrefetching: true`. "Set `partialPrefetching` explicitly. Leaving it unset logs a warning… Both features will be enabled everywhere in the next major release, and the options will be removed." *(canary docs; `partialPrefetching` was introduced in 16.3.0 per its version table)* — [Caching (Cache Components)](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx); [partialPrefetching](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/partialPrefetching.mdx)
- `cacheComponents` was "stabilized and moved from `experimental.cacheComponents` to the top-level option" in 16.0.0, and "controls the `ppr`, `useCache`, and `dynamicIO` flags as a single, unified configuration" — [cacheComponents](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheComponents.mdx)
- Next 16 removed `experimental.dynamicIO`, `experimental.useCache`, the experimental PPR flag, and route-level `experimental_ppr`. "Enabling `cacheComponents` is not a rename-only change: it can surface build errors for uncached data outside of `<Suspense>`." "PPR in Next.js 16 works differently than in Next.js 15 canaries" — [Next 16 upgrade guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-16.mdx)
- With Cache Components, "`GET` Route Handlers follow the same prerendering model as pages" — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)

**`'use cache'` / `cacheLife` / `cacheTag` (Cache Components model)**
- `'use cache'` caches the return value of async functions or components. It can apply at data level (a function) or UI level (a component/page/layout); at the top of a file it caches all exports. "We recommend pairing every cache directive with a `cacheLife`. Without one, the implicit `default` profile applies." — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)
  ```ts
  import { cacheLife, cacheTag } from 'next/cache'
  export async function getProducts() {
    'use cache'
    cacheLife('hours')
    cacheTag('products')
    return db.query('SELECT * FROM products')
  }
  ```
- Version history: `'use cache'` was introduced as experimental in 15.0.0 and stabilized in 16.0.0 under Cache Components. `cacheLife` and `cacheTag` were stabilized in 16.0.0, and `unstable_cacheLife` / `unstable_cacheTag` are deprecated (update imports) — [use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx); [cacheLife fn](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/cacheLife.mdx); [cacheTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/cacheTag.mdx)
- **Preset `cacheLife` profiles** (`stale` / `revalidate` / `expire`): `default` 5m/15m/never; `seconds` 30s/1s/1m; `minutes` 5m/1m/1h; `hours` 5m/1h/1d; `days` 5m/1d/1w; `weeks` 5m/1w/30d; `max` 5m/30d/1y. Any profile (including `default`) can be redefined in `next.config` `cacheLife`. `stale` is the client-side staleness window, `revalidate` is background regeneration (ISR-like), and `expire` is the hard maximum, which must be greater than `revalidate` — [cacheLife fn](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/cacheLife.mdx); [cacheLife config](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheLife.mdx)
- **Prerender thresholds.** `revalidate: 0` or `expire` < 5 min means the entry is excluded from prerender (a "dynamic hole" resolved at request time). `stale` < 30s is also excluded from prerender. `stale` from 30s to under 5 min is included in prerender but excluded from the App Shell. "Of the presets, only `seconds` falls under any of these thresholds." — [cacheLife fn](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/cacheLife.mdx)
- **Cache key** = build ID (or `deploymentId` if configured) + function ID (hash of location and signature) + serializable args, including **closed-over variables** + an HMR hash in dev. Only root params that are actually read join the key — [use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx)
- **Constraints.** Cached scopes cannot call `cookies()`, `headers()` or `searchParams`. The restriction "follows the call stack", and on dynamic routes it "can pass `next build` and fail under `next start`" (`next-request-in-use-cache`). Args and returns must be RSC-serializable (no class instances, URL instances or symbols). Non-serializable `children` and Server Actions may be passed through without introspection. Draft Mode makes all cached functions re-execute and skips writes — [use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx)
- **Runtime storage.** The default handler is an in-memory LRU. On serverless, "cache entries typically don't persist across requests"; self-hosted, entries persist (size set by `cacheMaxMemorySize`). "Neither caching directive carries over to a new deploy, because the cache key includes the build (or `deploymentId`) ID… For data that needs to persist across deploys, use `unstable_cache`… or the `fetch` cache." — [use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx)
- **`'use cache: remote'`** stores output in a durable shared handler ("a network roundtrip that pays off only at a high hit rate"). **`'use cache: private'`** can read cookies/headers/searchParams directly, lives **only in the browser** as part of prefetch, and is "not configurable" via handlers. Both were enabled with Cache Components in 16.0.0 — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx); [use cache: remote](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache-remote.mdx); [use cache: private](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache-private.mdx)
- On Vercel, `'use cache: remote'` maps to Vercel **Runtime Cache** (examples use `cacheLife({ expire: 3600 })` + `cacheTag`) — [Vercel Runtime Cache docs (via Vercel doc search)](https://vercel.com/docs/runtime-cache)
- **Runtime data pattern.** Read `cookies()` outside the cached scope, wrap that reader in `<Suspense>`, and pass the extracted value as an argument (it becomes part of the key). Use `connection()` before `Math.random()`, `Date.now()` or `crypto.randomUUID()` for per-request values; otherwise the dev overlay reports a blocking-prerender insight — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)
- **Where cached content lives.** (1) Prerendered HTML on disk (self-host) or platform durable storage behind the CDN. (2) The shared store (in-memory by default; `remote` uses a durable handler). (3) The browser (RSC payload kept fresh for `stale`). "All of these stores are scoped to a single deployment." — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)
- **ISR under Cache Components.** URLs not listed in `generateStaticParams` are served the App Shell instantly, then upgraded in the background and cached for the next visitor — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)
- **Bots.** Next detects some crawlers by user agent, skips the static shell, and renders dynamically. If build-time data sources are unavailable at runtime, "these bots receive a 500 error" — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)
- 16.3.0 stabilized the route segment exports `instant` and `prefetch` (they replace `unstable_instant` / `unstable_prefetch`, Cache Components only). `experimental.prefetchInlining` was added in 16.2 and enabled by default in 16.3 — [instant](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/03-file-conventions/02-route-segment-config/instant.mdx); [prefetch config](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/03-file-conventions/02-route-segment-config/prefetch.mdx); [prefetchInlining](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/prefetchInlining.mdx)
- **Prefetch with Partial Prefetching.** The router prefetches each route's App Shell by default. `<Link prefetch={true}>` also prefetches cached content that depends on URL params/searchParams, which "costs a server invocation per prefetchable link" — [Caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)

**Invalidation APIs (both models)**
- `revalidateTag(tag: string, profile: string | { expire?: number })`. It marks data stale; "the next request… is served stale content while it runs" (SWR). `'max'` is recommended. `{ expire: 0 }` means no stale serving, so the next request blocks; use it for webhooks where `updateTag` is not available. The single-arg form is **deprecated** (TypeScript error in 16) and behaves like `{ expire: 0 }`. Callable in Server Functions and Route Handlers, not in Client Components or Proxy. "A revalidation is triggered by a request, not by the `revalidateTag` call." Tags are case-sensitive, max 256 chars; an over-long tag is silently never assigned — [revalidateTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/revalidateTag.mdx); [Next 16 upgrade](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-16.mdx)
- `updateTag(tag)` is **Server Actions only** (it throws in Route Handlers). It "immediately expires the cached data… The next request will wait to fetch fresh data", giving read-your-own-writes — [updateTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/updateTag.mdx)
- `refresh()` from `next/cache` is **Server Actions only** and "refresh[es] the client router" — [refresh](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/refresh.mdx)
  ```ts
  'use server'
  import { updateTag, revalidateTag, refresh } from 'next/cache'
  export async function createPost(fd: FormData) {
    const post = await db.post.create({ data: { title: fd.get('title') } })
    updateTag('posts'); updateTag(`post-${post.id}`)  // read-your-writes
    // revalidateTag('catalog', 'max')               // background SWR for others
    // refresh()                                     // refresh client router only
  }
  // Route Handler / webhook: revalidateTag(tag, 'max') or revalidateTag(tag, { expire: 0 })
  ```
- "`revalidatePath` is a convenience layer on top of cache tags… [it] will call the `revalidateTag` function with a special default tag for the provided page." "`revalidatePath` invalidates the cache entries but regeneration happens on the next request." For eager regeneration, Pages Router `res.revalidate('/path')` remains — [Self-hosting](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/self-hosting.mdx); [ISR guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/incremental-static-regeneration.mdx)
- Vercel's purge doc maps the APIs this way for Next 16+: "Invalidate (serve stale)" = `revalidateTag(tag,'max')`; "Delete (regenerate in foreground)" = `revalidateTag(tag)`, `revalidatePath(path)`, `updateTag(tag)`. For Next ≤15 there is no invalidate in `next/cache` (use `invalidateByTag()` from `@vercel/functions`), and `unstable_expireTag` deletes. CLI: `vercel cache invalidate --tag foo`, `vercel cache dangerously-delete --tag foo`, `vercel cache purge --type cdn|data` — [Vercel CDN cache purge (via Vercel doc search)](https://vercel.com/docs/caching/cdn-cache/purge); [Vercel CLI](https://vercel.com/docs/cli)

**Previous model (no `cacheComponents`), which most existing 15.x and 16.x apps still use**
- **Next 15 default flip.** "`fetch` requests are no longer cached by default" (opt in with `cache: 'force-cache'` or segment `fetchCache = 'default-cache'`). "`GET` functions in Route Handlers are no longer cached by default" (opt in with `export const dynamic = 'force-static'`). For the Client Cache, "page segments are no longer reused" on `<Link>`/`useRouter` navigation, although they are still reused for back/forward and shared layouts — [Next 15 upgrade](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-15.mdx)
- **`fetch` options.** The default `auto no cache` is "fetch once during `next build` because the route will be statically prerendered" unless Request-time APIs are used. `no-store` fetches every request. `force-cache` matches on URL, method, headers and body, and "Caching is opt-in… including `POST` and requests that send `authorization` or `cookie` headers". `next: { revalidate: false | 0 | n, tags: [...] }` — max 128 tags, 256 chars each. Conflicting `{revalidate:3600, cache:'no-store'}` means both are ignored — [fetch](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/fetch.mdx)
- **Request memoization.** GET `fetch` with the same URL and options is memoized within one server render pass (layouts, pages, `generateStaticParams`, `generateViewport`). It does **not** apply in Route Handlers. For ORM/DB calls use `React.cache`. In dev, the HMR cache serves even `no-store` fetches across HMR refreshes — [fetch](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/fetch.mdx); [Previous model guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/caching-without-cache-components.mdx)
- **`unstable_cache(fn, keyParts, { tags, revalidate })`** (since v14.0.0) caches non-fetch functions and persists across deploys, unlike `'use cache'` — [Previous model guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/caching-without-cache-components.mdx); [use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx)
- **Segment config.** `dynamic = 'auto' | 'force-dynamic' | 'error' | 'force-static'`; `fetchCache` (7 modes); `revalidate = false | 0 | n`. The value must be statically analyzable (`600`, not `60*10`). "The lowest `revalidate` across each layout and page of a single route will determine the revalidation frequency of the entire route." Dev always renders on demand — [Previous model guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/caching-without-cache-components.mdx)
  ```ts
  export const revalidate = 3600            // route ISR
  const res = await fetch(url, { next: { revalidate: 60, tags: ['posts'] } })
  export const getUser = unstable_cache(async (id) => db.user(id), ['user'], { tags: ['user'], revalidate: 3600 })
  ```
- **Router (client) cache.** `experimental.staleTimes = { dynamic, static }` (still **experimental**). The `dynamic` default changed from 30s to 0s in v15.0.0; `static` is 5 min. Loading boundaries are reused for `static` — [staleTimes](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/staleTimes.mdx). Next 16 also added layout deduplication and incremental prefetching, which "may [produce] more individual prefetch requests with much lower total transfer sizes" — [Next 16 upgrade](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-16.mdx)
- **Pages Router.** `getStaticProps` returns `{ props, revalidate: 60 }`; `getStaticPaths` returns `fallback: 'blocking'`; on-demand revalidation uses `await res.revalidate('/posts/1')` in an API route. With on-demand only, omit `revalidate` (default `false`). You can set `Cache-Control` in `getServerSideProps` via `res.setHeader('Cache-Control','s-maxage=…, stale-while-revalidate')` — [ISR guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/incremental-static-regeneration.mdx); [headers config](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/headers.mdx)
- **Observability.** The `x-nextjs-cache` response header reports `HIT` / `STALE` / `MISS` / `REVALIDATED` — [ISR guide](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/incremental-static-regeneration.mdx)

**HTTP / CDN header mapping**
- Static pages get `s-maxage=31536000`. ISR pages get `s-maxage={revalidate}, stale-while-revalidate={expire - revalidate}` (default expire is 1 year). Dynamic pages get `private, no-cache, no-store, max-age=0, must-revalidate` (also Draft Mode). `/_next/static/*` gets `public, max-age=31536000, immutable`, which "cannot be overridden" — [CDN caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/cdn-caching.mdx); [Self-hosting](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/self-hosting.mdx)
- `expireTime` in next.config sets the SWR window. Example: revalidate 900 with expireTime 3600 gives `s-maxage=900, stale-while-revalidate=2700` — [expireTime](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/expireTime.mdx)
- **CDN pitfalls.** "CDN-level caching alone does not support on-demand revalidation… trigger CDN purges alongside your revalidation call (including both HTML and RSC variants)." App Router responses `Vary` on `rsc`, `next-router-state-tree`, `next-router-prefetch`, `next-router-segment-prefetch` and `next-url`. Rules: **forward the `rsc` header**; **include `_rsc` in the cache key** (many CDNs strip query params); a wrong `_rsc` triggers a 307 to the correct hash (disable with `experimental.validateRSCRequestHeaders: false`). Run `proxy.js` (formerly middleware) before the CDN. Under PPR, static prefetches are deterministic; with Cache Components, segment prefetches use pathname URLs (`/page.segments/_tree.segment.rsc`). The team is designing **pathname-based cache keying** (`.rsc` suffixes, no `Vary`); "It is in active design" — [CDN caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/cdn-caching.mdx)
- `images.minimumCacheTTL` default changed from 60s to **4 hours (14400s)** in Next 16. `cacheHandler` covers image-optimization caching since v16.2.0 — [Next 16 upgrade](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-16.mdx); [cacheHandler](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/incrementalCacheHandlerPath.mdx)

**Self-hosting and multi-instance caching**
- The ISR and data cache is "stored on the local filesystem (on disk) of each Next.js server instance", plus memory (default 50 MB). With k8s, each pod has its own copy, so configure a handler and disable in-memory caching. The `cacheHandler` (singular) class implements `get`, `set`, `revalidateTag` and `resetRequestCache`. A production handler must: use shared storage (Redis/S3, not a `Map`); bound size; **serialize `Buffer` (`rscData`) and `Map` (`segmentData`)**, otherwise you get errors like `segmentData.get is not a function`; index entries by tag (`x-next-cache-tags` in `data.headers` for `APP_PAGE` / `APP_ROUTE` / `PAGES`, `ctx.tags` for fetch); and handle storage errors. Community handlers listed: `@trieb.work/nextjs-turbo-redis-cache` and `@mrjasonroy/cache-components-cache-handler` — [Self-hosting](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/self-hosting.mdx)
- Use the same build across containers (`generateBuildId`), or set `deploymentId`, which yields a constant build ID — [Self-hosting](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/self-hosting.mdx)
- **`cacheHandlers`** (plural; stable top-level since 16.0.0): `{ default: require.resolve('./h/default.js'), remote: require.resolve('./h/remote.js') }`. Extra named handlers are used as `'use cache: <name>'`. Interface:
  - `get(cacheKey, softTags)` and `set(cacheKey, pendingEntry: Promise<CacheEntry>)`. `CacheEntry` = `{ value: ReadableStream<Uint8Array>, tags, stale, timestamp, expire, revalidate }`. The stream is **single-read** and request-bound, so do not retain it.
  - `refreshTags()` runs once per request and pulls shared invalidations; `getExpiration(tags)` and `updateTags(tags, {expire})` complete the tag API.
  - A `get()` exception becomes a render error, so return `undefined` on failure.
  - Platform support: Node and Docker yes; static export no; adapters are platform-specific.
  — [cacheHandlers](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheHandlers.mdx)
- "`cacheHandler` (singular) covers server cache paths like ISR, route handlers, patched `fetch`/`unstable_cache`, and image optimization. `cacheHandlers` (plural) configures `'use cache'` directive backends." The Deployment Adapter API (`adapterPath`) became stable top-level in 16.2.0. Verified adapters are open source and run the compatibility suite — [Deploying to platforms](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/deploying-to-platforms.mdx); [adapterPath](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/adapterPath.mdx)
- Feature matrix: ISR (time-based) works per-instance without a shared cache. On-demand ISR "needs shared cache for multi-instance". PPR requires streaming. `use cache` requires streaming and recommends a shared cache — [Deploying to platforms](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/deploying-to-platforms.mdx)
- Next 16 minimums: Node 20.9+ and TS 5.1+. Turbopack is the default bundler. `middleware` is renamed to `proxy` — [Next 16 upgrade](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/upgrading/version-16.mdx)

### Inferences
- **Decision rule for the skill.** If `cacheComponents` is absent, recommend previous-model APIs (`fetch` `force-cache` + `next.tags`, `unstable_cache`, segment `revalidate`). Do not sprinkle `'use cache'`: it is unavailable or inert without the flag, and turning the flag on is a migration. If the flag is present, recommend `'use cache'` + explicit `cacheLife` + `cacheTag`, Suspense around runtime reads, and `updateTag` in actions.
- **Always audit for `revalidateTag(x)` with one argument** after a 15→16 upgrade. It is deprecated and means immediate expiry. Prefer `'max'` for content or `updateTag` for user edits.
- On serverless platforms without a remote handler, `'use cache'` runtime entries rarely hit. Value comes mainly from build-time prerender, ISR shells and browser `stale`. Use `'use cache: remote'` only for expensive upstreams with high hit rates.
- When self-hosting behind a CDN, either purge the CDN on revalidate (both HTML and `_rsc` variants) or keep the CDN TTL short. Otherwise `revalidateTag` appears not to work.

### Gaps
- The Next.js 16.0, 16.1, 16.2, 16.3 and 16.4 release blog posts could not be read (nextjs.org blocked). It is unverified which minor made Cache Components the `create-next-app` default.
- The detailed client Router Cache semantics under Cache Components (beyond `cacheLife.stale` and per-session App Shell caching) were not exhaustively documented in the pages read.
- Whether `staleTimes` still applies when `cacheComponents` is on was not stated in the pages read.

---

## Q2. Nuxt 3/4 and Nitro: routeRules, cached handlers/functions, storage, useFetch/useAsyncData

### Takeaway
Stable Nuxt 4.6.x runs on **nitropack 2.13**, so Nitro v2 caching docs apply. Nuxt 5 and Nitro 3 are still pre-release. Server caching uses `routeRules` (`swr`, `isr`, `prerender`, `cache`, `headers`) plus `defineCachedEventHandler` / `defineCachedFunction`, backed by an unstorage `cache:` mount. That mount is **in-memory per instance in production by default**, so point it at Redis or KV for multi-instance setups. Client-side, `useAsyncData` / `useFetch` dedupe and share state by **key**, transfer server data via the payload, and expose `refresh` / `clear` plus the global `refreshNuxtData` / `clearNuxtData`.

### Cited Findings
- **Route rules:** `prerender: true`; `swr: true | n` ("cache it on the server or reverse proxy… The `node-server` preset of Nitro is able to cache the full response"); `isr: true | n` ("same as `swr` except… add the response to the CDN cache on platforms that support this (currently Netlify or Vercel)"; `true` persists until next deploy); `ssr: false`; `headers`; `cors`; `redirect`; `proxy`; `noScripts`; `appMiddleware`. "Routes using `isr` or `swr` also generate `_payload.json` files alongside HTML." Hybrid rendering is unavailable with `nuxt generate`. Route rules map to native platform rules on Netlify and Vercel — [Nuxt 4.x rendering concepts](https://github.com/nuxt/nuxt/blob/4.x/docs/3.guide/1.concepts/1.rendering.md)
  ```ts
  export default defineNuxtConfig({
    routeRules: {
      '/': { prerender: true },
      '/products/**': { swr: 3600 },
      '/blog/**': { isr: true },
      '/admin/**': { ssr: false },
      '/_nuxt/**': { headers: { 'cache-control': 'public, max-age=31536000, immutable' } },
    },
    nitro: { storage: { cache: { driver: 'redis', url: process.env.REDIS_URL } } },
  })
  ```
- `defineRouteRules({...})` inside a page is **experimental** and needs `experimental.inlineRouteRules` — [defineRouteRules](https://github.com/nuxt/nuxt/blob/4.x/docs/4.api/3.utils/define-route-rules.md)
- **Nitro (v2) cached handlers.** `defineCachedEventHandler(handler, { maxAge })` uses SWR by default ("stale value will be sent… set `swr: false`" for immediate). "All incoming request headers are dropped when handling cached responses" unless listed in `varies`; for multi-tenant use `['host','x-forwarded-host']`. Options: `base` (storage mount, default `cache`); `name`; `group` (`nitro/handlers` | `nitro/functions`); `getKey`; `integrity`; **`maxAge` default `1` second**; `staleMaxAge` (default 0; `-1` = always serve stale); `swr` (default true); `shouldInvalidateCache`; `shouldBypassCache`; `varies` — [Nitro v2 cache](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)
- **`defineCachedFunction`.** Results are JSON-serialized, so Maps, Sets and Symbols are unsupported. On edge workers, pass `event` as the first arg so Nitro can `event.waitUntil` the background revalidation — [Nitro v2 cache](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)
  ```ts
  export const getStars = defineCachedFunction(async (event: H3Event, repo: string) =>
    (await $fetch(`https://api.github.com/repos/${repo}`)).stargazers_count,
    { maxAge: 3600, name: 'ghStars', getKey: (_e, repo) => repo })
  ```
- **Storage.** The `cache:` mount uses the **memory driver in production** and the fs driver in dev. Override with `storage.cache` (or `nitro.storage.cache` in Nuxt) and `devStorage`. Route-rule `cache: { maxAge, base: 'redis' }` selects a custom mount — [Nitro v2 cache](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)
- **Invalidation.** Key = `${group}:${name}:${getKey(...)}.json`; invalidate with `await useStorage('cache').removeItem('nitro:functions:getAccessToken:default.json')`. Keys are **normalized** (`/\W/g` stripped), so `/api/products/sale-items` becomes `api/productssaleitems.json`; use `escapeKey()` when building keys to invalidate — [Nitro v2 cache](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)
- **useAsyncData / useFetch.**
  - "If you do not provide a key, then a key that is unique to the file name and line number… will be generated."
  - Calls with the same key share `data`, `error`, `status` and `pending`; the handler, `deep`, `transform`, `pick`, `getCachedData` and `default` must match across them.
  - Reactive (computed or getter) keys refetch, and "the old data will be cleaned up if no other components use it".
  - `dedupe` defaults to `'cancel'`. `enabled` was added in v4.5. **`serialize` (v4.6)**: `false` keeps data out of `__NUXT_DATA__`, so the client refetches. `middleware` was added in v4.6. `timeout` and abort `signal` are supported.
  — [useAsyncData (4.x)](https://github.com/nuxt/nuxt/blob/4.x/docs/4.api/2.composables/use-async-data.md); [Data fetching (4.x)](https://github.com/nuxt/nuxt/blob/4.x/docs/1.getting-started/10.data-fetching.md)
- **Default `getCachedData`:** `nuxtApp.isHydrating ? nuxtApp.payload.data[key] : nuxtApp.static.data[key]`. "This only caches data when `experimental.payloadExtraction` in `nuxt.config` is enabled." A custom `getCachedData(key, nuxtApp, ctx)` (where `ctx.cause` is `'initial' | 'refresh:manual' | 'refresh:hook' | 'watch'`) enables client caching across navigations — [useAsyncData (4.x)](https://github.com/nuxt/nuxt/blob/4.x/docs/4.api/2.composables/use-async-data.md)
- **Payload.** `useFetch` / `useAsyncData` prevent double-fetching (SSR then hydrate) by forwarding server data in the payload, serialized with `devalue` (Dates, Maps, Sets, refs). Use `pick` / `transform` to shrink the payload. Global invalidation uses `refreshNuxtData` and `clearNuxtData` — [Data fetching (4.x)](https://github.com/nuxt/nuxt/blob/4.x/docs/1.getting-started/10.data-fetching.md)

### Inferences
- Pitfall: `defineCachedEventHandler` without `maxAge` caches for only **1 second**. Always set `maxAge` (and `staleMaxAge` if you want bounded staleness).
- Pitfall: cached handlers drop request headers, so auth- or locale-dependent output must use `varies` or `getKey`, or must not be cached. Treat `swr` / `isr` routes as **shared**; never use them for per-user pages.
- Multi-instance or serverless: the default memory driver means per-instance caches and inconsistent invalidation. Configure `nitro.storage.cache` (Redis, Cloudflare KV, Vercel KV/Upstash, etc.).
- `isr` only gets CDN behavior on Vercel or Netlify presets. Elsewhere it degrades to `swr`-like headers or server caching.
- For a client "stale-while-revalidate across navigations" effect in Nuxt, implement `getCachedData` that returns `nuxtApp.payload.data[key] ?? nuxtApp.static.data[key]` with a timestamp check (inference from the documented signature).

### Gaps
- The Nitro v3 cache API (`nitro` 3.0 beta; docs at `nitrojs/nitro` main `docs/1.docs/7.cache.md`) was not read in detail. Expect h3 v2 naming changes (`defineCachedHandler`) for Nuxt 5 — unverified.
- No first-party source was read on how `isr` maps on Cloudflare, AWS or self-hosted Node beyond "currently Netlify or Vercel".

---

## Q3. SvelteKit (3.1): load caching, setHeaders, prerender, ISR, fetch dedupe, remote functions

### Takeaway
SvelteKit has no built-in server data cache. Caching is **HTTP-header driven** (`setHeaders` in `load`), plus **prerendering** (`prerender = true | 'auto'`), plus adapter features such as **Vercel ISR** (`config.isr`). On the client, `load` reruns are dependency-tracked and invalidated via `depends` / `invalidate` / `refreshAll`. SSR `fetch` responses are inlined into HTML and reused during hydration. Experimental **remote functions** (`query`) add request-scoped server dedupe and an in-use client cache. SvelteKit 3 moved all config into `vite.config.js`.

### Cited Findings
- **`setHeaders` in load** (server and universal; no-op in the browser) is used to cache the page's HTML. "Setting the same header multiple times (even in separate `load` functions) is an error." You cannot set `set-cookie` this way. Headers cannot be set inside streamed promises — [Loading data](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/20-load.md)
  ```js
  export async function load({ fetch, setHeaders }) {
    const res = await fetch('https://cms.example.com/products.json');
    setHeaders({ age: res.headers.get('age'), 'cache-control': res.headers.get('cache-control') });
    return res.json();
  }
  ```
- **`fetch` in load.** It inherits cookie and auth headers. Internal `+server.js` calls are direct function calls. "During server-side rendering, the response will be captured and inlined into the rendered HTML… headers will not be serialized, unless explicitly included via `filterSerializedResponseHeaders`. During hydration, the response will be read from the HTML… preventing an additional network request" — [Loading data](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/20-load.md)
- **Rerun / invalidation.** Load functions rerun when the params, url parts or parent they used change. Use `untrack()` to exclude dependencies, `depends('app:random')` with `invalidate('app:random')`, or `invalidate(url)`. `refreshAll()` reruns every load and all active queries. **`invalidateAll` is deprecated in v3 in favor of `refreshAll`** (which keeps `page.state`). "Server load functions will never automatically depend on a fetched `url`" — [Loading data](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/20-load.md); [Migrating to v3](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)
- **Prerender.** `export const prerender = true | false | 'auto'` (`'auto'` = prerender but keep in the SSR manifest for the long tail). The crawler follows `<a>` links; for unlinked params use `entries()` or `config.prerender.entries` — [Page options](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/40-page-options.md)
- **Vercel ISR.** `export const config = { isr: { expiration: 60, bypassToken: BYPASS_TOKEN, allowQuery: ['search'] } }` — `expiration` is required. "Use ISR only on routes where every visitor should see the same content." ISR on a `prerender = true` route has no effect — [adapter-vercel](https://github.com/sveltejs/kit/blob/main/documentation/docs/25-build-and-deploy/90-adapter-vercel.md)
- **SvelteKit 3 caching-relevant changes:**
  - adapter-vercel drops the `edge` runtime.
  - adapter-node serves static assets from a build-time list with **content-hash ETags and no `Last-Modified`**; only GET and HEAD are served.
  - adapter-cloudflare exposes `caches` as a global, `env` / `waitUntil` from `cloudflare:workers`, and needs wrangler ≥4.67.
  - adapter-netlify uses the Netlify Frameworks API.
  - `version.pollInterval` now defaults to **one hour**, which sets `updated.current`.
  - `$service-worker` is removed: use `$app/manifest` for offline caching lists.
  - `output.linkHeaderPreload` defaults to `<link>` elements, not `Link` headers.
  — [Migrating to v3](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)
- **Remote functions** are still **experimental** (`experimental.remoteFunctions` + `compilerOptions.experimental.async`).
  - `query` args are serialized into a cache key, with object keys sorted. Server: "a request-scoped cache so that multiple invocations… only result in the work happening once". Client: identical calls share one instance (`getPosts() === getPosts()`) while in use, and are released when unused.
  - Refresh with `getPosts().refresh()`; set with `getPost(id).set(v)` from the server in `form` / `command` handlers. Doing either replaces the default "invalidate everything" for that submission. Use `requested(getPosts, n)` for client-requested refreshes and `withOverride` for optimistic updates. `query.batch` solves n+1.
  - "Don't cache live query responses in a service worker."
  — [Remote functions](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/60-remote-functions.md); [Migrating to v3](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)

### Inferences
- The skill's SvelteKit playbook should be: `setHeaders({'cache-control': 'public, max-age=0, s-maxage=…, stale-while-revalidate=…'})` for shared pages; `prerender` for static content; `isr` on Vercel; and a server-side memo (for example an LRU/Redis wrapper in `$lib/server`) when data caching is needed, since none is built in.
- The "set the same header twice is an error" rule means layout and page `load` functions must coordinate: set `cache-control` in only one place, typically the leaf page.
- When upgrading from 2.x, `svelte.config.js` edits (`kit.prerender`, `kit.version`) must move into `vite.config.js` `sveltekit({...})`.

### Gaps
- Netlify and Cloudflare ISR-equivalents for SvelteKit 3 (for example Netlify durable cache headers via the adapter) were not documented in the pages read.
- The SvelteKit 3.0.0 release date and blog post were not retrieved.

---

## Q4. Remix / React Router v7 → v8 (framework mode): headers, loader caching, clientLoader, SPA mode

### Takeaway
React Router 8.5 is current (7.18.x is still tagged). Framework-mode caching is **HTTP-first**. Use the route-module `headers` export (deepest route wins; merge parents manually); loaders can attach headers via `data(value, { headers })`, but those must be re-emitted from `headers`. Client-side caching is **DIY via `clientLoader`** (+ `clientLoader.hydrate`), with revalidation controlled by `shouldRevalidate`. SPA mode (`ssr: false`) and `prerender` produce static output for CDN caching.

### Cited Findings
- **`headers` export.** Return `Headers` or `HeadersInit`. "Headers from loaders and actions are not sent automatically. You must explicitly return them from the `headers` export." "The headers from the deepest matching route will be sent", so parent and child merging is manual. `Set-Cookie` is the exception and is preserved automatically — [HTTP Headers how-to](https://github.com/remix-run/react-router/blob/main/docs/how-to/headers.md)
  ```tsx
  export async function loader({ params }: Route.LoaderArgs) {
    return data(await getPage(params.id), { headers: { 'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=86400' } })
  }
  export function headers({ loaderHeaders, parentHeaders }: Route.HeadersArgs) {
    return { 'Cache-Control': loaderHeaders.get('Cache-Control') ?? parentHeaders.get('Cache-Control') ?? 'no-store' }
  }
  ```
- **Client caching pattern.** Prime the cache on hydration with `clientLoader.hydrate = true`, serve subsequent navigations from cache in `clientLoader`, and invalidate in `clientAction`. `HydrateFallback` renders during SSR when client data is required — [Client data how-to](https://github.com/remix-run/react-router/blob/main/docs/how-to/client-data.md)
  ```tsx
  const cache = new Map()
  export async function clientLoader({ request, serverLoader }: Route.ClientLoaderArgs) {
    const key = new URL(request.url).pathname
    if (cache.has(key)) return cache.get(key)
    const d = await serverLoader(); cache.set(key, d); return d
  }
  clientLoader.hydrate = true as const
  export async function clientAction({ serverAction }) { cache.clear(); return serverAction() }
  ```
- **Revalidation defaults.**
  - Framework mode with SSR: active loaders revalidate on navigations and successful submissions. Failed 4xx/5xx submissions do not revalidate.
  - SPA mode and Data mode: GET navigations revalidate only when params or search params change. A navigation to the exact same URL acts like a refresh.
  - `fetcher.load` revalidates only after actions or `useRevalidator`.
  - Use `shouldRevalidate` and fall back to `defaultShouldRevalidate`.
  — [Revalidation optimization](https://github.com/remix-run/react-router/blob/main/docs/how-to/optimize-revalidation.md)
- **SPA mode.** `ssr: false` in `react-router.config.ts`, "React Router will still server render your root route at build time to generate the `index.html`". `clientLoader` / `clientAction` handle data — [SPA how-to](https://github.com/remix-run/react-router/blob/main/docs/how-to/spa.md)
- **Pre-rendering.** `prerender: true | string[] | async ({ getStaticPaths }) => [...] | { paths, concurrency }`. It works with `ssr: true` (default), with `ssr: false` (static host), or with `ssr: "unstable_api-only"` (experimental) — [Pre-rendering](https://github.com/remix-run/react-router/blob/main/docs/how-to/pre-rendering.md)
- **v8 breaking changes relevant to caching and CDNs.**
  - "Trailing slash-aware data request URLs are now the default" (`future.v8_trailingSlashAwareDataRequests` removed).
  - The raw request is always passed to loaders and actions; use `url` for the normalized URL without `.data` suffixes or `index` / `_routes` params.
  - Middleware is always enabled.
  - `react-router-dom` is removed; packages are ESM-only.
  - v8.3 adds RSC metadata so routes with `clientLoader` can skip server requests.
  — [react-router CHANGELOG](https://github.com/remix-run/react-router/blob/main/packages/react-router/CHANGELOG.md)

### Inferences
- `.data` requests (single-fetch) are separate cacheable URLs. If a CDN caches HTML documents, ensure `.data` responses carry matching `Cache-Control` via `headers`, and that CDN cache keys respect v8's trailing-slash-aware `.data` URLs.
- Remix v2 apps (`@remix-run/*` 2.17.x) use the same `headers` / `loader` / `clientLoader` concepts, so the skill can treat them like React Router 7 framework mode for caching recommendations.
- For data-heavy client caching in React Router apps, pairing `clientLoader` with TanStack Query's `queryClient.ensureQueryData` is a common choice (inference; not from RR docs).

### Gaps
- The React Router v7→v8 upgrade guide (`docs/upgrading/`) had no v8-specific file in the repo snapshot. Breaking changes were taken from the CHANGELOG.
- No source was found on built-in server-side loader caching (none appears to exist).

---

## Q5. Astro (7.4): static vs on-demand, route caching (now stable), server islands, adapter ISR

### Takeaway
Astro pages are **prerendered by default**. On-demand pages opt in via `export const prerender = false` or `output: 'server'`. **Route caching became stable in Astro 7.0** (it was experimental in 6.x): `cache: { provider }` + `Astro.cache.set({ maxAge, swr, tags })` + `cache.invalidate({ tags | path })` + config `routeRules`. First-party Netlify, Vercel and Cloudflare **CDN cache providers are still experimental**. Server islands are fetched via cacheable GET (encrypted props in the query string). The Vercel adapter also offers `isr`.

### Cited Findings
- **Route caching (since 7.0.0).** It is a platform-agnostic API for on-demand pages and endpoints, built on `max-age` and `stale-while-revalidate`, with tag and path invalidation, route rules and pluggable providers. There is a built-in `memoryCache()` provider. Use `Astro.cache` in `.astro` files and `context.cache` in endpoints and middleware — [Astro route caching guide](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)
  ```js
  // astro.config.mjs
  import { defineConfig, memoryCache } from 'astro/config'
  export default defineConfig({
    adapter: node({ mode: 'standalone' }),
    cache: { provider: memoryCache() },
    routeRules: { '/api/[...path]': { swr: 600 }, '/products/[...slug]': { maxAge: 3600, tags: ['products'] } },
  })
  // page: Astro.cache.set({ maxAge: 120, swr: 60, tags: ['home'] }); Astro.cache.set(false) to opt out
  // endpoint: await context.cache.invalidate({ tags: ['data'] }); await context.cache.invalidate({ path: '/api/data' })
  ```
- **Semantics.**
  - Merges across calls: `maxAge`, `swr` and `etag` are last-write-wins; `lastModified` takes the most recent; `tags` accumulate. Middleware, layouts, content loaders and pages can all contribute.
  - Path invalidation is exact-match only (no globs). `routeRules` use file-route syntax (`[...rest]`, not `*`).
  - In dev, `cache.enabled` is `false` and set and invalidate are no-ops. Without a provider, `set` warns and `invalidate` **throws**, so guard with `if (Astro.cache.enabled)`.
  — [Astro route caching guide](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)
- **Adapter CDN providers (experimental).**
  - `cacheNetlify()` from `@astrojs/netlify/cache` sets `Netlify-CDN-Cache-Control` and `Netlify-Cache-Tag`, using the durable cache.
  - `cacheVercel()` sets `Vercel-CDN-Cache-Control` and `Vercel-Cache-Tag`; "Tag invalidation is a soft invalidation" (SWR).
  - `cacheCloudflare()` sets `Cloudflare-CDN-Cache-Control` and `Cache-Tag`, and enables Workers Cache.
  - Each auto-tags responses with the request path, so path invalidation works on tag-only platforms. "In a future release, they will be enabled automatically by their adapters."
  — [Astro route caching guide](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)
- **v7 upgrade:** "Route caching is now stable… move `cache` and `routeRules` out of the `experimental` block." In Astro 6 it was `experimental.cache` — [Astro v7 upgrade](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/upgrade-to/v7.mdx); [Astro v6 experimental route caching (search result)](https://v6.docs.astro.build/en/reference/experimental-flags/route-caching/)
- **Server islands.** Data is "retrieved via a `GET` request, passing props as an encrypted string in the URL query", which allows `Cache-Control` caching. If the URL exceeds 2048 bytes, Astro sends a POST, which is not cacheable. The encryption key is random per build, so set `ASTRO_KEY` (generated via the CLI) for rolling deploys, multi-region setups or CDNs caching pages that contain islands — [Server islands](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/server-islands.mdx)
- **Vercel adapter `isr`.**
  - `isr: true | { expiration, bypassToken, exclude }`; it caches on-demand pages "for the duration of your deployment" by default.
  - Without `expiration`, "any Cache-Control headers are ignored" (cache shielding); setting `expiration` makes app Cache-Control respected.
  - ISR requests drop search params.
  - Middleware runs only on cache miss unless `middlewareMode: 'edge'`.
  — [@astrojs/vercel guide](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/integrations-guide/vercel.mdx)
- **Rendering defaults.** "By default, your entire Astro site will be prerendered." `output: 'server'` flips the default; per-page `prerender` overrides — [On-demand rendering](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/on-demand-rendering.mdx)

### Inferences
- The skill should check `astro` major. For ≥7, use top-level `cache` / `routeRules`. For 6.x, use `experimental.cache`. For ≤5, only manual `Astro.response.headers.set('Cache-Control', …)` and adapter ISR are available (inference from version notes).
- `memoryCache()` on multi-instance Node gives per-instance caches. For multi-instance deployments, prefer a CDN provider or a custom provider (see `cache-provider-reference`).

### Gaps
- `reference/cache-provider-reference.mdx` (custom provider interface, `memoryCache` options) was not read in detail.
- Integration between live content collections and `cache.invalidate` was mentioned in search snippets but not verified in v7 docs.

---

## Q6. Others: Angular, Gatsby, Qwik, SolidStart, TanStack Start, Vite/webpack hashing

### Takeaway
Most other frameworks expose **HTTP-header-centric caching** plus a client loader cache: Angular's HTTP **transfer cache**, Qwik's `cacheControl()`, TanStack Start route `headers()` + prerender, and Solid Router `query()`. Gatsby is static output with a strict header recipe. Build tools emit content-hashed assets that should be `immutable`, while HTML and manifest files must revalidate.

### Cited Findings
- **Angular 22.** `provideClientHydration(withHttpTransferCacheOptions({ includeHeaders, filter, includePostRequests, includeRequestsWithAuthHeaders }))`. By default `HttpClient` caches all `HEAD`/`GET` requests without `Authorization`, `Proxy-Authorization` or `Cookie` headers and without credentials. It skips the transfer cache when `Cache-Control` has `no-store`, `no-cache` or `private`, or fetch `cache: 'no-store'|'no-cache'`. No headers are included by default. Server routes use `RenderMode.Server | Prerender | Client` and per-route `headers` and `status`. "By default, Angular prerenders your entire application" (set `outputMode: 'static'` for fully static). There is a 1 MB response body limit for the SSR fetch backend — [Angular SSR guide](https://github.com/angular/angular/blob/main/adev/src/content/guide/ssr.md)
- **Gatsby 5.16.** HTML and `public/page-data/**` (including `app-data.json`) get `public, max-age=0, must-revalidate`. Hashed JS/CSS and `static/` get `public, max-age=31536000, immutable` — [Gatsby caching](https://github.com/gatsbyjs/gatsby/blob/master/docs/docs/how-to/previews-deploys-hosting/caching.md)
- **Qwik Router.** `export const onGet: RequestHandler = ({ cacheControl }) => cacheControl({ public, maxAge, sMaxAge, staleWhileRevalidate })`. Set it in the root layout and override in nested layouts (for example dashboard `public: false, maxAge: 0`) — [Qwik caching docs](https://github.com/QwikDev/qwik/blob/main/packages/docs/src/routes/docs/%28qwikrouter%29/caching/index.mdx)
- **Solid Router `query()`** (used by SolidStart). It caches by name + serialized args; preloaded data is reused for **5000 ms**; back/forward reuses entries; there is a request-scoped cache during SSR; client entries without subscribers can be deleted after **180000 ms**; `revalidate(key)` forces refresh — [Solid Router query reference](https://github.com/solidjs/solid-docs/blob/main/src/routes/solid-router/reference/data-apis/query.mdx)
- **TanStack Start.** ISR is done via a route `headers: () => ({ 'Cache-Control': 'public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400' })` plus `tanstackStart({ prerender: { routes, crawlLinks } })`. It "leverages standard HTTP cache headers that work with any CDN" — [TanStack Start ISR](https://github.com/TanStack/router/blob/main/docs/start/framework/react/guide/isr.md). The TanStack Router loader cache has `staleTime` default **0**, `preloadStaleTime` **30s**, and `gcTime` / `preloadGcTime` **5 min**; `router.invalidate()` reloads active routes — [TanStack Router data loading](https://github.com/TanStack/router/blob/main/docs/router/guide/data-loading.md)
- **Vite 8 build** emits "hashed assets (JS, CSS, and other file types like images)", which can be deployed and served separately from public files — [Vite build guide](https://github.com/vitejs/vite/blob/main/docs/guide/build.md)
- **React `cache()`** is for Server Components only. "React will invalidate the cache for all memoized functions for each server request." Each `cache(fn)` call creates a separate cache, so define memoized functions at module scope. `cacheSignal()` can abort work — [React cache reference](https://github.com/reactjs/react.dev/blob/main/src/content/reference/react/cache.md)

### Inferences
- **Universal static-asset rule** (Vite, webpack `[contenthash]`, Next `/_next/static`, Nuxt `/_nuxt`, SvelteKit `/_app/immutable`, Astro `/_astro`): hashed paths get `public, max-age=31536000, immutable`; HTML, manifests and service-worker files get `no-cache` or `max-age=0, must-revalidate`. The SvelteKit and Astro path names are background knowledge, not verified this session.
- Angular's transfer cache only prevents the SSR→hydration double fetch. It is not a runtime cache, so pair it with HTTP caching or an interceptor for runtime caching.

### Gaps
- The SolidStart 2 server-side caching story (h3 v2 / Nitro integration, route rules) was not researched.
- Qwik v2 (`@qwik.dev/router` RC) changes to `cacheControl` were not verified beyond the docs above.
- Angular incremental hydration and `httpResource` caching were not covered.
- webpack `[contenthash]` and `optimization.moduleIds: 'deterministic'` details were not sourced this session.

---

## Q7. Client data caches: TanStack Query, SWR, Apollo, Relay, urql, RTK Query, React cache()/use(), persistence

### Takeaway
All client caches revolve around a **key** (query key, SWR key, normalized entity ID or endpoint + args), a **freshness window** (TanStack `staleTime`, SWR `dedupingInterval` and revalidate triggers, RTK `refetchOnMountOrArgChange`), a **retention window** (TanStack `gcTime` 5 min, RTK `keepUnusedDataFor` 60s, Solid 180s), and **invalidation** (`invalidateQueries`, `mutate`, `invalidatesTags`, `cache.evict` / `modify`, Graphcache `updates`). Notable 2025–26 changes: TanStack `staleTime: 'static'` and the `context.client` mutation-callback signature; Apollo 4 `notifyOnNetworkStatusChange` default true; SWR 2.5 RSC `preload` + `cacheData`.

### Cited Findings
**TanStack Query v5 (5.105)**
- Defaults: cached data is **stale immediately** (`staleTime` 0). Stale queries refetch on mount, window refocus and reconnect. Inactive queries are GC'd after **5 min** (`gcTime`). Failures retry **3** times with exponential backoff. Results are structurally shared. `staleTime: Infinity` still allows manual invalidation; **`staleTime: 'static'`** blocks even `invalidateQueries` and `refetch*: 'always'` (use it for boot-time flags and permissions) — [Important defaults](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/important-defaults.md); [Caching](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/caching.md)
- Invalidation: `queryClient.invalidateQueries({ queryKey: ['todos'] })` matches by prefix; use `exact: true` for an exact match — [Query invalidation](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/query-invalidation.md)
- Optimistic updates (current signature, with mutation-function context):
  ```ts
  useMutation({
    mutationFn: addTodo,
    onMutate: async (newTodo, context) => {
      await context.client.cancelQueries({ queryKey: ['todos'] })
      const previous = context.client.getQueryData(['todos'])
      context.client.setQueryData(['todos'], (old) => [...old, newTodo])
      return { previous }
    },
    onError: (err, newTodo, onMutateResult, context) => context.client.setQueryData(['todos'], onMutateResult.previous),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['todos'] }), // documented form
  })
  ```
  — [Optimistic updates](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/optimistic-updates.md)
- SSR and hydration: "With SSR, we usually want to set some default staleTime above 0" (example 60s). Make a new `QueryClient` per request on the server (`environmentManager.isServer()`) and a singleton in the browser. `dehydrate` / `<HydrationBoundary>`; to stream, include pending queries via `shouldDehydrateQuery: q => defaultShouldDehydrateQuery(q) || q.state.status === 'pending'` — [Advanced SSR](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/advanced-ssr.md)
- Persistence: plugins include `persistQueryClient`, `createSyncStoragePersister`, `createAsyncStoragePersister`, `createPersister` and `broadcastQueryClient`. Default persisted `maxAge` is 24h, and `gcTime` must be ≥ `maxAge` or entries are discarded early. Pass `buster: buildHash` to invalidate on deploy. Max `gcTime` is about 24 days (setTimeout limit) — [persistQueryClient](https://github.com/TanStack/query/blob/main/docs/framework/react/plugins/persistQueryClient.md)

**SWR 2.5**
- Defaults: `revalidateIfStale = true`, `revalidateOnFocus = true`, `revalidateOnReconnect = true`, `refreshInterval = 0`, `dedupingInterval = 2000` ms, `focusThrottleInterval = 5000`, `keepPreviousData = false`, `strictServerPrefetchWarning = false` — [SWR API](https://github.com/vercel/swr-site/blob/main/content/docs/api.mdx)
- Cache provider: a global `Map` by default. Use `<SWRConfig value={{ provider: () => new Map() }}>`, defined high in the tree or outside render. Nested hooks use the nearest provider — [SWR cache](https://github.com/vercel/swr-site/blob/main/content/docs/advanced/cache.mdx)
- Mutation: `mutate(key)` without data revalidates. `mutate(key, data, { optimisticData, revalidate = true, populateCache = true, rollbackOnError })`. A function key acts as a filter. `useSWRMutation` is for remote mutations — [SWR mutation](https://github.com/vercel/swr-site/blob/main/content/docs/mutation.mdx)
- RSC: in a Server Component layout, `const cacheData = { ...preload('/api/user', fetchUser) }` then `<SWRConfig value={{ cacheData }}>`. Promises cross the client boundary and resolve during SSR — [SWR with Next.js](https://github.com/vercel/swr-site/blob/main/content/docs/with-nextjs.mdx)

**Apollo Client 4.3**
- The default fetch policy is `cache-first`. Others: `cache-only`, `cache-and-network`, `network-only`, `no-cache`, `standby`. `nextFetchPolicy` (including `defaultOptions.watchQuery.nextFetchPolicy`) governs later executions — [Apollo queries](https://github.com/apollographql/apollo-client/blob/main/docs/source/data/queries.mdx)
- The normalized `InMemoryCache` uses `typePolicies` (`keyFields`, field `merge`), `possibleTypes` and `dataIdFromObject` — [Cache configuration](https://github.com/apollographql/apollo-client/blob/main/docs/source/caching/cache-configuration.mdx). Eviction: `cache.evict({ id })` or `cache.evict({ id, fieldName })`, then `cache.gc()` (`{ resetResultCache: true }` frees memory). `cache.retain(id)` and `release` exist. `cache.modify` is used in mutation `update(cache)` — [Garbage collection](https://github.com/apollographql/apollo-client/blob/main/docs/source/caching/garbage-collection.mdx); [Cache interaction](https://github.com/apollographql/apollo-client/blob/main/docs/source/caching/cache-interaction.mdx)
- 4.x migration: "`notifyOnNetworkStatusChange` option now defaults to `true`" (more loading states). `canonizeResults` removed. New requirements apply to custom cache implementations — [Apollo Client 4 migration](https://github.com/apollographql/apollo-client/blob/main/docs/source/migrating/apollo-client-4-migration.mdx)

**Relay 21**
- Fetch policies: `store-or-network` (**default**), `store-and-network`, `network-only`, `store-only` — [Fetch policies](https://github.com/facebook/relay/blob/main/website/docs/guided-tour/reusing-cached-data/fetch-policies.md)
- GC deletes data not referenced by mounted components. `retain()` prevents collection. Store options are `gcScheduler` and `gcReleaseBufferSize` (`new Store(source, { gcReleaseBufferSize: 10 })`) — [Presence of data](https://github.com/facebook/relay/blob/main/website/docs/guided-tour/reusing-cached-data/presence-of-data.mdx)

**urql 5 / Graphcache 9**
- The default document cache uses `cache-first`; policies are `cache-first`, `cache-and-network`, `network-only`, `cache-only`. It invalidates by `__typename` seen in mutation results. Empty lists hide their typename, so use `additionalTypenames` or switch to Graphcache — [Document caching](https://github.com/urql-graphql/urql/blob/main/docs/basics/document-caching.md)
- Graphcache: `cacheExchange({ keys, resolvers, updates, optimistic })` for normalized caching — [Graphcache normalized caching](https://github.com/urql-graphql/urql/blob/main/docs/graphcache/normalized-caching.md)

**RTK Query (RTK 2.13)**
- Subscriptions are ref-counted. Unused data is removed after **60 seconds** by default (`keepUnusedDataFor`, global or per endpoint). Use `refetchOnMountOrArgChange: boolean | seconds`. `refetchOnFocus` and `refetchOnReconnect` need `setupListeners(store.dispatch)` — [RTKQ cache behavior](https://github.com/reduxjs/redux-toolkit/blob/master/docs/rtk-query/usage/cache-behavior.mdx)
- Tags: `tagTypes: ['Post','User']`, `providesTags: (result) => [...result.map(({id}) => ({ type: 'Post', id })), { type: 'Post', id: 'LIST' }]`, and `invalidatesTags` on mutations — [Automated re-fetching](https://github.com/reduxjs/redux-toolkit/blob/master/docs/rtk-query/usage/automated-refetching.mdx)

### Inferences
- Recommended defaults for the skill:
  - TanStack: `staleTime` 30–60s for most lists, `Infinity` for reference data, `'static'` for boot-time config; `gcTime` ≥ persister `maxAge`; always set `buster` to the build ID.
  - SWR: leave defaults, but raise `dedupingInterval` for expensive endpoints, and set `revalidateOnFocus: false` for heavy dashboards.
  - Apollo: `cache-and-network` for feeds, `cache-first` for entities, `keyFields` for non-`id` types.
  - RTK: `keepUnusedDataFor` 300 for tab-switching UIs.
- **Server and client double caching.** When a framework already caches (Next `use cache`, Nuxt payload, SvelteKit inlined fetch), set the client lib's initial `staleTime` above 0 to avoid an immediate refetch after hydration. TanStack's SSR guide makes this point explicitly.
- Persisted client caches must be scoped per user (include the user ID in the storage key or clear on logout) to avoid cross-account leaks on shared devices. This is general good practice, not sourced.

### Gaps
- React `use()` caching semantics (promise identity must be stable or cached) and React 19.3 changes were not sourced this session.
- RTK Query persistence (`extractRehydrationInfo`) and Apollo `apollo3-cache-persist` compatibility with Apollo 4 were not verified.
- urql v5 breaking changes (5.0 release notes) were not read.

---

## Q8. Hosting platform interactions: Vercel, Netlify, Cloudflare, AWS (OpenNext/SST), self-hosted Node/Docker

### Takeaway
Framework caches only become globally effective when the platform supplies **durable shared storage + tag purge**. Vercel and Netlify do this natively for Next.js ISR and tags, and for Nuxt `isr`, SvelteKit `isr` and Astro CDN providers. Cloudflare and AWS do it through **OpenNext** (R2/KV + D1/Durable Objects tag cache + DO queue + cache purge on Cloudflare; S3 + DynamoDB + SQS + CloudFront invalidation on AWS). Self-hosted Node/Docker is per-instance (filesystem plus memory) unless you configure a shared handler and purge your CDN.

### Cited Findings
- **Vercel CDN headers.** `Cache-Control` (browser), `CDN-Cache-Control` (downstream CDNs) and `Vercel-CDN-Cache-Control` (Vercel only, "not forwarded downstream") can all be set on the same response to target each layer. For external rewrites, projects created before 2026-04-06 must opt in to caching via `x-vercel-enable-rewrite-caching: 1` — [Vercel CDN cache (via Vercel doc search)](https://vercel.com/docs/caching/cdn-cache); [Vercel rewrites](https://vercel.com/docs/rewrites)
- **Vercel + Next.** `revalidateTag` / `revalidatePath` / `updateTag` purge or invalidate Vercel's CDN and data caches directly. `'use cache: remote'` uses Vercel Runtime Cache — [Vercel purge](https://vercel.com/docs/caching/cdn-cache/purge); [Vercel Runtime Cache](https://vercel.com/docs/runtime-cache)
- **Netlify + Next.** `@netlify/plugin-nextjs` (v5) "uses fine-grained caching on Netlify to support the Next.js Full Route Cache and Data Cache… static page responses are automatically cached at the edge and can be revalidated by path or tag" — [OpenNext Netlify page](https://github.com/opennextjs/docs/blob/main/pages/netlify/index.mdx)
- **Cloudflare + Next (`@opennextjs/cloudflare` 1.20).**
  - "All minor and patch versions of Next.js 16 and the latest minors of Next.js 14 and 15 are supported."
  - Composable caching (`'use cache'`) is supported (checked in its feature list).
  - Recommended small-site setup: `incrementalCache: r2IncrementalCache`, `queue: doQueue`, `tagCache: d1NextTagCache`, `enableCacheInterception: true`.
  - Large sites: `withRegionalCache(r2IncrementalCache, …)` + `doShardedTagCache({ regionalCache: true, shardReplication })` + `cachePurge: purgeCache({ type: 'direct' })`.
  - Workers KV is eventually consistent, so updates can take up to 60s. A Workers Static Assets incremental cache is read-only (no revalidation).
  - "The worker doesn't run **in front** of static assets, so the `headers` option of `next.config.ts` doesn't" apply to them.
  — [OpenNext Cloudflare caching](https://github.com/opennextjs/docs/blob/main/pages/cloudflare/caching.mdx); [OpenNext Cloudflare index](https://github.com/opennextjs/docs/blob/main/pages/cloudflare/index.mdx)
  ```ts
  // open-next.config.ts (Cloudflare)
  import { defineCloudflareConfig } from '@opennextjs/cloudflare'
  import r2IncrementalCache from '@opennextjs/cloudflare/overrides/incremental-cache/r2-incremental-cache'
  import d1NextTagCache from '@opennextjs/cloudflare/overrides/tag-cache/d1-next-tag-cache'
  import doQueue from '@opennextjs/cloudflare/overrides/queue/do-queue'
  export default defineCloudflareConfig({ incrementalCache: r2IncrementalCache, queue: doQueue, tagCache: d1NextTagCache, enableCacheInterception: true })
  ```
  (The import paths for r2 and d1 are inferred from the documented `overrides/...` pattern; only the doQueue, regional-cache, sharded-tag-cache and cache-purge paths were seen verbatim.)
- **AWS + Next (`@opennextjs/aws` 4.1).**
  - The default incremental cache is **S3** (`s3`, `s3-lite`, `fs-dev`, `multi-tier-ddb-s3`). The default tag cache is **DynamoDB** (PK `path`, SK `tag`). The revalidation queue is SQS.
  - Plain `next start` "does not work in a serverless environment because it tries to do the revalidation in the background."
  - Next's default `stale-while-revalidate` (without a value) "is not the proper syntax".
  - After `res.revalidate` or `revalidateTag`, "it is still necessary to invalidate the CloudFront cache". The docs show a DynamoDB query keyed `${NEXT_BUILD_ID}/${tag}` to find the paths to invalidate. An `automatic_cdn_invalidation` override exists.
  - "OpenNext aims to support all Next.js 15 features."
  — [OpenNext AWS caching internals](https://github.com/opennextjs/docs/blob/main/pages/aws/inner_workings/caching.mdx); [incremental_cache override](https://github.com/opennextjs/docs/blob/main/pages/aws/config/overrides/incremental_cache.mdx); [tag_cache override](https://github.com/opennextjs/docs/blob/main/pages/aws/config/overrides/tag_cache.mdx); [OpenNext AWS index](https://github.com/opennextjs/docs/blob/main/pages/aws/index.mdx)
- **Self-hosted Next.** One instance with persistent disk works automatically. Multiple instances or ephemeral disks need a `cacheHandler` and `cacheHandlers` on shared storage, plus CDN purge. The CDN must respect `s-maxage` / `stale-while-revalidate`, key on `_rsc` and forward `rsc` — [Self-hosting](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/self-hosting.mdx); [CDN caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/cdn-caching.mdx)
- **CDN primitives for Next adapters:**

  | CDN | Edge compute | Key-value / tags | Blob storage | PPR resuming |
  |---|---|---|---|---|
  | Cloudflare | Workers | KV | R2 | yes |
  | Akamai | EdgeWorkers | EdgeKV | — | yes |
  | CloudFront | Lambda@Edge | KeyValueStore | S3 | yes |
  | Fastly | Compute | KV Store | — | WASM |
  | Azure | Functions | Managed Redis | — | yes |
  | GCP | Cloud Run | — | — | yes |

  — [Deploying to platforms](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/deploying-to-platforms.mdx)
- **Nuxt / Nitro.** `isr` uses CDN caching "currently Netlify or Vercel". `swr` with the node-server preset caches full responses in Nitro storage — [Nuxt rendering](https://github.com/nuxt/nuxt/blob/4.x/docs/3.guide/1.concepts/1.rendering.md)
- **Astro.** Adapter cache providers map to `Netlify-CDN-Cache-Control` / `Netlify-Cache-Tag`, `Vercel-CDN-Cache-Control` / `Vercel-Cache-Tag`, and `Cloudflare-CDN-Cache-Control` / `Cache-Tag` + Workers Cache — [Astro caching](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)

### Inferences
- **Platform decision matrix for the skill:**
  - **Vercel/Netlify**: use framework-native APIs (tags and ISR) and trust platform purge.
  - **Cloudflare**: OpenNext with R2 + D1 or sharded-DO tags + cache purge for Next. Astro uses `cacheCloudflare()`; SvelteKit uses `setHeaders` + the `caches` global; Nuxt uses `nitro.storage.cache` on KV.
  - **AWS**: OpenNext (S3/DynamoDB/SQS) + CloudFront invalidation on revalidate.
  - **Docker/k8s**: a Redis `cacheHandler` + `cacheHandlers` for Next, `nitro.storage.cache: redis` for Nuxt, and CDN purge hooks.
- A cross-framework pitfall: "on-demand revalidation works locally but not in production" usually means a CDN in front is still serving its copy until `s-maxage` expires.

### Gaps
- Netlify's own Next.js runtime docs (durable cache, `Netlify-Vary`, cache-tag purge API) and Cloudflare's Workers Cache docs could not be fetched (domains blocked). Rely on the CDN/edge research notes for those details.
- SST-specific (`sst.aws.Nextjs`) defaults and the latest OpenNext AWS support status for Next 16 Cache Components were not confirmed. The AWS docs page still says "all Next.js 15 features".
