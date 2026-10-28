# Caching plan: store

Generated 2026-10-28 · Archetype: ecommerce · Stack: Next.js 16.4.3 (Cache Components), Vercel, Postgres via Prisma
Machine-readable version: `plan.json` (`validate_plan.py`: valid, 0 warnings)

## 1. Summary

- **Biggest risks found:** the CMS webhook has no signature check and uses the one-argument `revalidateTag` (a type error on Next 16); `/checkout` would be prerendered once the app builds.
- **Biggest wins:** product and related-product queries (~40 ms each, 300 ms p95) move into the framework cache, so warm product views make no database queries.
- **Freshness promise:** product edits visible within 60 s of the CMS webhook (stale-while-revalidate: one stale view, then fresh).
- **Decisions needed:** none. Assumed single tenant and a 60 s staleness budget for product data.

## 2. Findings

| # | Severity | Finding | Evidence | Fix (phase) |
|---|---|---|---|---|
| F1 | high | Webhook accepts unsigned requests: anyone can trigger revalidation | `app/api/cms-webhook/route.ts` | HMAC check, 401 otherwise (0) |
| F2 | medium | One-argument `revalidateTag` (deprecated in 16; `next build` fails type-check) | `app/api/cms-webhook/route.ts:4`, `find_cache_primitives.py` | `revalidateTag(tag, 'max')` (0) |
| F3 | medium | Checkout has no request-data read, so it would be prerendered and could be shared-cached | `app/checkout/page.tsx` | `connection()` + `export const instant = false` (0) |
| F4 | medium | Every product view queries the database twice | `lib/catalog.ts` | `'use cache'` + `cacheLife('hours')` + tags (5) |
| F5 | low | `cacheComponents` without `partialPrefetching` (build warning) | `next.config.ts` | `partialPrefetching: true` (5) |

## 3. Route and data classification

| ID | Route / data | Class · audience | Budget S | Browser `Cache-Control` | Shared layer | App cache | Tags | Invalidation → propagation | Step | Owner |
|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `/_next/static/*` | fingerprinted-asset · public | versioned | `public, max-age=31536000, immutable` | CDN | — | — | new URL per build → 0 s | 3 | platform |
| R2 | `/products/[slug]` | public-html-volatile · public | 60 s | Next dynamic default (`private, no-store`): the currency cookie makes the HTML dynamic; Vercel serves the PPR shell from its edge | none | framework (`'use cache'`, `cacheLife('hours')`) | `product:{id}`, `product-slug:{slug}`, `category:{id}` | CMS webhook → `revalidateTag(tag, 'max')` → ~30 s | 5 | storefront |
| R3 | `/cart` | personalized | 0 | `private, no-store` (static shell + streamed cart) | none | — | — | — | 2 | checkout |
| R4 | `/checkout` | sensitive | 0 | `private, no-store` (renders per request, no shell) | none | — | — | — | 1 | checkout |
| R5 | `POST /api/cms-webhook` | mutation | 0 | `no-store` | none | — | — | is the trigger | 0 | storefront |

## 4. Invalidation map

| Event | Keys / tags cleared | Order | Mechanism | Propagation |
|---|---|---|---|---|
| product.updated | `product:{id}`, `category:{id}` | CMS commit → webhook → `revalidateTag(tag, 'max')` → Vercel follows the tag | HMAC-signed webhook | ~30 s |
| product.created | `product-slug:{slug}` (clears a cached "not found") | same | same | ~30 s |

## 5. Stampede and failure handling

Framework single-flight plus stale-while-revalidate on `cacheLife` entries. After `revalidateTag(tag, 'max')`, one request regenerates in the background while others get the stale entry.

## 6. Security checks

- [x] No shared caching of cart, checkout or any cookie/session-dependent HTML (verified: `private, no-store`)
- [x] Webhook authenticated (HMAC), 401 otherwise
- [x] Leak test passes on `/products/*` and `/cart` (`probe_headers.py --cookie-a/--cookie-b`)
- [x] No web cache deception on asset-looking variants (`--deception`)

## 7. Rollout

| Phase | Work | Routes | Rollback |
|---|---|---|---|
| 0 | Webhook signature + two-argument `revalidateTag`; checkout forced dynamic | R4, R5 | revert commit |
| 5 | `'use cache'` on product/related reads; Suspense around cookie reads; `partialPrefetching` | R2, R3 | remove the directives (one commit) |

## 8. Monitoring and verification

| Metric | Target | Source |
|---|---|---|
| p95 TTFB `/products/*` | < 300 ms | Vercel Speed Insights |
| DB queries per warm product view | 0 | Prisma query log |
| Publish-to-fresh latency | p95 ≤ 60 s | synthetic check after webhook |

## 9. Open questions and assumptions

- To make product HTML cacheable at a generic CDN (not only Vercel's PPR shell), move currency into the URL (`/[currency]/products/[slug]`) or format prices client-side.
