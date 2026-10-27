# Shopify (Hydrogen and Liquid themes)

Last reviewed: 2026-10-27 · Applies to: Hydrogen on React Router 7 / Oxygen; Storefront API; Liquid Online Store themes

## When to read this

When the storefront is Shopify: a Hydrogen app (custom React storefront on Oxygen or another host) or a Liquid theme.

## How to detect

`package.json` with `@shopify/hydrogen`, `@shopify/remix-oxygen`/`@shopify/hydrogen-react`, `@shopify/cli`; `server.ts`/`app/entry.server.tsx` with `createStorefrontClient`; `.shopify/` or `oxygen` deploy config. Liquid themes: `layout/theme.liquid`, `sections/`, `templates/*.json`, `config/settings_schema.json`.

## Default recipe (Hydrogen)

```ts
import { CacheLong, CacheShort, CacheNone, CacheCustom } from '@shopify/hydrogen'

// Product data: long cache with SWR (subrequest cache, not the browser)
const { product } = await context.storefront.query(PRODUCT_QUERY, {
  variables: { handle },
  cache: CacheLong(),               // max-age=3600, stale-while-revalidate=82800
})

// Inventory-sensitive data
const { product: stock } = await context.storefront.query(STOCK_QUERY, {
  variables: { handle },
  cache: CacheShort(),              // short max-age + SWR
})

// Cart, customer account: never cached
const cart = await context.cart.get()              // uses CacheNone internally

// Third-party API with the same cache
const reviews = await context.withCache.fetch(`https://reviews.example.com/p/${handle}`, {},
  { cacheKey: ['reviews', handle], cacheStrategy: CacheCustom({ maxAge: 300, staleWhileRevalidate: 3600 }),
    shouldCacheResponse: (body) => !body?.errors })
```

Document responses: set `Cache-Control` in route `headers()` exports (React Router conventions, `references/frameworks/react-router-remix.md`) — public only for anonymous pages; `private, no-store` for account, cart and checkout.

## Rules and gotchas

1. Hydrogen cache strategies apply to sub-requests (Storefront API, `withCache`), not to the HTML response. The HTML document's caching is set separately via headers.
2. `CacheNone()` for anything with buyer identity (cart, customer, B2B company location pricing) and for queries with `buyerIdentity`/`country`/`language` context unless the cache key includes them.
3. Markets, currencies and languages change product prices: queries using `@inContext(country:, language:)` produce different results; caching them under one key mixes prices.
4. Don't use `CacheLong` for inventory or price-sensitive flash sales; use `CacheShort` or webhook-driven invalidation of your own caches.
5. Customer Account API and checkout are never cached.
6. The sub-request cache's behavior on non-Oxygen hosts depends on the cache implementation you pass to `createStorefrontClient` (`cache`); verify on your host.

## Liquid themes

The Online Store platform cache for Liquid themes isn't configurable by merchants (unverified detail); you control asset fingerprinting (`asset_url` adds versions) and what JavaScript fetches client-side. Keep personalized bits (cart drawer counts, customer name) in client-side fetches (`/cart.js`, section rendering API) instead of trying to cache-bust pages.

## Version notes

- Hydrogen moved from Remix to React Router 7 (2025). Cache strategy helpers unchanged.

<details><summary>Old patterns</summary>

- Hydrogen v1 (React Server Components) `CacheMinutes`/`CacheHours` helpers.
- `@shopify/remix-oxygen` loaders on Remix v2.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://shop.example.com/products/x | grep -iE 'cache-control|age|oxygen|x-cache'
curl -s -o /dev/null -D - https://shop.example.com/cart | grep -i cache-control   # private/no-store
```

## Sources

- [Hydrogen caching](https://shopify.dev/docs/storefronts/headless/hydrogen/caching)
- [Hydrogen CacheLong API](https://shopify.dev/docs/api/hydrogen/latest/utilities/caching/cachelong)
- [Hydrogen: caching third-party API data](https://shopify.dev/docs/storefronts/headless/hydrogen/caching/third-party)
- [Hydrogen: data loading](https://shopify.dev/docs/storefronts/headless/hydrogen/performance/data-loading)
- [Shopify/hydrogen discussion #2558](https://github.com/Shopify/hydrogen/discussions/2558)
