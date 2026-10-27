# App archetype blueprints

Last reviewed: 2026-10-27 · Applies to: any stack; pair with the framework and platform references

## Contents

- When to read this
- How archetypes differ
- static-docs-marketing
- news-media
- ecommerce
- saas-multitenant
- social-ugc
- realtime-collab
- public-api
- mobile-backend
- internal-tool
- ai-llm-app
- video-media
- Edge personalization pattern
- Sources

## When to read this

After fingerprinting, when you confirm the archetype with the user. `scripts/detect_stack.py` emits `archetype_candidates` with evidence; treat them as guesses. Apps are often a mix (an e-commerce site with a blog): apply each blueprint to the routes it covers.

## How archetypes differ

Four variables set the defaults: share of traffic that is public, staleness budget of the hot data, write rate, and variant count per URL. Published architectures (Shopify storefront: in-memory → node-local Redis full-page cache → query cache; Stack Overflow: L1 in-memory + L2 Redis with pub/sub eviction; Wikimedia: RAM Varnish in front of disk ATS with purge fan-out) all use several tiers, and all needed purge monitoring.

Row identifiers below refer to data classes in `references/core/decision-framework.md`.

## static-docs-marketing

Signals: static site generator, `output: 'export'`, Astro without SSR adapter, docs/marketing content folders, no auth.

| Layer | Blueprint |
|---|---|
| Build | SSG or ISR; fingerprint every asset; persist the framework build cache in CI |
| Browser | Assets `fingerprinted-asset`; HTML `no-cache` + `ETag` |
| CDN | HTML long shared TTL (1 day–1 year) purged on deploy/publish; SWR 1 day; SIE 1 week; strip `utm_*` from the key |
| App | None, or CMS fetch cache with tags |
| Extras | Speculation rules (prefetch/prerender), keep pages bfcache-eligible |
| KPIs | HTML cacheable hit ratio > 95%, TTFB p75 ≤ 0.8 s |

## news-media

Signals: CMS (WordPress, Drupal, headless), article/section models, high read spikes.

| Layer | Blueprint |
|---|---|
| Browser | HTML `no-cache`; assets immutable; images long |
| CDN | Articles: hours–days + tag purge (tags: `article:{id}`, `section:{slug}`, `author:{id}`, `all`). Fronts: `max-age=30–60, stale-while-revalidate=300+`, SIE long. Origin shield and request collapsing for spikes |
| App | Fragment cache for heavy modules (most-read, related) with short TTLs; Russian-doll keys `article:{id}:v{updated_at}` |
| Data | Read replicas; Redis sorted sets for most-read counters |
| Breaking news | Publish → purge or soft-purge front, section and article within seconds; keep SWR so purges don't stampede; pre-warm the front |
| Paywall | Public HTML stays public; entitlement/metering client-side or at the edge with cookie-free keys. A public HIT never contains user state |
| KPIs | Purge-to-visible < 30 s (set a target and probe it), front hit ratio, origin RPS during spikes |

## ecommerce

Signals: Shopify/Hydrogen, Magento, Medusa, Saleor, product/cart/order models, payment SDKs.

| Data | Blueprint |
|---|---|
| Assets, product images | Immutable; image CDN with format/width variants on a normalized `Accept` |
| Category / listing pages | Shared 60–300 s + SWR; tags per category and product; allow-listed, sorted facets; bypass deep filter combinations if hit ratio is low |
| Product detail copy | Shared hours + tag purge on product update |
| Price | Short TTL (≤ 30–60 s) or event purge for display; recompute at cart/checkout from the source of truth |
| Stock | Short TTL or event-driven display value; authoritative check at add-to-cart and checkout, never from cache |
| Personalization (recommendations, geo pricing, header) | Islands via client fetch or `private` endpoints; geo price as a country key dimension at the CDN, never `Vary: Cookie` |
| Cart | `private, no-cache` |
| Checkout, payment, account | `no-store` |
| Search | Cache normalized head queries briefly; cache facet counts |
| Flash sales | Pre-warm listing/product pages; SWR + collapsing; edge waiting room; stock decrement with atomic Redis `DECR`/Lua reconciled to the DB; keep price and stock out of long-TTL HTML |

## saas-multitenant

Signals: `tenant`/`organization_id`/`account_id` in models, auth libraries, dashboards.

| Layer | Blueprint |
|---|---|
| Browser | Assets immutable; HTML shell `no-cache`; API `private, no-cache` + `ETag` (304s are cheap); client query cache `staleTime` 30–60 s |
| CDN | Assets and the public marketing site only; app and API bypass |
| App | Every key prefixed `t:{tenant}:`; never build a key without the tenant ID; per-tenant config/permission cache with TTL ≤ acceptable revocation delay plus invalidate on change; precomputed aggregates or materialized views for reports; L1 for global reference data |
| Isolation | Separate Redis DB/cluster or ACL key prefixes for regulated tenants; encrypt per tenant if required |
| Consistency | Read-your-writes for the editor (bypass for N seconds after write, or write-through) |

## social-ugc

| Layer | Blueprint |
|---|---|
| Objects (posts, profiles) | Object cache by ID + version; public pages at the CDN with short TTL + SWR |
| Feeds | Precomputed per-user timelines in Redis lists/sorted sets (fan-out on write; fan-out on read for very large accounts); feed endpoints `private` |
| Counters | Redis `INCR` with periodic flush; tolerate staleness |
| Media | Content-addressed IDs + image CDN |
| Moderation | Takedown purge pipeline across CDN and object caches; measure purge latency |

## realtime-collab

Signals: socket.io, ws, Yjs, Liveblocks, Pusher, Ably, Phoenix channels.

- HTTP-cache only assets and the bootstrap snapshot (`GET` with `ETag`, `private`).
- Live state in memory on servers sharded by document/room; snapshots + op log in storage; cache snapshots to speed joins.
- Presence in Redis keys with TTL. Live endpoints `no-store`; no CDN caching.

## public-api

| Layer | Blueprint |
|---|---|
| HTTP | `ETag` + `Last-Modified`; honor `If-None-Match` → 304. Public resources: `public, max-age` + CDN-targeted TTL + SWR. Authenticated: `private`. `Vary` only on negotiation headers |
| URLs | Version immutable representations in the URL |
| GraphQL | Persisted queries over GET; response `Cache-Control` from the minimum field max-age; see `references/layers/api-graphql-rpc.md` |
| Server | Request-scoped DataLoader; entity caches; Redis rate-limit counters |
| Docs | Document caching semantics in the API reference |

## mobile-backend

- Clients cache whatever headers allow (iOS `URLCache`, OkHttp). Send validators so 304s save cellular data.
- Old binaries live for months: TTLs come from the server, never hard-coded in the app; persisted client caches carry a version buster.
- Config/feature flags as CDN-served JSON with short TTL. Image CDN with device-appropriate variants.
- See `references/layers/mobile-native.md`.

## internal-tool

- Low traffic, high cost of wrong data. Default `private, no-cache`; `no-store` for sensitive admin data.
- Fix queries first. Cache only expensive reference lookups and reports server-side. A client query cache is often enough.

## ai-llm-app

- Order: provider prompt (prefix) caching → exact-match response cache → embedding cache keyed by content + model → retrieval-result cache → tool/API result caches → semantic cache only for public, non-personalized Q&A with a strict threshold.
- Streamed and user-specific responses are `private`/`no-store`. Track cached-token share and cost per request.
- See `references/layers/ai-llm.md`.

## video-media

- VOD segments and init files immutable with long TTL behind an origin shield/tiered cache.
- Live manifests: TTL ≈ half a segment duration (1–2 s) with request collapsing; VOD manifests longer.
- Respect the CDN's maximum cacheable object size (over it, Cloudflare reports `BYPASS`). Check range-request behavior.
- Protected content: signed URLs/cookies validated at the edge, with the signature excluded from the cache key.

## Edge personalization pattern

Use when a mostly public page has a small personalized part:

1. Cache a public shell (no `Set-Cookie`, no user data).
2. Fetch the personalized island client-side from a `private` endpoint, or stream it (Next.js PPR / `'use cache: private'`, ESI at the edge).
3. Add only low-cardinality key dimensions at the edge (country, language, device class, A/B bucket), each normalized. Never key on raw cookies.

## Sources

- [Shopify Engineering: Simplify, Batch, and Cache](https://shopify.engineering/simplify-batch-cache-optimized-server-side-storefront-rendering)
- [Shopify Engineering: Shop app caching](https://shopify.engineering/shop-app-custom-caching-solution)
- [Stack Overflow: caching for a multi-tenant architecture](https://stackoverflow.blog/2019/08/06/how-stack-overflow-caches-apps-for-a-multi-tenant-architecture/)
- [Wikimedia Phabricator T133821](https://phabricator.wikimedia.org/T133821)
- [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- [Azure CDN guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/cdn)
- [Next.js caching](https://nextjs.org/docs/app/getting-started/caching)
- [csswizardry: Cache-Control request header](https://csswizardry.com/2025/03/why-do-we-have-a-cache-control-request-header/)
