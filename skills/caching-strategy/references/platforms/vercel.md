# Vercel

Last reviewed: 2026-10-27 · Applies to: Vercel CDN, ISR/Data Cache, Runtime Cache, Edge Config, image optimization; Next.js, Nuxt, SvelteKit, Astro adapters

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Headers and defaults
- Tags and purge
- Framework integration
- Runtime Cache and Edge Config
- Images
- Status headers
- Version notes
- Verify
- Sources

## When to read this

When the app deploys to Vercel. Framework APIs live in `references/frameworks/*.md`; vendor-neutral CDN concepts in `references/layers/cdn-concepts.md`.

## How to detect

`vercel.json`, a `.vercel/` directory, `@vercel/*` deps (`@vercel/functions`, `@vercel/edge-config`), response headers `x-vercel-cache`, `x-vercel-id`, `server: Vercel`.

## Default recipe

```http
# Route handler / function response that should be cached at the edge
Cache-Control: no-cache                                   # browsers revalidate
Vercel-CDN-Cache-Control: max-age=3600, stale-while-revalidate=86400, stale-if-error=86400
Vercel-Cache-Tag: product:123,all
```

Or in `vercel.json` (full example: `assets/snippets/cdn/vercel.json`):

```json
{
  "headers": [
    { "source": "/api/catalog/(.*)", "headers": [
      { "key": "Vercel-CDN-Cache-Control", "value": "max-age=300, stale-while-revalidate=3600" }
    ]}
  ]
}
```

For Next.js, prefer the framework APIs (`'use cache'`/`cacheLife`/`cacheTag`, segment `revalidate`, `revalidateTag`); Vercel maps them to CDN and data cache behavior.

## Rules and gotchas

1. Dynamic responses aren't cached unless headers opt in. Static assets and prerendered pages are cached automatically.
2. Header precedence: `Vercel-CDN-Cache-Control` (Vercel only, not forwarded) > `CDN-Cache-Control` (Vercel and downstream CDNs) > `Cache-Control`. Use the vendor header for edge TTL so browsers and downstream CDNs keep their own policy.
3. Vercel consumes `stale-while-revalidate` and `stale-if-error` and strips them from the client response. `s-maxage` range: 1 s to 1 year.
4. Tags are case-sensitive here (unlike Cloudflare/Netlify): normalize to lowercase in app code. ≤ 128 tags per cached response, ≤ 256 bytes each, no commas inside a tag.
5. Prefer `invalidateByTag` (serve stale, refresh in background) over `dangerouslyDeleteByTag` (delete, regenerate in the foreground) unless content must disappear now.
6. External rewrites: projects created before 2026-04-06 must opt in with `x-vercel-enable-rewrite-caching: 1` to cache rewrite responses (`0` opts out). Newer projects appear to cache them by default (inferred from the docs; verify for the project).
7. Image optimization bills per variant: bound widths/qualities/formats (see Images).
8. Vercel-hosted Next.js apps were unaffected by several Next.js cache-poisoning CVEs because Vercel's edge keys RSC/HTML variants correctly; moving off Vercel reopens them (see `references/core/security.md`).

## Headers and defaults

| Header | Scope |
|---|---|
| `Cache-Control` | Browser (and Vercel/downstream CDNs if no targeted header) |
| `CDN-Cache-Control` | Vercel + downstream CDNs |
| `Vercel-CDN-Cache-Control` | Vercel only |
| `Vercel-Cache-Tag` | Tags for purge (stripped) |

Example from Vercel docs: `Cache-Control: s-maxage=1, stale-while-revalidate=59` serves stale and updates asynchronously; `max-age=604800, stale-if-error=86400` serves stale when revalidation errors.

## Tags and purge

| API | Effect |
|---|---|
| `invalidateByTag(tags)` / `invalidateBySrcImage(src)` (`@vercel/functions`) | Mark stale; serve stale while refreshing |
| `dangerouslyDeleteByTag(tags)` / `dangerouslyDeleteBySrcImage(src)` | Delete; next request regenerates in the foreground |
| `addCacheTag(tag)` (`@vercel/functions`) | Tag the current response |
| REST `POST /v1/edge-cache/invalidate-by-tags`, `/v1/edge-cache/dangerously-delete-by-tags` | Same from outside |
| CLI `vercel cache invalidate --tag a,b`, `vercel cache dangerously-delete --tag a`, `vercel cache purge --type cdn|data`, `vercel cache invalidate --srcimg /images/hero.png` | Ops |

Next.js 16+ on Vercel: "invalidate (serve stale)" = `revalidateTag(tag, 'max')`; "delete" = `revalidateTag(tag)`, `revalidatePath(path)`, `updateTag(tag)`. Next ≤ 15 has no invalidate in `next/cache`; use `invalidateByTag()` from `@vercel/functions`.

Blob `del()` can take up to a minute to clear from the CDN.

## Framework integration

- Next.js: `revalidateTag`/`revalidatePath`/`updateTag` purge Vercel's CDN and data caches directly; `'use cache: remote'` uses Vercel Runtime Cache. See `references/frameworks/nextjs.md`.
- Nuxt `routeRules` `isr` maps to Vercel's CDN; SvelteKit `config.isr` (adapter-vercel; `expiration` required); Astro `isr` and the experimental `cacheVercel()` provider (sets `Vercel-CDN-Cache-Control` and `Vercel-Cache-Tag`; tag invalidation is soft).
- Astro `isr` without `expiration` ignores app `Cache-Control` headers.

## Runtime Cache and Edge Config

- Runtime Cache (`getCache()` from `@vercel/functions`): `get`/`set(key, value, { ttl, tags })`, max item 2 MB, ≤ 128 tags, regional. Pattern: CDN `s-maxage=60` on the response plus a 1 h regional data cache underneath.
- Edge Config: most reads < 15 ms at P99, often < 1 ms; for frequently read, rarely updated data (flags, redirects, allow-lists). Propagation timing wasn't confirmed.
- Details: `references/layers/serverless-edge-data.md`.

## Images

- Next.js 16: `minimumCacheTTL` default 4 h (was 60 s); effective TTL = max(`minimumCacheTTL`, upstream max-age); default `qualities` `[75]`; `formats` default `['image/webp']` (order matters; AVIF first if enabled).
- Variants = sources × qualities × widths × formats (1 image × 2 formats × 2 qualities × 8 widths = 32 entries). Restrict `deviceSizes`/`imageSizes`/`qualities`.
- Invalidate all variants of a source with `invalidateBySrcImage`.

## Status headers

`x-vercel-cache`: `HIT`, `MISS`, `STALE` (served stale, refreshing), `PRERENDER` (served from a prerendered build output), `REVALIDATED`. Next.js also emits `x-nextjs-cache` (`HIT`/`STALE`/`MISS`/`REVALIDATED`) for ISR.

## Version notes

- 2026-04-06: external rewrite caching default changed for new projects.
- Next.js 16 image defaults (4 h TTL, qualities `[75]`).

<details><summary>Old patterns</summary>

- `unstable_expireTag` (Next ≤ 15) for deletes; single-argument `revalidateTag` in Next 16 (deprecated; behaves as immediate expiry).
- Vercel KV for caching (use Runtime Cache or a Marketplace Redis such as Upstash).

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://app.example.com/products/1 | grep -iE 'x-vercel-cache|age|cache-control|x-nextjs-cache'
vercel cache invalidate --tag product:1    # then re-request: STALE once, then fresh HIT
```

## Sources

- [Vercel CDN cache](https://vercel.com/docs/caching/cdn-cache)
- [Vercel cache-control headers](https://vercel.com/docs/caching/cache-control-headers)
- [Vercel CDN purge](https://vercel.com/docs/caching/cdn-cache/purge)
- [Vercel cache status](https://vercel.com/docs/caching/cache-status)
- [Vercel rewrites](https://vercel.com/docs/rewrites)
- [Vercel Runtime Cache](https://vercel.com/docs/caching/runtime-cache)
- [Vercel Edge Config](https://vercel.com/docs/edge-config)
- [Vercel KB: reduce image optimization costs](https://vercel.com/kb/guide/reduce-image-optimization-costs-on-vercel)
- [Vercel CLI cache](https://vercel.com/docs/cli/cache)
