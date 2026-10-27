# Netlify

Last reviewed: 2026-10-27 · Applies to: Netlify CDN, Functions, Edge Functions, durable cache, Cache API, `@netlify/cache`, `@netlify/plugin-nextjs` 5.x

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Headers and variants
- Tags and purge
- Durable cache and Cache API
- Framework integration
- Status headers
- Version notes
- Verify
- Sources

## When to read this

When the app deploys to Netlify. Netlify's caching specifics in this file came from Netlify's own agent guidance rather than a public docs page; confirm details against docs.netlify.com before relying on exact limits.

## How to detect

`netlify.toml`, `_headers`/`_redirects` files, `netlify/functions/` or `netlify/edge-functions/`, `@netlify/*` deps, response headers `x-nf-request-id`, `cache-status: "Netlify Edge"; …`, `server: Netlify`.

## Default recipe

```http
# Function response cached at the edge, shared across nodes via the durable cache
Cache-Control: public, max-age=0, must-revalidate
Netlify-CDN-Cache-Control: public, durable, s-maxage=3600, stale-while-revalidate=86400
Netlify-Cache-Tag: product:123,all
Netlify-Vary: query=page|sort
```

`netlify.toml` example: `assets/snippets/cdn/netlify.toml`.

## Rules and gotchas

1. Dynamic responses (Functions, Edge Functions, proxies) aren't cached unless headers opt in. Only GET is cached.
2. Header precedence: `Netlify-CDN-Cache-Control` (Netlify only) > `CDN-Cache-Control` > `Cache-Control` (the latter two pass downstream).
3. Basic auth on any page disables caching for the entire site.
4. Static assets are fresh up to a year at the edge and a shorter `max-age` is ignored; they change only on deploy or purge. Atomic deploys invalidate automatically.
5. Without `Netlify-Vary: query=…`, the full query string is the key and `utm_*`/`fbclid` fragment the cache.
6. A URL must return the same `Netlify-Vary` on every response; the first cached response's instructions win.
7. Each request may hit a different cache instance: without `durable` or steady traffic, expect several misses before hits.
8. Never opt sensitive content out of deploy invalidation (`Netlify-Cache-ID`); it could stay publicly cached after a fix.
9. `netlify dev` doesn't emulate the CDN cache; test on a deploy preview.
10. Purge rate limit: each tag (or the site) can be purged twice per 5 seconds; beyond that you get 429s. Debounce webhook purges.

## Headers and variants

Defaults: static `Netlify-CDN-Cache-Control: public, s-maxage=31536000, must-revalidate`; dynamic `Cache-Control: public, max-age=0, must-revalidate`.

`Netlify-Vary` keys on specific parts instead of whole headers:

```http
Netlify-Vary: query=item_id|page, country=es+de|us, cookie=ab_test|is_logged_in, language=en|es+pt, header=Device-Type
```

You can't vary on `Accept*`, `Cache-Control`, `Connection`, `Content-Length`, `Cookie`, `Host`, `If-*`, `Range`, `Referer`, `Upgrade`, `User-Agent` headers directly; use the `cookie=`/`language=`/`country=` forms.

## Tags and purge

- `Netlify-Cache-Tag: tag1,tag2` (wins over `Cache-Tag`, which passes downstream; set both when another CDN in front strips `Cache-Tag`). Case-insensitive, ≤ 1,024 chars per tag, ≤ 500 tags per response.
- Purge from code: `purgeCache({ tags })` from `@netlify/functions` (no args = whole site; options `tags`, `deployAlias`, `domain`).
- Purge API: `POST https://api.netlify.com/api/v1/purge` with `site_id`/`site_slug` and `cache_tags`. Omitting `cache_tags` purges the whole site; an empty list purges nothing.
- No soft purge: purge is a hard purge. Use `stale-while-revalidate` to soften expiry.

## Durable cache and Cache API

- `durable` (in `Netlify-CDN-Cache-Control`, serverless functions only, not Edge Functions): stores responses in a shared durable cache so other edge nodes reuse them instead of invoking the function. Eventually consistent, co-located with the functions region. Next.js runtime ≥ 5.5.0 uses it automatically.
- Cache API (`caches.open/match/put`) inside handlers: ≤ 100 lookups and ≤ 20 insertions/deletions per invocation; per region, not replicated; invalidated on redeploy; can't cache 206, `Vary: *` or non-GET; requires `public`, 2xx and `max-age`/`s-maxage` ≥ 1 s. Deletes are eventually consistent. No request collapsing.
- `@netlify/cache`: `fetchWithCache(url, opts, { ttl, swr, tags, vary, durable })`, `cacheHeaders()`, `getCacheStatus()`, `needsRevalidation()`.

## Framework integration

- Next.js: `@netlify/plugin-nextjs` (v5) supports the Full Route Cache and Data Cache; static page responses are cached at the edge and revalidate by path or tag.
- Nuxt `isr` route rules map to Netlify's CDN; Astro's experimental `cacheNetlify()` sets `Netlify-CDN-Cache-Control` and `Netlify-Cache-Tag` with the durable cache.

## Status headers

RFC 9211 `Cache-Status`, e.g. `"Netlify Edge"; hit`, `"Netlify Edge"; hit; fwd=stale` (SWR), `"Netlify Durable"; fwd=uri-miss; stored=true; ttl=3600`.

## Version notes

- On-demand Builders are legacy; use `durable` + cache headers or framework ISR.
- Next.js runtime 5.5.0+ uses the durable cache automatically.

<details><summary>Old patterns</summary>

- On-demand Builders (`builder()` wrapper) for ISR-like behavior.
- Relying on `Cache-Control` alone for function caching (no shared durable cache).

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://site.netlify.app/api/products | grep -iE 'cache-status|age|cache-control'
curl -X POST https://api.netlify.com/api/v1/purge -H "Authorization: Bearer $NETLIFY_TOKEN" \
  -H 'Content-Type: application/json' -d '{"site_id":"'"$SITE_ID"'","cache_tags":["product:123"]}'
```

## Sources

- [Netlify caching overview](https://docs.netlify.com/platform/caching/)
- [Netlify cache tags and purge](https://docs.netlify.com/platform/caching/#on-demand-invalidation)
- [OpenNext: Netlify](https://github.com/opennextjs/docs/blob/main/pages/netlify/index.mdx)
- [Astro route caching (adapter providers)](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)
- [Nuxt rendering (route rules)](https://github.com/nuxt/nuxt/blob/4.x/docs/3.guide/1.concepts/1.rendering.md)
