---
name: caching-strategy
description: Designs, audits and implements caching for a specific website or app across every layer, including HTTP/browser headers (Cache-Control, ETag, Vary), service workers, CDNs and edge (Cloudflare, Vercel, Netlify, Fastly, CloudFront, Akamai), nginx/Varnish, in-process and Redis/Valkey/Memcached caches, database and ORM caches, framework caching (Next.js use cache/ISR, Nuxt, SvelteKit, Astro, Rails, Django, Laravel, Spring, ASP.NET), CMS, REST/GraphQL APIs, mobile clients, LLM prompt and semantic caching, and CI build caches. Detects the stack, classifies every route, and writes a validated caching plan covering invalidation, stampede protection, cache security and verification. Use when the user mentions caching, stale content, purging, CDN or Redis setup, or when pages are slow, TTFB is high, or origin, database or hosting costs are too high, even if they never say "cache". Not for clearing local package-manager caches or explaining CPU caches.
license: MIT
compatibility: Live header probes need network access and user-supplied URLs; every other step runs offline with the Python 3 standard library.
metadata:
  version: "1.1.1"
  last-reviewed: "2026-10-28"
---

# Caching strategy

Produce caching that is correct first and fast second, tailored to the app in front of you: its stack and versions, its routes, its staleness tolerance and its failure modes. Paths below are relative to this skill's directory.

## Rules that hold for the whole task

1. Classify every route or data type with [references/core/decision-framework.md](references/core/decision-framework.md) before proposing any cache. Record the decision step.
2. Never put `public`, `s-maxage`, a CDN TTL or a CDN/proxy/framework shared-cache rule on a response whose body depends on cookies, sessions, `Authorization`, tenant, entitlement or A/B bucket. Use `private` (with `no-cache` + ETag); `no-store` for secrets, payment and auth.
3. Every response, including errors and redirects, gets an explicit `Cache-Control`. Default `no-store`; routes opt in. Platform and CDN defaults differ and change without notice.
4. The cache key must fully determine the response: allow-list query params, normalize, include host/tenant/locale where they change output. Never `Vary: Cookie` or `Vary: User-Agent` on shared caches.
5. Use only APIs that exist in the detected framework version. Read versions from lockfiles; prefer the project's bundled docs (Next.js 16.3+ ships `node_modules/next/dist/docs`).
6. On writes: commit the database first, then delete (not set) cache entries, inner layer before outer (app cache → proxy → CDN). Keep a TTL backstop. Use leases or version-conditional sets where stale-set races matter.
7. Every hot or expensive cache gets single-flight (or request collapsing), TTL jitter and stale-while-revalidate, and the app must keep working when the cache is down.
8. An error is not a miss: never cache 5xx as data, never treat a cache failure as "not found", never delete entries because a backend failed.
9. Purges, flushes, CDN rule changes and cache-store migrations are destructive or outward-facing: write `plan.json`, run `scripts/validate_plan.py`, show the user the change and get approval first.
10. Nothing is done until headers, HIT/`Age` behavior, a conditional GET (304) and a two-session leak test pass on the real path through the CDN.

## Workflow (copy into your response and tick off)

```text
- [ ] 0. Scope: audit + plan, implement a phase, or answer one question? (narrow question → read the matching reference, answer with the output contract, still obey the rules)
- [ ] 1. python scripts/detect_stack.py <repo>      → read every path in "read"; note "read_when"
- [ ] 2. python scripts/find_cache_primitives.py <repo>  → existing caches + warnings (confirm each)
- [ ] 3. Inventory routes/endpoints/data types (method, auth, cookies read, params, sources, writes)
- [ ] 4. If the user gives URLs: python scripts/probe_headers.py <url>... [--cookie-a ... --cookie-b ...] [--deception]
- [ ] 5. Confirm archetype, staleness budgets, tenancy and instance count with the user (one round of questions)
- [ ] 6. Classify each row (decision tree steps 0–9); fill assets/caching-plan.template.md and write plan.json
- [ ] 7. python scripts/validate_plan.py plan.json  → fix until valid
- [ ] 8. Implement phase by phase (safety fixes first), with approval before destructive steps
- [ ] 9. Verify per references/core/observability-testing.md; leave monitoring and rollback in place
```

Ask before assuming when it changes the plan: who may see the response (public vs per user/tenant), the staleness budget per data type, which CDN fronts production, and how many app instances run. Everything else, decide with the defaults in the references and state the assumption.

## Scripts

| Command | Output |
|---|---|
| `python scripts/detect_stack.py <repo>` | Frameworks with versions and config (Next `cacheComponents`, SvelteKit adapter, …), hosting/CDN, proxies, data stores, ORM, CMS, API, mobile, AI, CI, service workers, instance count (k8s, compose, Fly, Render, ECS, serverless), archetype candidates, `read` and `read_when` reference lists |
| `python scripts/find_cache_primitives.py <repo> [--layer L]` | Existing caching code/config with `file:line`, layer, kind; heuristic warnings (one-argument `revalidateTag`, `Vary: Cookie`, `KEYS`, unbounded LRU, module-level DataLoader, …) |
| `python scripts/probe_headers.py <url>... [--cookie-a 'k=v'] [--cookie-b 'k=v'] [--deception]` | Read-only live probe: repeat GETs (MISS→HIT, `Age`), conditional GET, header findings, two-session leak test, web cache deception probes. Cookie values are never printed. Only for URLs the user owns or is authorized to test |
| `python scripts/validate_plan.py plan.json` | `{valid, errors, warnings}`; exit 1 on errors (shared caching of private data, TTL over budget, missing invalidation/owner/verify, bad tags, `Vary: Cookie`, …) |
| `python scripts/size_cache.py --rps R --hit-ratio h --hit-ms A --miss-ms B [--keys K --avg-bytes V]` | Effective latency, origin load, hit ratio needed for a target, memory estimate |

All scripts are Python 3.9+ standard library, print JSON on stdout and accept `--help`.

## Routing table

Read the files `detect_stack.py` lists; this table is the same mapping for manual use. Read only what the stack needs.

| Signal | Read |
|---|---|
| Always | [references/core/decision-framework.md](references/core/decision-framework.md), [references/core/http-semantics.md](references/core/http-semantics.md), [references/core/security.md](references/core/security.md) |
| Confirming the archetype | [references/core/archetypes.md](references/core/archetypes.md) |
| Adding an app cache, CDN purge or tag scheme | [references/core/invalidation-consistency.md](references/core/invalidation-consistency.md), [references/core/stampede-failure.md](references/core/stampede-failure.md) |
| Verification, monitoring, rollout | [references/core/observability-testing.md](references/core/observability-testing.md) |
| Any web app | [references/layers/browser-platform.md](references/layers/browser-platform.md), [references/layers/cdn-concepts.md](references/layers/cdn-concepts.md) |
| Service worker, PWA, Workbox/Serwist | [references/layers/service-workers.md](references/layers/service-workers.md) |
| nginx, Varnish, HAProxy, Caddy, Traefik | [references/layers/reverse-proxies.md](references/layers/reverse-proxies.md) |
| In-process caches (lru-cache, cachetools, Caffeine, Otter, IMemoryCache, Cachex) | [references/layers/in-process.md](references/layers/in-process.md) |
| Redis, Valkey, Memcached, Dragonfly, Solid Cache | [references/layers/distributed-cache.md](references/layers/distributed-cache.md) |
| ORM, database, connection pooling, query caches | [references/layers/database-orm.md](references/layers/database-orm.md) |
| Serverless/edge runtimes and KV stores | [references/layers/serverless-edge-data.md](references/layers/serverless-edge-data.md) |
| REST, GraphQL, gRPC/Connect, tRPC, API gateways | [references/layers/api-graphql-rpc.md](references/layers/api-graphql-rpc.md) |
| iOS, Android, React Native/Expo, Flutter clients | [references/layers/mobile-native.md](references/layers/mobile-native.md) |
| LLM SDKs, RAG, vector stores | [references/layers/ai-llm.md](references/layers/ai-llm.md) |
| Build, CI, Docker layers, DNS/TLS (only when asked) | [references/layers/build-ci-network.md](references/layers/build-ci-network.md) |
| `next` | [references/frameworks/nextjs.md](references/frameworks/nextjs.md) |
| `nuxt`, `nitropack`/`nitro` | [references/frameworks/nuxt-nitro.md](references/frameworks/nuxt-nitro.md) |
| `@sveltejs/kit` | [references/frameworks/sveltekit.md](references/frameworks/sveltekit.md) |
| React Router framework mode, Remix | [references/frameworks/react-router-remix.md](references/frameworks/react-router-remix.md) |
| `astro` | [references/frameworks/astro.md](references/frameworks/astro.md) |
| Angular, Gatsby, Qwik, SolidStart, TanStack Start, Vite SPA, static site generators | [references/frameworks/other-frontend.md](references/frameworks/other-frontend.md) |
| TanStack Query, SWR, Apollo Client, Relay, urql, RTK Query | [references/frameworks/client-data-caches.md](references/frameworks/client-data-caches.md) |
| Rails | [references/frameworks/rails.md](references/frameworks/rails.md) |
| Django | [references/frameworks/django.md](references/frameworks/django.md) |
| Laravel, Symfony, PHP | [references/frameworks/laravel-php.md](references/frameworks/laravel-php.md) |
| Spring Boot, Quarkus, Micronaut, Hibernate | [references/frameworks/spring-jvm.md](references/frameworks/spring-jvm.md) |
| ASP.NET Core | [references/frameworks/aspnet.md](references/frameworks/aspnet.md) |
| Express, Fastify, NestJS, Koa, Hono | [references/frameworks/node-backends.md](references/frameworks/node-backends.md) |
| FastAPI, Flask, Starlette, Litestar | [references/frameworks/python-web.md](references/frameworks/python-web.md) |
| Go | [references/frameworks/go.md](references/frameworks/go.md) |
| Elixir/Phoenix | [references/frameworks/elixir.md](references/frameworks/elixir.md) |
| WordPress, WooCommerce | [references/cms/wordpress.md](references/cms/wordpress.md) |
| Drupal | [references/cms/drupal.md](references/cms/drupal.md) |
| Shopify Hydrogen or Liquid | [references/cms/shopify-hydrogen.md](references/cms/shopify-hydrogen.md) |
| Magento / Adobe Commerce | [references/cms/magento.md](references/cms/magento.md) |
| Sanity, Contentful, Strapi, Payload, other headless CMS | [references/cms/headless-cms.md](references/cms/headless-cms.md) |
| Cloudflare | [references/platforms/cloudflare.md](references/platforms/cloudflare.md) |
| Vercel | [references/platforms/vercel.md](references/platforms/vercel.md) |
| Netlify | [references/platforms/netlify.md](references/platforms/netlify.md) |
| Fastly | [references/platforms/fastly.md](references/platforms/fastly.md) |
| CloudFront, Amplify, OpenNext on AWS | [references/platforms/cloudfront.md](references/platforms/cloudfront.md) |
| Akamai | [references/platforms/akamai.md](references/platforms/akamai.md) |
| Google Cloud CDN/Media CDN, Azure Front Door | [references/platforms/gcp-azure-cdn.md](references/platforms/gcp-azure-cdn.md) |
| Fly, Render, Railway, Heroku, Firebase, GitHub Pages, bunny.net | [references/platforms/other-hosts.md](references/platforms/other-hosts.md) |

No CDN detected: ask what fronts production before choosing shared-cache headers. Mixed stacks or monorepos: run `detect_stack.py` per app directory.

## Gotchas that span layers

- A missing `Cache-Control` is not "uncached": caches apply heuristic freshness to 200, 301, 404 and others.
- `no-cache` means "store but revalidate"; `no-store` means "don't store". Shared caches still collapse requests for `no-cache`/`max-age=0`, so personalized responses need `private`.
- `Set-Cookie` on a public page silently disables caching at most CDNs, or gets cached and replayed at others. Strip cookies from anonymous cacheable responses.
- Browser caches can't be purged: browser TTL ≤ staleness budget unless the URL is versioned.
- Layers stack: worst-case staleness is the sum of tier TTLs plus stale windows when each refills from a stale lower tier.
- Framework revalidation (`revalidateTag`, `revalidatePath`) doesn't purge a CDN you run; "works locally, stale in production" is almost always a CDN copy.
- `immutable` only on fingerprinted URLs. Keep previous builds' assets deployed so old HTML still loads.
- One hot key expiring is a stampede even with jitter; use single-flight, SWR or early refresh.
- In-process caches drift per instance; serverless module scope is an opportunistic L1 only.
- Path confusion (`/account.css`, `/account;x.css`, `%2F`) plus extension-based CDN rules is web cache deception: origins must send `private`/`no-store` for authenticated paths.
- Hit ratio excludes BYPASS/uncacheable requests; measure per path class.
- When a vendor or framework skill is installed (Next.js cache components, Cloudflare, Redis, Vercel), use it for API detail; this skill owns the cross-layer plan and safety rules.

## Glossary

| Term | Meaning |
|---|---|
| shared cache | Any cache serving many users: CDN, edge, reverse proxy, API gateway, framework full-route cache |
| private cache | A cache for one user: browser HTTP cache, mobile client cache |
| app cache | Server-side data cache: in-process L1 and/or distributed L2 (Redis, Valkey, Memcached) |
| staleness budget (S) | Max age of data the business tolerates being served, in seconds |
| cache key | Everything that selects a stored response/value (URL, allowed query params, `Vary` headers, tenant, version) |
| variant | One stored response per distinct cache key for the same URL |
| tag | Label for group invalidation (Cache-Tag, Surrogate-Key, `cacheTag`); lowercase `entity:id` plus `all`, ≤ 50 per response |
| soft purge / hard purge | Mark stale and revalidate / delete outright |
| SWR / SIE | stale-while-revalidate / stale-if-error (500, 502, 503, 504 only) |
| single-flight | Coalescing concurrent misses for one key into one recomputation |
| negative caching | Caching "not found" briefly |
| TTL jitter | Randomizing TTLs (about ±10 %) so keys don't expire together |
| cache-aside | App reads the cache; on a miss loads the source and fills the cache |

App-cache keys: `{app}:{env}:v{schema}:[t:{tenant}:]{entity}:{id}`. Bump `v{schema}` instead of flushing.

## Output contract

For an audit or plan, deliver:

1. **Findings**, safety issues first, each with evidence (`file:line`, probe output) and the fix's phase.
2. **The plan** from [assets/caching-plan.template.md](assets/caching-plan.template.md) plus `plan.json` per [assets/plan.schema.json](assets/plan.schema.json) (complete example: [assets/plan.example.json](assets/plan.example.json)), with `validate_plan.py` passing. Defaults per data class: [assets/policy-defaults.csv](assets/policy-defaults.csv).
3. **Every row** states: route and methods, data class, audience, staleness budget, browser `Cache-Control`, shared layer and exact header, `Vary`/cache key, app-cache mechanism and key, tags, invalidation trigger → mechanism → propagation time, decision step, owner, and a verification command. `no-store` rows stay in the table.
4. **Rollout phases** ordered by risk and ROI (safety first), each with a rollback, plus monitoring targets.
5. **Assumptions and open questions**, explicitly.

For a narrow question, answer with the same fields that apply (mechanism, scope, TTL/freshness, key/`Vary`, invalidation, how to verify) and exact copy-paste headers or code for the detected version.

When implementing, start from the snippets and adapt them to the codebase's conventions:

| Need | Snippet |
|---|---|
| Default `no-store` + per-route policies | [assets/snippets/headers/express-default-headers.js](assets/snippets/headers/express-default-headers.js), [assets/snippets/headers/django_cache_headers_middleware.py](assets/snippets/headers/django_cache_headers_middleware.py), [assets/snippets/headers/rails_cache_headers.rb](assets/snippets/headers/rails_cache_headers.rb), [assets/snippets/headers/nextjs-route-handler-headers.ts](assets/snippets/headers/nextjs-route-handler-headers.ts) |
| CDN config | [assets/snippets/cdn/cloudflare-cache-rules.md](assets/snippets/cdn/cloudflare-cache-rules.md), [assets/snippets/cdn/cloudfront-cache-policy.tf](assets/snippets/cdn/cloudfront-cache-policy.tf), [assets/snippets/cdn/fastly-surrogate-keys.vcl](assets/snippets/cdn/fastly-surrogate-keys.vcl), [assets/snippets/cdn/vercel.json](assets/snippets/cdn/vercel.json), [assets/snippets/cdn/netlify.toml](assets/snippets/cdn/netlify.toml) |
| Reverse proxy | [assets/snippets/proxy/nginx-microcache.conf](assets/snippets/proxy/nginx-microcache.conf), [assets/snippets/proxy/varnish-xkey.vcl](assets/snippets/proxy/varnish-xkey.vcl) |
| App cache and stampede control | [assets/snippets/app/cache-aside.ts](assets/snippets/app/cache-aside.ts), [assets/snippets/app/cache_aside.py](assets/snippets/app/cache_aside.py), [assets/snippets/app/singleflight.go](assets/snippets/app/singleflight.go), [assets/snippets/app/xfetch.py](assets/snippets/app/xfetch.py), [assets/snippets/app/redis-lease.lua](assets/snippets/app/redis-lease.lua), [assets/snippets/app/redis-version-set.lua](assets/snippets/app/redis-version-set.lua) |
| Next.js multi-instance and CMS revalidation | [assets/snippets/frameworks/nextjs-cache-handler.mjs](assets/snippets/frameworks/nextjs-cache-handler.mjs), [assets/snippets/frameworks/nextjs-cms-webhook-route.ts](assets/snippets/frameworks/nextjs-cms-webhook-route.ts) |
| Service worker | [assets/snippets/browser/workbox-sw.js](assets/snippets/browser/workbox-sw.js) |
| CI caching | [assets/snippets/ci/github-actions-cache.yml](assets/snippets/ci/github-actions-cache.yml) |
| Regression tests | [assets/snippets/tests/header-snapshot.test.ts](assets/snippets/tests/header-snapshot.test.ts), [assets/snippets/tests/leak-test.sh](assets/snippets/tests/leak-test.sh) |
