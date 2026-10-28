# Reference solution: next16-vercel-store (eval 1)

What a good run of the skill produces for `evals/fixtures/next16-vercel-store`, built and checked against real Next.js 16.4.3. Use it to calibrate graders. It is not the only acceptable answer.

Files here replace the fixture's files of the same path: `plan.json`, `caching-plan.md`, `next.config.ts`, `lib/catalog.ts`, `app/products/[slug]/page.tsx`, `app/cart/page.tsx`, `app/checkout/page.tsx` and `app/api/cms-webhook/route.ts`.

## How it was verified (2026-10-28)

The fixture was copied out of the repo. A root layout, a tsconfig with the `@/*` alias, a fake in-memory database that counts queries, a cookie-reading `auth()` and a test-only edit route were added so it could run. Then:

| Check | Result |
|---|---|
| `next build` on the original fixture | Fails type-check: `revalidateTag` "Expected 2 arguments, but got 1" |
| `next build` with checkout reading `connection()` at the top level | Fails: "blocking-prerender-dynamic"; fixed with `export const instant = false` |
| `next build` with this solution | Passes; products and cart are PPR (◐), checkout is dynamic (ƒ) |
| `scripts/validate_plan.py plan.json` | Valid, 0 warnings |
| `/products/*`, `/cart`, `/checkout` headers | `private, no-cache, no-store, max-age=0, must-revalidate` (Next's dynamic default) |
| `/_next/static/*` | `public, max-age=31536000, immutable` |
| Webhook with a bad signature | 401 |
| DB queries for a product view | 2 cold, 0 warm |
| Edit product in DB, then view | Still the cached name (no invalidation yet) |
| Signed webhook, then two views | First view stale (regenerating), second fresh: `revalidateTag(tag, 'max')` = stale-while-revalidate |
| Unknown slug, three views | 1 query: the "not found" result is cached (hence the `product-slug:{slug}` tag) |
| `probe_headers.py` (leak test with two sessions, deception probes) | No leak, no deception, no findings |
