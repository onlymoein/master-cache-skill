# App-Specific Caching Strategy: Discovery Workflow, Decision Frameworks, Archetype Blueprints, Plan Template, and Adjacent Layers (state as of October 2026)

## 1. Discovery and audit methodology: what to inspect in a repo and deployment, how to probe live responses, what existing caching to find, and which metrics to collect

### Takeaway
A repeatable audit runs in six passes. (A) Identify the stack and hosting from manifests and config files. (B) Inventory every route, endpoint and data source. (C) Probe live responses for each resource class (HTML, hashed assets, unhashed assets, API, media) and read CDN cache-status headers. (D) Grep for caching primitives that already exist. (E) Record baseline metrics: hit ratio, origin load, p95, TTFB/LCP and CrUX navigation types. (F) Classify each resource with the decision tree in Section 2. Primary sources supply the detection steps for missing caching (Azure), the header semantics (MDN, web.dev) and the measurement framing (CrUX navigation types, TTFB thresholds). No authoritative source publishes a "repo file → caching implication" checklist, so the fingerprint tables below are practitioner synthesis.

### Cited Findings
- **Azure's procedure for detecting the No-Caching antipattern** has five steps. (1) Review the design, take inventory of the data stores, check whether each one is cached and find out how often its data changes ("good initial candidates… data that changes slowly, and static reference data that is read frequently"). (2) Instrument the live system and monitor how often data is retrieved or computed. (3) Profile in a test environment. (4) Load test with realistic access patterns. (5) Examine data-access statistics for repeated queries. In Azure's worked example, `sys.dm_exec_cached_plans.UseCounts` showed one query run more than 250,000 times — [Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)
- Azure recommends: "Always include instrumentation that detects cache hits and cache misses. Use this information to tune caching policies." Before caching computed results, "instrument the application to determine whether the application is really CPU bound." It also warns: "If the lack of caching is a bottleneck, adding caching might increase the volume of requests so much that the web front end becomes overloaded… HTTP 503" — [Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)
- **A missing `Cache-Control` header does not mean "don't cache".** Browsers apply heuristic caching. For a response with `Last-Modified` and no `max-age`, the spec suggests reusing it for about 10% of the time since its last modification. "Basically all responses should explicitly specify a `Cache-Control` header." The audit should therefore flag every response that lacks `Cache-Control` — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching); also [web.dev HTTP cache](https://web.dev/articles/http-cache) ("Leaving out the Cache-Control response header does not disable HTTP caching!")
- **CDN defaults to check during probing (Cloudflare):**
  - Cloudflare decides what to cache "based on file extension and not by MIME type" and "does not cache HTML or JSON by default". It does cache `robots.txt` by default.
  - It does not cache a response whose `Cache-Control` is `private`, `no-store`, `no-cache` or `max-age=0`, or one that carries `Set-Cookie`.
  - Source: [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/)
- **Reading Cloudflare's cache-status header (2026 change):** since 2026-05-26 Cloudflare returns `BYPASS` consistently whenever a response is uncacheable. Reasons include exceeding the maximum cacheable size, origin `no-cache`/`private`/`max-age=0`, `Set-Cookie` on the response, and `Authorization` on the request. `MISS` now means only "cacheable but not in the local cache". Before this, oversize responses returned `MISS` on every request, which looked like a cold cache — [Cloudflare changelog 2026-05-26](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-05-26-bypass-status-for-uncacheable-responses.mdx)
- **Cloudflare's stale-while-revalidate is asynchronous since 2026-02-26.** The first request after expiry gets stale content immediately with status `UPDATING`, and revalidation happens in the background. This applies to Free/Pro/Business zones; about 75% of Enterprise zones had been migrated at announcement — [Cloudflare changelog 2026-02-26](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-02-26-async-stale-while-revalidate.mdx)
- **Expected Next.js headers to verify:**
  - Static pages get `s-maxage=31536000`.
  - ISR pages get `s-maxage={revalidate}, stale-while-revalidate={expire - revalidate}`; the default `expire` is one year.
  - App Router responses carry `Vary` on custom headers such as `rsc`. Next.js also adds an `_rsc` search-param hash as a cache-key surrogate for CDNs that ignore `Vary`.
  - "CDN-level caching alone does not support on-demand revalidation (`revalidateTag()`/`revalidatePath()`)."
  - `proxy.js` (previously Middleware) "should run before the CDN cache so it remains the source of truth for auth, redirects, and rewrites."
  - Source: [Next.js CDN caching guide](https://nextjs.org/docs/app/guides/cdn-caching)
- **Next.js caching model as of v16:**
  - Cache Components is enabled with `cacheComponents: true`. "New App Router apps created with the recommended `create-next-app` defaults already have Cache Components and Partial Prefetching enabled."
  - Caching primitives are `'use cache'` (on functions, components or files), `cacheLife`, `cacheTag`, `'use cache: private'` (can read cookies/headers/searchParams) and `'use cache: remote'`.
  - Runtime APIs (`cookies`, `headers`, `params`, `searchParams`) must sit inside `<Suspense>`, otherwise the route blocks the prerender.
  - `cacheLife` was stabilized in v16.0.0.
  - Sources: [Next.js caching](https://nextjs.org/docs/app/getting-started/caching); [Next.js cacheLife](https://nextjs.org/docs/app/api-reference/functions/cacheLife)
- Next.js keeps a build cache in `.next/cache`. If CI does not persist it, the build reports "No Cache Detected" — [Next.js CI build caching](https://nextjs.org/docs/app/guides/ci-build-caching)
- **Measuring with CrUX navigation types (Harry Roberts, 2024):**
  - The types are mutually exclusive: Navigate, Cache, Back–Forward, bfcache, Reload, Restore and Prerender.
  - BBC example split: 70% navigate, 0.6% cache, 5.4% back–forward (not bfcache), 13.7% bfcache, 7.5% reload, 0.2% restore, 2.5% prerender.
  - bfcache hit rate = bfcache / (bfcache + back–forward). For the BBC that is 13.7 / (13.7 + 5.4) = 71.7%.
  - CrUX covers only hard navigations, so SPAs are under-represented.
  - Source: [csswizardry "Cache Grab"](https://csswizardry.com/2024/08/cache-grab-how-much-are-you-leaving-on-the-table/)
- **TTFB thresholds:** "most sites should strive to have Time To First Byte of 0.8 seconds or less". Good is ≤0.8 s and poor is >1.8 s, measured at the 75th percentile. TTFB "is not a Core Web Vitals metric" — [web.dev TTFB](https://web.dev/articles/ttfb)
- **Test hygiene:**
  - Keep three conditions separate: **cold cache** (clear once, then load with caching enabled), **warm cache** (revisit normally) and **cache disabled** (a separate diagnostic mode, not a warm-cache test).
  - Record the browser version and whether DevTools/Ignore Cache was active.
  - Safari Web Inspector's "Ignore Cache" used to overwrite page-authored `Cache-Control` request headers with `no-cache`. Safari Technology Preview 250 fixed this.
  - Source: [csswizardry 2026-08](https://csswizardry.com/2026/08/when-safaris-ignore-cache-ignored-cache-control/)
- **Reloads distort cache measurements:**
  - On a refresh, Chrome sends `Cache-Control: max-age=0` plus conditional headers, Firefox sends only conditional headers, and Safari sends `Cache-Control: no-cache` plus `Pragma: no-cache`, which always produces a 200.
  - A hard refresh in every browser sends `no-cache` and `Pragma: no-cache` for the document and all subresources, including `immutable` ones.
  - Source: [csswizardry, Cache-Control request header](https://csswizardry.com/2025/03/why-do-we-have-a-cache-control-request-header/)
- **Debugging gotcha with `No-Vary-Search`:** if a document uses it, appending a throwaway query string may no longer bypass the cache — [csswizardry No-Vary-Search](https://csswizardry.com/2026/05/better-browser-caching-with-no-vary-search/)
- **Prior art for an agent skill:** Vercel's `vercel-optimize` agent skill treats edge caching "as a safety question first." A route "must be a public, cacheable GET path before a shared-cache recommendation is allowed." Before recommending `s-maxage`, it requires ruling out "cookies, sessions, authorization, draft state, and user-specific data." It checks method distribution, cache breakdown and headers. It never mixes `private` with shared-cache directives. When the right policy is `no-store`, it emits no change — [vercel-labs/agent-skills cdn-cache-auth-safety](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md). A companion rule says: "Do not suggest APIs outside the detected Next.js version… Do not claim `cacheLife()` emits CDN `Cache-Control` headers… Omitted `cacheLife()` calls use the default profile" — [vercel-labs/agent-skills nextjs-version-cache-semantics](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/nextjs-version-cache-semantics.md)

### Inferences

**A. Audit procedure (the order a skill should run it):**

| Pass | Goal | Actions | Output |
|---|---|---|---|
| A. Fingerprint | Stack, framework version, rendering mode, hosting/CDN | Read manifests and lockfiles (exact versions), deploy configs, IaC, Dockerfiles, web server configs (table B) | "App profile" block: archetype guess, framework@version, runtime, hosting, CDN, data stores |
| B. Inventory | Every route/endpoint and data source | Framework route tree (table C); OpenAPI/GraphQL schema; ORM models; external API clients; queues | Resource inventory with method, auth requirement, params, data sources touched |
| C. Live probe | What actually happens today | curl matrix (block D) across HTML, assets, API, media; repeat for HIT/Age; conditional requests; probe with and without a session cookie | Header table per route; leaks; missing validators |
| D. Existing caching | Which caches already exist, and where | Grep patterns (block E); CDN rules in IaC/dashboards; Redis/Memcached connection config; client query caches | List of existing caches with key, TTL and invalidation |
| E. Baseline metrics | Where caching would pay off | CDN analytics, APM, DB stats, RUM/CrUX (table F) | Baseline numbers with date, window and source |
| F. Classify and plan | Per-resource policy | Section 2 decision tree and matrix → Section 6 template | Cache policy matrix plus rollout plan |

**B. Repo fingerprint signals (practitioner synthesis; verify per repo):**

| File / signal | What it reveals | Caching implications to check |
|---|---|---|
| `package.json` + lockfile | Framework and version: `next`, `nuxt`, `@sveltejs/kit`, `@remix-run/*`/`react-router` v7, `astro`, `gatsby`, `@angular/ssr`, `express`/`fastify`/`hono`/`@nestjs/*`; cache clients (`ioredis`, `redis`, `@upstash/redis`, `lru-cache`, `keyv`, `cache-manager`, `node-cache`); client caches (`@tanstack/react-query`, `swr`, `@apollo/client`, `@reduxjs/toolkit` RTK Query); `workbox-*` | Next ≥15/16: check `'use cache'`/`cacheLife`/`cacheTag`/`cacheComponents`; older versions: `fetch` cache options, `export const revalidate`, `unstable_cache`. Nuxt: `routeRules` (`swr`, `isr`, `cache`). SvelteKit: `setHeaders`. Astro: static vs SSR output. |
| `next.config.*` | `cacheComponents`, `cacheHandlers`, `cacheLife` profiles, `images`, `headers()`, `assetPrefix`, `output: 'export'` | Static export → pure CDN. Custom cache handler → shared ISR/data cache (Redis) needed for multi-instance self-hosting. |
| `requirements.txt` / `pyproject.toml` | Django / Flask / FastAPI; `django-redis`, `cachetools`, `Flask-Caching`, `aiocache`, `fastapi-cache2`, `redis` | Django `@cache_page`, `cache_control`, `ConditionalGetMiddleware`, `CACHES` setting; FastAPI response headers |
| `Gemfile` | Rails; `redis`, `dalli` (Memcached), `solid_cache` | `Rails.cache`, fragment/Russian-doll `cache` blocks, `fresh_when`/`stale?` (ETag/304), `expires_in` |
| `composer.json` | Laravel / Symfony / WordPress plugins | Laravel `Cache::remember`, `ResponseCache`; Symfony `HttpCache`/ESI; WordPress object cache (`object-cache.php`), page-cache plugins, transients |
| `go.mod` | `net/http`, Gin, Echo, Fiber; `go-redis`, `ristretto`, `bigcache`, `groupcache`, `singleflight` | In-process caches plus explicit `singleflight` |
| `pom.xml` / `build.gradle` | Spring Boot; `spring-boot-starter-cache`, Caffeine, Ehcache, Hazelcast, Redisson | `@Cacheable`/`@CacheEvict`, Hibernate L2 cache, `CacheControl` in Spring MVC |
| `*.csproj` | ASP.NET Core | `OutputCache`, `ResponseCaching`, `IMemoryCache`/`IDistributedCache`/`HybridCache` |
| `Dockerfile`, `docker-compose.yml`, `k8s/*.yaml`, Helm | Runtime, replica count, sidecars (redis, varnish, nginx) | Replica count above 1 means process-local caches diverge (Azure private-cache warning). Look for a Redis service. |
| `vercel.json` | Vercel hosting; `headers`, `rewrites`, `crons`, regions | Vercel CDN/ISR; check custom `Cache-Control`/`CDN-Cache-Control` |
| `netlify.toml` / `_headers` / `_redirects` | Netlify; header rules; edge functions | Netlify CDN; check `[[headers]]` per path |
| `wrangler.toml` / `wrangler.jsonc` | Cloudflare Workers/Pages; KV, R2, D1, Durable Objects, Hyperdrive bindings | Cache API in Workers; KV as an edge cache; Cache Rules and Cache Response Rules |
| `firebase.json`, `app.yaml`, `amplify.yml`, `render.yaml`, `fly.toml`, `railway.json` | Other PaaS | Platform CDN defaults differ; check `headers` config |
| `nginx.conf` / `conf.d/*` | Reverse proxy | `proxy_cache`, `fastcgi_cache`, `expires`, `add_header Cache-Control`, `proxy_cache_use_stale`, `proxy_cache_lock`, `keepalive` |
| `*.vcl`, `haproxy.cfg`, `Caddyfile`, `traefik.*` | Varnish / other proxies | Grace/keep (stale), purge/ban ACLs |
| `serverless.yml`, SAM `template.yaml`, CDK (`aws-cloudfront`), Terraform (`aws_cloudfront_distribution`, `aws_cloudfront_cache_policy`, `aws_elasticache_*`, `cloudflare_ruleset`, `fastly_service_vcl`, `google_compute_backend_bucket` with `cdn_policy`, `azurerm_cdn_frontdoor_*`) | CDN, cache policy, managed cache clusters | Cache key policy (headers/cookies/query strings forwarded), min/default/max TTLs, origin shield, invalidation tooling |
| `.github/workflows/*.yml`, `.gitlab-ci.yml`, `turbo.json`, `nx.json`, `.bazelrc` | CI and build caching | `actions/cache`, `setup-* cache:`, BuildKit `cache-to/cache-from`, Turborepo/Nx remote cache (Section 7) |
| `sw.js`, `workbox-config.js`, `manifest.json` | PWA / service worker | SW cache strategy; SW script must itself be served `no-cache` (inference) |
| OpenAPI / `schema.graphql` / tRPC routers | API surface | GET vs POST (GraphQL over POST is uncacheable at the CDN without persisted queries/GET) |
| ORM schema (Prisma, Drizzle, ActiveRecord, Django models, JPA) | Entities, relations, write paths | Read/write ratio per entity; where invalidation hooks go (`afterSave`, signals, CDC) |

**C. Route inventory by framework (synthesis):**
- Next App Router: `app/**/page.tsx`, `route.ts`, `layout.tsx`, `generateStaticParams`. Pages Router: `pages/**`, `getStaticProps`/`getServerSideProps`/`revalidate`.
- Nuxt: `pages/**`, `server/api/**`. SvelteKit: `src/routes/**/+page(.server).ts`, `+server.ts`. Remix/RR7: `app/routes/**` (`loader`, `headers` export).
- Rails: `bin/rails routes`. Django: `urls.py`. Laravel: `php artisan route:list`. Spring: `@GetMapping`. Express/Fastify: grep `app.get(`/`router.get(`.
- Enrich each route with: method; auth required; whether it reads cookies/headers/session; query params; data sources; write side-effects; expected traffic share (from access logs or analytics).

**D. Live probe recipe (curl matrix; header names are practitioner knowledge, so verify per vendor):**
```bash
H='cache-control|cdn-cache-control|surrogate-control|age|etag|last-modified|expires|vary|set-cookie|cache-status|cf-cache-status|x-cache|x-vercel-cache|x-nextjs-cache|x-served-by|x-amz-cf-pop|via|server|surrogate-key|cache-tag|no-vary-search'
for u in / /some/article /_next/static/chunks/main-abc.js /favicon.ico /api/products?id=1 /images/hero.jpg; do
  echo "== $u"; curl -sS -o /dev/null -D - --compressed "https://SITE$u" | grep -iE "^($H):"
done
# Run twice: Age should increase and status should go MISS→HIT on cacheable public URLs
# Validator check: curl -sI URL -H 'If-None-Match: "<etag>"'  → expect 304
# Leak check: request with and without a session cookie, and with two different users' cookies;
#   any shared-cache HIT that returns user-specific content, or a public cached response carrying Set-Cookie, is a P0
# Variant check: vary Accept-Encoding / Accept-Language / utm_* params and confirm the cache key behaves as intended
```
Status vocabularies to interpret:
- Cloudflare `cf-cache-status`: HIT/MISS/EXPIRED/REVALIDATED/UPDATING/BYPASS/DYNAMIC.
- Vercel `x-vercel-cache`: HIT/MISS/STALE/PRERENDER/REVALIDATED.
- CloudFront `x-cache: Hit/Miss/RefreshHit from cloudfront`.
- Fastly `x-cache` plus `x-served-by`.
- RFC 9211 `Cache-Status` (used by several CDNs, including Netlify).
- Vocabulary beyond the Cloudflare items cited above is from practitioner knowledge.

**E. Grep patterns for existing caching:**
- HTTP: `Cache-Control|s-maxage|stale-while-revalidate|stale-if-error|CDN-Cache-Control|Surrogate-(Control|Key)|Cache-Tag|ETag|Last-Modified|Vary|No-Vary-Search|Clear-Site-Data`
- Next.js: `'use cache'|cacheLife|cacheTag|revalidateTag|revalidatePath|updateTag|unstable_cache|export const (revalidate|dynamic)|force-cache|no-store|generateStaticParams|cacheHandlers`
- App/data: `Redis|ioredis|createClient|Memcache|dalli|lru-cache|cachetools|lru_cache|@cache|@Cacheable|Rails.cache|Cache::remember|IMemoryCache|HybridCache|singleflight|setex|EXPIRE|TTL`
- Client: `staleTime|gcTime|cacheTime|fetchPolicy|InMemoryCache|keepUnusedDataFor|useSWR|workbox|caches.open`
- Proxy/CDN: `proxy_cache|fastcgi_cache|expires |vcl_|beresp.ttl|grace|aws_cloudfront_cache_policy|cloudflare_ruleset|cache_rules`

**F. Metrics to gather (baseline before any change):**

| Metric | Source | Why |
|---|---|---|
| CDN request and byte hit ratio, per path class | CDN analytics/logs (exclude BYPASS when computing "cacheable hit ratio") | Origin offload headroom |
| Origin RPS, p50/p95/p99 latency per route | APM / access logs | Finds expensive hot routes |
| Request popularity distribution (top-N URL share; Zipf head) | Logs | High head concentration means high achievable hit ratio |
| Read:write ratio per entity/table | DB stats (`pg_stat_statements`, slow log, `sys.dm_exec_query_stats`), ORM logs | Cache candidates: high read:write, slow change |
| Top repeated queries and their cost | DB stats (Azure method) | Cache-aside targets, or fix the query first |
| Redis/Memcached hit/miss, evictions, memory, latency | `INFO stats` (keyspace_hits/misses, evicted_keys) | Existing cache effectiveness |
| TTFB p75 (good ≤0.8 s), LCP p75 | RUM / CrUX | User impact of HTML caching |
| CrUX navigation types (cache, bfcache, prerender shares) | CrUX / Treo | bfcache and prerender opportunities |
| Traffic shape: peak/mean ratio, spikes (launches, breaking news) | Analytics | Stampede risk; need for SWR and coalescing |
| Egress/compute cost per 1M requests | Billing | ROI for the plan |
| CI build duration, cache hit rate | CI logs, Turborepo/Nx summaries | Build-cache ROI |

### Gaps
- **Method note:** in this session WebFetch could not resolve hosts and the egress proxy blocked direct HTTPS to most documentation sites. Primary documentation was therefore read from the source repositories via raw GitHub/git on 2026-10-27:
  - mdn/content
  - GoogleChrome/web.dev (archived repo; content as of 2023)
  - MicrosoftDocs/architecture-center (caching guidance dated 03/25/2026)
  - cloudflare/cloudflare-docs (production branch)
  - vercel/next.js (canary docs)
  - docker/docs
  - github/docs
  - nrwl/nx
  - vercel/turborepo
  - csswizardry/csswizardry.github.com
  - jakearchibald/jakearchibald.com
  
  Canonical URLs are cited. The AWS caching best-practices page and the Google Cloud Architecture Center could not be reached and are **not** cited.
- No authoritative published checklist maps repo files to caching implications. Tables B–E are synthesis.
- Vendor cache-status vocabularies other than Cloudflare's (Vercel, Fastly, CloudFront, Akamai, Netlify) were not re-verified this session.

## 2. Classification criteria and decision frameworks: classifying each resource and choosing layer, TTL and invalidation

### Takeaway
Experts work from three base patterns:
1. **Immutable, versioned URL + very long `max-age`/`immutable`.**
2. **Mutable URL + always revalidate** (`no-cache` + ETag).
3. **Managed (purgeable) shared cache in front of mutable content.** A CDN or reverse proxy uses `s-maxage`/`CDN-Cache-Control` with stale-while-revalidate (SWR) and tag-based purge or invalidation, which makes caching HTML and API responses safe.

Before choosing a pattern, run a safety gate on audience and sensitivity (`private`/`no-store`). After choosing, tune for variant cardinality (`Vary`, query normalization, `No-Vary-Search`), cost and popularity (server-side cache-aside), and write-consistency needs (invalidate-on-write vs write-through). "Small `max-age` on mutable content" is the classic bad compromise.

### Cited Findings
- **web.dev's baseline, with a flowchart appendix that picks among the directives:**
  - `no-cache` means "must revalidate with the server every time before using a cached version".
  - `no-store` means browsers and intermediaries "never store any version".
  - `private` means only the browser may store it; `public` means any cache may store it.
  - Versioned/fingerprinted URLs get `max-age=31536000`, optionally with `immutable`.
  - "ETag is the recommended approach because it's more accurate" than `Last-Modified`.
  - Example values: `max-age=86400` (1 day for browser and intermediaries); `private, max-age=600`; `public, max-age=31536000`; `no-store`.
  - Tips: use consistent URLs; minimize churn by splitting frequently-changing code from stable library code.
  - Source: [web.dev HTTP cache](https://web.dev/articles/http-cache)
- **Jake Archibald's two patterns:** "Pattern 1: Immutable content + long max-age" and "Pattern 2: Mutable content, always server-revalidated" (`no-cache`). Using "a smallish max-age and mutable content" is "a baaaad compromise." His worked example: HTML, CSS and JS all served `must-revalidate, max-age=600` end up with mismatched versions because the browser evicts entries independently. Short `max-age` on mutable content is acceptable only when the resource has no dependencies or dependents that could get out of sync; his own articles use `max-age` of 3 minutes behind Cloudflare. "Favour immutable content for any URL that can easily change, otherwise play it safe with server revalidation" — [Jake Archibald, Caching best practices](https://jakearchibald.com/2016/caching-best-practices/)
- **Harry Roberts' recipes:**

  | Case | Cache-Control |
  |---|---|
  | Online banking page | `no-store`, or defensively `private, no-cache, no-store` |
  | Live train times | `no-cache` ("usually a sensible default for almost all webpages") |
  | FAQ page | `max-age=604800, must-revalidate` |
  | Fingerprinted app bundle | `max-age=31536000, immutable` |
  | Decorative image | `max-age=2419200, must-revalidate, stale-while-revalidate=86400` |
  | `stale-if-error` example | `max-age=2419200, stale-if-error=86400` |

  Rules:
  - "Work out your cache busting strategy before you begin work on your caching strategy."
  - Fingerprinted filenames are preferred. Query-string busting is fragile because CDNs may normalize or strip the query string. Per-file hash or version beats release-directory versioning.
  - `public` on responses to requests with `Authorization` forces storage in shared caches, which "you really, really do not want".
  - Don't send `max-age` alongside `no-cache`.
  - Pages with different HTML cache policies can reference different asset versions.
  - Source: [csswizardry, Cache-Control for Civilians](https://csswizardry.com/2019/03/cache-control-for-civilians/)
- **MDN's recommended defaults:**
  - Give every response an explicit default. `Cache-Control: no-cache` is common, and personalized content (cookies/logins) adds `private`: `no-cache, private`.
  - Hashed subresources: `public, max-age=31536000, immutable` "if you never personalize responses via Authorization", else `max-age=2592000`. Add `ETag`/`Last-Modified`.
  - Main HTML: `no-cache` plus `ETag`/`Last-Modified`; when personalized via cookies, `no-cache, private`.
  - "The same can be used for `favicon.ico`, `manifest.json`, `.well-known`, and API endpoints whose URLs cannot be changed."
  - Common QPACK-indexed values: `max-age=0`, `604800`, `2592000`, `no-cache`, `no-store`, `public, max-age=31536000`.
  - Source: [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- **MDN on `no-store` vs `no-cache`:**
  - Don't grant `no-store` liberally: "you lose… the browser's back/forward cache… prefer the use of `no-cache` in combination with `private`."
  - `no-store` "does not delete any already-stored response for the same URL", while `no-cache` forces revalidation.
  - Kitchen-sink headers (`no-store, no-cache, max-age=0, must-revalidate, proxy-revalidate`) are workarounds for outdated implementations.
  - Source: [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- **MDN on cache keys and `Vary`:**
  - Use `Vary: Accept-Language` for content negotiation.
  - Avoid `Vary: User-Agent`, which has very high cardinality.
  - For cookie-personalized content, "specify `Cache-Control: private` instead of specifying a cookie for `Vary`."
  - Shared caches perform **request collapse** even when the response says `max-age=0`/`no-cache`, so personalized responses need `private`.
  - Once an intermediate cache has stored a response with a long `max-age`, there is no protocol way to delete it. `Clear-Site-Data: cache` clears browsers only.
  - Managed caches (CDNs with purge APIs, service workers) make caching main HTML feasible: "storing the main resource and explicitly purging… when an update occurs."
  - CDN-specific headers such as `Surrogate-Control` exist, and `CDN-Cache-Control` (RFC 9213) standardizes them.
  - Source: [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- **Cloudflare `CDN-Cache-Control` precedence:**
  - Origins can send `CDN-Cache-Control` (Cloudflare evaluates it and proxies it downstream) or `Cloudflare-CDN-Cache-Control` (Cloudflare-only, not proxied). `Cache-Control` then passes to browsers unchanged.
  - A Cache Response Rule `set_cache_control` takes precedence over both. An Edge Cache TTL rule overrides edge TTLs.
  - Source: [Cloudflare CDN-Cache-Control](https://developers.cloudflare.com/cache/concepts/cdn-cache-control/)
- **New 2026 CDN controls that change the decision space (Cloudflare):**
  - **Cache Response Rules (2026-03-24)** can modify `Cache-Control`, manage cache tags and strip `Set-Cookie` from origin responses *before* caching. This increases cacheability without touching the origin — [changelog](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-03-24-cache-response-rules.mdx)
  - **Vary support in Cache Rules (2026-07-02).** Each varied header gets an action: `normalize` (collapse equivalent values; "most Accept, Accept-Language, and Accept-Encoding use cases"), `passthrough`, or `bypass` ("per-user values, or headers with too many possible values to cache safely") — [changelog](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-07-02-vary-for-cache-rules.mdx)
  - **Invalidate instead of purge (2026-09-28).** Invalidation marks content stale; on the next request Cloudflare revalidates with the origin and reuses the cached copy on `304`. It requires the origin to send `ETag`/`Last-Modified` and support conditional requests. Selectors: URLs, cache tags, hostnames, URL prefixes, everything (`POST …/invalidate_cache`) — [changelog](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-09-28-cache-invalidation.mdx)
  - **Cloudflare's cache now runs on Pingora** (Rust proxy) as of 2026-05-04, cited for "improved RFC compliance" — [changelog](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-05-04-pingora-powers-cache.mdx)
- **`No-Vary-Search` (2026 status: experimental, so treat it as progressive enhancement):**
  - `params=("utm_source" …)` ignores the listed params. This is the *defensive* default because unknown params still vary the key.
  - `except=("colour" "size")` ignores everything except the listed params.
  - `except=()` ignores all params. The spec dropped the boolean `params` form.
  - `key-order` makes parameter order irrelevant.
  - The syntax uses Structured Fields (space-separated quoted strings). Never ignore a parameter that affects the HTML.
  - Source: [csswizardry No-Vary-Search](https://csswizardry.com/2026/05/better-browser-caching-with-no-vary-search/)
- **Azure: when caching works best.** "Caching is most effective when a client instance repeatedly reads the same data", especially when the original store is "relatively static", "slow compared to the speed of the cache", "subject to a high level of contention", or "far enough away… that network latency is significant." "Consider caching data that's read frequently but modified infrequently." "Don't use the cache as the authoritative store of critical information" — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Azure: partial and dynamic data.** Cache static portions of an entity (name, address) and fetch dynamic parts (account balance) live. Highly dynamic, noncritical data such as device telemetry can live directly in the cache without being persisted — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Azure: write consistency.** **Invalidate on write** (cache-aside) keeps writes simple, but a reader "can experience a cache miss or briefly see stale data". **Write-through** updates the store and the cache in the same write. "Use write-through only for read-heavy access paths that need read-after-write freshness. For data that's rarely read after it's written or that changes constantly, invalidate on write or bypass the cache" — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Azure: consistency and resilience.**
  - Most distributed caches including Redis favor availability and partition tolerance (AP) over consistency. "Decide how much staleness your application can tolerate and set TTL values accordingly. For data that must be current, use shorter TTLs or bypass the cache entirely."
  - With eventual consistency (replicas), cache-aside can repopulate the cache with an old value.
  - Use a local in-memory L1 plus a shared L2.
  - Make the app survive cache outages (circuit breaker, fall back to the store), while noting the store can be swamped during recovery.
  - Source: [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Azure: TTL and eviction.**
  - "If you make [expiration] too short, objects expire too quickly and you reduce the benefits… too long, you risk the data becoming stale."
  - Both absolute and sliding expiration exist.
  - Eviction is typically LRU. Azure Managed Redis defaults to `volatile-lru`; alternatives are `allkeys-lru`, `volatile-random` and `noeviction`.
  - Structure keys like `customer:100` and `orders:100`. In clustered Redis, use hash tags (`customer:{123}:name`) so multi-key operations land in the same slot.
  - Source: [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Azure cache-aside "might not be suitable"** when the data is "sensitive or security related", when "the cached data set is static" (prime it at startup and don't expire), or when "most requests don't experience a cache hit." Expensive-to-retrieve items should get per-item TTL and eviction configuration — [Azure Cache-Aside pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
- **Stampede/thundering-herd controls:**
  - Request coalescing / single-flight: one rebuild per key; for example a Redis `SET NX PX` lock that *must* expire.
  - Probabilistic early expiration (X-Fetch, using regeneration time `delta`, `beta` ≈ 1.0 and a random draw).
  - TTL jitter of about ±10%. It only helps synchronized expiry, not a single hot key.
  - Stale-while-revalidate / Varnish grace.
  - Consensus: jitter all TTLs, coalesce on the read path, and use early refresh for the hottest, most expensive keys.
  - Source: [Redis (antirez) cache stampede prevention](https://redis.antirez.com/fundamental/cache-stampede-prevention.html); secondary blogs agree.
- **Next.js `cacheLife` built-in profiles** give a ready vocabulary for TTL tiers (stale / revalidate / expire):

  | Profile | stale | revalidate | expire |
  |---|---|---|---|
  | `default` | 5 min | 15 min | never |
  | `seconds` | 30 s | 1 s | 1 min |
  | `minutes` | 5 min | 1 min | 1 h |
  | `hours` | 5 min | 1 h | 1 day |
  | `days` | 5 min | 1 day | 1 week |
  | `weeks` | 5 min | 1 week | 30 days |
  | `max` | 5 min | 30 days | 1 year |

  Source: [Next.js cacheLife](https://nextjs.org/docs/app/api-reference/functions/cacheLife)

### Inferences

**A. Master decision tree (apply per resource or route; first match wins):**
```
0. METHOD: not GET/HEAD (mutation)?             → no-store at HTTP layers; on success, run the invalidation hooks (tags/keys) for affected reads. STOP.
1. SAFETY GATE: response contains secrets/regulated data (auth tokens, payment data, PHI, balances, statements)?
                                                → Cache-Control: no-store (optionally "private, no-store"). No shared cache. No server cache
                                                  unless tenant/user-scoped + encrypted + short TTL. STOP.
2. AUDIENCE: does the body depend on identity (cookie/session/Authorization/tenant/entitlement/AB bucket/geo-pricing)?
   2a. Yes, wholly personalized               → "private, no-cache" + ETag (or "private, max-age=<small>" for idempotent dashboards);
                                                  server cache keyed by {tenant}:{user}:{resource}:{version}; never s-maxage. STOP.
   2b. Mostly public with a personalized island → SPLIT: public shell cached at CDN (go to 3) + island fetched client-side / streamed
                                                  (PPR, 'use cache: private', ESI/edge include). Strip Set-Cookie from the public part.
   2c. No → public; continue.
3. VERSIONABLE: can the URL change whenever content changes (content hash, version id, immutable upload id)?
   → Yes: "public, max-age=31536000, immutable" (drop "public" if responses could ever be Authorization-gated). No invalidation needed. STOP.
4. STALENESS BUDGET S (business impact of showing an old version):
   4a. S = 0 (prices at payment, stock at checkout, auth/permissions, balances, live odds)
       → browser no-cache (or no-store); shared cache only if event-purged AND the commit path re-reads the source of truth. 
   4b. S = seconds–minutes (homepages, news fronts, listings, scores, feeds)
       → browser "max-age=0"/no-cache; CDN "s-maxage=S, stale-while-revalidate=k·S, stale-if-error=long"; micro-cache 1–10 s on hot dynamic routes.
   4c. S = hours–days (articles, docs, product detail copy, catalogs)
       → CDN long s-maxage (hours–days, up to 1 year with purge) + tag purge/invalidate on publish; browser no-cache or short max-age.
5. INVALIDATION AVAILABLE? (CDN purge-by-tag/surrogate-key/prefix, Next revalidateTag, webhook on CMS publish, CDC)
   → Yes: long shared TTL + event-driven purge (prefer "invalidate→revalidate" + ETag where supported).
   → No: shared TTL = S; add SWR and stale-if-error; never exceed S.
6. VARIANTS / CARDINALITY:
   Accept-Encoding → let CDN handle; Accept-Language/Accept → Vary with normalization; device → avoid Vary: User-Agent (normalize to 2–3 buckets or use separate URLs);
   query string → allowlist meaningful params, strip/sort tracking params (CDN cache key rules; No-Vary-Search params=(…)); cookies → never Vary: Cookie (use private, or strip cookies for public paths).
   If effective variants per URL ≫ requests per TTL window → hit rate collapses → cache a lower layer (data/fragments) instead.
7. COST × POPULARITY (server-side): hot (Zipf head) AND expensive (slow query, fan-out, 3rd-party/LLM call) → cache-aside in Redis/Memcached (+ L1 in-process for ultra-hot),
   jittered TTL ≤ S, single-flight, SWR/early refresh; cold long tail OR cheap → don't cache (fix query/index instead).
8. WRITE CONSISTENCY: read-after-write required for the writer → write-through, or invalidate-on-write + per-session "bypass cache for N s after write"; otherwise invalidate-on-write or TTL.
9. FAILURE MODE: cache must be optional (circuit breaker); define behavior on cache outage and on origin outage (stale-if-error).
```
The web.dev flowchart is an image that was not machine-readable. Steps 1–3 reconstruct its question order from the directives the article lists: "reusable?" → "revalidate each time?" → "cacheable by intermediaries?" → "max-age?" (reconstruction, not a quote).

**B. Data-class → policy matrix (starting points; TTLs are synthesized defaults that must be checked against each app's staleness budget):**

| # | Data class (examples) | Browser `Cache-Control` | Shared cache / CDN | Server / data cache | Starting TTL | Invalidation | Key risks |
|---|---|---|---|---|---|---|---|
| 1 | Fingerprinted static assets (JS/CSS/fonts/images with hash) | `public, max-age=31536000, immutable` | Same; serve from CDN/object storage | n/a | 1 year | New URL per build (content hash) | Non-hashed file mistakenly marked `immutable`; deploying HTML before assets (keep old assets for N releases) |
| 2 | Unhashed static files (`favicon.ico`, `robots.txt`, `/logo.png`, `manifest.json`, `.well-known/*`) | `no-cache` + ETag (or `max-age=86400` for truly stable files) | `s-maxage` 1 h–1 day + purge on deploy | n/a | 1 h–1 day shared | Purge on deploy | Long browser TTL can't be recalled |
| 3 | Service worker script (`sw.js`) | `no-cache` (`max-age=0`) | Short or none | n/a | 0 | Deploy | Stale SW pins old app versions (Jake) |
| 4 | Public HTML, rarely changing (docs, marketing, blog posts) | `no-cache` (or `max-age=0, must-revalidate`) + ETag | `s-maxage=86400–31536000, stale-while-revalidate=86400` + tag purge on publish (SSG/ISR) | Framework data cache (`cacheLife('days'/'max')`) | 1 day–1 year with purge | CMS publish webhook → purge/invalidate by tag/path | Inconsistent policies across pages; `Set-Cookie` on public pages kills CDN caching |
| 5 | Public HTML, volatile (home, news front, category/listing pages) | `max-age=0`/`no-cache` | `s-maxage=30–300, stale-while-revalidate=300–3600, stale-if-error=86400`; micro-cache 1–10 s for hottest routes | Fragment/data cache with tags | 30 s–5 min | Event purge by tag + short TTL backstop | Stampede at expiry; breaking-news latency |
| 6 | Public page + personalized island (logged-in header, cart count, recommendations) | Shell: as #4/#5; island API: `private, no-cache` | Shell cached; island bypasses | Island data per user/session | Shell as #4/#5 | Shell: tags; island: per-user keys | Leaking a personalized shell to the CDN; `Vary: Cookie` |
| 7 | Fully personalized HTML/dashboards (SaaS, account pages) | `private, no-cache` + ETag (bfcache-friendly) | Bypass (no `s-maxage`) | Per-tenant/user query cache; precomputed aggregates | Seconds–minutes server-side | Invalidate on write (tenant-scoped tags) | Cross-tenant key collision; request collapse without `private` |
| 8 | Sensitive/regulated (banking, PHI, checkout payment step, auth endpoints, tokens) | `no-store` (defensive: `private, no-cache, no-store`) | Bypass | None, or encrypted per-user with minimal TTL | 0 | n/a | Disk persistence in browsers and proxies; logs |
| 9 | Public API GET, reference data (catalog, config, countries, feature lists) | `public, max-age=60–300` or `no-cache` + ETag | `s-maxage` hours + tag purge | Cache-aside / preload at startup (static set: prime, no expiry) | Hours–days | Admin publish → purge/invalidate tags; versioned keys | Clients hard-coding long `max-age` |
| 10 | Public API GET, volatile (price, stock level, scores, odds display) | `max-age=0`/`no-cache` (or `no-store` for odds/trading) | `s-maxage=1–30, stale-while-revalidate` short; or no CDN | Short TTL + event updates; write-through for hot SKUs | 1–30 s display; 0 at commit | Event-driven (stock change → purge/update) | Overselling: always re-check at commit |
| 11 | Authenticated API GET (user/tenant data) | `private, no-cache` + ETag, or `private, max-age=<s>` | Bypass | Per-user/tenant cache-aside | Seconds–minutes | Invalidate on write | `public` + `Authorization` stores in shared caches |
| 12 | Mutations (POST/PUT/PATCH/DELETE) | `no-store` | Never cached | Trigger invalidation | n/a | Emit events/tags | Missing invalidation leaves stale reads |
| 13 | Search / faceted listing (high-cardinality params) | `no-cache` or `max-age=60` | Cache normalized popular queries only (allowlist params, sort keys); `No-Vary-Search` for tracking params | Result cache for head queries; cache the underlying facet counts | 30 s–10 min | TTL plus index-update events | Cardinality explosion → low hit rate, memory churn |
| 14a | Media: user uploads / originals | `public, max-age=31536000, immutable` (content-addressed IDs) | CDN + tiered cache/shield; image CDN variants | n/a | 1 year | New ID on change; purge on takedown | Private media needs signed URLs, not `public` |
| 14b | Video VOD segments (HLS/DASH `.ts/.m4s`) | Long `max-age`, immutable | CDN with shield; check max cacheable object size | n/a | Days–1 year | Immutable | Origin egress on the long tail |
| 14c | Live manifests (`.m3u8`/`.mpd`) | `max-age` ≈ ½ segment duration or `no-cache` | Very short `s-maxage` (1–2 s) + request collapsing | n/a | ≈ segment/2 | TTL | Stale manifest stalls playback |
| 15 | Session state / auth tokens / rate-limit counters | `no-store` | Bypass | Redis as primary-ish store (session) with persistence/replication; atomic `INCR` for counters | Session lifetime | Logout/rotation deletes key | Cache used as the only store for critical state |
| 16 | Expensive aggregates (reports, counts, leaderboards, recommendations) | `private` or public depending on audience | Public aggregates can be CDN-cached briefly | Precompute/materialize (Redis sorted sets, materialized views) + scheduled refresh | Minutes–hours | Scheduled or event-driven recompute | Recompute storms; show "as of" timestamps |
| 17 | Third-party API responses (rate-limited, paid) | n/a | n/a | Cache-aside honoring the provider's `Cache-Control`/terms; negative caching for 404s | Per provider terms | TTL; webhooks | ToS violations; caching errors |
| 18 | Feature flags / remote config | `no-cache` | Edge config/KV with push updates | In-process cache with streaming updates | Seconds | Push/stream | Kill-switch latency |
| 19 | LLM outputs / embeddings / RAG retrievals | `private`/`no-store` for user content | Usually none | Exact-match cache keyed by hash(model, params, prompt) for deterministic calls; embedding cache keyed by hash(content, model version); provider prompt-prefix caching; semantic cache only for public, non-sensitive FAQ-like queries | Hours–days (embeddings: until model change) | Model/prompt version bump in key | Semantic false positives; cross-user leakage |
| 20 | Real-time streams (WebSocket/SSE), presence, collaborative docs | n/a (not HTTP-cached) | Cache only the initial snapshot/bootstrap GET | In-memory state on sharded servers; snapshot cache + op log | n/a | Ops/CRDT updates | Treating live data as cacheable |

**C. Invalidation method selection:**

| Method | Use when | Notes |
|---|---|---|
| Content-addressed URL (hash/version) | The asset can be renamed per change | Zero-cost invalidation; the gold standard (Jake, Harry, MDN) |
| TTL expiry only | Staleness budget ≥ TTL and no event source | Add jitter; add SWR to hide refresh latency |
| Purge by tag / surrogate key | One content change affects many URLs (article → home, section, tag pages, feeds) | Tag every response with entity IDs; purge on publish |
| Invalidate (mark stale + conditional revalidate) | Many URLs share a tag but few changed | Requires ETag/Last-Modified (Cloudflare 2026-09) |
| Purge by prefix/hostname/everything | Deploys, emergencies | Origin-load spike risk; prefer invalidate |
| Versioned/namespaced cache keys (`v42:product:123`) | Schema/serialization change; bulk invalidation of app caches | Old keys age out via TTL/LRU |
| Invalidate-on-write (cache-aside delete) | Default for app/data caches | Race: read-old-then-set after delete; mitigate with short TTL, versioned values, or delayed double-delete (inference) |
| Write-through | Read-heavy and read-after-write critical | Higher write latency (Azure) |
| CDC / event bus (DB changes → invalidate) | Many writers, polyglot services | Decouples writers from cache logic |
| `Clear-Site-Data: "cache"` | Emergency browser-side clear | Not in Safari; Firefox dropped the `"cache"` value in v94; disables caching while active (Harry) |

**D. Cache-worthiness score (simple ROI heuristic for server-side caches):**
`benefit/sec ≈ request_rate × expected_hit_rate × (miss_cost − hit_cost)`. Expected hit rate rises with request concentration and with TTL relative to the inter-request interval per key. It falls with variant cardinality and write frequency. Cache only when the benefit is material **and** staleness ≤ budget **and** a safe key exists (scoped by tenant/user where needed). If the miss cost is high because of an unindexed or N+1 query, fix the query first.

### Gaps
- The web.dev Cache-Control flowchart is an image and could not be read. The question order above is a reconstruction.
- No vendor publishes a canonical "data type → numeric TTL" table. All TTLs in the matrix are synthesized starting points.
- AWS "Caching best practices" (lazy loading vs write-through, TTL jitter, Russian-doll caching) could not be fetched this session. The equivalent concepts are cited from Azure and Redis instead.

## 3. Per-archetype blueprints: layer-by-layer recommendations and case studies

### Takeaway
Archetypes differ mainly in four things: the share of traffic that is public, the staleness budget of the hot data, the write rate, and variant cardinality.
- **Static/docs/marketing:** nearly everything is cacheable at the CDN.
- **News/media:** cache aggressively at the CDN with tag purge and SWR.
- **E-commerce:** split catalog (cacheable) from price/stock (short or event-driven) from cart/checkout (never shared).
- **SaaS/internal tools:** mostly private, so caching moves to the data layer with tenant-scoped keys.
- **Social/feeds:** precomputed per-user feeds plus a public object cache.
- **Real-time apps:** cache only the bootstrap snapshot and static assets.
- **Public APIs:** HTTP semantics (ETag/`Cache-Control`/`Vary`) plus rate limits.
- **Video:** immutable segments with shielding.
- **AI apps:** add prompt, embedding and (carefully) semantic caches.

Published case studies (Shopify, Stack Overflow, Wikimedia) all show **multi-tier** designs: in-process L1 → node-local or shared Redis/Memcached L2 → DB, with CDN tiers and purge pipelines in front.

### Cited Findings
- **Shopify storefront rendering:**
  - The renderer stores "the final output (most often an HTML or JSON string) into the local Redis… for subsequent requests that match the same cache key". This is a full-page cache that avoids regenerating responses.
  - The layers are an in-memory cache in the renderer, a **node-local Redis** shared by the workers on a node ("node-local data transfer prevents network overhead"), and DB query-result caching.
  - Source: [Shopify Engineering, Simplify, Batch, and Cache](https://shopify.engineering/simplify-batch-cache-optimized-server-side-storefront-rendering) (snippet via search; full numbers not retrieved)
- **Shopify Shop app:** a custom write-through cache for the home feed "reduced database load by 15% and overall app latency by about 20%" after about six weeks of work. They chose distributed Memcached over Redis because they "didn't need Redis' complexity" — [Shopify Engineering, Shop app caching](https://shopify.engineering/shop-app-custom-caching-solution) (via search snippet)
- **Stack Overflow** describes its app caching for a multi-tenant architecture (2019, Nick Craver) — [Stack Overflow blog](https://stackoverflow.blog/2019/08/06/how-stack-overflow-caches-apps-for-a-multi-tenant-architecture/). A library inspired by it describes Stack Overflow's design as "a custom 2-layer caching solution with in-memory and Redis": L1 `IMemoryCache` plus L2 Redis, with L1 evictions propagated via Redis pub/sub — [L1L2RedisCache](https://github.com/null-d3v/L1L2RedisCache). The L1/L2 detail was not confirmed from Craver's own text this session.
- **Wikimedia CDN:**
  - Two cache layers per data center: frontend Varnish in RAM, and backend ATS on disk with URL-hash routing to a backend. TLS is terminated by ATS.
  - Article edits trigger purges via HTCP (multicast UDP). Wikimedia documented packet loss and races between frontend and backend purges as problems.
  - Sources: [Wikimedia Phabricator T133821](https://phabricator.wikimedia.org/T133821); [O'Reilly 97 Things excerpt](https://www.oreilly.com/library/view/97-things-every/9781492081487/ch10.html)
- **Azure's CDN uses and limits:**
  - Uses: static resources; public JSON/XML datasets for device clients; entire public static sites; video streaming; absorbing surges such as OS-update downloads.
  - Less useful when the data is private. The CDN can be a single point of failure. Local testing is hard. A separate domain can affect SEO. "These features don't replace application-level authorization for private content."
  - Source: [Azure CDN guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/cdn)
- **Azure Redis patterns that fit archetypes:** session state and output cache shared across instances (no server affinity); leaderboards with sorted sets (`ZADD` O(log N)); recency lists with `LPUSH` + `LTRIM`; atomic counters and rate limiters with `INCR`; fire-and-forget for noncritical counters — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Semantic caching for LLM apps (Azure):** it "reduces the number of requests and tokens sent to language models. Only use semantic caching when the data supports semantic equivalence, doesn't risk returning unrelated responses, and doesn't contain private and sensitive data" — [Azure Cache-Aside pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
- **Real-time / trading / betting:** respond with `Cache-Control: no-store` and request with `Cache-Control: no-store`. Add `private` if user-specific. Offline-first apps can request `Cache-Control: only-if-cached`, which returns 504 when the item isn't cached — [csswizardry request header](https://csswizardry.com/2025/03/why-do-we-have-a-cache-control-request-header/)
- **Next.js rendering model (relevant to most JS archetypes):**
  - Static shell plus Suspense-streamed dynamic parts.
  - `'use cache'` with `cacheLife` and `cacheTag` for shared data.
  - `'use cache: private'` for per-user, prefetchable data.
  - ISR headers `s-maxage`/`stale-while-revalidate` for CDNs.
  - Sources: [Next.js caching](https://nextjs.org/docs/app/getting-started/caching); [Next.js CDN caching](https://nextjs.org/docs/app/guides/cdn-caching)
- **Large media:** Cloudflare's default maximum cacheable file size is 5 GB for Enterprise and differs by plan. Responses above the limit return `BYPASS` — [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/); [changelog 2026-05-26](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-05-26-bypass-status-for-uncacheable-responses.mdx). A video-AI company put an in-memory Varnish in front of object storage to cut video latency and found in-memory Varnish "can only scale so large before it becomes cost-prohibitive" — [Matt Basta](https://blog.mattbasta.com/p/making-a-cache-cluster-more-effective) (secondary)

### Inferences
Blueprints use the matrix rows from Section 2 (#n). "Browser / CDN / App / Data" are the layers.

**3.1 Static / marketing / docs (SSG + CDN)**

| Layer | Recommendation |
|---|---|
| Build | SSG or ISR; fingerprint all assets; persist the framework build cache in CI |
| Browser | Assets #1 (`immutable`, 1 y); HTML `no-cache` + ETag (or `max-age=0, must-revalidate`) |
| CDN | HTML `s-maxage` long (1 d–1 y) + purge on deploy/publish (or invalidate); SWR 1 d; `stale-if-error` 1 week; strip/normalize `utm_*` from the key; `No-Vary-Search: params=("utm_source" …)` as enhancement |
| App/Data | None, or CMS fetch cache with tags |
| Invalidation | Deploy → purge HTML (assets are immutable); CMS webhook → tag purge |
| Extras | Speculation Rules prefetch/prerender, bfcache eligibility (avoid `no-store`), `Clear-Site-Data` emergency page |
| KPIs | CDN hit ratio >95% on HTML (synthesized target), TTFB p75 ≤0.8 s |

**3.2 Blogs / news / media publishers**

| Layer | Recommendation |
|---|---|
| Browser | HTML `no-cache` (or `max-age=0`); assets immutable; images long |
| CDN | Article pages: `s-maxage` hours–days + tag purge on update (tags: article ID, section, author, tag). Fronts/sections: `s-maxage=30–60, stale-while-revalidate=300+`, `stale-if-error` long; request collapsing/origin shield for spikes |
| App | Fragment cache for heavy modules (most-read, related) with short TTLs; Russian-doll fragment keys (`article:{id}:v{updated_at}`) |
| Data | Read replicas plus Redis for counters (most-read via sorted sets) |
| Breaking news | Publish → purge or invalidate tags for the front, section and article within seconds; keep SWR so the purge doesn't stampede the origin; pre-warm the front after purge |
| Paywall/personalization | Keep HTML public; enforce metering/entitlement client-side or at the edge with cookie-stripped cache keys. A public HIT must never contain user state. |
| Reference | Wikimedia's two-tier CDN with purge fan-out shows purge reliability (lost purges, inter-tier races) needs monitoring: track purge-to-visible latency |

**3.3 E-commerce**

| Data | Recommendation |
|---|---|
| Static assets, product images | #1 / #14a; image CDN variants (format and width via normalized Accept) |
| Category/PLP pages | CDN `s-maxage=60–300` + SWR; tags per category and per product; normalize facets (allowlist, sorted); bypass on deep filter combinations if the hit rate is low |
| PDP copy/specs | CDN hours + tag purge on product update |
| Price | Display: short TTL (≤30–60 s) or event purge; recompute at cart/checkout from the source of truth |
| Inventory | Display "in stock/low stock" from a short TTL or event-driven value; **authoritative check at add-to-cart/checkout, never from cache** |
| Personalization (recommendations, geo pricing, logged-in header) | Islands fetched client-side or via `private` endpoints; geo pricing → separate cache key dimension (country) at the CDN, never `Vary: Cookie` |
| Cart, checkout, account, payment | `private, no-cache` (cart) / `no-store` (payment, account details); no shared cache |
| Search | Cache top queries (normalized) briefly; cache facet counts |
| Flash sales / drops | Pre-warm PLP/PDP; SWR + collapsing; queue/waiting room at the edge; stock decrement via atomic Redis `DECR`/Lua with DB reconciliation; keep price and stock out of long-TTL HTML (render them as an island) |
| Reference | Shopify: node-local Redis full-page cache + in-memory + query cache; write-through home-feed cache cut DB load 15% |

**3.4 SaaS dashboards / B2B multi-tenant**

| Layer | Recommendation |
|---|---|
| Browser | App shell and assets #1; HTML shell `no-cache`; API `private, no-cache` + ETag (304s are cheap); client query cache (TanStack Query `staleTime` 30–60 s, refetch on focus) |
| CDN | Assets and the public marketing site only; app/API bypass |
| App/Data | Tenant-scoped keys `t:{tenant}:…` (never derive a key without the tenant ID); per-tenant config/permissions cache (short TTL + invalidate on change); precomputed aggregates/materialized views for heavy reports; L1 in-process for global reference data |
| Isolation | Separate Redis DB/cluster or ACL prefixes per tier for regulated tenants; encrypt per-tenant if required (Azure "partition or encrypt subsets") |
| Consistency | Read-after-write for the editing user (bypass for N seconds after write, or write-through) |
| Pitfalls | Request collapse without `private`; caching permission checks too long (cap the TTL to an acceptable revocation latency) |

**3.5 Social / UGC / feeds**

| Layer | Recommendation |
|---|---|
| Objects (posts, profiles) | Public object cache (Redis/Memcached) keyed by ID + version; CDN for public profile/post pages with short `s-maxage` + SWR |
| Feeds | Precomputed per-user timelines (fan-out on write for most users, fan-out on read for celebrity accounts) in Redis lists/sorted sets; feed endpoints `private` |
| Counters (likes, views) | Redis `INCR` with periodic flush; tolerate staleness; fire-and-forget |
| Media | #14a content-addressed + image CDN |
| Moderation/takedown | Purge-by-key pipeline for the CDN and object caches; audit purge latency |

**3.6 Real-time / collaborative (chat, docs, whiteboards, multiplayer)**
- HTTP caching only for assets and the initial bootstrap (document snapshot GET with ETag, `private`).
- Live state stays in memory on sharded servers (per document/room). Persist snapshots plus an op log, and cache snapshots to speed joins.
- Presence in Redis with TTL keys; WebSocket connection reuse; no CDN caching of live endpoints.
- Respond `no-store` where data is time-critical (Harry's realtime pattern).

**3.7 Public REST / GraphQL APIs**
- REST GET: send `ETag` and `Last-Modified`, and honor `If-None-Match` → 304. Public resources get `public, max-age` + `s-maxage` + SWR; authenticated ones get `private`. Use `Vary` only on real negotiation headers (`Accept`, `Accept-Language`), never `Authorization`; per-user data must be `private`.
- Version resources in URLs for immutable representations.
- GraphQL: POST is not CDN-cacheable. Use persisted queries over GET with a hash key, response-level `Cache-Control` computed from the minimum field max-age, and a normalized client cache.
- Server: DataLoader request-scoped batching/caching plus entity caches.
- Rate limits: Redis counters.
- Document caching semantics in the API reference.

**3.8 Mobile app backends**
- Clients cache aggressively: the OS HTTP cache (`URLCache`/OkHttp cache honor `Cache-Control`) and an offline DB. Use ETags so 304s save cellular data.
- Config/feature flags via CDN-backed JSON with a short TTL.
- Version API responses and support multiple app versions (keys include API version).
- Image CDN with device-appropriate variants. Use `only-if-cached`-style offline-first reads.

**3.9 Internal tools / admin panels**
- Low traffic, so the ROI of HTTP/CDN caching is small. Default to `private, no-cache`, or `no-store` for sensitive admin data.
- Cache only expensive reference lookups and reports server-side.
- Avoid stale data that drives wrong operator actions.
- Main lever: fix queries; maybe a client query cache.

**3.10 AI/LLM-powered apps**
- Layers:
  1. Provider prompt (prefix) caching: put stable system prompts, tools and documents first.
  2. Exact-match response cache for deterministic or idempotent calls, keyed by `hash(model, version, params, normalized prompt, tool schema)`.
  3. Embedding cache keyed by `hash(chunk content, embedding model)`, valid until the model changes.
  4. Retrieval-result cache for popular queries.
  5. Tool/API result caches.
  6. Semantic cache only for public, non-personalized Q&A, with a similarity threshold and evaluation (Azure caveat).
- Streamed responses are not CDN-cacheable. User-content responses are `private`/`no-store`.
- Track token savings and cache hit rate.

**3.11 Media / video streaming**
- VOD segments and init files: immutable, long TTL; origin shield / tiered cache to protect object storage.
- Manifests: TTL tied to segment duration for live, longer for VOD.
- Respect plan cacheable-size limits.
- Range-request behavior at the CDN.
- Signed URLs/cookies for protected content: the cache key must exclude the signature while still validating it at the edge (inference).
- Thumbnails via image CDN.

**3.12 Cross-archetype "edge personalization" pattern:** cache a public shell, personalize via islands, edge-side key dimensions with low cardinality (country, language, device class, AB bucket), and never key on raw cookies.

### Gaps
- Primary engineering write-ups for Discord, Figma, Notion, GitHub, Etsy, The Guardian, NYTimes and BBC caching layers could not be retrieved (fetch blocked; searches did not surface them). The archetype blueprints for social, real-time, news and collaboration rely on vendor documentation and practitioner synthesis rather than those case studies.
- The Shopify and Stack Overflow details come from search snippets and a third-party README, not from full-text reads.
- Provider prompt-caching specifics (TTLs, minimum token counts, pricing) were not researched here; another notes file likely covers them.
- Cloudflare AI Gateway caching changelogs (2026-09-09 custom cache token costs; 2026-06-24 AI Search similarity cache controls) exist in the docs repo but were not read.

## 4. When NOT to cache, and anti-patterns

### Takeaway
Don't cache in these cases:
- The data is sensitive or security-critical.
- Personalized responses would go to a shared cache.
- The staleness budget is zero and there is no reliable invalidation.
- Most requests would miss (long tail or high cardinality).
- The "expense" is really a fixable slow query.
- The cache would become the only copy of critical data.

The most damaging HTTP anti-patterns are: short `max-age` on interdependent mutable resources; `public` with `Authorization`; `Vary: Cookie`/`User-Agent`; `immutable` on unversioned files; kitchen-sink `no-store` everywhere (it kills bfcache); and a single TTL for everything.

### Cited Findings
- **Short `max-age` on mutable, interdependent resources** produces version mismatches (Jake's HTML/CSS/JS example). Users only escape it by refreshing. A service worker can extend the life of such bugs — [Jake Archibald](https://jakearchibald.com/2016/caching-best-practices/)
- **HTML and busting (Harry Roberts):**
  - "Generally speaking, caching HTML… is a bad idea. HTML URLs can't be busted… you'll end up caching the references to your static assets." This holds without a managed, purgeable cache.
  - Different cache policies on different HTML page types cause inconsistencies.
  - Never apply `immutable` to files that aren't immutable.
  - Query-string cache busting can be stripped or normalized by CDNs.
  - Source: [csswizardry](https://csswizardry.com/2019/03/cache-control-for-civilians/)
- **`public` on `Authorization` responses** causes shared caches to store them — [csswizardry](https://csswizardry.com/2019/03/cache-control-for-civilians/); MDN recommends `public` "only if there is a need to store the response when the Authorization header is set" — [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- **`no-store` everywhere:** it loses bfcache and other platform features, and does not remove already-stored responses. Use `private` rather than `Vary: Cookie`, and avoid `Vary: User-Agent` — [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- **Using the cache as the system of record** is an anti-pattern. So is making the app depend on cache availability: it "shouldn't become unresponsive or fail while waiting for the cache service" — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Cache-aside is unsuitable** for sensitive data, static datasets (prime them instead), and workloads where most requests miss — [Azure Cache-Aside](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
- **Why teams skip caching** ("simpler… works adequately under low loads", unclear trade-offs, freshness concerns, on-prem migrations, unawareness of ETags). When adding caching for computations, "first instrument… to determine whether the application is really CPU bound" — [Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)
- **`No-Vary-Search: except=(…)`/`except=()`** is "the easiest way to shoot yourself in the foot". Unknown params should bust the cache by default — [csswizardry](https://csswizardry.com/2026/05/better-browser-caching-with-no-vary-search/)
- **`Clear-Site-Data` on all HTML** "effectively disabl[es] caching for your site the whole time". It is not supported in Safari/iOS, and Firefox removed the `"cache"` directive in v94 — [csswizardry](https://csswizardry.com/2023/10/clear-cache-on-customer-device/)
- **Build-cache poisoning:**
  - GitHub warns not to store tokens or credentials in cache paths, because anyone with read access can open a PR and read caches.
  - Since 2026, runs triggered by low-trust events get read-only access to default-branch caches.
  - Source: [GitHub dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
  - Nx warns about cache poisoning and recommends read-only tokens except on protected branches — [Nx cache security](https://github.com/nrwl/nx/blob/master/astro-docs/src/content/docs/kb/cache-security.mdoc)
- **Kitchen-sink headers** (`no-store, no-cache, max-age=0, must-revalidate, proxy-revalidate`) are legacy workarounds. Prefer `no-cache` (+`private`) — [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

### Inferences
**Anti-pattern catalog for the skill (with detection and fix):**

| Anti-pattern | Detection signal | Fix |
|---|---|---|
| Personalized HTML/API cached at the CDN | Shared-cache HIT on routes that read cookies/session; `Set-Cookie` or user names in a cached body; `s-maxage` on authenticated routes | `private`; split shell and island; strip cookies on public paths; cache key excludes cookies; CDN bypass on auth cookie |
| Web cache deception / poisoning | CDN caches by extension (e.g., `/account.css` path confusion); unkeyed headers (`X-Forwarded-Host`) reflected in cached responses | Cache only explicit path patterns; origin returns `private`/`no-store` on auth routes regardless of extension; key or strip reflected headers (practitioner knowledge; e.g., PortSwigger research) |
| One TTL for everything | Single global `max-age`/`expires` in nginx or CDN default | Per-class policy matrix |
| Short `max-age` on unversioned, interdependent assets | `max-age=600` on `style.css`/`app.js` without hashes | Fingerprint + `immutable`; HTML `no-cache` |
| Caching to hide slow queries | Cache added in front of a query with a full scan / N+1; low hit rate; p95 unchanged on misses | Index, batch, denormalize first; then cache if still hot and expensive |
| Premature caching | Low traffic; no metrics; cache code paths without hit/miss instrumentation | Measure first (Azure steps); instrument hit/miss |
| Cache as source of truth | Data written only to Redis without persistence or replication | Persist to the DB; Redis persistence is not backup (Azure) |
| No stampede protection | Latency spikes and DB CPU spikes at TTL boundaries; synchronized expiries after deploy/flush | Jitter, single-flight, SWR, early refresh |
| Cache key without tenant/user scope | Keys like `report:42` in multi-tenant code | Prefix tenant/user; code-review rule |
| `Vary: Cookie` / `Vary: User-Agent` | Response headers | `private`, or normalized device buckets |
| `no-store` on every page | Global middleware sets `no-store` | `no-cache, private` for personalized pages; regain bfcache |
| Unbounded cache growth | No TTL; `noeviction` with OOM write failures | TTL + eviction policy aligned to key usage |
| Purge-everything on every deploy | Origin spike after each deploy | Hashed assets need no purge; tag purge for changed content; invalidate (revalidate) instead of purge |
| Caching errors/empty results by accident | 5xx/404 cached with long TTL | Short negative-cache TTLs; `stale-if-error` instead |
| Ignoring query-string chaos | Many keys differing only by `utm_*`/`fbclid` | CDN key normalization; `No-Vary-Search` |

**When not to cache at all:** mutation endpoints; one-time tokens and OTPs; payment and auth flows; data with legal freshness requirements; truly unique per-request responses; very low-traffic internal tools (cost and complexity without benefit); and anything the team cannot invalidate or observe.

### Gaps
- No primary source in this session documents web cache deception or poisoning (e.g., PortSwigger/Omer Gil research). Those rows are from practitioner knowledge and should be cited separately if the security notes file covers them.

## 5. Prioritization: sequencing caching work by ROI and measuring success

### Takeaway
Sequence the work as follows:
1. Fix correctness and safety problems (leaks).
2. Add the near-free wins: hashed assets with `immutable`; explicit default headers plus validators.
3. Put public HTML/API behind the CDN with SWR and tag purge.
4. Reclaim bfcache and add speculative loading.
5. Add server-side data caching for measured hot, expensive reads.
6. Do the advanced tuning: key normalization, `No-Vary-Search`, tiered cache, service workers, build/CI caching.

Measure each step against the baseline: hit ratios that exclude BYPASS, origin RPS/CPU, p95, TTFB/LCP p75, CrUX navigation-type shares, DB QPS and cost.

### Cited Findings
- "The best request is the one that never happens… avoiding the network is far better than hitting the network at all." Solve cache busting before writing caching policy — [csswizardry](https://csswizardry.com/2019/03/cache-control-for-civilians/)
- **Versioned URLs** let browsers skip the network entirely for a year; build tools such as webpack automate hashing — [web.dev](https://web.dev/articles/http-cache)
- **bfcache and Prerender** give near-instant navigations and are "much cheaper optimisations than we're commonly told to implement". The goal is to raise the bfcache, Prerender and (where appropriate) Cache shares in CrUX — [csswizardry Cache Grab](https://csswizardry.com/2024/08/cache-grab-how-much-are-you-leaving-on-the-table/)
- `no-store` makes pages ineligible for some platform features, including bfcache — [MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- TTFB target ≤0.8 s at p75 — [web.dev TTFB](https://web.dev/articles/ttfb)
- Instrument hit and miss; load-test to validate; adding a cache can shift the bottleneck to the front end — [Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)
- Example outcome: Shopify's Shop app home-feed write-through cache cut DB load about 15% and app latency about 20% in roughly six weeks — [Shopify Engineering](https://shopify.engineering/shop-app-custom-caching-solution)
- **Accurate Cloudflare hit ratio:** since 2026-05-26 `BYPASS` marks uncacheable responses and `MISS` only cacheable misses. Compute the cacheable hit ratio as HIT / (HIT + MISS + EXPIRED…), and track BYPASS separately as the opportunity size — [Cloudflare changelog](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-05-26-bypass-status-for-uncacheable-responses.mdx)
- Cloudflare's 2026 invalidate (revalidate) option avoids re-downloading unchanged content after a broad tag invalidation. This reduces origin egress compared with purge — [Cloudflare changelog](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-09-28-cache-invalidation.mdx)

### Inferences
**ROI-ordered roadmap (default order; reorder by the audit's findings):**

| Phase | Change | Effort | Typical impact | Risk |
|---|---|---|---|---|
| 0 | **Safety fixes:** remove shared caching of personalized/sensitive responses; add `private`/`no-store` where needed; strip `Set-Cookie` from public cached responses | Low | Prevents data leaks (P0) | Low |
| 1 | **Hashed static assets** → `public, max-age=31536000, immutable`; serve via CDN; keep N previous builds' assets available | Low | Large repeat-view and bandwidth win; fewer 304s | Low (requires hashing) |
| 2 | **Explicit default `Cache-Control` on every response** (`no-cache`, plus `private` where personalized) and **validators** (ETag/Last-Modified) on HTML/API | Low | Kills heuristic caching surprises; cheap 304s | Low |
| 3 | **CDN for public HTML / public API** with `s-maxage` + `stale-while-revalidate` + `stale-if-error`; tag/surrogate-key purge on publish; cache-key normalization (query allowlist, strip tracking params, ignore cookies on public paths) | Medium | Biggest origin offload and TTFB win for content sites | Medium (needs a correct audience classification) |
| 4 | **bfcache and speculation:** remove `no-store` from navigations that don't need it, fix bfcache blockers; add Speculation Rules prefetch/prerender | Low–Med | Near-instant back/forward and next-page navigations | Low |
| 5 | **App/data caching** for top N expensive and hot reads (cache-aside with jitter + single-flight; L1+L2 for ultra-hot); precompute aggregates | Medium | Lower DB load and p95 | Medium (consistency) |
| 6 | **API HTTP caching:** ETags/304 for authenticated APIs; client query caches (`staleTime`) | Low–Med | Fewer bytes, smoother UX | Low |
| 7 | **Advanced:** origin shield/tiered cache; `No-Vary-Search`; service-worker offline caching; edge KV for config; micro-caching hot dynamic routes | Medium | Incremental | Medium |
| ∥ | **Build/CI caching** (parallel track): dependency cache, Docker layer cache, Turborepo/Nx remote cache, framework build cache | Low–Med | Faster CI, cheaper builds | Cache-poisoning controls |

**Success measurement (before/after, same window and traffic mix):**

| KPI | How | Target direction (synthesized targets) |
|---|---|---|
| CDN cacheable hit ratio (requests and bytes) | CDN analytics excluding BYPASS | ↑ (static ≥95%, public HTML ≥80–90% for content sites) |
| Origin RPS and egress | Origin logs/billing | ↓ |
| p95/p99 latency per route (hit vs miss split) | APM | ↓ |
| TTFB p75, LCP p75 | RUM/CrUX | TTFB ≤0.8 s; LCP into "good" |
| CrUX navigation types | CrUX | bfcache share ↑, Back–Forward (non-bfcache) ↓, Prerender ↑ |
| DB QPS / CPU / top-query counts | DB stats | ↓ on cached queries |
| Redis hit rate, evictions, memory | `INFO` | Hit rate ↑; evictions stable |
| Staleness incidents / purge-to-visible latency | Synthetic checks after publish | Within budget (e.g., <30 s for news) |
| Error rate during origin incidents | `stale-if-error` effectiveness | ↓ user-visible 5xx |
| CI duration and cache hit rate | CI logs | ↓ duration |

### Gaps
- No primary source publishes a quantitative ROI ranking of caching interventions. The phase order is practitioner consensus drawn from the cited guidance.
- The LCP "good" threshold (2.5 s at p75) is widely published but was not re-read from a primary source this session.

## 6. Deliverable template: contents of a good caching plan / cache policy matrix, plus rollout and verification checklist

### Takeaway
The plan should be one document containing:
- An app profile.
- Baseline metrics.
- Constraints (sensitivity, consistency).
- A **per-resource policy matrix** with columns for route pattern, data class, audience, layer, key and `Vary`, browser and shared directives, app TTL, SWR/SIE, invalidation trigger and mechanism, tags, staleness budget, owner and verification command.
- An invalidation map (event → tags/keys).
- Failure-mode safeguards.
- A phased rollout with verification and rollback.

Prior-art agent skills (Vercel's) require each recommendation to name its mechanism, scope, TTL/freshness and `Vary`, and to justify safety for shared caches.

### Cited Findings
- **Vercel's agent skill verification format:** "Name GET share, cache mix, file line, and policy: mechanism, scope, TTL/freshness, and `Vary`. If the right policy is `no-store`, emit no-change/observation." The Next.js variant requires naming "the detected Next.js version and exact cache primitive or route header" — [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md)
- **Key design:** use structured keys (`customer:100`, `orders:100`) and Redis hash tags for co-located keys in clusters — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- **Expiration must match access patterns** in cache-aside. Configure expensive items individually — [Azure Cache-Aside](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)
- **Testing conditions:** cold, warm and cache-disabled kept separate; record the browser version and DevTools state — [csswizardry 2026-08](https://csswizardry.com/2026/08/when-safaris-ignore-cache-ignored-cache-control/)
- **Invalidation selectors available on modern CDNs:** URL, tag, hostname, prefix, everything, for both purge and invalidate — [Cloudflare changelog 2026-09-28](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/changelog/cache/2026-09-28-cache-invalidation.mdx)

### Inferences
**Caching plan template (Markdown skeleton for the skill to fill):**
```markdown
# Caching Plan — <App> — <date> — v<n>
## 0. Summary
- Archetype: <e.g., e-commerce (Next.js 16 on Vercel + Postgres + Redis)>
- Top 5 changes (ordered by ROI) with expected impact and risk
## 1. App profile
- Stack & versions; hosting/CDN; regions; instances/replicas; data stores; external APIs
- Traffic: RPS peak/mean, top routes share, read:write ratios, spike events
## 2. Baseline (date range, source)
- CDN hit ratio (req/bytes, excl. BYPASS); origin RPS/egress; p95 per top route; TTFB/LCP p75; CrUX nav types; DB top queries; Redis hit/evictions; CI build time
## 3. Constraints
- Sensitive/regulated data classes; consistency requirements (staleness budgets per data class); compliance (PII, PCI, HIPAA, GDPR erasure ⇒ cache purge paths); multi-tenancy isolation
## 4. Cache policy matrix  (one row per route pattern / resource class)
## 5. Layer designs
- Browser & service worker · CDN/edge (cache key rules, shield/tiering, purge API) · Reverse proxy · App (in-process L1) · Shared cache (Redis/Memcached: topology, eviction, persistence, memory budget) · DB (materialized views, read replicas) · Client state (query cache staleTime)
## 6. Invalidation map
| Event (source) | Affected entities | Tags/keys purged/invalidated | Mechanism (API/webhook/CDC) | Expected propagation time | Owner |
## 7. Failure modes & safeguards
- Stampede (jitter/single-flight/SWR) · Cache outage (circuit breaker, fallback limits) · Origin outage (stale-if-error) · Poisoning/deception (key rules, allowlisted paths) · Leak tests · Memory/eviction alarms
## 8. Rollout plan (phases, flags, canary %, success criteria per phase)
## 9. Verification checklist & monitoring (dashboards, alerts, synthetic checks)
## 10. Rollback plan (per change; e.g., set CDN rule to bypass, revert headers, flush namespace by version bump)
## 11. Ownership & review cadence (quarterly review of TTLs vs. staleness incidents)
```

**Policy matrix columns (with an example row):**

| ID | Route / resource pattern | Method | Data class (§2 #) | Audience | Staleness budget | Layers | Cache key (+Vary, normalization) | Browser `Cache-Control` | Shared directive (`s-maxage` / `CDN-Cache-Control`) | App/data TTL | SWR / SIE | Invalidation trigger → mechanism | Tags / surrogate keys | Owner | Verify | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `/_next/static/*` | GET | 1 | public | ∞ (versioned) | Browser, CDN | URL | `public, max-age=31536000, immutable` | same | — | — | new hash per build | — | web | `curl -sI …` shows immutable | ✅ |
| R2 | `/products/[slug]` | GET | 4 + 10 (island) | public shell | copy 1 h; price 60 s | CDN, app | path; query allowlist `variant`; ignore `utm_*` | `no-cache` | `s-maxage=3600, stale-while-revalidate=86400` | `cacheLife('hours')` + `cacheTag('product:{id}')` | SWR 1 d / SIE 1 d | product update webhook → `revalidateTag('product:{id}')` + CDN tag invalidate | `product:{id}`, `category:{id}` | catalog | 2× curl shows HIT, Age↑; purge test < 30 s | planned |
| R3 | `/api/cart` | GET | 7 | private | 0 | browser (validators only) | — | `private, no-cache` | none (bypass) | — | — | — | — | checkout | two-session leak test | planned |
| R4 | `/checkout/*` | GET/POST | 8 | private | 0 | none | — | `no-store` | bypass | — | — | — | — | checkout | no Age/HIT ever | planned |

**Rollout and verification checklist:**
1. **Pre-flight:**
   - Baseline captured.
   - The matrix is reviewed by the data owner for staleness budgets and by security for the audience classification.
   - The purge/invalidate API is tested in staging.
   - Feature flags or CDN rules exist so each change can be toggled.
2. **Header verification** (per route class): `Cache-Control`/`CDN-Cache-Control` match the matrix. No `Set-Cookie` on publicly cached responses. `ETag`/`Last-Modified` are present on revalidated resources. `Vary` is minimal and correct.
3. **Leak tests:**
   - Request each personalized route as user A, then user B, then anonymously; verify no shared-cache HIT carries A's data.
   - Run path-confusion probes (e.g., `/account/x.css`) to confirm the CDN does not cache auth routes by extension.
   - Check unkeyed-header reflection.
4. **Hit behavior:** a second request shows HIT and `Age` increments. A conditional request returns 304. Query-param variants map to the intended keys.
5. **Invalidation tests:** publish/edit in staging → measure purge-to-visible time. Verify SWR serves stale while revalidating, and that `stale-if-error` serves when the origin is down.
6. **Load test:** cold-cache plus spike scenario; confirm single-flight/SWR prevents origin overload and that cache-down fallback degrades gracefully (Azure).
7. **Canary:** roll out per route class at a small traffic percentage. Watch error rate, hit ratio, origin RPS and user-reported staleness.
8. **Monitoring:**
   - Dashboards for hit ratio (excluding BYPASS), origin RPS, p95, Redis hit/evictions/memory, and purge failures.
   - Alerts on hit-ratio drops, eviction spikes and purge API errors.
   - A synthetic "freshness probe" that edits a canary record and checks it propagates within budget.
9. **Rollback:** CDN rule → bypass; revert headers; bump the cache namespace version to discard poisoned or wrong entries; keep previous asset builds deployed.
10. **Post-rollout review:** before/after report on the Section 5 KPIs; update TTLs where staleness incidents or low hit rates appear.

### Gaps
- I found no published industry-standard "caching plan" template. The template above synthesizes the cited guidance and the Vercel agent-skill verification format.

## 7. Adjacent caching layers: build/CI, package managers, DNS, TLS resumption and 0-RTT, connection reuse, OS page cache

### Takeaway
These layers are brief but high-leverage.
- **CI:** cache dependencies keyed on lockfile hashes, use BuildKit layer and cache-mount caching with an external backend, and use Turborepo/Nx remote caches. Treat cache writes as a trust boundary: read-only for untrusted triggers, no secrets in caches.
- **DNS:** lower TTLs at least one current-TTL period before migrations (commonly 24–48 h ahead, to about 300 s), then restore them.
- **TLS:** use session resumption, and allow 0-RTT only for idempotent requests.
- **Connections:** keep-alive and pooling to origins and caches.
- **OS:** rely on the page cache for hot static files and size memory accordingly.

### Cited Findings
- **GitHub Actions cache limits:**
  - Default 10 GB per repository, configurable up to 25 GB.
  - Eviction deletes "in order of last access date, from oldest to most recent".
  - If you exceed the limit, GitHub saves the new cache and then evicts.
  - Source: [GitHub dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- **GitHub Actions key matching:**
  - `key` is matched exactly, then by prefix, then `restore-keys` are tried in order.
  - The current branch is searched first, then the default/base branch.
  - PR caches are scoped to the merge ref and are restorable only by re-runs of that PR.
  - `setup-node` (npm/Yarn/pnpm), `setup-python` (pip/pipenv/Poetry) and others provide built-in caching.
  - Source: [GitHub dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- **GitHub Actions cache trust model (current docs):**
  - Only `push`, `workflow_dispatch`, `repository_dispatch`, `delete`, `registry_package`, `page_build` and `schedule` can create or overwrite caches in the default branch's scope. Other triggers resolving to the default branch get read-only access, and a save fails with a warning only.
  - A new `cache-mode` key (`read` | `write` | `write-only`) at workflow or job level grants least-privilege cache access. Explicit `write` on untrusted triggers "reintroduces the risk of cache-poisoning".
  - Use `actions/cache/restore` in low-trust workflows.
  - Don't store tokens or credentials in cached paths.
  - Source: [GitHub dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- **Docker BuildKit:**
  - Optimization levers: order layers (least-changing first), keep the build context small (`.dockerignore`), use bind mounts, use **cache mounts** (`RUN --mount=type=cache,…` so package managers download only new or changed packages), and use an external cache.
  - Source: [Docker build cache optimization](https://docs.docker.com/build/cache/optimize/)
  - Backends: `inline`, `registry`, `local`, `gha`, `s3`, `azblob`. All except the always-on local BuildKit cache must be explicitly exported and imported. Cache export `mode=min` (default) or `mode=max`.
  - Source: [Docker cache backends](https://docs.docker.com/build/cache/backends/); the `gha` backend (`scope`, `mode`, v2 URL) — [Docker GHA cache backend](https://docs.docker.com/build/cache/backends/gha/)
- **Turborepo** caches to the local filesystem by default, so identical tasks re-run on every machine without a remote cache. Remote Caching is "free to use on all plans" with Vercel even if apps aren't hosted on Vercel, or can be self-hosted. "Turborepo treats logs as artifacts", so watch for secrets in task logs — [Turborepo remote caching](https://turborepo.dev/docs/core-concepts/remote-caching)
- **Nx:**
  - Remote caches carry a cache-poisoning risk.
  - Use read-write tokens only on protected branches and read-only everywhere else.
  - Don't put CI tokens in `nx.json`.
  - Personal access tokens allow per-developer access control. Unauthenticated access can be restricted to read-only.
  - Source: [Nx cache security](https://github.com/nrwl/nx/blob/master/astro-docs/src/content/docs/kb/cache-security.mdoc)
- **Next.js** requires persisting `.next/cache` between CI builds; examples key on the lockfile checksum — [Next.js CI build caching](https://nextjs.org/docs/app/guides/ci-build-caching)
- **DNS TTL:**
  - Longer TTLs mean faster lookups and more cache hits, but slower propagation of changes.
  - Cloudflare proxied records are fixed at Auto = 300 s. DNS-only records allow 30 s (Enterprise) or 60 s (others) up to 1 day. Local resolvers may still take longer than 5 minutes.
  - Source: [Cloudflare DNS TTL](https://developers.cloudflare.com/dns/manage-dns-records/reference/ttl/)
- **DNS migrations:** lower the TTL well ahead, because the TTL change itself is cached under the old TTL. For example, a record at 14,400 s changed to 300 takes up to 4 h to propagate. Common practice is 24–48 h ahead (or at least one full current TTL), lowering to about 300 s, then restoring to 3,600 s or more after verification. These are conventions, not a standard — [CanSpace KB](https://www.canspace.ca/clients/knowledgebase/101/TTL-and-when-to-lower-it-before-a-DNS-change.html); [APIVerve TTL best practices](https://apiverve.com/marketplace/dnspropagation/learn/ttl-best-practices)
- **TLS 1.3 0-RTT:**
  - Early data can be replayed.
  - Allow it only for idempotent requests (e.g., GET) and force a full 1-RTT handshake for state-changing requests.
  - Proxies (e.g., nginx) may forward early-data requests without a marker unless one is configured (e.g., an `Early-Data` header with a 425 response).
  - Make non-idempotent endpoints idempotent with request tokens.
  - Sources: [Cloudflare TLS 1.3 overview](https://blog.cloudflare.com/tls-1-3-overview-and-q-and-a/); [StackHarbor 0-RTT trade-offs](https://stackharbor.com/en/knowledge-base/dnstls-tls13-zero-rtt-tradeoffs/) (secondary)
- **Redis client connections:** create the connection once and reuse it ("Don't reconnect and disconnect each time you perform a Redis operation"). Co-locate the cache and the app in the same region — [Azure caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)

### Inferences
**Build/CI caching checklist:**

| Layer | Key / config | Notes |
|---|---|---|
| Package manager cache | `actions/setup-node` `cache: pnpm` (store `~/.local/share/pnpm/store` or `pnpm store path`), npm `~/.npm` with `npm ci`, Yarn Berry `.yarn/cache`, pip `~/.cache/pip`, Poetry/uv caches, Go `~/go/pkg/mod` + `~/.cache/go-build`, Maven `~/.m2/repository`, Gradle `~/.gradle/caches` (or `gradle/actions/setup-gradle`), Cargo `~/.cargo/registry` + `target/` (sccache) | Key = OS + tool version + lockfile hash; `restore-keys` prefix fallback; never cache `node_modules` across Node versions |
| Docker layers | `docker/build-push-action` with `cache-from/cache-to: type=gha,mode=max` or `type=registry,ref=…:buildcache,mode=max`; `RUN --mount=type=cache,target=/root/.npm` | Copy lockfile → install → copy source (layer order); `.dockerignore` |
| Monorepo task cache | Turborepo (`turbo.json` `inputs`/`outputs`, env hashing, `TURBO_TOKEN`/`TURBO_TEAM`), Nx (`namedInputs`, Nx Cloud or self-hosted) | Read-only tokens for PRs/forks; verify outputs are deterministic |
| Framework build cache | `.next/cache`, Gatsby `.cache` + `public`, Astro `node_modules/.astro`, Vite `node_modules/.vite`; Vercel/Netlify persist these automatically on their platforms (practitioner knowledge) | Key on lockfile + config hash |
| Bazel | `--remote_cache=grpcs://…` / `--disk_cache`; hermetic actions | Upload only from trusted CI |
| Security | Least-privilege `cache-mode`; no secrets in cached paths or logs; separate caches for release builds | Treat the cache as a supply-chain input |

**Network/OS layers (brief practitioner guidance):**
- **DNS:** steady-state TTL 1 h–1 day for stable records. Use 60–300 s for records behind failover or load-balancing health checks. Before migrations, lower to about 300 s at least one old-TTL period in advance, then restore. CNAME chains multiply lookups; use `dns-prefetch`/`preconnect` for critical third-party origins.
- **TLS:** enable session resumption (tickets/PSK with rotated keys) at the CDN and origin; 0-RTT only for GET/HEAD; prefer TLS 1.3, HTTP/2 or HTTP/3 for multiplexing.
- **Connection reuse:** HTTP keep-alive and connection pooling between CDN↔origin and app↔DB/Redis/upstream APIs (`keepalive` in nginx upstreams; HTTP agents with keepAlive in Node; DB poolers such as PgBouncer/RDS Proxy/Hyperdrive). Cold connection setup often dominates TTFB on uncached misses.
- **OS page cache:** static files served by nginx/Varnish benefit from RAM sized above the hot working set (`sendfile`, `open_file_cache` in nginx). Databases rely on the page cache plus their buffer pool; don't starve it with oversized in-process caches in the same container. Watch container memory limits: the page cache counts toward cgroup memory but is reclaimable.

### Gaps
- Default package-manager cache paths, Vercel/Netlify automatic build-cache behavior, Bazel remote-cache flags, TLS session-ticket rotation guidance and nginx keepalive/`open_file_cache` tuning are from practitioner knowledge and were not re-verified against primary docs this session.
- GitHub's documentation (as read) did not state a fixed inactivity-based eviction window for Actions caches beyond the size-based last-access eviction policy, so this notes file does not claim one.
- DNS-migration lead times come from hosting-provider knowledge-base articles (conventions), not an RFC.
