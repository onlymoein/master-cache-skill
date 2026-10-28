# CDN and edge caching concepts

Last reviewed: 2026-10-27 · Applies to: any CDN; vendor specifics in `references/platforms/*.md`

## Contents

- When to read this
- Default recipe
- Rules and gotchas
- Defaults differ by vendor
- Cache key design
- Purge and invalidation
- Tiering, collapsing and stale serving
- Edge personalization
- Images and media variants
- Authenticated content at the edge
- Cost and hit ratio
- Version notes
- Verify
- Sources

## When to read this

For any app behind (or that should be behind) a CDN or edge platform. Read the vendor file for the detected CDN too: defaults diverge so much that header advice is wrong without knowing the vendor.

## Default recipe

Origin sends explicit headers on every response; the CDN honors origin headers; rules only add bypasses and key normalization.

```http
# Public HTML or public API (CDN caches, browser revalidates)
Cache-Control: no-cache
CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400
ETag: "<content hash>"
Cache-Tag: page:home,section:news,all          # vendor tag header; see the platform file

# Personalized
Cache-Control: private, no-cache

# Hashed assets
Cache-Control: public, max-age=31536000, immutable
```

CDN configuration:

1. Bypass the cache when a session/auth cookie or `Authorization` is present, and for `/account`, `/checkout`, `/api/private/*`-style paths.
2. Allow-list query params in the key; drop `utm_*`, `gclid`, `fbclid`; sort params if order doesn't matter.
3. Enable the shield tier and request collapsing.
4. Purge by tag on content change; prefer soft purge.

## Rules and gotchas

1. Ask "which CDN?" before giving header advice. Cloudflare doesn't cache HTML at all by default; Azure Front Door caches responses without directives for 1–3 days.
2. Any "cache everything"/override mode (Cloudflare Edge TTL "ignore origin", Google `FORCE_CACHE_ALL`, CloudFront policies with `MinTTL > 0`, Akamai TTL rules) can cache `private`/`no-store` responses. Pair every override with an explicit bypass for authenticated paths and cookies.
3. Origin headers are the primary control. CDN-side protections (deception armor, cookie stripping) are backups.
4. Strip `Set-Cookie` at the origin for cacheable responses; don't rely on the CDN to strip it.
5. Never put raw session IDs or bearer tokens in a cache key. If per-user edge caching is truly needed, key on a stable user ID.
6. Keep at most 50 lowercase tags per response; it fits every vendor's limit (CloudFront stores 50 per object).
7. Order of operations on a change: commit the database, purge the inner layer (app cache, origin proxy), then the CDN. Purging first lets the next request re-cache the old version.
8. Soft purge by default; hard purge only for legal takedowns, leaked data or wrong-content incidents.
9. CMS webhook purges must batch and debounce (Cloudflare Free: 5 tag-purge requests per minute, 100 tags each; Netlify: each tag twice per 5 s).
10. Request collapsing means one origin fetch per key; responses that won't be cacheable must be marked uncacheable, or waiters queue behind a fetch whose result is thrown away.
11. With a tag-purging CDN in front, keep any origin proxy TTL at 1–10 s.

## Defaults differ by vendor

| Vendor | HTML/dynamic cached by default? | Honors origin headers? | CDN-only header | Tag header | Soft purge |
|---|---|---|---|---|---|
| Cloudflare | No (extension list only) | Yes (Origin Cache Control) | `Cloudflare-CDN-Cache-Control` (stripped) or `CDN-Cache-Control` | `Cache-Tag` | `invalidate_cache` |
| Vercel | No (headers must opt in) | Yes | `Vercel-CDN-Cache-Control` | `Vercel-Cache-Tag` | `invalidateByTag` |
| Netlify | No for functions/proxies | Yes | `Netlify-CDN-Cache-Control` | `Netlify-Cache-Tag` | Purge only |
| Fastly | Caches any valid response, including errors | Yes; `Surrogate-Control` > `s-maxage` > `max-age` > `Expires` | `Surrogate-Control` | `Surrogate-Key` | `Fastly-Soft-Purge: 1` |
| CloudFront | Per cache policy TTLs | Within policy min/max TTL | `s-maxage` + policy | Opt-in `CacheTagConfig` (2026) | — |
| Akamai | Per property rules | Only if the Caching behavior honors origin | `s-maxage` (when honored) | `Edge-Cache-Tag` (verify) | Invalidate vs delete |
| Azure Front Door | Yes, 1–3 days without directives | Yes ("honor origin") | — | — | — |
| Google Cloud CDN | `CACHE_ALL_STATIC` default (no HTML) | `USE_ORIGIN_HEADERS` mode | — | — | — |
| bunny.net | Per pull zone | Configurable | — | `CDN-Tag` | — |
| Fly.io | No HTTP cache at all | — | — | — | — |

## Cache key design

- Default key: scheme + host + path + full query string. Every extra dimension multiplies variants.
- Query strings: allow-list meaningful params; strip tracking params; sort when order doesn't matter (sorting can break order-dependent endpoints).
- Headers: only real negotiation headers, normalized (`Accept-Language` → a few languages; image `Accept` → avif/webp/original). Never raw `User-Agent`; use a device class (2–3 values) if needed.
- Cookies: never the whole `Cookie` header. If a variant is needed (A/B bucket), key on that one small cookie, or move the bucket into the URL path (works on every CDN).
- Geography: group countries; prefer locale in the URL over `Accept-Language` variance.
- Host: include it when one origin serves several tenants or domains.
- If you purge by URL on a CDN whose key includes headers, the purge must include those header values.

## Purge and invalidation

| Type | Use when |
|---|---|
| Tag / surrogate key (soft) | Default for content changes: one entity change fans out to many URLs |
| URL | One-offs |
| Prefix / hostname | Sections, tenants, emergencies |
| Everything | Last resort; origin spike. Fastly's purge-all can't be soft, so tag everything with `all` and soft-purge that |
| Content-hashed URLs | Assets: no purge needed |

Vendor limits that bound a tag scheme: CloudFront 50 tags per object, each tag billed as one invalidation path; Vercel 128 per response, case-sensitive; Netlify 500 per response; Cloudflare about 1,000 (16 KB header); Fastly 16 KB header with overflow silently dropped. Normalize tags to lowercase; hash long IDs if you might switch CDNs.

## Tiering, collapsing and stale serving

- Enable the shield tier: Cloudflare Smart Tiered Cache (free, all plans), CloudFront Origin Shield, Fastly shielding, Akamai Tiered Distribution, bunny Origin Shield. Two stacked CDNs means two shield layers; use vendor-specific headers per layer to avoid conflicting TTLs.
- Collapsing is automatic on Cloudflare zone cache, Cloudflare Workers Caching, Fastly, Varnish, nginx (`proxy_cache_lock`); opt-in on Google Cloud CDN (`requestCoalescing`); not on the Cloudflare Workers Cache API or Netlify Cache API (implement your own lock for expensive misses).
- Stale serving: send SWR and SIE in the CDN-targeted header. On Cloudflare don't combine them with `s-maxage`/`must-revalidate`/`no-cache` in the same header.
- Persistent tiers (Cloudflare Cache Reserve, Netlify durable cache, bunny Perma-Cache) protect long-tail objects from LRU eviction; each has purge caveats (see platform files).

## Edge personalization

- Cache an anonymous shell keyed only on URL (+ a bucketed A/B cookie if needed), then personalize client-side or with an edge function on top of the cached response (Cloudflare HTMLRewriter, Vercel/Netlify edge middleware).
- ESI is a Fastly/Akamai/Varnish feature (Fastly VCL ESI: `include`/`comment`/`remove`, up to 256 fragments, uncompressed bodies only; Fastly's Compute ESI library adds more).
- Variant dimensions must stay tiny: bucketed cookies, normalized languages, country groups, device class.

## Images and media variants

- Variants = sources × widths × qualities × formats. Bound widths to a fixed set (≈ 8), qualities to 1–2, formats to avif/webp/original.
- Never key on raw `Accept`; use the vendor's format negotiation or normalize to 3 values before lookup.
- Content-hash or version source URLs so source changes don't need purges. Put originals, not variants, in persistent tiers.
- Next.js 16 image optimization: `minimumCacheTTL` default 4 h, `qualities` default `[75]`. Vercel and Cloudflare can invalidate all variants of a source at once.
- Respect the CDN's maximum cacheable object size (Cloudflare 512 MB Free/Pro/Business, 5 GB Enterprise default).

## Authenticated content at the edge

- Default: authenticated responses are `private` or `no-store` and bypass the CDN.
- Many users, identical data: authenticate at the edge, strip `Authorization`, and fetch a cached shared response (Cloudflare Workers Caching gateway pattern), or use signed URLs/cookies (CloudFront) so the credential is verified at the edge but isn't in the key.
- GraphQL/POST APIs: move cacheable queries to GET with persisted-query hashes.

## Cost and hit ratio

- Measure hit ratio over cacheable requests (exclude bypass), and byte hit ratio separately: large files dominate egress.
- Working targets (judgment, not vendor benchmarks): hashed assets ≥ 95–99%; anonymous HTML with SWR 80–95%; public APIs 50–90% depending on key cardinality.
- Invalidation is free (rate-limited) on Cloudflare, Vercel, Netlify and Fastly. CloudFront bills beyond 1,000 paths/month; a wildcard or a tag counts as one path.
- Caching in front of functions (Workers Caching, Netlify `durable`, Vercel CDN) avoids invocations and CPU billing.

## Version notes

- 2025–26: Cloudflare Cache Rules replaced Page Rules; Cache Response Rules, async SWR, Vary in Cache Rules, `invalidate_cache`; Vercel `invalidateByTag`/`dangerouslyDeleteByTag`; CloudFront tag invalidation (April 2026); Akamai fast-invalidate behavior deprecated. Details in platform files.

## Verify

```bash
URL=https://example.com/page
for i in 1 2; do curl -s -o /dev/null -D - "$URL" | grep -iE '^(cache-control|cdn-cache-control|age|cache-status|cf-cache-status|x-cache|x-vercel-cache|x-served-by|set-cookie):'; echo; done
# Second run: HIT and a larger Age. Then with a session cookie: expect BYPASS/MISS and no Age.
curl -s -o /dev/null -D - -H 'Cookie: session=test' "$URL" | grep -iE 'cache-status|cf-cache-status|x-cache|age'
```

Run a purge in staging and time how long until the new content is visible (purge-to-visible).

## Sources

- [RFC 9213 Targeted Cache-Control](https://httpwg.org/specs/rfc9213.html)
- [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior)
- [Vercel CDN cache](https://vercel.com/docs/caching/cdn-cache)
- [Fastly cache control headers](https://www.fastly.com/documentation/guides/full-site-delivery/caching/about-cache-control-headers)
- [CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md)
- [Akamai: learn about caching](https://techdocs.akamai.com/property-mgr/docs/know-caching)
- [Azure Front Door caching](https://learn.microsoft.com/azure/frontdoor/front-door-caching)
- [Google Cloud CDN cache modes](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy)
- [Fly Proxy](https://fly.io/docs/reference/fly-proxy/)
- [Vercel KB: reduce image optimization costs](https://vercel.com/kb/guide/reduce-image-optimization-costs-on-vercel)
