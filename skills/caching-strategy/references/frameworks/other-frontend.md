# Other frontends and static site generators

Last reviewed: 2026-10-27 · Applies to: Angular 22 (SSR), Gatsby 5.16, Qwik City 1.x (Qwik Router 2 RC), SolidStart 2.1, TanStack Start/Router 1.x, Vite 8 SPAs, Hugo, Jekyll, Eleventy, Docusaurus, VitePress, MkDocs

## When to read this

When the frontend is one of these. They all follow the universal rule: hashed assets immutable, HTML and manifests revalidate, server responses set explicit headers per route.

## Universal static-asset rule

| Path (typical) | Header |
|---|---|
| Hashed build output (Vite `assets/*-[hash]`, webpack `[contenthash]`, `/_next/static`, `/_nuxt`, SvelteKit `/_app/immutable`, `/_astro`) | `public, max-age=31536000, immutable` |
| `index.html`, other HTML, web manifest, `sw.js`, `page-data` JSON | `no-cache` (or `max-age=0, must-revalidate`) + `ETag` |
| Unhashed `public/` files | `no-cache` or a short `max-age` |

Keep previous builds' hashed assets deployed for weeks (deploy skew; see `references/layers/browser-platform.md`).

## Angular (22, `@angular/ssr`)

- HTTP transfer cache prevents the SSR → hydration double fetch; it is not a runtime cache:

```ts
provideClientHydration(withHttpTransferCacheOptions({
  includeHeaders: ['etag'],
  filter: (req) => !req.url.includes('/api/me'),
  includePostRequests: false,
  includeRequestsWithAuthHeaders: false,   // keep the default
}))
```

- By default it caches GET/HEAD `HttpClient` requests without `Authorization`, `Proxy-Authorization` or `Cookie` and without credentials, and skips responses marked `no-store`/`no-cache`/`private`. No headers are included by default.
- Server routes: `RenderMode.Server | Prerender | Client` with per-route `headers`. Angular prerenders the whole app by default (`outputMode: 'static'` for fully static). SSR fetch backend has a 1 MB response body limit.

## Gatsby (5.16)

HTML and `public/page-data/**` (including `app-data.json`): `public, max-age=0, must-revalidate`. Hashed JS/CSS and `static/`: `public, max-age=31536000, immutable`. Persist `.cache` and `public` between CI builds. Gatsby has had no release since 2026-02; weigh that for new work.

## Qwik City / Qwik Router

```ts
export const onGet: RequestHandler = ({ cacheControl }) => {
  cacheControl({ public: true, maxAge: 0, sMaxAge: 300, staleWhileRevalidate: 3600 })
}
```

Set it in the root layout and override in nested layouts (e.g. dashboards `public: false, maxAge: 0`). Qwik Router 2 (`@qwik.dev/router`) is a release candidate; re-check `cacheControl` changes before using it.

## SolidStart (2.1) and Solid Router

- `query()` caches by name + serialized args; preloaded data reused for 5 s; back/forward reuses entries; request-scoped cache during SSR; unsubscribed client entries can be dropped after 180 s; `revalidate(key)` forces refresh.
- Server-side caching in SolidStart 2 (h3 v2) wasn't covered by this skill's research; set explicit response headers and use your own cache-aside helper.

## TanStack Start and Router

```ts
export const Route = createFileRoute('/blog/$slug')({
  headers: () => ({ 'Cache-Control': 'public, max-age=0, s-maxage=3600, stale-while-revalidate=86400' }),
  loader: ({ params }) => getPost(params.slug),
})
```

- Prerender with `tanstackStart({ prerender: { routes, crawlLinks } })`.
- Router loader cache: `staleTime` 0, `preloadStaleTime` 30 s, `gcTime`/`preloadGcTime` 5 min; `router.invalidate()` reloads active routes. Pair with TanStack Query for data caching (`references/frameworks/client-data-caches.md`).

## Plain Vite / SPA

- `vite build` emits hashed assets; serve `index.html` `no-cache` with an `ETag`, everything under `assets/` immutable.
- SPA fallback routing (all paths → `index.html`) must keep the `no-cache` header on every fallback response.

## Static site generators (Hugo, Jekyll, Eleventy, Docusaurus, VitePress, MkDocs)

- Enable fingerprinting/hashing (Hugo `resources.Fingerprint`, Docusaurus/VitePress hash by default; Jekyll/Eleventy/MkDocs need a pipeline or plugin).
- HTML `no-cache` in browsers; long CDN TTL with purge on deploy (`references/core/archetypes.md`, static-docs-marketing).
- Configure headers on the host (`_headers`, `netlify.toml`, `vercel.json`, `firebase.json`, S3/CloudFront metadata).

## Verify

```bash
curl -sI https://example.com/ | grep -iE 'cache-control|etag'                      # no-cache + ETag
curl -sI https://example.com/assets/index-3f9a1c.js | grep -i cache-control         # immutable
```

## Sources

- [Angular SSR guide](https://angular.dev/guide/ssr)
- [Gatsby caching](https://www.gatsbyjs.com/docs/how-to/previews-deploys-hosting/caching/)
- [Qwik caching](https://qwik.dev/docs/caching/)
- [Solid Router query](https://docs.solidjs.com/solid-router/reference/data-apis/query)
- [TanStack Start ISR](https://tanstack.com/start/latest/docs/framework/react/guide/isr)
- [TanStack Router data loading](https://tanstack.com/router/latest/docs/framework/react/guide/data-loading)
- [Vite build](https://vite.dev/guide/build)
