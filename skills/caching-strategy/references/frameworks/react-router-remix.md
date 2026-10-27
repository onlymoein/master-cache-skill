# React Router (framework mode) and Remix

Last reviewed: 2026-10-27 · Applies to: React Router 8.5 (7.18 still maintained) framework mode; Remix v2 (`@remix-run/*` 2.17, same concepts)

## When to read this

When `react-router` with `@react-router/dev` (or `react-router.config.*`) or `@remix-run/*` is a dependency. Caching is HTTP-first: the route `headers` export, plus DIY client caching in `clientLoader`. There is no built-in server loader cache.

## How to detect

`@react-router/dev` or `react-router.config.ts` = framework mode (`react-router` alone can be data/declarative mode). `@remix-run/react` 2.x = Remix v2. React Router 8 removed the `react-router-dom` package and is ESM-only. `remix@3.x` is a different framework (not covered).

## Default recipe

```tsx
// app/routes/products.$id.tsx
import { data } from 'react-router'
import type { Route } from './+types/products.$id'

export async function loader({ params }: Route.LoaderArgs) {
  const product = await getProduct(params.id)            // your own server cache if needed
  return data(product, {
    headers: { 'Cache-Control': 'public, max-age=0, s-maxage=300, stale-while-revalidate=86400' },
  })
}

// Loader headers are NOT sent automatically; re-emit them here
export function headers({ loaderHeaders, parentHeaders }: Route.HeadersArgs) {
  return {
    'Cache-Control': loaderHeaders.get('Cache-Control') ?? parentHeaders.get('Cache-Control') ?? 'no-store',
  }
}
```

## Rules and gotchas

1. Headers from loaders/actions aren't sent unless the `headers` export returns them. Only the deepest matching route's headers are sent; merge parent headers manually. `Set-Cookie` is the exception (preserved automatically). Default to `no-store` when no route sets a policy.
2. Single-fetch `.data` requests are separate URLs. If a CDN caches documents, make sure `.data` responses carry the same `Cache-Control` and that the CDN key respects v8's trailing-slash-aware `.data` URLs.
3. CVE-2025-43864 / CVE-2025-43865: request headers (`X-React-Router-SPA-Mode`, `X-React-Router-Prerender-Data`) could make an error or altered response cacheable by a CDN. Fixed in 7.5.2; keep React Router patched.
4. Revalidation defaults: framework mode with SSR revalidates active loaders after navigations and successful submissions (not after 4xx/5xx submissions). SPA/data mode revalidates GET navigations only when params/search change. Tune with `shouldRevalidate` (fall back to `defaultShouldRevalidate`).
5. Personalized loaders return `private, no-cache` (or `no-store`), never `s-maxage`.

## Client caching

```tsx
const cache = new Map<string, unknown>()

export async function clientLoader({ request, serverLoader }: Route.ClientLoaderArgs) {
  const key = new URL(request.url).pathname
  if (cache.has(key)) return cache.get(key)
  const result = await serverLoader()
  cache.set(key, result)
  return result
}
clientLoader.hydrate = true as const        // prime the cache on hydration

export async function clientAction({ serverAction }: Route.ClientActionArgs) {
  cache.clear()                             // invalidate on writes
  return serverAction()
}
```

Bound this cache (LRU) and clear it on logout. Pairing `clientLoader` with TanStack Query's `queryClient.ensureQueryData` is a common alternative (`references/frameworks/client-data-caches.md`).

## SPA mode and prerendering

- `ssr: false` in `react-router.config.ts`: root route rendered at build time to `index.html`; data via `clientLoader`/`clientAction`. Serve `index.html` `no-cache`, hashed assets `immutable`.
- `prerender: true | string[] | async ({ getStaticPaths }) => [...]` works with `ssr: true` or `false`; prerendered HTML can get long CDN TTLs with purge on deploy.

## Version notes

- v8: `react-router-dom` removed; ESM-only; Node ≥ 22.22; middleware always on; trailing-slash-aware data URLs by default; raw request passed to loaders (use the normalized `url`). v8.3 adds RSC metadata so routes with `clientLoader` can skip server requests.

<details><summary>Old patterns</summary>

- Remix v1/v2 `json()` helper with headers (use `data()` in React Router 7+).
- `react-router-dom` imports (removed in v8).

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/products/1 | grep -iE 'cache-control|age|cache-status'
curl -s -o /dev/null -D - 'https://example.com/products/1.data' | grep -i cache-control      # matches the document policy
curl -s -o /dev/null -D - -H 'X-React-Router-SPA-Mode: yes' https://example.com/ | grep -iE 'cache-control|status'
```

## Sources

- [React Router: HTTP headers](https://reactrouter.com/how-to/headers)
- [React Router: client data](https://reactrouter.com/how-to/client-data)
- [React Router: revalidation](https://reactrouter.com/how-to/optimize-revalidation)
- [React Router: SPA mode](https://reactrouter.com/how-to/spa)
- [React Router: pre-rendering](https://reactrouter.com/how-to/pre-rendering)
- [React Router CHANGELOG](https://github.com/remix-run/react-router/blob/main/packages/react-router/CHANGELOG.md)
- [Vercel: CVE-2025-43864 protection](https://vercel.com/changelog/protection-against-react-router-and-remix-vulnerabilities-cve-2025-43864)
