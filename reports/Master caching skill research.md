# Route, classify and verify every cache layer

A master caching skill should be a **thin, safety-first router rather than an encyclopedia**: a SKILL.md under 500 lines that opens with ten standing safety rules, runs a deterministic stack-detection script, sends every route through one ten-step decision tree (method, sensitivity, audience, versionability, staleness budget, invalidation, variants, cost × popularity, write consistency, failure mode) and emits a plan from a fixed template that a validator script checks, while about **48 focused reference files** carry the layer, framework, CDN, CMS and platform detail and load only when the detected stack needs them. No existing skill fills this role, because today's caching skills each cover one vendor or one layer (Vercel's Next.js skills and `vercel-optimize`, Cloudflare's router and `web-perf`, Redis's data-structure and semantic-cache skills, Addy Osmani's performance skill), and none designs a coordinated browser-to-database plan for an arbitrary stack such as Rails, Django, Laravel, Spring, .NET or Go behind CloudFront, Fastly, Akamai or nginx. The stakes are correctness as much as speed: misconfigured caches exposed about 34,000 Steam users' pages in 2015 and cached authenticated responses at Railway in March 2026, and frameworks keep shipping cache-poisoning CVEs, so the skill must default to `no-store`, make every route opt in and prove safety with leak tests. Its content must also survive constant drift, since Next.js 16's two caching models, SvelteKit 3, Astro 7, React Router 8, five Cloudflare cache changes and CloudFront tag invalidation all landed in 2025–26, so every reference needs version-keyed guidance and a review date. Structurally, the skill should use only the six frontmatter fields of the open Agent Skills standard so that one folder installs in Claude Code, claude.ai, the API and the rest of the roughly 46 agent clients that support the standard, ship scripts that need only the Python standard library because the API sandbox has no network or package installs, and be built eval-first against one small fixture repo per app archetype.

## Existing skills stop at one vendor while cache mistakes leak data

As of October 2026, plenty of caching knowledge is packaged as agent skills, but every piece is shaped by a single vendor or a single layer.

| Skill (owner) | What it covers | What it leaves out |
|---|---|---|
| `next-cache-components-adoption`, `-optimizer` and a partial-prefetching pair (Vercel, inside the Next.js repo) ([vercel/next.js skills](https://github.com/vercel/next.js/tree/canary/skills)) | Next.js Cache Components workflows | Everything outside Next.js |
| `vercel-optimize` v1.2.0 (Vercel) ([vercel-optimize](https://github.com/vercel-labs/agent-skills/tree/HEAD/skills/vercel-optimize)) | Cost and performance on Vercel, starting from metrics; a 322-line SKILL.md with 15 scripts | Other hosts and non-JavaScript backends |
| `cloudflare` umbrella and `web-perf` (Cloudflare) ([cloudflare/skills](https://github.com/cloudflare/skills); [web-perf](https://github.com/cloudflare/skills/blob/HEAD/skills/web-perf/SKILL.md)) | Routing across Cloudflare products via 139 bundled files; flags weak `Cache-Control` and `ETag` headers | No dedicated reference on cache rules or the Cache API |
| `redis-core`, `redis-connections`, `redis-semantic-cache` (Redis) ([redis/agent-skills](https://github.com/redis/agent-skills)) | Data structures, RESP3 client-side caching, LLM semantic caching | HTTP and CDN layers |
| `performance` (Addy Osmani) ([web-quality-skills](https://github.com/addyosmani/web-quality-skills)) | Standard header recipes and service-worker caching | Stack-specific or server-side design |
| Community Next.js caching skills ([openskillindex](https://openskillindex.com/skills/comeonoliver-skillshub-nextjs-caching)) | Next.js only | Uneven quality; one still calls `'use cache'` experimental |

Anthropic's own skills repo and the official Claude Code marketplace contain no multi-layer caching skill ([anthropics/skills](https://github.com/anthropics/skills); [claude-plugins-official](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)). The open space is the work between these skills. Each one assumes you already know you are on Next.js, Vercel, Cloudflare or Redis. None detects an arbitrary stack, keeps TTLs, cache keys and invalidation consistent from the browser through the CDN, proxy and application cache to the database, or covers Rails, Django, Laravel, Spring, ASP.NET, Go or any CDN beyond Vercel and Cloudflare, and none treats cache security as a hard gate or produces a reviewable plan with a verification loop.

The master skill should own exactly that cross-layer work. For implementation detail it should hand off to vendor skills when they are installed, the pattern Cloudflare's router already uses when it tells Claude to "load named skills when installed" ([cloudflare SKILL.md](https://github.com/cloudflare/skills/blob/HEAD/skills/cloudflare/SKILL.md)).

The safety gate matters because caching incidents keep repeating the same few failures. Each one maps to a rule the skill must enforce.

| Incident | What happened | Rule it implies |
|---|---|---|
| Steam, December 2015 | A caching change "incorrectly enabled caching for authenticated users", so store pages with billing details for **about 34,000 users** may have been served to strangers ([SteamDB](https://steamdb.info/blog/recent-caching-issues-on-steam)) | Authenticated responses carry `private` or `no-store` at the origin, regardless of CDN rules |
| Railway, March 30, 2026 | A change tied to a Surrogate Keys rollout turned on caching for domains whose CDN was off; for 52 minutes "most GET responses without explicit cache headers were cached by default" ([Railway incident report](https://blog.railway.com/p/incident-report-march-30-2026-authenticated-user-data-cached)) | Every response gets an explicit `Cache-Control`, because platform defaults change |
| Slack, February 22, 2022 | A control plane replaced warm memcached nodes with empty spares during a Consul restart; the hit rate collapsed at peak and overwhelmed the Vitess databases ([Slack Engineering](https://slack.engineering/slacks-incident-on-2-22-22/)) | Rate-limit automated cache changes, and size the database for a degraded hit rate |
| Facebook, September 2010 | Clients treated database errors as invalid values and deleted cache keys, which kept the outage going ([Facebook Engineering](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/)) | An error is not a miss; never delete entries because a backend failed |

Frameworks add a steady stream of their own cache bugs. Next.js's September 2026 security release fixed several cache-poisoning issues and told users to move to **16.3.8 or 15.5.27** ([Next.js blog](https://nextjs.org/blog/september-2026-security-release)). Django 6.0.6 and 6.0.7 patched shared-cache leaks. One of them, CVE-2026-48588, let a response that set a session cookie be stored in the shared cache ([Django 6.0.7 notes](https://django.readthedocs.io/en/stable/_sources/releases/6.0.7.txt)).

The second design constraint is drift. Next.js 16 split caching into a Cache Components model and a "previous" model, each with different APIs ([Next.js caching docs](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)). SvelteKit 3 dropped `svelte.config.js` ([SvelteKit 3 migration](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)). Astro 7 made route caching stable ([Astro v7 upgrade](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/upgrade-to/v7.mdx)). Between February and September 2026, Cloudflare made stale-while-revalidate asynchronous, added Cache Response Rules, began reporting `BYPASS` consistently, added `Vary` support to Cache Rules and shipped a soft "invalidate" ([Cloudflare cache changelog](https://developers.cloudflare.com/changelog/product/cache/)). CloudFront added tag-based invalidation in April 2026 ([CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md)).

Even settled advice ages. Guidance from 2023 said Safari lacks `Clear-Site-Data` and Firefox had dropped its `"cache"` directive. Current compatibility data shows Safari 17 supports it and Firefox re-enabled `"cache"` in version 138 ([BCD Clear-Site-Data](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Clear-Site-Data.json)).

Vercel's response to drift was to move its Next.js skills into the framework repo "so they stay version-matched with the framework instead of drifting" ([vercel-labs/next-skills](https://github.com/vercel-labs/next-skills)). A cross-vendor skill cannot live inside every framework's repo. It must instead detect versions, key its guidance to them, and put a review date on every reference file.

## Six audit passes and a ten-step decision tree tailor every plan

Tailoring starts with evidence, not recommendations. Azure's procedure for detecting the "no caching" antipattern makes a good backbone. It has five steps: list the data stores and how often each changes, instrument the live system, profile it, load-test it, and mine statistics for repeated queries. In Azure's worked example, one query ran more than 250,000 times ([Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)). The skill should expand this into six passes.

| Pass | What the skill does | Output |
|---|---|---|
| 1. Fingerprint | Reads exact framework versions from lockfiles; SvelteKit 3 and React Router 8 moved their config conventions, so the version decides where to look. Reads hosting and CDN from deploy configs and infrastructure-as-code, and data stores and replica counts from Docker or Kubernetes manifests. | App profile |
| 2. Inventory | Lists every route with its method, auth requirement, cookies and headers read, query parameters, data sources and write side effects | Resource inventory |
| 3. Live probe (optional) | Fetches each resource class twice, expecting `MISS` then `HIT` with a rising `Age`. Sends a conditional request and expects a 304. Repeats with and without a session cookie, and tries deception URLs. | Header table and leak findings |
| 4. Existing caches | Greps for cache headers, framework primitives, Redis, Memcached and LRU clients, client-side query caches and proxy configs | Inventory of existing caches with keys, TTLs and invalidation |
| 5. Baseline | Collects the metrics listed below, with date range and source | Dated baseline |
| 6. Classify | Runs the decision tree for each resource | Policy-matrix rows |

No authoritative source maps repo files to caching implications, so the skill must encode those fingerprint rules itself.

Probing has traps the skill must spell out. A missing `Cache-Control` header does not mean "don't cache": caches apply heuristic freshness, typically 10% of the time since `Last-Modified`, so every headerless response is a finding ([MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)). Cloudflare's `MISS` also changed meaning on May 26, 2026, when it began reporting `BYPASS` for every uncacheable response and reserving `MISS` for cacheable misses; the useful KPI is therefore a hit ratio over cacheable requests that excludes `BYPASS`, with `BYPASS` volume tracked separately as the size of the opportunity ([Cloudflare changelog](https://developers.cloudflare.com/changelog/post/2026-05-26-bypass-status-for-uncacheable-responses/)). Reloads distort measurements differently per browser, because Chrome sends `max-age=0`, Safari sends `no-cache` plus `Pragma`, and a hard refresh revalidates even `immutable` subresources ([csswizardry](https://csswizardry.com/2025/03/why-do-we-have-a-cache-control-request-header/)), so cold-cache, warm-cache and cache-disabled runs must never be mixed ([csswizardry 2026](https://csswizardry.com/2026/08/when-safaris-ignore-cache-ignored-cache-control/)).

The baseline should record: CDN request and byte hit ratios per path class; origin requests per second and p95 latency per route; the read-to-write ratio per entity; Redis `keyspace_hits`, `keyspace_misses` and `evicted_keys`; time to first byte at p75, against web.dev's 0.8-second "good" threshold ([web.dev TTFB](https://web.dev/articles/ttfb)); and Chrome UX Report navigation types.

The navigation types expose a cheap win most plans ignore: the back/forward cache (bfcache). In Harry Roberts' BBC example, 13.7% of navigations came from the bfcache and another 5.4% were back/forward navigations that missed it, a **71.7% bfcache hit rate** ([csswizardry Cache Grab](https://csswizardry.com/2024/08/cache-grab-how-much-are-you-leaving-on-the-table/)).

Classification rests on three base patterns that MDN, Jake Archibald and Harry Roberts all converge on: immutable, versioned URLs with a one-year `max-age`; mutable URLs that always revalidate, using `no-cache` plus an ETag; and a managed, purgeable shared cache in front of mutable content.

Archibald calls the tempting fourth option, "a smallish max-age and mutable content", "a baaaad compromise". HTML, CSS and JavaScript that depend on each other expire at different moments and fall out of sync ([Jake Archibald](https://jakearchibald.com/2016/caching-best-practices/); [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)). The skill should run every route through the tree below, stop at the first match, and record the deciding step in the plan.

| Step | Question | Outcome when it matches |
|---|---|---|
| 0 | Is the method anything other than GET/HEAD? | `no-store`. On success, run the invalidation hooks for the reads it affects. Stop. |
| 1 | Does the response carry secrets or regulated data (tokens, payments, health data, balances)? | `no-store` and no shared cache. A server-side cache is allowed only if it is tenant- or user-scoped, encrypted, and has a minimal TTL. Stop. |
| 2 | Does the body depend on who is asking (cookie, session, `Authorization`, tenant, entitlement, A/B bucket, geographic price)? | Wholly: `private, no-cache` plus ETag, server keys scoped to `{tenant}:{user}`, and never `s-maxage`. Partly: split a public shell from a private island (partial prerendering, `'use cache: private'`, edge-side includes, or a client fetch), and strip `Set-Cookie` from the shell. |
| 3 | Can the URL change every time the content changes? | `max-age=31536000, immutable`. Add `public` only if `Authorization` never reaches these URLs. No invalidation needed. Stop. |
| 4 | What is the staleness budget S? | S = 0: browser `no-cache`, and re-read the source of truth at commit. Seconds to minutes: CDN `s-maxage=S` with stale-while-revalidate and `stale-if-error`, plus a 1–10 s micro-cache on hot routes. Hours to days: long CDN TTL plus tag purge on publish. |
| 5 | Is event-driven invalidation available (tag purge, webhook, change data capture)? | Yes: long shared TTL plus soft purge, with an ETag so revalidation can return 304. No: shared TTL no longer than S, plus stale-while-revalidate and `stale-if-error`. |
| 6 | How many variants does each URL have? | Normalize `Accept-Language`, allow-list query parameters, strip tracking parameters, and never `Vary: Cookie` or `Vary: User-Agent`. If variants far outnumber requests per TTL window, cache a lower layer instead. |
| 7 | Is the read both hot and expensive? | Cache-aside with a jittered TTL no longer than S, single-flight, stale-while-revalidate, and an in-process L1 cache for the hottest keys. Otherwise fix the query or index. |
| 8 | Does the writer need to read their own write? | Write-through, or bypass the cache (pin to the primary database) for N seconds after the write. |
| 9 | What happens when the cache or origin fails? | The cache is optional behind a circuit breaker, `stale-if-error` is served, and degraded behavior is defined. |

Steps 1 and 2 encode the rule Vercel's skill already enforces: a route "must be a public, cacheable GET path before a shared-cache recommendation is allowed", and "if the right policy is `no-store`, emit no-change" ([vercel-optimize cdn-cache-auth-safety](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md)). Step 6 carries MDN's guidance on keeping variants few: use `private` instead of `Vary: Cookie`, and avoid `Vary: User-Agent` ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)).

Step 7 is where server-side caching earns or loses its place. Azure warns that cache-aside suits neither sensitive data, nor static datasets (prime those instead), nor workloads where most requests miss ([Azure Cache-Aside](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)). The skill should compute rather than guess, using `effective_latency = h·L_hit + (1−h)·(L_hit + L_miss)` and `DB_load = (1−h)·request_rate`. With a 1 ms Redis hit, a 50 ms database miss and a 90% hit rate, latency falls to 6 ms and database reads fall tenfold. Going from 90% to 99% cuts reads tenfold again, so small hit-rate gains at the top matter more than they look. That arithmetic belongs in a small script.

The leaves of the tree map to a data-class matrix that the skill ships as an editable asset. Its header values follow MDN's recommended defaults and Harry Roberts' recipes ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching); [csswizardry, Cache-Control for Civilians](https://csswizardry.com/2019/03/cache-control-for-civilians/)). No vendor publishes a canonical table mapping data types to TTLs, so the TTLs below are starting points to check against each app's staleness budget.

| Data class | Browser `Cache-Control` | Shared cache / CDN | Server or data cache | Invalidation |
|---|---|---|---|---|
| Fingerprinted JS, CSS, fonts, images | `public, max-age=31536000, immutable` | Same | — | New URL per build; keep several old builds deployed |
| Fixed URLs (`favicon.ico`, `manifest.json`, `/.well-known/*`) | `no-cache` + ETag | `s-maxage` 1 hour to 1 day | — | Purge on deploy |
| Service worker script | `no-cache` | Short or none | — | Deploy |
| Public HTML, rarely changing | `no-cache` + ETag | `s-maxage` 1 day to 1 year, stale-while-revalidate 1 day | Framework data cache | Publish webhook triggers tag invalidation |
| Public HTML, volatile (home, fronts, listings) | `max-age=0` | `s-maxage=30–300`, stale-while-revalidate, `stale-if-error` | Fragment cache with tags | Event purge, with a short TTL as backstop |
| Fully personalized pages and APIs | `private, no-cache` + ETag | Bypass | Cache-aside scoped to tenant or user | Invalidate on write |
| Sensitive (payment, health data, auth, tokens) | `no-store` | Bypass | None | — |
| Public reference API (catalog, config) | `public, max-age=60–300`, or `no-cache` + ETag | `s-maxage` of hours, with tags | Preload at startup | Purge on admin publish; versioned keys |
| Volatile public API (price, stock) | `no-cache` | 1–30 s, or none | Short TTL plus events | Event-driven; re-check at commit |
| Search and faceted listings | `no-cache` or `max-age=60` | Only the most popular queries, normalized | Result cache for popular queries | TTL plus index-update events |
| Mutations | `no-store` | Never | Trigger invalidation | Emit tags or events |
| LLM outputs and embeddings | `private` / `no-store` | None | Exact-match, embedding and guarded semantic caches | Model and prompt version in the key |

App archetypes then set the defaults for the whole matrix. Archetypes differ in four things: the share of traffic that is public, the staleness budget of the hot data, the write rate, and how many variants each URL has. The skill should guess the archetype while fingerprinting, confirm it with the user, and then load `archetypes.md`.

| Archetype | Dominant constraint | Blueprint core |
|---|---|---|
| Static, docs, marketing | Nearly all traffic is public | Static generation or ISR; immutable assets; HTML `no-cache` in browsers but long `s-maxage` at the CDN, purged on deploy or publish; strip `utm_*` from the cache key; bfcache and speculation rules |
| News and media | Spikes plus freshness within minutes | Articles cached for hours to days with tag purge (article, section, author); front pages `s-maxage=30–60` with stale-while-revalidate; shield and request collapsing; a target time from purge to visible; paywall state never in public HTML |
| E-commerce | Several staleness budgets on one page | Catalog and product copy cacheable with tags; price and stock in islands with short TTLs or event-driven updates, checked authoritatively at checkout; cart `private`; checkout `no-store`; normalized facets |
| SaaS and B2B multi-tenant | Mostly private | CDN only for assets and the marketing site; `private` APIs with ETags; every key prefixed `t:{tenant}:`; precomputed aggregates; permission-cache TTL no longer than the acceptable revocation delay |
| Social and UGC | Fan-out and counters | Object cache keyed by ID and version; precomputed feeds in Redis; `INCR` counters with periodic flush; a takedown purge pipeline |
| Real-time and collaborative | Live state | Cache only assets and the initial snapshot; live state in memory on sharded servers; `no-store` on live endpoints |
| Public REST or GraphQL API | HTTP semantics are the product | ETags and 304s; `public` or `private` by audience; `Vary` only on content-negotiation headers; persisted GraphQL queries over GET; gateway cache keys include caller identity |
| Mobile backend | Old binaries live for months | Validators for cheap 304s; TTLs set by the server, not hard-coded in the app; versioned cache busters; config JSON served from the CDN |
| Internal tools | Low traffic, high cost of wrong data | `private, no-cache`; fix queries first; cache only expensive reference lookups |
| AI and LLM apps | Token cost | Provider prompt (prefix) caching first; exact-match, embedding and retrieval caches; semantic caching only for public FAQs |
| Video and large media | Origin egress | Immutable segments behind an origin shield; live manifests with a TTL of about half a segment; respect the CDN's maximum object size |

Published case studies all show several cache tiers working together. **Shopify's storefront renderer** stores final HTML or JSON in a Redis instance on each node, shared by that node's workers and layered over in-memory and query caches ([Shopify Engineering](https://shopify.engineering/simplify-batch-cache-optimized-server-side-storefront-rendering)). **Shopify's Shop app** added a custom write-through home-feed cache that cut database load by **15%** and latency by about **20%** ([Shopify Engineering](https://shopify.engineering/shop-app-custom-caching-solution)). **Wikimedia** runs Varnish in RAM in front of disk-backed Apache Traffic Server. Its multicast (HTCP) purge messages suffered packet loss and races between tiers, which is why the news blueprint carries a purge-to-visible target ([Wikimedia T133821](https://phabricator.wikimedia.org/T133821)). **Discord** coalesces identical reads and routes them by channel ID with consistent hashing. It reports p99 reads near 15 ms, against 40–125 ms before ([InfoQ](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)).

The social, real-time and news blueprints lean more on vendor documentation and synthesis, because write-ups from Figma, Notion, the Guardian and others could not be retrieved.

The plan sequences work by return on investment. This is a consensus order rather than a measured ranking; no primary source ranks caching interventions quantitatively.

| Phase | Work |
|---|---|
| 0 | Safety: remove shared caching of personalized responses |
| 1 | Hashed static assets marked `immutable` |
| 2 | An explicit `Cache-Control` and validators on every response |
| 3 | CDN caching for public HTML and APIs, with stale-while-revalidate, `stale-if-error`, tag purge and cache-key normalization |
| 4 | bfcache and speculation rules |
| 5 | Server-side caching of measured hot, expensive reads |
| 6 | API ETags and client query caches |
| 7 | Origin shields, `No-Vary-Search`, service workers and edge key-value stores |

Build and CI caching runs as a parallel track. Azure's warning shapes the rollout: adding a cache can shift the bottleneck so far that the web front end starts returning 503s ([Azure No-Caching](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)). Each phase therefore gets a canary and a load test.

The deliverable is one document. It opens with a summary, the app profile and a dated baseline, then states the constraints: sensitive data classes, staleness budgets, compliance (including GDPR erasure paths) and tenancy. Its core is the per-route policy matrix, a design for each layer, and an invalidation map that links each event to the affected entities, the tags or keys, the mechanism, the expected propagation time and an owner. It closes with failure safeguards, a phased rollout, verification and monitoring, rollback paths (a CDN bypass rule, a header revert or a cache-namespace version bump), and ownership with a review cadence.

Vercel's skill sets the bar for each matrix row. Every recommendation must name its "mechanism, scope, TTL/freshness, and `Vary`", plus the exact cache primitive for the detected framework version ([vercel-optimize](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md)). A condensed example:

| ID | Route | Class | Staleness budget | Browser | Shared cache | App layer | Invalidation | Verify |
|---|---|---|---|---|---|---|---|---|
| R1 | `/_next/static/*` | Fingerprinted asset | Unlimited (versioned) | `public, max-age=31536000, immutable` | Same | — | New hash per build | `curl -sI` shows `immutable` |
| R2 | `/products/[slug]` | Public shell with a price island | Copy 1 h; price 60 s | `no-cache` | `s-maxage=3600, stale-while-revalidate=86400` | `cacheLife('hours')`, `cacheTag('product:{id}')` | Product webhook calls `revalidateTag('product:{id}', 'max')` and invalidates the CDN tag | Two `curl` requests show `HIT` with rising `Age`; a purge is visible within 30 s |
| R3 | `/api/cart` | Personalized API | 0 | `private, no-cache` | Bypass | — | — | Leak test with two sessions |
| R4 | `/checkout/*` | Sensitive | 0 | `no-store` | Bypass | — | — | Never shows `HIT` or `Age` |

## Every layer in the brief maps to 48 reference files of gotchas

Anthropic's skill guidance and the open agentskills guide agree on what reference content is for. Claude "is already very smart", so a skill should add only what Claude would otherwise get wrong. Gotchas are "the highest-value content in many skills" ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)). Each reference file should therefore hold four things: the current default recipe; the counter-intuitive rules; version notes, with superseded APIs folded into an "old patterns" block; and pointers to ready-made snippets.

The map below covers every layer in the brief. The subsections after it give the cited rules each file must carry.

| Layer | Reference file(s) | What it holds |
|---|---|---|
| Decision logic | `core/decision-framework.md`, `core/archetypes.md` | Decision tree, data-class matrix, TTL ladder, ROI order, archetype blueprints |
| HTTP semantics | `core/http-semantics.md` | RFC 9111/9110 directives, validators, `Vary`, CDN-targeted headers, recipes per resource type, TTLs for redirects and errors |
| Browser platform | `layers/browser-platform.md` | bfcache, cache partitioning, speculation rules, `No-Vary-Search`, compression dictionaries, `Clear-Site-Data`, asset versioning and deploy skew |
| Service workers | `layers/service-workers.md` | Lifecycle, Workbox strategy per route, Cache API cleanup, quotas and eviction |
| CDN and edge | `layers/cdn-concepts.md` plus `platforms/{cloudflare,vercel,netlify,fastly,cloudfront,akamai,gcp-azure-cdn,other-hosts}.md` | Defaults, key rules, CDN-targeted headers, purge APIs and limits, shields, stale serving, edge data stores, image variants |
| Reverse proxies | `layers/reverse-proxies.md` | nginx proxy and FastCGI micro-caching, Varnish grace and xkey, HAProxy, Caddy/Souin, Traefik |
| Frontend frameworks | `frameworks/{nextjs,nuxt-nitro,sveltekit,react-router-remix,astro,other-frontend}.md` | Version-specific APIs, header mapping, self-hosting cache handlers, CDN pitfalls |
| Client data caches | `frameworks/client-data-caches.md` | TanStack Query, SWR, Apollo, Relay, urql and RTK Query defaults; persistence |
| Backend frameworks | `frameworks/{rails,django,laravel-php,spring-jvm,aspnet,node-backends,python-async,go,elixir}.md` | Stores, decorators, HTTP helpers, stampede options, pitfalls, PHP OPcache |
| CMS and commerce | `cms/{wordpress,drupal,shopify-hydrogen,magento,headless-cms}.md` | Page and object caches, tags and contexts, sub-request strategies, webhook revalidation |
| In-process | `layers/in-process.md` | Library per runtime, eviction algorithms, memory bounds, drift between instances |
| Distributed | `layers/distributed-cache.md` | Engine choice and licensing, configuration, key naming, serialization, big and hot keys, L1+L2, client-side caching, sizing math |
| Database | `layers/database-orm.md` | Buffer caches, query-cache proxies, materialized views, replicas, ORM caches, poolers |
| Serverless and edge data | `layers/serverless-edge-data.md` | Connection budgets, HTTP Redis, key-value store consistency, platform runtime caches |
| APIs | `layers/api-graphql-rpc.md` | Cacheable GET design, gateways, GraphQL persisted queries and response caches, DataLoader, gRPC/Connect, tRPC |
| Mobile | `layers/mobile-native.md` | URLCache, OkHttp, image caches, offline-first stores, version skew |
| AI/LLM | `layers/ai-llm.md` | Provider prompt caching; exact-match, embedding, retrieval and semantic caches |
| Correctness | `core/invalidation-consistency.md`, `core/stampede-failure.md` | Invalidation strategies, races, leases, TTL design, stampede and failure defenses |
| Security and verification | `core/security.md`, `core/observability-testing.md` | Attack classes, CVE watchlist, tenant isolation, metrics, debug headers, test recipes |
| Adjacent layers | `layers/build-ci-network.md` | CI, package, Docker and monorepo caches; DNS TTLs; TLS resumption and 0-RTT; connection reuse; OS page cache |

### Most HTTP mistakes come from misreading four directives

RFC 9111, the HTTP caching standard, is routinely misremembered, so the reference must state four of its rules plainly ([RFC 9111](https://httpwg.org/specs/rfc9111.html)). `no-cache` means "store, but revalidate before every reuse". Only `no-store` prevents storage. `must-revalidate` takes effect only once a response is stale, and at that point it can turn an origin outage into 504 errors. `s-maxage` also carries `proxy-revalidate` semantics. `public` lets a cache store a response "even if it would otherwise be prohibited". Together with `must-revalidate` and `s-maxage`, it is one of only three directives that let a shared cache store a response to a request that carried `Authorization`.

Status codes 200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414 and 501 are cacheable by heuristic. A 301 or a temporary 404 sent without headers can therefore stick ([RFC 9110](https://httpwg.org/specs/rfc9110.html)).

Browser support is uneven. Firefox and Safari honor `immutable`, but Chrome has never implemented it. Browsers have honored `stale-while-revalidate` since Chrome 75, Firefox 68 and Safari 14 ([BCD Cache-Control](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Cache-Control.json)).

The kitchen-sink header `private, no-cache, no-store, max-age=0, must-revalidate` is "basically meaningless". It reduces to `no-store`, which also gives up the bfcache ([MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)). Shared caches also merge concurrent identical requests even for `max-age=0` responses, so personalized responses need `private` ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)).

Validators bring their own traps. nginx downgrades strong ETags to weak ones when it gzips a response, and drops unquoted upstream ETags entirely ([nginx trac #377](https://trac.nginx.org/nginx/ticket/377)). JavaScript that adds `If-None-Match` to a `fetch()` call silently switches the request to `no-store` cache mode ([Fetch Standard](https://fetch.spec.whatwg.org/#concept-request-cache-mode)). An `Access-Control-Allow-Origin` value computed per request needs `Vary: Origin` ([Fetch Standard](https://fetch.spec.whatwg.org/#cors-protocol-and-http-caches)).

The browser platform shifted a lot in 2025–26. Since Chrome 86 the HTTP cache has been partitioned by top-level site, so public CDN copies of shared libraries give no cross-site hits and should be self-hosted ([Chrome](https://developer.chrome.com/blog/http-cache-partitioning)). Chrome finished enabling the bfcache for `no-store` pages in spring 2025, with a 3-minute timeout and eviction when cookies change ([Chrome bfcache-ccns](https://developer.chrome.com/docs/web-platform/bfcache-ccns)), so pages that must not be restored after logout need a `pageshow` re-check rather than `no-store` alone. From Chrome 155, `unload` handlers fire only when a `Permissions-Policy` header opts in ([BCD](https://github.com/mdn/browser-compat-data/blob/main/api/Window.json)). `No-Vary-Search` reaches the HTTP cache in Chrome 141 and Firefox 154 but not Safari ([BCD](https://github.com/mdn/browser-compat-data/blob/main/http/headers/No-Vary-Search.json)), and Chrome engineers warned in January 2026 that a syntax change could break deployments ([IETF list](https://lists.w3.org/Archives/Public/ietf-http-wg/2026JanMar/0027.html)), so it stays a progressive enhancement. Compression dictionaries (RFC 9842) work in Chrome 130+, but a dictionary is silently ignored unless its response has a positive freshness lifetime ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)). Speculation-rules prefetches are cached for 5 minutes ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)), and HTTP/2 Server Push is gone ([Chrome](https://developer.chrome.com/blog/removing-push)).

Two diagnostic traps belong here too. Lighthouse's "Use efficient cache lifetimes" insight skips anything marked `no-cache`, `no-store`, `must-revalidate` or `private`, and ignores TTLs of 30 days or more, so a passing score says nothing about HTML policy ([devtools Cache.ts](https://github.com/ChromeDevTools/devtools-frontend/blob/main/front_end/models/trace/insights/Cache.ts)). Deploy skew means that old tabs request chunks a deploy has deleted and fail with `ChunkLoadError`. Old hashed assets must therefore outlive the maximum cache age of the HTML and service worker that reference them ([Sentry](https://sentry.io/answers/chunk-load-errors-javascript)).

Service workers form a separate cache with separate rules. The Cache API is "entirely separate from the HTTP cache", and its entries never expire unless deleted ([MDN Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)). Workbox 7.4.1 (May 2026) is current. Its `pageCache()` recipe is network-first with a 3-second timeout, and its `imageCache()` keeps 60 entries for 30 days ([workbox-recipes](https://www.npmjs.com/package/workbox-recipes)). Since Chrome 68, update checks for the main service-worker script bypass the HTTP cache ([MDN register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register)). Safari deletes script-created storage for origins without user interaction in the last 7 days ([MDN storage quotas](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)).

The classic "stuck forever" bug is a cache-first route serving URLs without content hashes. That rule is synthesized rather than cited, but it belongs in the file.

### CDN defaults diverge so much that the vendor must be known first

The skill must answer "which CDN?" before giving header advice, because defaults diverge sharply. **Cloudflare** caches by file extension and never caches HTML or JSON by default ([Cloudflare](https://developers.cloudflare.com/cache/concepts/default-cache-behavior)). **Azure Front Door** caches a response that has no cache directive for **1–3 days** ([Azure](https://learn.microsoft.com/azure/frontdoor/front-door-caching)). **Akamai** ignores the origin's `Cache-Control` unless its Caching behavior is set to honor it ([Akamai](https://techdocs.akamai.com/property-mgr/docs/know-caching)). **Google Cloud CDN's** `FORCE_CACHE_ALL` mode ignores `private` and `no-store` ([GCP](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy)). **CloudFront** policies with a minimum TTL above zero can override an origin's `no-store` ([AWS](https://docs.aws.amazon.com/es_es/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)).

Targeted headers let one response give browsers, downstream CDNs and the vendor's own edge three different TTLs. RFC 9213 defines `CDN-Cache-Control`. Vercel and Cloudflare each add a vendor-only variant that they strip before forwarding ([RFC 9213](https://httpwg.org/specs/rfc9213.html); [Vercel](https://vercel.com/docs/caching/cdn-cache); [Cloudflare](https://developers.cloudflare.com/workers/cache/configuration/)), and Fastly uses `Surrogate-Control` ([Fastly](https://developer.fastly.com/reference/http-headers/Surrogate-Control/)).

One trap needs a callout. On Cloudflare, `s-maxage`, `must-revalidate` or `no-cache` sent alongside `stale-while-revalidate` silently disables stale serving ([Cloudflare revalidation](https://developers.cloudflare.com/cache/concepts/revalidation/)). The portable edge header is therefore `CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400`.

Soft purge, which marks content stale instead of deleting it, reached rough parity across vendors in 2026. **Cloudflare** added `invalidate_cache` on September 28. It revalidates with the origin and reuses the cached body on a 304 ([Cloudflare](https://developers.cloudflare.com/cache/guides/invalidate-cache/)). **Vercel** separates `invalidateByTag` from `dangerouslyDeleteByTag` ([Vercel](https://vercel.com/docs/caching/cdn-cache/purge)). **Fastly** uses the `Fastly-Soft-Purge: 1` header ([Fastly](https://docs.fastly.com/en/guides/soft-purges)). **Akamai** separates "invalidate" from "delete" ([Akamai](https://techdocs.akamai.com/purge-cache/docs/purge-methods)).

Tag limits set the floor for any tag scheme.

| Vendor | Tag limit | Notes |
|---|---|---|
| CloudFront | 50 tags per object | Each tag is billed as one invalidation path, against 1,000 free paths per month ([CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md); [CloudFront pricing](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PayingForInvalidation.md)) |
| Vercel | 128 tags per response | Case-sensitive ([Vercel](https://vercel.com/docs/caching/cdn-cache/purge)) |
| Cloudflare | About 1,000 tags | 16 KB header limit ([Cloudflare](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/)) |
| Fastly | 16 KB header | Keys beyond the limit are silently dropped and can never be purged ([Fastly](https://www.fastly.com/documentation/ja/guides/full-site-delivery/purging/purging-with-surrogate-keys/)) |

The skill should therefore prescribe at most 50 lowercase tags per response. Cloudflare's Free plan allows only 5 tag-purge requests per minute ([Cloudflare](https://developers.cloudflare.com/cache/how-to/purge-cache/)), so CMS webhooks must batch and debounce purges. Order also matters: update the origin first, purge after, and purge inner layers before outer ones.

Tiering and edge data stores have their own gotchas. **Cloudflare's Smart Tiered Cache** is free on all plans ([Cloudflare](https://developers.cloudflare.com/cache/how-to/tiered-cache/)). **The Workers Cache API** neither collapses concurrent requests nor uses tiers ([Workers limitations](https://developers.cloudflare.com/workers/cache/limitations/)). **Workers Caching** puts the Worker version in its cache key by default, so every deploy starts cold ([cache keys](https://developers.cloudflare.com/workers/cache/cache-keys/)). **Workers KV** can take up to 60 seconds to propagate a write ([KV](https://developers.cloudflare.com/kv/api/write-key-value-pairs/)). **Fly.io's proxy** does no HTTP response caching at all ([Fly](https://fly.io/docs/reference/fly-proxy/)). **Next.js 16 images** now have a 4-hour minimum TTL, and cached variants multiply across sources × qualities × widths × formats ([Vercel KB](https://vercel.com/kb/guide/reduce-image-optimization-costs-on-vercel)).

For self-hosted origins, the default recipe is nginx micro-caching with `proxy_cache_lock`, `proxy_cache_use_stale updating` and `proxy_cache_background_update` ([F5 NGINX](https://www.f5.com/pt_br/company/blog/nginx/nginx-caching-guide)). Varnish adds grace mode and xkey soft purge for tag invalidation ([Varnish](https://www.varnish.org/docs/tutorials/cache-invalidation/)). HAProxy's cache is in-memory only, capped at 4,095 MB, and skips any response with `Vary` unless `process-vary` is on ([HAProxy](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/performance/caching)). With a tag-purging CDN in front, keep the origin proxy's TTL at 1–10 seconds so it does not become a second invalidation problem.

### Framework guidance must be keyed to the detected version

The current stable lines are Next.js 16.4, Nuxt 4.6, SvelteKit 3.1, React Router 8.5, Astro 7.4 and Angular 22.2 ([npm registry](https://registry.npmjs.org/next)).

Next.js needs the most care. In the Cache Components model (`cacheComponents: true`), everything is dynamic until opted in with `'use cache'`, `cacheLife` and `cacheTag`. The previous model keeps `fetch` options, `unstable_cache` and segment `revalidate` ([Next.js caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)). The skill must never add `'use cache'` to an app without the flag, because turning the flag on is a migration. The Next.js reference must also state these rules. The single-argument `revalidateTag` is deprecated and behaves as immediate expiry, so use `revalidateTag(tag, 'max')` ([revalidateTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/revalidateTag.mdx)). `updateTag` works only in Server Actions, so CMS webhook routes must use `revalidateTag` ([updateTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/updateTag.mdx)). `'use cache'` entries never survive a deploy, because the build ID is part of the key ([use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx)). Self-hosting on several instances needs both a shared `cacheHandler` and `cacheHandlers` ([cacheHandlers](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheHandlers.mdx)). A CDN in front must forward the `rsc` header, include `_rsc` in its cache key, and be purged alongside `revalidateTag` ([Next.js CDN caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/cdn-caching.mdx)). OpenNext on AWS still needs a CloudFront invalidation after revalidation ([OpenNext AWS](https://github.com/opennextjs/docs/blob/main/pages/aws/inner_workings/caching.mdx)).

That last point explains the classic complaint "revalidation works locally but not in production": it almost always means a CDN copy is still being served.

Other frameworks have their own traps. **Nuxt** (via its Nitro server) defaults `defineCachedEventHandler` to a `maxAge` of **1 second**, drops request headers not listed in `varies`, and stores entries in per-instance memory in production ([Nitro cache](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)). **SvelteKit** has no server data cache, and setting the same header in two `load` functions is an error ([SvelteKit load](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/20-load.md)). **React Router** does not send loader headers automatically; the route's `headers` export must re-emit them ([React Router headers](https://github.com/remix-run/react-router/blob/main/docs/how-to/headers.md)). **Astro 7's** `cache.invalidate` throws when no cache provider is configured ([Astro caching](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)). Server islands on CDN-cached pages need a fixed `ASTRO_KEY` ([Astro server islands](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/server-islands.mdx)).

Client data caches need their defaults stated. **TanStack Query** treats data as stale immediately, garbage-collects inactive queries after 5 minutes, and with `staleTime: 'static'` blocks even manual invalidation ([TanStack](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/important-defaults.md)). Its SSR guide asks for a `staleTime` above zero to avoid an immediate refetch after hydration ([TanStack SSR](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/advanced-ssr.md)). **SWR** dedupes identical requests within 2 seconds ([SWR](https://github.com/vercel/swr-site/blob/main/content/docs/api.mdx)). **Apollo Client 4** now defaults `notifyOnNetworkStatusChange` to true ([Apollo](https://github.com/apollographql/apollo-client/blob/main/docs/source/migrating/apollo-client-4-migration.mdx)). **RTK Query** drops unused data after 60 seconds ([RTK](https://github.com/reduxjs/redux-toolkit/blob/master/docs/rtk-query/usage/cache-behavior.mdx)).

Backend frameworks each have a recommended default and at least one silent trap.

| Framework | What to recommend | Gotcha the reference must state |
|---|---|---|
| Rails 8 | Solid Cache, the database-backed default store; 37signals' cache passed **10 TB** on disk ([Honeybadger](https://www.honeybadger.io/blog/rails-8/)) | Russian-doll invalidation fails silently without `touch: true` ([Rails Guides](https://guides.rubyonrails.org/caching_with_rails.html)); `race_condition_ttl` does not stop stampedes while a cold cache is being filled ([Kit Engineering](https://engineering.kit.com/2019/10/29/we-built-our-own-cache/)) |
| Django 6.x | Redis backend; `cache_control`; conditional GET; low-level caching for hot queries | `cache_page` does not vary on cookies or authentication by default, and middleware order decides whether `Vary` is honored ([Django cache docs](https://docs.djangoproject.com/en/6.0/topics/cache/)); pin the 2026 patch releases that fixed the leaks |
| Laravel 13 | `Cache::flexible` (stale-while-revalidate), request-scoped `Cache::memo()`, the `failover` store, `Cache::touch()` ([Laravel docs](https://laravel.com/docs/12.x/cache); [Laravel News 12.35](https://laravel-news.com/laravel-12-35-0)) | `optimize:clear` also wipes application data from the default store ([benjamincrozat](https://benjamincrozat.com/laravel-clear-cache)) |
| Spring Boot 4 | Caffeine locally, Redis shared, `sync=true` against stampedes | Calling a cached method from the same bean bypasses `@Cacheable`; `sync=true` cannot be combined with `unless` ([Spring](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)); `CompositeCacheManager` does not create tiers ([devops-monk](https://blog.devops-monk.com/2026/05/spring-boot-caching-caffeine-redis/)) |
| ASP.NET Core (.NET 10) | Output Caching for responses; HybridCache (L1+L2, stampede protection, tags) for data ([MS Learn output caching](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output?view=aspnetcore-10.0); [HybridCache](https://learn.microsoft.com/aspnet/core/performance/caching/hybrid)) | Output Caching refuses authenticated and cookie-setting responses by default; caching them per user needs an explicit vary-by-user rule |
| Node (Express, NestJS) | Explicit headers plus Redis cache-aside | Express generates weak ETags by default ([expressjs#2667](https://github.com/expressjs/express/issues/2667)) |
| FastAPI | `cashews` or explicit Redis ([FastAPI-CacheX PR #449](https://github.com/allen0099/FastAPI-CacheX/pull/449)) | `fastapi-cache2` has had no release since 2024 ([FastAPI-CacheX #423](https://github.com/allen0099/FastAPI-CacheX/issues/423)) |
| Go | Otter v2 or ristretto, plus `singleflight` ([Otter](https://github.com/maypok86/otter)) | A ristretto `Set` is not guaranteed to be stored ([ristretto](https://pkg.go.dev/github.com/dgraph-io/ristretto)) |
| PHP runtime | OPcache always enabled | OPcache is always compiled in from PHP 8.5, and JIT has been off by default since 8.4 ([PHP manual](https://www.php.net/manual/en/opcache.configuration.php)) |

CMS platforms have their own layers. **WordPress** needs an `object-cache.php` drop-in before Redis does anything ([Hostinger](https://www.hostinger.com/tutorials/what-is-object-cache/)). Plugins that set cookies can make every visitor bypass Cloudflare APO ([StackHarbor](https://stackharbor.com/en/knowledge-base/wp-cdn-cloudflare-apo-deep-config/)). **Drupal** propagates cache tags, contexts and max-age up through render arrays ([Drupal.org](https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays)). Its Internal Page Cache, however, applies one site-wide max-age to anonymous responses ([Lullabot](https://www.lullabot.com/articles/common-max-age-pitfalls-with-drupal-cache)). **Shopify Hydrogen's** `CacheLong` is 1 hour fresh plus 23 hours of stale-while-revalidate ([Shopify](https://shopify.dev/docs/api/hydrogen/latest/utilities/caching/cachelong)). **Adobe Commerce** has replaced Redis with Valkey in current patches ([Experience League](https://experienceleague.adobe.com/en/docs/commerce-operations/implementation-playbook/best-practices/planning/redis-valkey-service-configuration)). **Sanity**, a headless CMS, runs its own API CDN with roughly 10 minutes of stale-while-revalidate that Next.js `revalidate` does not control ([Sanity](https://www.sanity.io/answers/difference-between-api-requests-and-cdn-requests-in-sanity-io-)). **Contentful** webhooks should tag by `sys.id` rather than by slug ([Contentful](https://www.contentful.com/blog/nextjs-cache-components/)).

### Data-layer choices turn on eviction, licensing and staleness models

In-process caches should default to eviction that weighs how often a key is used, not just how recently. Caffeine's W-TinyLFU gives "near optimal" hit rates for about 8 bytes of bookkeeping per entry ([Caffeine](https://github.com/ben-manes/caffeine/wiki/Efficiency)). The newer S3-FIFO and SIEVE algorithms build on the same insight that most cached objects are used only once ([S3-FIFO](https://junchengyang.com/publication/sosp23-s3fifo.pdf); [SIEVE](https://junchengyang.com/slides/nsdi24-SIEVE.pdf)).

The skill should name one default library per runtime: Caffeine (JVM), Otter v2 (Go), Moka (Rust), cachetools (Python) and lru-cache v11 (Node). lru-cache refuses to run unbounded without `max`, `ttl` or `maxSize` ([lru-cache](https://github.com/isaacs/node-lru-cache); [Otter](https://github.com/maypok86/otter)). The file should also state that each instance's L1 cache is a separate copy that can drift, so its TTL must stay shorter than the shared L2 cache's.

For distributed caches, licensing drove the engine choice in 2026. **Valkey** (BSD-3) shipped 9.0 with multi-database clusters ([Linux Foundation](https://www.linuxfoundation.org/press/valkey-9.0-delivers-performance-and-resiliency-for-real-time-workloads)). ElastiCache Serverless for Valkey is priced **33%** below the Redis OSS option ([AWS](https://aws.amazon.com/blogs/database/amazon-elasticache-and-amazon-memorydb-announce-support-for-valkey/)). **Redis 8** is tri-licensed, with AGPLv3 as one option ([redis/redis](https://github.com/redis/redis)). **Azure Cache for Redis** blocked new instance creation for all customers from October 1, 2026 ([Azure](https://docs.azure.cn/en-us/azure-cache-for-redis/cache-retired-features)).

Three configuration traps follow. Open-source Redis defaults to `noeviction` ([Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)), so a cache must set `maxmemory` and an `allkeys-*` policy. Capacity planning must subtract the 25% of memory that ElastiCache reserves by default ([ElastiCache](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html)). Server-assisted client-side caching needs RESP3 and Redis 7.4, as in Jedis 5.2 ([Redis blog](https://redis.io/blog/faster-redis-client-library-support-for-client-side-caching/)).

At the database, the cheapest cache already exists, so tuning comes first. Postgres `shared_buffers` typically starts around 25% of RAM ([CYBERTEC](https://pgconfigurator.cybertec-postgresql.com/docs/parameters/shared_buffers)), and MySQL removed its query cache in 8.0 ([Readyset](https://readyset.io/blog/mysql-5-7-eol-the-end-of-mysql-query-cache)). Each transparent query cache then has its own staleness model. **Cloudflare Hyperdrive** caches reads for 60 seconds with 15 seconds of stale-while-revalidate, and "does not invalidate cached read query results when your application writes" ([Hyperdrive](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/)). **Prisma Accelerate** takes `ttl`, `swr` and tags per query ([Prisma](https://prisma.io/docs/accelerate/api-reference)). **Hibernate's query cache** can raise query counts when its expirations do not match the entity cache's ([DZone](https://dzone.com/articles/pitfalls-hibernate-second-0)).

Connection poolers are not caches, but PgBouncer only gained transaction-mode prepared statements in 1.21 ([Crunchy Data](https://www.crunchydata.com/blog/prepared-statements-in-transaction-mode-for-pgbouncer)). In serverless, the failure mode is connection fan-out: 1,000 concurrent invocations hold 1,000 connections. HTTP-based Redis and small, capped module-scope pools are therefore the defaults ([OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-connection-short-lived-functions/markdown)).

### API, mobile and AI caching each have one dominant hazard

APIs carry several rules. **AWS API Gateway** caches GET responses for 300 seconds by default and 3,600 at most. Unless "Require authorization" is on, any client can invalidate an entry by sending `Cache-Control: max-age=0` ([AWS](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html)). **GraphQL over POST** defeats URL-keyed caches; persisted queries sent as GET fix this ([Apollo APQ](https://www.apollographql.com/docs/apollo-server/performance/apq)). Apollo Server 4 reached end of life on January 26, 2026 ([Apollo migration](https://apollographql.com/docs/apollo-server/migration)). **GraphQL response caches** need a per-session partition. Yoga's `useResponseCache` takes a `session` function and invalidates on mutation ([Yoga](https://the-guild.dev/graphql/yoga-server/docs/features/response-caching)), and Grafbase scopes entity caches by the headers it forwards ([Grafbase](https://grafbase.com/docs/gateway/performance/entity-caching)). **DataLoader** must be created per request, since its docs state it "does not replace Redis" ([DataLoader](https://github.com/graphql/dataloader)). **Connect RPC** can serve `NO_SIDE_EFFECTS` methods over cacheable GET ([Connect](https://connectrpc.com/docs/go/get-requests-and-caching/)). **Idempotency keys** make writes safe to retry rather than acting as a read cache. The IETF draft for them expired in April 2026 ([IETF](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)).

Mobile clients cache whatever the server's headers allow. iOS `URLCache` follows HTTP cache headers by default ([tanaschita](https://tanaschita.com/20221031-managing-cache-when-working-with-urlsession-in-ios/)), and Android's OkHttp honors the same headers ([OkHttp](https://square.github.io/okhttp/features/caching/)). Image caches set their own expiry. Kingfisher's disk cache expires entries after 7 days by default, and expo-image has no TTL, so refreshing means rotating its `cacheKey` ([Kingfisher](https://github.com/onevcat/Kingfisher/discussions/2087); [Expo](https://docs.expo.dev/versions/latest/sdk/image/)). Old app versions stay installed for months, so persisted cache schemas need version busters ([TanStack persist](https://tanstack.com/query/v5/docs/framework/react/plugins/persistQueryClient)). Realm's Atlas Device Sync reached end of life on September 30, 2025 ([MongoDB](https://mongodb.com/community/forums/t/atlas-device-sync-end-of-life-and-deprecation/296687)).

For AI features, provider prompt caching is the largest and safest lever.

| Provider | Facts the reference must carry |
|---|---|
| Anthropic | Cache writes cost **1.25×** for a 5-minute TTL and **2×** for 1 hour; reads cost about **0.1×**; at most 4 breakpoints per request, each looking back at most 20 blocks; timestamps or unsorted JSON in the prefix silently break the cache ([Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)) |
| OpenAI | Automatic for prompts of 1,024 tokens or more; `prompt_cache_key` and 24-hour retention available; writes cost 1.25× from GPT-5.6 onward ([OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching)) |
| Gemini | 90% implicit discount on 2.5+ models ([Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview)) |

Semantic caching, which returns a stored answer for a *similar* prompt, is the risky layer. Redis LangCache defaults to a 0.85 similarity threshold ([Redis LangCache](https://redis.io/docs/latest/develop/ai/context-engine/langcache/concepts/)), yet correct and incorrect hits have "highly overlapping similarity distributions" ([vCache](https://arxiv.org/html/2502.03771v5)). Attackers can also craft prompts that collide with cached keys ([arXiv 2601.23088](https://arxiv.org/pdf/2601.23088)), and GPTCache has stopped adding support for new models ([GPTCache](https://github.com/zilliztech/GPTCache)).

The reference should therefore rank LLM caches, consistent with Azure's caveat on semantic caching ([Azure Cache-Aside](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)): exact-match response caching comes first, embedding caches keyed by model and version come second, and semantic caching comes last, used only for public, non-personalized questions, namespaced by tenant, model, prompt version and corpus version, and guarded by a strict threshold and a verifier.

The adjacent layers are short but security-relevant. **GitHub Actions** caches default to 10 GB per repo, configurable to 25 GB. Low-trust triggers now get read-only access to default-branch caches, a new `cache-mode` key grants least privilege, and secrets must never sit in cached paths ([GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)). **Docker BuildKit** cache mounts and external backends speed up builds ([Docker](https://docs.docker.com/build/cache/optimize/)). **Turborepo** "treats logs as artifacts", so anything printed to logs is cached ([Turborepo](https://turborepo.dev/docs/core-concepts/remote-caching)). **Nx** recommends read-only cache tokens everywhere except on protected branches ([Nx](https://github.com/nrwl/nx/blob/master/astro-docs/src/content/docs/kb/cache-security.mdoc)). **Next.js** needs `.next/cache` persisted between CI builds ([Next.js](https://nextjs.org/docs/app/guides/ci-build-caching)). **DNS** TTLs must drop at least one full old-TTL period before a migration ([CanSpace](https://www.canspace.ca/clients/knowledgebase/101/TTL-and-when-to-lower-it-before-a-DNS-change.html)). **TLS 1.3 0-RTT** belongs only on idempotent requests, because early data can be replayed ([Cloudflare](https://blog.cloudflare.com/tls-1-3-overview-and-q-and-a/)).

## Correctness lives in write ordering, stampede control and leak tests

No single invalidation strategy is enough. Production systems layer several: a TTL as backstop; delete-on-write for object caches; versioned or generational keys for bulk invalidation; tags or surrogate keys to fan out at the HTTP layer; and invalidation driven by the database's change log wherever correctness matters.

Kleppmann argues that "dual writes" from application code race and drift, and that the fix is to write once to the database and derive caches from its change log ([Kleppmann](https://martin.kleppmann.com/2015/05/27/logs-for-data-infrastructure.html)). Facebook runs this pattern in production: its mcsqueal daemon tails the MySQL commit log and broadcasts memcache deletes ([summary of NSDI 2013](https://hemantkgupta.medium.com/insights-from-paper-scaling-memcache-at-facebook-1386a5956859)). For smaller teams, the transactional outbox with Debezium captures the change and the intent to invalidate in one atomic write ([Debezium](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)).

At the CDN, Fastly's recommended header for purge-driven content pairs a one-year `max-age` with `stale-while-revalidate=60` and `stale-if-error=31536000` ([Fastly on DEV](https://dev.to/fastly/is-purging-still-the-hardest-problem-in-computer-science-339i)). Because Fastly's purge-all can never be soft, the workaround is to tag every object with one constant key and soft-purge that key ([Fastly soft purges](https://www.fastly.com/documentation/guides/full-site-delivery/purging/soft-purges/)).

The canonical consistency bug is the **stale set** ([Redisson](https://redisson.pro/glossary/cache-invalidation.html)). A reader misses the cache and reads the old row; a writer then commits and deletes the still-empty key; finally the reader's delayed `set` writes the stale value back, where it stays until the TTL expires.

Fixes run from weak to strong. A delayed double delete is only a timing heuristic ([Alibaba Cloud](https://www.alibabacloud.com/blog/exploring-cache-data-consistency_600308)). Facebook-style leases give the reader a token on its miss; an intervening delete invalidates the token, so the stale set is rejected ([summary](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce)). One secondary account credits leases with cutting peak database queries from 17K/s to 1.3K/s, though this could not be checked against the paper ([Engineer's Codex](https://read.engineerscodex.com/p/how-facebook-scaled-memcached)).

Meta's 2022 work shows why measurement beats design alone. It raised cache consistency in TAO, its social-graph cache, from **six nines to ten nines**. Its Polaris checker found bugs hiding in error-handling paths, including a cache fill that read the value and the version separately ([Meta Engineering](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/); [recreation](https://github.com/Mayank-Sharma-27/meta-cache-made-consistent)).

Read replicas widen the stale-set window to the full replication lag. The skill should therefore ship three tools: a recipe that pins the writing user to the primary for N seconds after a write ([Codemia](https://codemia.io/archive/read-your-writes-consistency)); Lua scripts for lease-based and version-conditional sets; and a small Polaris-style sampler that checks the cache against the database.

TTLs come from the business's tolerance for staleness, not from how often data changes. The AWS Builders' Library splits a soft TTL (refresh after this) from a hard TTL (never serve after this, except on error) ([AWS Builders' Library](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/)). Caffeine pairs `refreshAfterWrite` with `expireAfterWrite` ([Caffeine Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh)), and FusionCache adds "fail-safe" reuse of expired entries when the source fails ([FusionCache](https://github.com/ZiggyCreatures/FusionCache)). Jitter, such as a random 55–65 minutes for a nominal hour, keeps keys from expiring together ([Redis blog](https://redis.io/blog/how-to-tame-the-thundering-herd-problem/)).

A stampede is many requests recomputing the same expired value at once, and the skill should default to the cheapest of four defenses that works. It can coalesce misses, as Go's `singleflight` does by ensuring "only one execution is in-flight for a given key at a time" ([singleflight](https://pkg.go.dev/golang.org/x/sync/singleflight)); refresh early, as XFetch does when `now − δ·β·ln(rand) ≥ expiry` ([xfetch](https://docs.rs/xfetch/)); serve stale content while one request refreshes; or route each key to one node, as Discord did ([InfoQ](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)).

Varnish's hit-for-pass mechanism shows why uncacheable responses must be marked explicitly. Otherwise requests queue behind a fetch whose result will never be cached ([Varnish](https://www.varnish.org/docs/users-guide/increasing-your-hitrate/)). The broader failure modes map to defenses as follows. The big-key row is practitioner heuristic rather than sourced guidance.

| Failure mode | Trigger | Defense the skill prescribes |
|---|---|---|
| Avalanche | Many keys share one expiry, or a cache node is lost | TTL jitter, soft TTL plus stale-while-revalidate, staggered warm-up, concurrency limits on the database |
| Penetration | Requests for IDs that don't exist | Short-TTL negative cache stored as a sentinel, Bloom filter of valid IDs, input validation |
| Breakdown | One very hot key expires | Single-flight plus stale-while-revalidate, XFetch, scheduled refresh for the top N keys |
| Hot key | One key saturates a shard | In-process L1 with a 1–5 s TTL, key splitting (`k#0..N`), replicas, CDN for public data |
| Big key | Multi-megabyte values | Chunking, caching projections, compression, deleting with `UNLINK` |
| Cold start | New key prefix after a deploy, a new region, a flush | Warm from a peer, pre-warm the top N keys, ramp traffic gradually, bump prefixes instead of flushing |
| Cache down | Cluster unreachable | Millisecond timeouts, a circuit breaker, fail open only into a coalesced and rate-limited database path, serve stale L1 data |
| Retry storm | Clients retry cache or database errors | Retry budgets, backoff with jitter, and errors treated as errors rather than misses |

Most of these are capacity failures in disguise: the database is sized for the healthy hit rate, so the skill should require a plan for a degraded one. Failing open is safe only into a guarded path, which is what Facebook's "gutter pool" of about 1% of its servers provides by absorbing a failed node's traffic instead of rehashing it onto healthy servers ([paper notes](https://distributed-computing-musings.com/2022/03/paper-notes-scaling-memcache-at-facebook/)). Facebook's 2010 outage shows why an error must never be treated as a miss or an invalid value. `stale-if-error` covers only 500, 502, 503 and 504, not 404 ([RFC 5861](https://httpwg.org/specs/rfc5861.html)). And the CDN itself can fail: a latent bug took about 85% of Fastly's network down in June 2021, with recovery taking up to 49 minutes ([Fastly](https://www.fastly.com/blog/summary-of-june-8-outage)).

Security deserves its own reference file and a hard gate in SKILL.md. The attack classes are well documented. **Cache poisoning** exploits inputs that the cache ignores but the app uses, such as `X-Forwarded-Host` ([Kettle](https://portswigger.net/kb/papers/7q1e9u9a/web-cache-poisoning.pdf)). Variants include parameter cloaking and GET requests that carry a body ([Web Cache Entanglement](https://portswigger.net/research/web-cache-entanglement)). **Cache deception** exploits delimiter confusion. Rails treats `.` as a format delimiter and Spring treats `;` as one, so `/MyAccount.css` can get a private page cached as if it were a static file ([Gotta cache 'em all](https://portswigger.net/research/gotta-cache-em-all)). **Cache-Poisoned Denial of Service (CPDoS)** gets error pages cached through oversized headers, meta characters or method overrides ([SecurityWeek](https://www.securityweek.com/researchers-warn-new-cache-poisoned-dos-attack-method)). **HTTP/1.1 desync attacks** can also poison caches ([PortSwigger](https://portswigger.net/research/http1-must-die)). **2026 research** added cache-key collisions caused by missing separators ([CyberSecurityNews](https://cybersecuritynews.com/web-cache-keys-poisoning/)) and "Web Cache Overflow", which forces evictions ([arXiv 2608.04744](https://arxiv.org/pdf/2608.04744)).

Prevalence is real but not universal. 56 of the Tranco top 1,000 sites were vulnerable to poisoning ([CCS 2024](https://dl.acm.org/doi/pdf/10.1145/3658644.3690361)), and the largest deception study found 1,188 vulnerable domains ([Golinelli thesis](https://iris.unitn.it/retrieve/321462a9-e212-4e50-9525-62409b6397c6/phd_unitn_golinelli_matteo.pdf)).

Framework CVEs share one root cause: a shared cache keys on the URL without distinguishing which variant of the response the framework sent.

| Framework | Cache-variant bug |
|---|---|
| Next.js | A missing `Vary` header let RSC payloads replace HTML (CVE-2025-49005), and HTML and RSC were confused again in 2026 (CVE-2026-44576) ([GitLab advisories](https://advisories.gitlab.com/npm/next/CVE-2026-44576/)) |
| React Router | An error triggered by a request header could be cached (CVE-2025-43864) ([Vercel changelog](https://vercel.com/changelog/protection-against-react-router-and-remix-vulnerabilities-cve-2025-43864)) |
| Nuxt | A `_payload.json` response could be cached and served to visitors (CVE-2025-27415) ([GitLab](https://advisories.gitlab.com/npm/nuxt/CVE-2025-27415/)) |

Advisories often say apps hosted on Vercel were unaffected, because Vercel's edge already keys these responses correctly. Moving an app off Vercel therefore reopens the holes.

Infrastructure and tenancy add their own risks. Research on the RediShell remote-code-execution bug found about 60,000 Redis instances exposed to the internet with no authentication ([Wiz](https://www.wiz.io/vulnerability-database/cve/cve-2025-49844)). Multi-tenant leaks usually come from a code path that forgot the tenant prefix, not from key collisions ([Redis blog](https://redis.io/blog/data-isolation-multi-tenant-saas/)). Cloudflare's Cache Deception Armor can be overridden by TTL rules, so correct origin headers remain the primary control ([Cloudflare](https://developers.cloudflare.com/cache/about/cache-deception-armor)).

The whole security file reduces to one checkable invariant: **the cache key must fully and precisely determine the response.**

Observability starts with one vocabulary. The skill should map `cf-cache-status`, `x-vercel-cache`, the `X-Cache` headers from Fastly and CloudFront, and Akamai's debug output onto hit, miss, stale and bypass. It should prefer the standard RFC 9211 `Cache-Status` header where present, because it reports TTL, cache key and request collapsing for each cache along the path ([RFC 9211](https://www.rfc-editor.org/rfc/rfc9211); [Cloudflare statuses](https://developers.cloudflare.com/cache/concepts/cache-responses/); [Vercel statuses](https://vercel.com/docs/caching/cache-status)). Three measurement rules matter. **Redis hit ratio** should come from deltas of `INFO` counters, not cumulative totals ([OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-cache-hit-ratio-optimize/markdown)). Rising `evicted_keys` means the cache is too small, unlike `expired_keys` ([Netdata](https://www.netdata.cloud/guides/redis/redis-low-keyspace-hit-rate/)). **OpenTelemetry** has no standard cache-hit attribute, so the plan should fix a custom one such as `cache.hit` ([OTel](https://opentelemetry.io/docs/specs/semconv/database/redis)). **Browser real-user monitoring** can count a cache hit when `transferSize === 0` and `decodedBodySize > 0` ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/transferSize)).

Testing should combine: fake-clock unit tests for TTL logic; header snapshot tests per route class, which would have caught the missing-`Vary` CVE; a two-user leak test run through the real CDN; deception probes such as `/account;.css`; the Web Cache Vulnerability Scanner (WCVS) in CI, which covers 9 poisoning and 3 deception techniques and emits JSON ([WCVS](https://github.com/Hackmanit/Web-Cache-Vulnerability-Scanner)); a self-hosted REDbot header checker, since the public site forbids scripted use ([PyPI redbot](https://pypi.org/project/redbot/)); load tests that start from a cold cache; chaos tests that kill Redis; and a synthetic freshness probe that measures the time from purge to visible change.

## Package it as a lean router with offline scripts and fixture evals

### Six portable frontmatter fields carry a 945-character description

Portability dictates the frontmatter. The open Agent Skills standard defines six fields: `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools` ([spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)). Claude Code accepts more, but "outside Claude Code (claude.ai uploads, the Skills API, `package_skill.py`), any other field … causes a hard error" ([Claude Code skills](https://code.claude.com/docs/en/skills)). Anthropic's skill-creator validator hard-codes the same six ([quick_validate.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py)).

The `name` must be lowercase with hyphens, at most 64 characters, match its directory, and avoid "claude" and "anthropic" ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). The spec and the API cap the `description` at 1,024 characters, even though Claude Code's own listing truncates only at 1,536 ([Claude Code skills](https://code.claude.com/docs/en/skills)).

The guides disagree on voice. The platform guide wants third person, while the agentskills guide prefers imperative phrasing and says to "err on the side of being pushy". Both put *what* before *when* ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx)).

The proposed description in the skeleton below is 945 characters. It names layers and vendors as trigger vocabulary. It adds symptoms users report without saying "cache", such as slow pages and hosting costs, and it excludes near misses. `compatibility` records that live probes need network access, and `metadata` carries `version` and `last-reviewed`. The name `caching-strategy` is a noun phrase, which the guidance accepts; `optimizing-app-caching` fits its preferred gerund form.

### Safety rules sit at the top because only the first 5,000 tokens survive compaction

Progressive disclosure dictates the shape. Metadata costs about 100 tokens and is always loaded. The SKILL.md body should stay under 500 lines and about 5,000 tokens. Bundled files cost nothing until read ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). Every reference should sit one link from SKILL.md, because Claude may only preview files nested deeper, and any reference over 100 lines needs a table of contents ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).

Two Claude Code behaviors make ordering critical. The skill file is not re-read on later turns, so its rules must be written as standing instructions. After compaction, only the first 5,000 tokens of each invoked skill survive, within a 25,000-token total ([Claude Code skills](https://code.claude.com/docs/en/skills)). The safety rules therefore go at the very top.

The agentskills guide warns that "overly comprehensive skills can hurt more than they help" ([agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)). That argues for a router that loads only the six to ten files a given stack needs, the way Cloudflare's 151-line umbrella skill fronts 139 files. The recommended layout:

```text
caching-strategy/
├── SKILL.md                      ≤500 lines: rules, workflow, routing table, gotchas, glossary, output contract
├── LICENSE.txt
├── references/                   48 files, each linked directly from SKILL.md; table of contents when >100 lines
│   ├── core/          (7)        decision-framework, archetypes, http-semantics, invalidation-consistency,
│   │                             stampede-failure, security, observability-testing
│   ├── layers/        (12)       browser-platform, service-workers, cdn-concepts, reverse-proxies, in-process,
│   │                             distributed-cache, database-orm, serverless-edge-data, api-graphql-rpc,
│   │                             mobile-native, ai-llm, build-ci-network
│   ├── frameworks/    (16)       nextjs, nuxt-nitro, sveltekit, react-router-remix, astro, other-frontend,
│   │                             client-data-caches, rails, django, laravel-php, spring-jvm, aspnet,
│   │                             node-backends, python-async, go, elixir
│   ├── cms/           (5)        wordpress, drupal, shopify-hydrogen, magento, headless-cms
│   └── platforms/     (8)        cloudflare, vercel, netlify, fastly, cloudfront, akamai, gcp-azure-cdn, other-hosts
├── scripts/                      stdlib-only Python; JSON on stdout, diagnostics on stderr; --help; never prompts
│   ├── detect_stack.py           versions, hosting/CDN, data stores, replicas → exact list of references to read
│   ├── find_cache_primitives.py  existing caches with file:line
│   ├── probe_headers.py          opt-in, networked: HIT/Age, 304, cookie on/off leak and deception probes
│   ├── validate_plan.py          schema check + safety lint of plan.json
│   └── size_cache.py             working-set and hit-ratio arithmetic
├── assets/
│   ├── caching-plan.template.md
│   ├── plan.schema.json
│   ├── policy-defaults.csv       the data-class matrix as editable defaults
│   └── snippets/                 nginx micro-cache, Varnish xkey VCL, Cloudflare/CloudFront rules, vercel.json,
│                                 Next.js cacheHandlers stub, secure-default header middleware,
│                                 Redis lease and version-conditional Lua, Workbox service worker, CI cache YAML
└── evals/                        excluded from .skill packages
    ├── evals.json                output-quality cases (skill-creator format)
    ├── trigger_queries.json      ~20 should-trigger / should-not-trigger queries
    └── fixtures/                 one small repo per archetype × stack
```

### SKILL.md holds rules, a checklist, routing and an output contract

SKILL.md should contain six blocks in this order: the non-negotiable rules; a workflow checklist that Claude copies into its reply and ticks off; the routing table; gotchas that cut across layers; a short glossary ("shared cache", "private cache", "staleness budget", "soft purge"), since the guide asks for consistent terminology; and the output contract.

Freedom should match risk, as the guide recommends ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). Analysis and trade-offs get high freedom. Safety rules, purges and CDN rule changes get low freedom and a plan-validate-execute loop, because they are destructive. Version-sensitive guidance follows the guide's "current method" convention, with old patterns in a collapsed block.

The skill should tell Claude to prefer project-bundled docs when they exist. Next.js 16.3+ ships docs in `next/dist/docs` and generates an AGENTS.md file ([vercel-labs/next-skills](https://github.com/vercel-labs/next-skills)). When `next-cache-components-*`, `cloudflare`, `redis-development` or `vercel-optimize` is installed, the skill should hand implementation detail to it. A skeleton:

```markdown
---
name: caching-strategy
description: Designs, audits and implements caching for a specific website or app across every layer: HTTP/browser headers (Cache-Control, ETag, Vary), service workers, CDNs and edge (Cloudflare, Vercel, Netlify, Fastly, CloudFront, Akamai), nginx/Varnish, in-process and Redis/Valkey/Memcached caches, database and ORM caches, framework caching (Next.js use cache/ISR, Nuxt, SvelteKit, Astro, Rails, Django, Laravel, Spring, ASP.NET), CMS, REST/GraphQL APIs, mobile clients, LLM prompt and semantic caching, and CI build caches. Detects the stack, classifies every route, and writes a validated caching plan covering invalidation, stampede protection, cache security and verification. Use when the user mentions caching, stale content, purging, CDN or Redis setup, or when pages are slow, TTFB is high, or origin, database or hosting costs are too high, even if they never say "cache". Not for clearing local package-manager caches or explaining CPU caches.
license: Apache-2.0
compatibility: Live header probes need network access and user-supplied URLs; every other step runs offline with the Python 3 standard library.
metadata:
  version: "1.0.0"
  last-reviewed: "2026-10-27"
---
# Caching strategy

## Rules that hold for the whole task
1. Classify every route with references/core/decision-framework.md before proposing any cache.
2. Never put `public`, `s-maxage`, CDN TTLs or CDN cache rules on a response whose body depends on
   cookies, sessions, Authorization, tenant, entitlement or A/B bucket. Use `private`; `no-store` for secrets.
3. Every response, including errors and redirects, gets an explicit Cache-Control. Default `no-store`;
   routes opt in. Platform and CDN defaults change without notice.
4. The cache key must fully determine the response. Never `Vary: Cookie` or `Vary: User-Agent`.
5. Use only APIs that exist in the detected framework version; prefer the project's bundled docs.
6. On writes, commit the database first, then delete (not set) cache entries, inner layer before outer.
   Keep a TTL backstop.
7. Every cache gets single-flight, TTL jitter and stale-while-revalidate, and the app must survive it being down.
8. An error is not a miss: never store 5xx as data; never delete entries because a backend failed.
9. Purges, flushes and CDN rule changes are destructive: write plan.json, run scripts/validate_plan.py, ask the user.
10. Nothing is done until headers, HIT/Age behavior and a two-user leak test pass.

## Workflow (copy into your response and tick off)
- [ ] 1. python scripts/detect_stack.py <repo>  → read every file listed under "read"
- [ ] 2. python scripts/find_cache_primitives.py <repo>
- [ ] 3. Inventory routes; if the user supplies URLs, run scripts/probe_headers.py
- [ ] 4. Confirm archetype and staleness budgets with the user
- [ ] 5. Fill assets/caching-plan.template.md and write plan.json
- [ ] 6. python scripts/validate_plan.py plan.json → fix until it passes
- [ ] 7. Implement phase by phase with user approval
- [ ] 8. Verify with references/core/observability-testing.md

## Routing table (one row per reference file)
| detect_stack signal                     | Read                                        |
|-----------------------------------------|---------------------------------------------|
| framework=next, cacheComponents=true    | references/frameworks/nextjs.md             |
| cdn=cloudflare                          | references/platforms/cloudflare.md          |
| …                                       | …                                           |

## Gotchas that span layers
## Glossary
## Output contract (plan template, required fields per row, verification commands)
```

### Five standard-library scripts make routing and safety deterministic

Scripts carry the deterministic work, because their code never enters context; only their output does. The API sandbox has "no network access" and "no runtime package installation", so everything except live probing must run on the Python standard library alone ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). The agentskills script guide adds hard requirements: no interactive prompts, a documented `--help`, structured JSON on stdout and diagnostics on stderr ([using scripts](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/using-scripts.mdx)).

| Script | Role |
|---|---|
| `detect_stack.py` | Reports framework versions, hosting, CDN, data stores and replica counts, plus the exact list of reference files to read. This makes routing deterministic and keeps SKILL.md short. |
| `find_cache_primitives.py` | Lists existing caches with file and line |
| `probe_headers.py` | The only networked script. It is opt-in, read-only, limited to URLs the user supplies, and never forwards credentials. It runs the request matrix, HIT/Age and 304 checks, cookie on/off leak probes and deception probes. |
| `validate_plan.py` | Validates `plan.json` against `plan.schema.json`, then runs the safety checks listed below |
| `size_cache.py` | Does the working-set and hit-ratio arithmetic |

`validate_plan.py` fails a plan when any row puts `public`, `s-maxage` or a CDN TTL on an authenticated data class, when a cacheable row lacks an invalidation mechanism, an owner or a verification command, when a TTL exceeds its staleness budget, or when a response carries more than 50 tags or any uppercase tag.

The platform's advice to treat skills like installed software also applies ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). The portable version should omit `allowed-tools`, which Claude Code applies even when the user has not marked the workspace as trusted ([Claude Code skills](https://code.claude.com/docs/en/skills)).

### Evals come first and run against one fixture repo per archetype

Evaluation should come first and drive what goes into the content. Anthropic's guidance has four steps ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). First, run Claude on representative tasks without the skill. Second, build at least three scenarios. Third, write only the instructions that close the observed gaps. Fourth, test on Haiku, Sonnet and Opus. Haiku matters most for a router, because it shows whether "read only the matching files" is actually followed.

Two eval harnesses exist, and their formats "aren't interchangeable" ([Claude Code skills](https://code.claude.com/docs/en/skills)). The skill-creator workflow stores cases in `evals/evals.json`. It compares runs with and without the skill, and grades assertions only on concrete evidence ([evaluating skills](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/evaluating-skills.mdx)). `claude plugin eval` runs each case three times against a baseline without the plugin. Its graders are regex, `tool_used`, `tool_order`, `file_exists`, LLM and baseline, with "no custom-code graders". Its most common first finding is a score difference near zero because the skill never triggered ([plugin evals](https://code.claude.com/docs/en/plugin-evals)).

Trigger tuning should use about 20 queries: roughly half should trigger the skill and half should be near misses that should not. Run each query three times, with a fixed 60/40 train/validation split. Do not add specific keywords from failed queries, because that overfits ([optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx)). Output evals then use one fixture repo per archetype and stack.

| Fixture | Prompt | Assertions to grade |
|---|---|---|
| Next.js 16 store on Vercel with `cacheComponents: true` | "Product pages feel slow and our Vercel bill jumped" | `detect_stack` ran; uses `'use cache'` with `cacheLife` and `cacheTag`; no single-argument `revalidateTag`; cart is `private, no-cache`; checkout is `no-store` |
| Next.js 15 self-hosted on Kubernetes behind CloudFront | "revalidateTag works locally but not in production" | Names the CDN TTL as the cause; shared `cacheHandler`; CloudFront invalidation; `_rsc` in the cache key; no `'use cache'` |
| Django 6 multi-tenant SaaS with Redis | "Dashboards are slow" | No `cache_page` on authenticated views; `t:{tenant}:` key prefix; Django patch release pinned; `private` plus ETag |
| Rails 8 news site on Fastly | "Breaking news takes minutes to show up" | Surrogate keys with soft purge; stale-while-revalidate and `stale-if-error`; a purge-to-visible probe; `touch: true` |
| WordPress behind Cloudflare APO | "cf-cache-status is always BYPASS" | Diagnoses plugin `Set-Cookie`; object-cache drop-in; a single page-cache layer |
| Express API with Apollo Server | "Cut database load from our GraphQL API" | Persisted queries over GET; `sessionId` set; a DataLoader per request; Apollo Server 5 |
| Expo app with a REST backend | "Users see old avatars after changing them" | Versioned `cacheKey`; ETags on the API; no long TTL hard-coded in the client |
| RAG support bot | "Our LLM bill is too high" | Stable prefix first; cached-token KPI; exact-match before semantic caching; namespace by tenant, model and prompt version |
| Near-miss negatives | "Implement an LRU cache for an interview", "clear my pip cache", "explain CPU L1 cache" | Skill not invoked (a `tool_used: Skill` grader with `arm: both`) |

### One repository feeds every distribution channel

Distribution must reach separate surfaces, because "Custom Skills do not sync across surfaces" ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). One public repo should hold the canonical, spec-compliant folder and feed every channel.

| Surface | How to ship | Constraint |
|---|---|---|
| Other agents (Cursor, Codex, Copilot, Gemini CLI and roughly 40 more) | `npx skills add <org>/<repo>` ([agentskills clients](https://github.com/agentskills/agentskills/blob/HEAD/docs/snippets/clients.jsx); [next-skills](https://github.com/vercel-labs/next-skills)) | Spec fields only |
| Claude Code | `.claude-plugin/marketplace.json` in the same repo, with a `strict: false` entry listing the skill folders. This is Anthropic's own pattern, and it avoids the duplicated copy Redis maintains ([anthropics/skills marketplace](https://github.com/anthropics/skills/blob/main/.claude-plugin/marketplace.json); [redis/agent-skills](https://github.com/redis/agent-skills); [plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)) | A plugin variant may add Claude Code-only fields and plugin evals |
| claude.ai | A zip built by `package_skill.py`, which leaves out a root-level `evals/` folder ([package_skill.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/package_skill.py)) | Uploaded per user; not managed by the organization |
| Claude API | `POST /v1/skills` ([Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)) | Under 30 MB uncompressed; each version is a full snapshot shared across the workspace; no network at runtime |

Versioning should combine `metadata.version`, the plugin `version` and a changelog, with a quarterly content review.

### Five open questions should be settled by evals, not assumptions

Several questions remain open and should be settled by evals rather than assumption. No source says how many routing rows Claude navigates well before reading too much or too little, so the 48-row table needs testing on Haiku, and no official guidance covers a monorepo that mixes stacks such as Next.js and Django. The open spec was read from its GitHub source dated August 2026 rather than the live agentskills.io site. Netlify specifics were available only from an agent context with no public URL and are omitted here, while Fastly's default TTL and Akamai's current tag header remain unverified. Several 2026 Next.js CVE version ranges also conflict across aggregators and must be confirmed against GitHub's advisories before the security file quotes them.

## Conclusion

The research moves the skill's value away from per-layer facts, which vendors increasingly ship as their own skills and which change monthly. What nobody ships is the coordination between layers: a TTL ladder that is shortest in the browser, which cannot be purged, and longest at the edge, which can; a purge order that runs from database to inner cache to outer cache; tag schemes that fit the most constrained CDN; in-process TTLs kept below shared-cache TTLs; and one cache-key rule that covers poisoning, deception and tenant leaks at once. A master skill wins by owning classification, cross-layer consistency, safety gates and verification while leaving syntax to version-matched vendor skills and bundled docs, which makes it smaller and longer-lived than an encyclopedia.

The skill should also be maintained the way its own advice says to run a cache: its references are cached knowledge with a staleness budget (a `last-reviewed` date and a quarterly refresh), its detection script acts as the version key, and its eval suite plays the role of a Polaris-style checker that catches silent drift. Its most durable recommendation is also the cheapest. Railway's 2026 incident repeated Steam's from 2015 because platform defaults changed underneath the apps, so before any clever cache the skill should land an explicit `Cache-Control` header on every response and guard it with header snapshot tests in CI.
