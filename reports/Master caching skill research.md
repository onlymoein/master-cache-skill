# Route, classify and verify every cache layer

A master caching skill should be a **thin, safety-first router, not an encyclopedia**. That means a SKILL.md under 500 lines that opens with ten standing safety rules and runs a deterministic stack-detection script. It then puts every route through one ten-step decision tree covering method, sensitivity, audience, versionability, staleness budget, invalidation, variants, cost × popularity, write consistency and failure mode. The output is a plan written from a fixed template and checked by a validator script. About **48 focused reference files** carry the layer, framework, CDN, CMS and platform detail, and Claude reads only the ones the detected stack needs.

No existing skill fills this role. Today's caching skills each cover one vendor or one layer: Vercel's Next.js skills and `vercel-optimize`, Cloudflare's router and `web-perf`, Redis's data-structure and semantic-cache skills, and Addy Osmani's performance skill. None designs a coordinated browser-to-database plan for an arbitrary stack, such as a Rails, Django, Laravel, Spring, .NET or Go app behind CloudFront, Fastly, Akamai or nginx.

The stakes are correctness as much as speed. Misconfigured caches exposed about 34,000 Steam users' account pages in 2015 and cached authenticated responses at Railway in March 2026, and frameworks keep shipping cache-poisoning CVEs. The skill must therefore default to `no-store`, make every route opt in, and prove safety with leak tests.

Its content also has to survive constant change. Next.js 16's two caching models, SvelteKit 3, Astro 7, React Router 8, five Cloudflare cache changes and CloudFront tag invalidation all landed in 2025–26, so every reference needs version-keyed guidance and a review date. Structurally, the skill should:

- use only the six open-standard frontmatter fields, so one folder installs in Claude Code, claude.ai, the API and roughly 46 other agent clients;
- ship scripts that need only the Python standard library, because the API sandbox has no network and cannot install packages;
- be built eval-first against one small fixture repo per app archetype.

## Existing skills stop at one vendor while cache mistakes leak data

As of October 2026, plenty of caching knowledge exists as agent skills, but each skill covers one vendor or one layer.

| Skill (owner) | What it covers | What it leaves out |
|---|---|---|
| `next-cache-components-adoption`, `-optimizer` and a partial-prefetching pair (Vercel, inside the Next.js repo) ([vercel/next.js skills](https://github.com/vercel/next.js/tree/canary/skills)) | Next.js Cache Components workflows | Everything outside Next.js |
| `vercel-optimize` v1.2.0 (Vercel) ([vercel-optimize](https://github.com/vercel-labs/agent-skills/tree/HEAD/skills/vercel-optimize)) | Cost and performance on Vercel, driven by metrics; 322-line SKILL.md with 15 scripts | Other hosts and non-JavaScript backends |
| `cloudflare` umbrella and `web-perf` (Cloudflare) ([cloudflare/skills](https://github.com/cloudflare/skills); [web-perf](https://github.com/cloudflare/skills/blob/HEAD/skills/web-perf/SKILL.md)) | Routes product questions over 139 bundled files; flags weak `Cache-Control` and `ETag` headers | No dedicated reference on cache rules or the Cache API |
| `redis-core`, `redis-connections`, `redis-semantic-cache` (Redis) ([redis/agent-skills](https://github.com/redis/agent-skills)) | Data structures, client-side caching over the RESP3 protocol, LLM semantic caching | HTTP and CDN layers |
| `performance` (Addy Osmani) ([web-quality-skills](https://github.com/addyosmani/web-quality-skills)) | Standard header recipes and service-worker caching | Stack-specific or server-side design |
| Community Next.js caching skills ([openskillindex](https://openskillindex.com/skills/comeonoliver-skillshub-nextjs-caching)) | Next.js only | Uneven quality; one still calls `'use cache'` experimental |

Anthropic's own skills repo and the official Claude Code marketplace contain no multi-layer caching skill ([anthropics/skills](https://github.com/anthropics/skills); [claude-plugins-official](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)).

The gap is the work that sits between these skills. Every one assumes you already know you are on Next.js, Vercel, Cloudflare or Redis. None of them detects an arbitrary stack, or keeps TTLs, cache keys and invalidation consistent across the browser, CDN, proxy, application cache and database. None covers Rails, Django, Laravel, Spring, ASP.NET or Go, or a CDN other than Vercel or Cloudflare. None treats cache security as a hard gate, and none produces a reviewable plan with a verification loop. The master skill should own exactly that cross-layer work. For implementation detail it should hand off to vendor skills when they are installed, the same way Cloudflare's router tells Claude to "load named skills when installed" ([cloudflare SKILL.md](https://github.com/cloudflare/skills/blob/HEAD/skills/cloudflare/SKILL.md)).

The safety gate matters because caching incidents keep repeating the same few failures.

- **Steam, December 2015.** A caching configuration change "incorrectly enabled caching for authenticated users". Store pages with billing details for **about 34,000 users** may have been served to strangers ([SteamDB](https://steamdb.info/blog/recent-caching-issues-on-steam)).
- **Railway, March 30, 2026.** A configuration change tied to a Surrogate Keys rollout turned on caching for domains whose CDN was switched off. For 52 minutes, "most GET responses without explicit cache headers were cached by default" ([Railway incident report](https://blog.railway.com/p/incident-report-march-30-2026-authenticated-user-data-cached)).
- **Slack, February 22, 2022.** A cache control plane replaced warm memcached nodes with empty spares during a Consul restart. The hit rate collapsed at peak and the Vitess databases were overwhelmed ([Slack Engineering](https://slack.engineering/slacks-incident-on-2-22-22/)).
- **Facebook, 2010.** The outage fed on itself because clients treated database errors as invalid values and deleted cache keys ([Facebook Engineering](https://engineering.fb.com/2010/09/23/uncategorized/more-details-on-today-s-outage/)).

Frameworks add risk of their own. Next.js's September 2026 security release fixed several cache-poisoning bugs and told users to move to **16.3.8 or 15.5.27** ([Next.js blog](https://nextjs.org/blog/september-2026-security-release)). Django 6.0.6 and 6.0.7 patched leaks through the shared cache. In one of them, CVE-2026-48588, a response that set a session cookie could be stored in the shared cache ([Django 6.0.7 notes](https://django.readthedocs.io/en/stable/_sources/releases/6.0.7.txt)).

The second design constraint is how fast the underlying tools change:

- Next.js 16 split caching into a Cache Components model and a "previous" model, each with different APIs ([Next.js caching docs](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)).
- SvelteKit 3 dropped `svelte.config.js` ([SvelteKit 3 migration](https://github.com/sveltejs/kit/blob/main/documentation/docs/60-appendix/35-migrating-to-sveltekit-3.md)).
- Astro 7 made route caching stable ([Astro v7 upgrade](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/upgrade-to/v7.mdx)).
- Between February and September 2026, Cloudflare made stale-while-revalidate asynchronous, added Cache Response Rules, started reporting `BYPASS` consistently, added `Vary` support to Cache Rules, and shipped a soft "invalidate" ([Cloudflare cache changelog](https://developers.cloudflare.com/changelog/product/cache/)).
- CloudFront added tag-based invalidation in April 2026 ([CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md)).

Even settled guidance ages. Advice from 2023 said Safari lacks `Clear-Site-Data` and Firefox dropped its `"cache"` directive. Current compatibility data shows Safari 17 support and Firefox re-enabling `"cache"` in version 138 ([BCD Clear-Site-Data](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Clear-Site-Data.json)).

Vercel's answer was to move its Next.js skills into the framework repo "so they stay version-matched with the framework instead of drifting" ([vercel-labs/next-skills](https://github.com/vercel-labs/next-skills)). A cross-vendor skill cannot live inside every framework's repo. It has to substitute version detection, guidance keyed to version ranges, and a review date on every reference file.

## Six audit passes and a ten-step decision tree tailor every plan

Tailoring starts with evidence, not recommendations. Azure's procedure for spotting the "no caching" antipattern makes a good backbone. It has five steps:

1. Take inventory of the data stores and how often each one changes.
2. Instrument the live system.
3. Profile it.
4. Load-test it.
5. Mine the statistics for repeated queries. In Azure's worked example, one query ran more than 250,000 times.

([Azure No-Caching antipattern](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/))

The skill should expand this into six passes:

| Pass | What the skill does | Output |
|---|---|---|
| 1. Fingerprint | Reads exact framework versions from lockfiles (SvelteKit 3 and React Router 8 moved their config conventions, so the version decides where to look). Reads hosting and CDN from deploy configs and infrastructure-as-code, and data stores and replica counts from Docker or Kubernetes manifests. | App profile |
| 2. Inventory | Lists every route with its method, auth requirement, cookies and headers read, query parameters, data sources and write side effects | Resource inventory |
| 3. Live probe (optional) | Fetches each resource class twice (expect `MISS` then `HIT`, with `Age` rising). Sends a conditional request and expects a 304. Repeats with and without a session cookie, and tries deception URLs. | Header table and leak findings |
| 4. Existing caches | Greps for cache headers, framework cache primitives, Redis, Memcached and LRU clients, client-side query caches and proxy configs | Inventory of existing caches with keys, TTLs and invalidation |
| 5. Baseline | Collects the metrics listed below, with date range and source | Dated baseline |
| 6. Classify | Runs the decision tree for each resource | Rows of the policy matrix |

No authoritative source publishes a map from repo files to caching implications, so the skill has to encode those fingerprint rules itself.

Probing has traps the skill must spell out:

- **No header does not mean "don't cache".** When `Cache-Control` is missing, caches apply heuristic freshness, typically 10% of the time since `Last-Modified`. Every response without the header is therefore a finding ([MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)).
- **Cloudflare's status labels changed.** Since May 26, 2026, Cloudflare reports `BYPASS` for every response it cannot cache, and `MISS` only for cacheable misses. The useful KPI is the hit ratio over cacheable traffic, with `BYPASS` volume tracked separately as the size of the opportunity ([Cloudflare changelog](https://developers.cloudflare.com/changelog/post/2026-05-26-bypass-status-for-uncacheable-responses/)).
- **Reloads distort measurements, differently per browser.** Chrome sends `max-age=0`, Safari sends `no-cache` plus `Pragma`, and a hard refresh revalidates even `immutable` subresources ([csswizardry](https://csswizardry.com/2025/03/why-do-we-have-a-cache-control-request-header/)).
- **Test conditions must stay separate.** Cold-cache, warm-cache and cache-disabled runs must never be mixed ([csswizardry 2026](https://csswizardry.com/2026/08/when-safaris-ignore-cache-ignored-cache-control/)).

The baseline should record these metrics:

- CDN request and byte hit ratios per path class.
- Origin requests per second and p95 latency per route.
- The read-to-write ratio per entity.
- Redis `keyspace_hits`, `keyspace_misses` and `evicted_keys`.
- Time to first byte at the 75th percentile, against web.dev's 0.8-second "good" threshold ([web.dev TTFB](https://web.dev/articles/ttfb)).
- Navigation types from the Chrome UX Report (CrUX). These expose a cheap win most plans ignore: the back/forward cache (bfcache). In Harry Roberts' BBC example, 13.7% of navigations used the bfcache and 5.4% were back/forward navigations that missed it, a **71.7% bfcache hit rate** ([csswizardry Cache Grab](https://csswizardry.com/2024/08/cache-grab-how-much-are-you-leaving-on-the-table/)).

Classification rests on three base patterns that MDN, Jake Archibald and Harry Roberts all converge on:

- **Immutable, versioned URLs** with a one-year `max-age`.
- **Mutable URLs that always revalidate** (`no-cache` plus an ETag).
- **A managed, purgeable shared cache** in front of mutable content.

Archibald calls the tempting fourth option, "a smallish max-age and mutable content", "a baaaad compromise". HTML, CSS and JavaScript that depend on each other expire at different times and fall out of sync ([Jake Archibald](https://jakearchibald.com/2016/caching-best-practices/); [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)).

The skill should run every route through the tree below. The first step that matches decides the policy, and the plan records which step that was.

| Step | Question | Outcome when it matches |
|---|---|---|
| 0 | Is the method anything other than GET or HEAD? | `no-store`. On success, run the invalidation hooks for the reads it affects. Stop. |
| 1 | Does it carry secrets or regulated data (tokens, payments, health data, balances)? | `no-store`, with no shared cache. A server-side cache is allowed only if it is scoped to the tenant or user, encrypted, and has a minimal TTL. Stop. |
| 2 | Does the body depend on who is asking (cookie, session, `Authorization`, tenant, entitlement, A/B bucket, geographic price)? | Fully personalized: `private, no-cache` plus an ETag, with server keys scoped to `{tenant}:{user}` and never `s-maxage`. Partly personalized: split a public shell from a private island (partial prerendering, `'use cache: private'`, edge-side includes or a client fetch), and strip `Set-Cookie` from the shell. |
| 3 | Can the URL change every time the content changes? | `max-age=31536000, immutable`. Add `public` only if `Authorization` never reaches these URLs. No invalidation needed. Stop. |
| 4 | What is the staleness budget S? | S = 0: browser `no-cache`, and re-read the source of truth at commit. Seconds to minutes: CDN `s-maxage=S` with `stale-while-revalidate` and `stale-if-error`, plus a 1–10 s micro-cache on hot routes. Hours to days: a long CDN TTL plus tag purge on publish. |
| 5 | Is event-driven invalidation available (tag purge, webhook, change data capture)? | Yes: long shared TTL plus soft purge, with an ETag so revalidation can return 304. No: shared TTL ≤ S, plus `stale-while-revalidate` and `stale-if-error`. |
| 6 | How many variants does each URL have? | Normalize `Accept-Language`, allow-list query parameters, strip tracking parameters, and never use `Vary: Cookie` or `Vary: User-Agent`. If variants far outnumber requests per TTL window, cache a lower layer instead. |
| 7 | Is the read both hot and expensive? | Cache-aside with a jittered TTL ≤ S, single-flight on misses, `stale-while-revalidate`, and an in-process L1 cache for the hottest keys. Otherwise fix the query or index. |
| 8 | Does the writer need to read their own writes immediately? | Write-through, or bypass the cache and pin reads to the primary database for N seconds after the write. |
| 9 | What happens when the cache or the origin fails? | Make the cache optional behind a circuit breaker, serve `stale-if-error`, and define how the app degrades. |

Steps 1 and 2 encode a rule Vercel's skill already enforces. A route "must be a public, cacheable GET path before a shared-cache recommendation is allowed", and "if the right policy is `no-store`, emit no-change" ([vercel-optimize cdn-cache-auth-safety](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md)).

Step 6 carries MDN's advice on limiting variants: use `private` instead of `Vary: Cookie`, and avoid `Vary: User-Agent` ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)).

Step 7 is where a server-side cache earns its place or doesn't. Azure warns that cache-aside suits neither sensitive data, nor static datasets (prime those at startup instead), nor workloads where most requests miss ([Azure Cache-Aside](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)). The skill should compute rather than guess, using two formulas:

- `effective_latency = h·L_hit + (1−h)·(L_hit + L_miss)`
- `DB_load = (1−h)·request_rate`

With a 1 ms Redis hit, a 50 ms database miss and a 90% hit rate (h = 0.9), latency falls to 6 ms and database reads fall tenfold. Going from 90% to 99% cuts reads tenfold again, so small hit-rate gains at the top matter more than they look. This arithmetic belongs in a small script rather than in prose.

Each outcome of the tree maps to a data-class matrix that the skill ships as an editable asset. Its header values follow MDN's recommended defaults and Harry Roberts' recipes ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching); [csswizardry, Cache-Control for Civilians](https://csswizardry.com/2019/03/cache-control-for-civilians/)). No vendor publishes a canonical table mapping data types to TTLs. The TTLs below are therefore starting points to check against each app's staleness budget, not standards.

| Data class | Browser `Cache-Control` | Shared cache / CDN | Server or data cache | Invalidation |
|---|---|---|---|---|
| Fingerprinted JS, CSS, fonts, images | `public, max-age=31536000, immutable` | Same | — | New URL per build; keep several old builds deployed |
| Fixed URLs (`favicon.ico`, `manifest.json`, `/.well-known/*`) | `no-cache` + ETag | `s-maxage` of 1 hour to 1 day | — | Purge on deploy |
| Service worker script | `no-cache` | Short or none | — | Deploy |
| Public HTML that rarely changes | `no-cache` + ETag | `s-maxage` of 1 day to 1 year, with 1 day of `stale-while-revalidate` | Framework data cache | Publish webhook triggers a tag invalidation |
| Public HTML that changes often (home page, news fronts, listings) | `max-age=0` | `s-maxage=30–300`, with `stale-while-revalidate` and `stale-if-error` | Fragment cache with tags | Purge on events, plus a short TTL as backstop |
| Fully personalized pages and APIs | `private, no-cache` + ETag | Bypass | Cache-aside scoped to tenant or user | Invalidate on write |
| Sensitive data (payments, health, auth, tokens) | `no-store` | Bypass | None | — |
| Public reference API (catalog, config) | `public, max-age=60–300`, or `no-cache` + ETag | `s-maxage` of hours, plus tags | Preload at startup | Purge on admin publish; versioned keys |
| Volatile public API (price, stock) | `no-cache` | 1–30 s, or none | Short TTL plus events | Event-driven; re-check at commit |
| Search and faceted listings | `no-cache` or `max-age=60` | Only the most popular queries, normalized | Result cache for popular queries | TTL plus index-update events |
| Mutations | `no-store` | Never | Trigger invalidation | Emit tags or events |
| LLM outputs and embeddings | `private` / `no-store` | None | Exact-match, embedding and guarded semantic caches | Model and prompt version in the key |

App archetypes then set defaults for the whole matrix. Archetypes differ in four things: the share of traffic that is public, the staleness budget of the hot data, the write rate, and how many variants each URL has. The skill should guess the archetype while fingerprinting, confirm it with the user, and then load `archetypes.md`.

| Archetype | Dominant constraint | Core of the blueprint |
|---|---|---|
| Static, docs, marketing | Nearly all traffic is public | Static generation or incremental regeneration; immutable assets; HTML `no-cache` in the browser and a long `s-maxage` at the CDN, purged on deploy or publish; strip `utm_*` from the cache key; bfcache and speculation rules |
| News and media | Traffic spikes plus freshness measured in minutes | Articles cached for hours to days with tag purge (article, section, author); front pages at `s-maxage=30–60` with `stale-while-revalidate`; origin shield and request collapsing; a target time from purge to visible; paywall state never in public HTML |
| E-commerce | Several staleness budgets on one page | Catalog and product copy cacheable with tags; price and stock in islands with short TTLs or event-driven updates, re-checked against the source at checkout; cart `private`; checkout `no-store`; normalized facet parameters |
| Multi-tenant SaaS and B2B | Mostly private data | CDN only for assets and the marketing site; APIs `private` with ETags; every key prefixed `t:{tenant}:`; precomputed aggregates; permission cache TTL no longer than the acceptable revocation delay |
| Social and user-generated content | Fan-out and counters | Object cache keyed by ID and version; precomputed feeds in Redis; counters via Redis `INCR` with periodic flushes; a takedown purge pipeline |
| Real-time and collaborative | Live state | Cache only assets and the initial snapshot; live state held in memory on sharded servers; `no-store` on live endpoints |
| Public REST or GraphQL API | HTTP semantics are the product | ETags and 304s; `public` or `private` by audience; `Vary` only on content-negotiation headers; persisted GraphQL queries sent as GET; gateway cache keys include caller identity |
| Mobile backend | Old app versions stay installed for months | Validators for cheap 304s; TTLs set by the server, not hard-coded in the app; versioned cache busters; config JSON served from the CDN |
| Internal tools | Low traffic, high cost of wrong data | `private, no-cache`; fix queries first; cache only expensive reference lookups |
| AI and LLM apps | Token cost | Provider prefix caching first; exact-match, embedding and retrieval caches; semantic caching only for public FAQs |
| Video and large media | Origin egress cost | Immutable segments behind an origin shield; live manifests with a TTL of about half a segment; respect the CDN's maximum object size |

Published case studies all show several cache tiers working together:

- **Shopify's storefront renderer** stores final HTML or JSON in a Redis instance local to each node, shared by that node's workers and layered over in-memory and query caches ([Shopify Engineering](https://shopify.engineering/simplify-batch-cache-optimized-server-side-storefront-rendering)).
- **Shopify's Shop app** added a custom write-through cache for its home feed. It cut database load by **15%** and latency by about **20%** ([Shopify Engineering](https://shopify.engineering/shop-app-custom-caching-solution)).
- **Wikimedia** runs Varnish in RAM in front of disk-backed Apache Traffic Server caches. Its multicast purge messages (HTCP) suffered packet loss and races between tiers. That is why the news blueprint includes a target for purge-to-visible latency ([Wikimedia T133821](https://phabricator.wikimedia.org/T133821)).
- **Discord** collapses identical reads into one and routes them by channel ID with consistent hashing, with reported p99 reads around 15 ms against 40–125 ms before ([InfoQ](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)).

The social, real-time and news blueprints rest more on vendor documentation and synthesis than on case studies. Write-ups from Figma, Notion, the Guardian and others could not be retrieved.

The plan sequences work by expected return. This is a consensus order rather than a measured ranking; no primary source ranks caching changes quantitatively.

| Phase | Work |
|---|---|
| 0 | Safety: remove shared caching from personalized responses |
| 1 | Hashed static assets marked `immutable` |
| 2 | An explicit `Cache-Control` header and validators on every response |
| 3 | CDN caching for public HTML and APIs, with `stale-while-revalidate`, `stale-if-error`, tag purge and cache-key normalization |
| 4 | bfcache and speculation rules |
| 5 | Server-side caching for measured hot, expensive reads |
| 6 | API ETags and client-side query caches |
| 7 | Origin shields, `No-Vary-Search`, service workers and edge key-value stores |

Build and CI caching runs in parallel. Azure's warning shapes the rollout: adding a cache can shift the bottleneck so far that the web front end starts returning 503s ([Azure No-Caching](https://learn.microsoft.com/en-us/azure/architecture/antipatterns/no-caching/)). Each phase therefore gets a canary and a load test.

The deliverable is one document with these sections:

0. Summary
1. App profile
2. Dated baseline
3. Constraints: sensitive data classes, staleness budgets, compliance (including GDPR erasure paths) and tenancy
4. Policy matrix, one row per route
5. Design for each cache layer
6. Invalidation map, linking each event to the entities it touches, the tags or keys to purge, the mechanism, the expected propagation time and an owner
7. Failure safeguards
8. Phased rollout
9. Verification and monitoring
10. Rollback (a CDN bypass rule, a header revert, or bumping the cache namespace version)
11. Ownership and review cadence

Vercel's skill sets the bar for each row. A recommendation must name the "mechanism, scope, TTL/freshness, and `Vary`", plus the exact cache primitive for the detected framework version ([vercel-optimize](https://github.com/vercel-labs/agent-skills/blob/main/skills/vercel-optimize/references/support-topics/cdn-cache-auth-safety.md)). A condensed example of the matrix:

| ID | Route | Class | Staleness budget | Browser | Shared cache | App layer | Invalidation | Verify |
|---|---|---|---|---|---|---|---|---|
| R1 | `/_next/static/*` | Fingerprinted asset | Unlimited (versioned) | `public, max-age=31536000, immutable` | Same | — | New hash on each build | `curl -sI` shows `immutable` |
| R2 | `/products/[slug]` | Public shell with a price island | Copy 1 h; price 60 s | `no-cache` | `s-maxage=3600, stale-while-revalidate=86400` | `cacheLife('hours')`, `cacheTag('product:{id}')` | Product webhook calls `revalidateTag('product:{id}', 'max')` and invalidates the CDN tag | Two `curl` requests show `HIT` with rising `Age`; purge visible in under 30 s |
| R3 | `/api/cart` | Personalized API | 0 | `private, no-cache` | Bypass | — | — | Leak test with two sessions |
| R4 | `/checkout/*` | Sensitive | 0 | `no-store` | Bypass | — | — | Never shows `HIT` or `Age` |

## Sixteen layers map to 48 reference files built around gotchas

Anthropic's skill guidance and the agentskills guide agree on what reference content is for. Claude "is already very smart", so a skill should add only what Claude would otherwise get wrong. Gotchas, the non-obvious rules, are "the highest-value content in many skills" ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)). Each reference file should therefore hold four things:

- the current default recipe;
- the counter-intuitive rules;
- version notes, with superseded APIs folded into an "old patterns" block;
- pointers to ready-made config snippets.

The map below covers every layer in the brief. The subsections after it give the cited rules each file must carry.

| Layer | Reference file(s) | What it holds |
|---|---|---|
| Decision logic | `core/decision-framework.md`, `core/archetypes.md` | Decision tree, data-class matrix, TTL ladder, ROI order, archetype blueprints |
| HTTP semantics | `core/http-semantics.md` | RFC 9111/9110 directives, validators, `Vary`, CDN-targeted headers, recipes per resource type, TTLs for redirects and errors |
| Browser platform | `layers/browser-platform.md` | bfcache, cache partitioning, speculation rules, `No-Vary-Search`, compression dictionaries, `Clear-Site-Data`, asset versioning and deploy skew |
| Service workers | `layers/service-workers.md` | Lifecycle, Workbox strategy per route, Cache API cleanup, storage quotas and eviction |
| CDN and edge | `layers/cdn-concepts.md` plus `platforms/{cloudflare,vercel,netlify,fastly,cloudfront,akamai,gcp-azure-cdn,other-hosts}.md` | Defaults, cache-key rules, CDN-only headers, purge APIs and limits, origin shields, stale serving, edge data stores, image variants |
| Reverse proxies | `layers/reverse-proxies.md` | nginx proxy and FastCGI micro-caching, Varnish grace and xkey, HAProxy, Caddy/Souin, Traefik |
| Frontend frameworks | `frameworks/{nextjs,nuxt-nitro,sveltekit,react-router-remix,astro,other-frontend}.md` | APIs keyed to version, how each framework sets headers, self-hosting cache handlers, CDN pitfalls |
| Client data caches | `frameworks/client-data-caches.md` | Defaults and persistence for TanStack Query, SWR, Apollo, Relay, urql and RTK Query |
| Backend frameworks | `frameworks/{rails,django,laravel-php,spring-jvm,aspnet,node-backends,python-async,go,elixir}.md` | Cache stores, decorators, HTTP helpers, stampede options, pitfalls, PHP OPcache |
| CMS and commerce | `cms/{wordpress,drupal,shopify-hydrogen,magento,headless-cms}.md` | Page and object caches, tags and contexts, caching strategies for sub-requests, webhook revalidation |
| In-process caches | `layers/in-process.md` | Library per runtime, eviction algorithms, memory bounds, drift between instances |
| Distributed caches | `layers/distributed-cache.md` | Engine choice and licensing, config, key naming, serialization, big and hot keys, two-tier L1+L2 setups, client-side caching, sizing math |
| Database | `layers/database-orm.md` | Buffer caches, query-cache proxies, materialized views, read replicas, ORM caches, connection poolers |
| Serverless and edge data | `layers/serverless-edge-data.md` | Connection budgets, Redis over HTTP, consistency of key-value stores, platform runtime caches |
| APIs | `layers/api-graphql-rpc.md` | Cacheable GET design, API gateways, GraphQL persisted queries and response caches, DataLoader, gRPC/Connect, tRPC |
| Mobile | `layers/mobile-native.md` | iOS URLCache, Android OkHttp, image caches, offline-first stores, skew between app versions |
| AI and LLMs | `layers/ai-llm.md` | Provider prompt caching; exact-match, embedding, retrieval and semantic caches |
| Correctness | `core/invalidation-consistency.md`, `core/stampede-failure.md` | Invalidation strategies, races, leases, TTL design, defenses against stampedes and failures |
| Security and verification | `core/security.md`, `core/observability-testing.md` | Attack classes, CVE watchlist, tenant isolation, metrics, debug headers, test recipes |
| Adjacent layers | `layers/build-ci-network.md` | CI, package, Docker and monorepo caches; DNS TTLs; TLS resumption and 0-RTT; connection reuse; OS page cache |

### Most HTTP mistakes come from misreading four directives

RFC 9111, the HTTP caching standard, is routinely misremembered ([RFC 9111](https://httpwg.org/specs/rfc9111.html)):

- **`no-cache` does not prevent storage.** It means "store, but revalidate before every reuse". Only `no-store` prevents storage.
- **`must-revalidate` applies only once a response is stale.** Even then it can turn an origin outage into 504 errors.
- **`s-maxage` carries `proxy-revalidate` semantics.** Shared caches may not serve the response once it is stale.
- **`public` overrides restrictions.** A cache "MAY store the response even if it would otherwise be prohibited". Together with `must-revalidate` and `s-maxage`, it is one of only three directives that let a shared cache store a response to a request that carried `Authorization`.

Other rules the reference must state:

- **Heuristic caching applies to many status codes.** These are 200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414 and 501, so a 301 or a transient 404 sent without headers can stick in caches ([RFC 9110](https://httpwg.org/specs/rfc9110.html)).
- **Browser support is uneven.** Firefox and Safari honor `immutable`, but Chrome has never implemented it. Browsers have supported `stale-while-revalidate` since Chrome 75, Firefox 68 and Safari 14 ([BCD Cache-Control](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Cache-Control.json)).
- **The "kitchen-sink" header is redundant.** `private, no-cache, no-store, max-age=0, must-revalidate` is "basically meaningless": it amounts to `no-store`, which also gives up the bfcache ([MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)).
- **Shared caches collapse concurrent requests.** They merge simultaneous requests into one even for `max-age=0` responses, so personalized responses need `private` ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)).

Validators (ETags and `Last-Modified`) have traps of their own:

- nginx downgrades strong ETags to weak ones when it gzips a response, and drops unquoted upstream ETags entirely ([nginx trac #377](https://trac.nginx.org/nginx/ticket/377)).
- JavaScript that adds `If-None-Match` to a `fetch()` call silently switches that request to `no-store` cache mode ([Fetch Standard](https://fetch.spec.whatwg.org/#concept-request-cache-mode)).
- An `Access-Control-Allow-Origin` value computed per request needs `Vary: Origin` ([Fetch Standard](https://fetch.spec.whatwg.org/#cors-protocol-and-http-caches)).

The browser platform shifted a lot in 2025–26:

- **Cache partitioning.** Since Chrome 86, the HTTP cache has been keyed by the top-level site, so shared public CDN copies of libraries never produce cross-site hits and should be self-hosted ([Chrome](https://developer.chrome.com/blog/http-cache-partitioning)).
- **bfcache with `no-store`.** Chrome finished enabling the bfcache for `no-store` pages in spring 2025, with a 3-minute timeout and eviction when cookies change ([Chrome bfcache-ccns](https://developer.chrome.com/docs/web-platform/bfcache-ccns)). Pages that must not be restored after logout therefore need a `pageshow` re-check, not `no-store` alone.
- **`unload` handlers.** From Chrome 155, these fire only when the `Permissions-Policy` header opts in ([BCD](https://github.com/mdn/browser-compat-data/blob/main/api/Window.json)).
- **`No-Vary-Search`.** This header reaches the HTTP cache in Chrome 141 and Firefox 154 but not Safari ([BCD](https://github.com/mdn/browser-compat-data/blob/main/http/headers/No-Vary-Search.json)). In January 2026 Chrome engineers warned that a syntax change could break deployments ([IETF list](https://lists.w3.org/Archives/Public/ietf-http-wg/2026JanMar/0027.html)), so it stays a progressive enhancement.
- **Compression dictionaries (RFC 9842).** These work in Chrome 130+, and a dictionary is silently ignored unless it has a positive freshness lifetime ([MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)).
- **Speculation rules.** Prefetched pages are cached for 5 minutes ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)).
- **HTTP/2 Server Push** is gone ([Chrome](https://developer.chrome.com/blog/removing-push)).

Two more traps belong in this file. The Lighthouse and DevTools insight "Use efficient cache lifetimes" skips anything marked `no-cache`, `no-store`, `must-revalidate` or `private`, and ignores TTLs of 30 days or more, so a passing score says nothing about HTML policy ([devtools Cache.ts](https://github.com/ChromeDevTools/devtools-frontend/blob/main/front_end/models/trace/insights/Cache.ts)). Deploy skew means tabs still running an old build request chunks that a deploy deleted, and fail with `ChunkLoadError`. Old hashed assets must therefore stay deployed longer than the maximum cache age of HTML and service workers ([Sentry](https://sentry.io/answers/chunk-load-errors-javascript)).

Service workers form a separate cache with separate rules:

- **The Cache API** is "entirely separate from the HTTP cache", and its entries never expire unless deleted ([MDN Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)).
- **Workbox 7.4.1** (May 2026) is current. Its `pageCache()` recipe is NetworkFirst with a 3-second timeout, and `imageCache()` keeps 60 entries for 30 days ([workbox-recipes](https://www.npmjs.com/package/workbox-recipes)).
- **Update checks.** Since Chrome 68, update checks for the main service-worker script bypass the HTTP cache ([MDN register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register)).
- **Safari eviction.** Safari deletes script-created storage for origins without user interaction in the last 7 days ([MDN storage quotas](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)).

The classic bug is synthesized rather than cited, but worth stating: a CacheFirst route on URLs without content hashes gets "stuck forever" on an old version.

### CDN defaults diverge so much that the vendor must be known first

The skill has to answer "which CDN?" before giving any header advice, because the defaults differ:

- **Cloudflare** decides by file extension and never caches HTML or JSON by default ([Cloudflare](https://developers.cloudflare.com/cache/concepts/default-cache-behavior)).
- **Azure Front Door** caches a response with no cache directive for **1–3 days** ([Azure](https://learn.microsoft.com/azure/frontdoor/front-door-caching)).
- **Akamai** ignores the origin's `Cache-Control` unless its Caching behavior is set to honor it ([Akamai](https://techdocs.akamai.com/property-mgr/docs/know-caching)).
- **Google Cloud CDN** has a `FORCE_CACHE_ALL` mode that ignores `private` and `no-store` ([GCP](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy)).
- **CloudFront** policies with a minimum TTL above zero can override an origin's `no-store` ([AWS](https://docs.aws.amazon.com/es_es/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)).

CDN-only headers let one response set separate lifetimes for the browser, downstream CDNs and the vendor's own edge. RFC 9213 defines `CDN-Cache-Control`, and Vercel and Cloudflare each add a vendor-only variant that is stripped before the response is forwarded ([RFC 9213](https://httpwg.org/specs/rfc9213.html); [Vercel](https://vercel.com/docs/caching/cdn-cache); [Cloudflare](https://developers.cloudflare.com/workers/cache/configuration/)). Fastly uses `Surrogate-Control` ([Fastly](https://developer.fastly.com/reference/http-headers/Surrogate-Control/)).

One Cloudflare trap needs special mention. Sending `s-maxage`, `must-revalidate` or `no-cache` alongside `stale-while-revalidate` silently disables stale serving ([Cloudflare revalidation](https://developers.cloudflare.com/cache/concepts/revalidation/)). The portable edge header is therefore `CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400`.

By the end of 2026, every major CDN had a "soft purge" that marks content stale instead of deleting it:

- **Cloudflare** added `invalidate_cache` on September 28. It revalidates with the origin and reuses the cached body if the origin answers 304 ([Cloudflare](https://developers.cloudflare.com/cache/guides/invalidate-cache/)).
- **Vercel** separates `invalidateByTag` from `dangerouslyDeleteByTag` ([Vercel](https://vercel.com/docs/caching/cdn-cache/purge)).
- **Fastly** uses the `Fastly-Soft-Purge: 1` header ([Fastly](https://docs.fastly.com/en/guides/soft-purges)).
- **Akamai** separates "invalidate" from "delete" ([Akamai](https://techdocs.akamai.com/purge-cache/docs/purge-methods)).

Tag limits set the floor for any tag scheme:

| Vendor | Tag limit | Notes |
|---|---|---|
| CloudFront | 50 tags per object | Each tag is billed as a path, against 1,000 free paths a month ([CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md); [CloudFront pricing](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PayingForInvalidation.md)) |
| Vercel | 128 tags per response | Tags are case-sensitive ([Vercel](https://vercel.com/docs/caching/cdn-cache/purge)) |
| Cloudflare | About 1,000 tags | Limited by a 16 KB header ([Cloudflare](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/)) |
| Fastly | 16 KB header | Keys beyond the limit are silently dropped and can never be purged ([Fastly](https://www.fastly.com/documentation/ja/guides/full-site-delivery/purging/purging-with-surrogate-keys/)) |

The skill should therefore prescribe at most 50 lowercase tags per response. Cloudflare's Free plan allows only 5 tag-purge requests per minute ([Cloudflare](https://developers.cloudflare.com/cache/how-to/purge-cache/)), so CMS webhooks must batch and debounce purges. The order also matters: update the origin first, then purge, and purge inner layers before outer ones.

Tiering and edge data stores have their own gotchas:

- **Smart Tiered Cache.** Cloudflare's version is free on all plans ([Cloudflare](https://developers.cloudflare.com/cache/how-to/tiered-cache/)).
- **Workers Cache API.** It neither collapses concurrent requests nor uses tiers ([Workers limitations](https://developers.cloudflare.com/workers/cache/limitations/)).
- **Workers Caching.** It puts the Worker version in the cache key by default, so every deploy starts cold ([cache keys](https://developers.cloudflare.com/workers/cache/cache-keys/)).
- **Workers KV.** A write can take up to 60 seconds to propagate ([KV](https://developers.cloudflare.com/kv/api/write-key-value-pairs/)).
- **Fly.io.** Its proxy does no HTTP response caching at all ([Fly](https://fly.io/docs/reference/fly-proxy/)).
- **Next.js 16 images.** They now have a 4-hour minimum TTL, and the number of cached variants multiplies across sources × qualities × widths × formats ([Vercel KB](https://vercel.com/kb/guide/reduce-image-optimization-costs-on-vercel)).

For self-hosted origins, the defaults are:

- **nginx** micro-caching with `proxy_cache_lock`, `proxy_cache_use_stale updating` and `proxy_cache_background_update` ([F5 NGINX](https://www.f5.com/pt_br/company/blog/nginx/nginx-caching-guide)).
- **Varnish** for stale serving ("grace") and tag invalidation through soft purges with the xkey module ([Varnish](https://www.varnish.org/docs/tutorials/cache-invalidation/)).
- **HAProxy** only with care: its cache lives in memory, is capped at 4,095 MB, and skips any response with `Vary` unless `process-vary` is on ([HAProxy](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/performance/caching)).

When a CDN with tag purge sits in front, the origin proxy's TTL should stay at 1–10 seconds so it doesn't become a second invalidation problem.

### Framework guidance must be keyed to the detected version

The current stable lines are Next.js 16.4, Nuxt 4.6, SvelteKit 3.1, React Router 8.5, Astro 7.4 and Angular 22.2 ([npm registry](https://registry.npmjs.org/next)). Next.js needs the most careful handling:

- **Two caching models.** Under Cache Components (`cacheComponents: true`), everything is dynamic until opted in with `'use cache'`, `cacheLife` and `cacheTag`. The previous model keeps `fetch` cache options, `unstable_cache` and per-segment `revalidate` ([Next.js caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/01-getting-started/08-caching.mdx)). The skill must never add `'use cache'` to an app without the flag, because turning the flag on is a migration.
- **`revalidateTag`.** The single-argument form is deprecated and behaves as immediate expiry, so use `revalidateTag(tag, 'max')` ([revalidateTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/revalidateTag.mdx)).
- **`updateTag`.** It works only in Server Actions, so CMS webhook routes must use `revalidateTag` ([updateTag](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/04-functions/updateTag.mdx)).
- **Deploys.** `'use cache'` entries never survive one, because the build ID is part of the key ([use cache](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/01-directives/use-cache.mdx)).
- **Self-hosting on several instances.** This needs both a shared `cacheHandler` and `cacheHandlers` ([cacheHandlers](https://github.com/vercel/next.js/blob/canary/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheHandlers.mdx)).
- **A CDN in front.** It must forward the `rsc` header, include `_rsc` in its cache key, and be purged alongside `revalidateTag` ([Next.js CDN caching](https://github.com/vercel/next.js/blob/canary/docs/01-app/02-guides/cdn-caching.mdx)).
- **OpenNext on AWS.** It still needs a CloudFront invalidation after each revalidation ([OpenNext AWS](https://github.com/opennextjs/docs/blob/main/pages/aws/inner_workings/caching.mdx)).

The classic complaint "revalidation works locally but not in production" almost always means a CDN copy is still being served.

Other frameworks have their own traps:

- **Nuxt and Nitro.** `defineCachedEventHandler` defaults `maxAge` to **1 second**, drops request headers unless they are listed in `varies`, and stores entries in per-instance memory in production ([Nitro cache](https://github.com/nitrojs/nitro/blob/v2/docs/1.guide/6.cache.md)).
- **SvelteKit.** It has no server-side data cache, and setting the same header in two `load` functions is an error ([SvelteKit load](https://github.com/sveltejs/kit/blob/main/documentation/docs/20-core-concepts/20-load.md)).
- **React Router.** It does not send loader headers automatically; the route's `headers` export must re-emit them ([React Router headers](https://github.com/remix-run/react-router/blob/main/docs/how-to/headers.md)).
- **Astro 7.** `cache.invalidate` throws if no cache provider is configured ([Astro caching](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/caching.mdx)). Server islands on CDN-cached pages need a fixed `ASTRO_KEY` ([Astro server islands](https://github.com/withastro/docs/blob/main/src/content/docs/en/guides/server-islands.mdx)).

Client-side data caches need their defaults stated:

- **TanStack Query** treats data as stale immediately and garbage-collects inactive queries after 5 minutes. With `staleTime: 'static'`, it blocks even manual invalidation ([TanStack](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/important-defaults.md)). Its server-rendering guide asks for a `staleTime` above zero to avoid an immediate refetch after hydration ([TanStack SSR](https://github.com/TanStack/query/blob/main/docs/framework/react/guides/advanced-ssr.md)).
- **SWR** de-duplicates identical requests within 2 seconds ([SWR](https://github.com/vercel/swr-site/blob/main/content/docs/api.mdx)).
- **Apollo Client 4** now defaults `notifyOnNetworkStatusChange` to true ([Apollo](https://github.com/apollographql/apollo-client/blob/main/docs/source/migrating/apollo-client-4-migration.mdx)).
- **RTK Query** drops unused data after 60 seconds ([RTK](https://github.com/reduxjs/redux-toolkit/blob/master/docs/rtk-query/usage/cache-behavior.mdx)).

Backend frameworks each have one recommended default and at least one silent trap:

| Framework | What to recommend | Gotcha the reference must state |
|---|---|---|
| Rails 8 | Solid Cache, the default database-backed store (37signals' cache passed **10 TB** on disk) ([Honeybadger](https://www.honeybadger.io/blog/rails-8/)) | Russian-doll invalidation fails silently without `touch: true` ([Rails Guides](https://guides.rubyonrails.org/caching_with_rails.html)); `race_condition_ttl` does not stop stampedes while the cache is first filling ([Kit Engineering](https://engineering.kit.com/2019/10/29/we-built-our-own-cache/)) |
| Django 6.x | Redis backend, `cache_control`, conditional GET, low-level caching for hot queries | `cache_page` does not vary on cookies or authentication by default, and middleware order decides whether `Vary` is honored ([Django cache docs](https://docs.djangoproject.com/en/6.0/topics/cache/)); pin the 2026 patch releases that fixed the leaks |
| Laravel 13 | `Cache::flexible` (stale-while-revalidate), request-scoped `Cache::memo()`, the `failover` store, `Cache::touch()` ([Laravel docs](https://laravel.com/docs/12.x/cache); [Laravel News 12.35](https://laravel-news.com/laravel-12-35-0)) | `optimize:clear` also wipes application data from the default store ([benjamincrozat](https://benjamincrozat.com/laravel-clear-cache)) |
| Spring Boot 4 | Caffeine for local caching, Redis for shared caching, `sync=true` against stampedes | A method calling another method on the same bean bypasses `@Cacheable`; `sync=true` cannot be combined with `unless` ([Spring](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)); `CompositeCacheManager` does not create tiers ([devops-monk](https://blog.devops-monk.com/2026/05/spring-boot-caching-caffeine-redis/)) |
| ASP.NET Core (.NET 10) | Output Caching for responses; HybridCache (in-process plus distributed, stampede protection, tags) for data ([MS Learn output caching](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output?view=aspnetcore-10.0); [HybridCache](https://learn.microsoft.com/aspnet/core/performance/caching/hybrid)) | Output Caching refuses authenticated and cookie-setting responses by default; caching them needs a per-user vary |
| Node (Express, NestJS) | Explicit headers plus Redis cache-aside | Express generates weak ETags by default ([expressjs#2667](https://github.com/expressjs/express/issues/2667)) |
| FastAPI | `cashews` or explicit Redis ([FastAPI-CacheX PR #449](https://github.com/allen0099/FastAPI-CacheX/pull/449)) | `fastapi-cache2` has had no release since 2024 ([FastAPI-CacheX #423](https://github.com/allen0099/FastAPI-CacheX/issues/423)) |
| Go | Otter v2 or ristretto, plus `singleflight` ([Otter](https://github.com/maypok86/otter)) | A ristretto `Set` is not guaranteed to be stored ([ristretto](https://pkg.go.dev/github.com/dgraph-io/ristretto)) |
| PHP runtime | OPcache always enabled | OPcache is compiled in from PHP 8.5; JIT has been off by default since 8.4 ([PHP manual](https://www.php.net/manual/en/opcache.configuration.php)) |

CMS platforms add their own layers:

- **WordPress** needs an `object-cache.php` drop-in before Redis does anything ([Hostinger](https://www.hostinger.com/tutorials/what-is-object-cache/)). Plugins that set cookies can make every visitor bypass Cloudflare APO ([StackHarbor](https://stackharbor.com/en/knowledge-base/wp-cdn-cloudflare-apo-deep-config/)).
- **Drupal** propagates cache tags, contexts and max-age up through its render arrays ([Drupal.org](https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays)). Its Internal Page Cache, however, applies one site-wide max-age to anonymous responses ([Lullabot](https://www.lullabot.com/articles/common-max-age-pitfalls-with-drupal-cache)).
- **Shopify Hydrogen's** `CacheLong` strategy means 1 hour fresh plus 23 hours of `stale-while-revalidate` ([Shopify](https://shopify.dev/docs/api/hydrogen/latest/utilities/caching/cachelong)).
- **Adobe Commerce** has replaced Redis with Valkey in its current patches ([Experience League](https://experienceleague.adobe.com/en/docs/commerce-operations/implementation-playbook/best-practices/planning/redis-valkey-service-configuration)).
- **Sanity** runs an API CDN with roughly 10 minutes of `stale-while-revalidate` that Next.js `revalidate` does not control ([Sanity](https://www.sanity.io/answers/difference-between-api-requests-and-cdn-requests-in-sanity-io-)).
- **Contentful** webhooks should tag by `sys.id` rather than by slug ([Contentful](https://www.contentful.com/blog/nextjs-cache-components/)).

### Data-layer choices turn on eviction, licensing and staleness models

**In-process caches.** Eviction that tracks how often keys are used should be the default. Caffeine's W-TinyLFU gives "near optimal" hit rates for about 8 bytes of sketch per entry ([Caffeine](https://github.com/ben-manes/caffeine/wiki/Efficiency)). The newer S3-FIFO and SIEVE algorithms build on the same observation that most cached objects are used only once ([S3-FIFO](https://junchengyang.com/publication/sosp23-s3fifo.pdf); [SIEVE](https://junchengyang.com/slides/nsdi24-SIEVE.pdf)). The skill should name one default library per runtime: Caffeine (JVM), Otter v2 (Go), Moka (Rust), cachetools (Python), and lru-cache v11 (Node), which refuses to run unbounded without `max`, `ttl` or `maxSize` ([lru-cache](https://github.com/isaacs/node-lru-cache); [Otter](https://github.com/maypok86/otter)). It should also state that each instance's in-process cache (L1) is a separate copy that can drift. Its TTL must stay shorter than that of the shared cache (L2).

**Distributed caches.** In 2026 the choice of engine turns on licensing. Valkey (BSD-3) shipped version 9.0 with multi-database clusters ([Linux Foundation](https://www.linuxfoundation.org/press/valkey-9.0-delivers-performance-and-resiliency-for-real-time-workloads)), and ElastiCache Serverless for Valkey is priced **33%** below the Redis OSS option ([AWS](https://aws.amazon.com/blogs/database/amazon-elasticache-and-amazon-memorydb-announce-support-for-valkey/)). Redis 8 is tri-licensed, with AGPLv3 as one option ([redis/redis](https://github.com/redis/redis)). Azure Cache for Redis stopped allowing new instances for all customers on October 1, 2026 ([Azure](https://docs.azure.cn/en-us/azure-cache-for-redis/cache-retired-features)).

Configuration traps follow:

- **Eviction is off by default.** Open-source Redis defaults to `noeviction` ([Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)), so a cache must set `maxmemory` and an `allkeys-*` eviction policy.
- **Size against usable memory.** ElastiCache reserves 25% of memory by default ([ElastiCache](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/redis-memory-management.html)).
- **Client-side caching needs new versions.** Server-assisted client-side caching requires the RESP3 protocol and Redis 7.4, as in Jedis 5.2 ([Redis blog](https://redis.io/blog/faster-redis-client-library-support-for-client-side-caching/)).

**Databases.** The cheapest cache is already there, so tune it before adding layers. Postgres `shared_buffers` usually starts at about 25% of RAM ([CYBERTEC](https://pgconfigurator.cybertec-postgresql.com/docs/parameters/shared_buffers)). MySQL removed its query cache in version 8.0 ([Readyset](https://readyset.io/blog/mysql-5-7-eol-the-end-of-mysql-query-cache)).

Each transparent query cache has its own staleness model:

- **Cloudflare Hyperdrive** caches reads for 60 seconds, with 15 seconds of `stale-while-revalidate`, and "does not invalidate cached read query results when your application writes" ([Hyperdrive](https://developers.cloudflare.com/hyperdrive/concepts/query-caching/)).
- **Prisma Accelerate** takes `ttl`, `swr` and tags per query ([Prisma](https://prisma.io/docs/accelerate/api-reference)).
- **Hibernate's query cache** can increase query counts when its expirations don't match the entity cache's ([DZone](https://dzone.com/articles/pitfalls-hibernate-second-0)).

Connection poolers are not caches, but they interact with prepared-statement caching. PgBouncer gained transaction-mode prepared statements only in version 1.21 ([Crunchy Data](https://www.crunchydata.com/blog/prepared-statements-in-transaction-mode-for-pgbouncer)).

**Serverless.** The typical failure is connection fan-out: 1,000 concurrent invocations hold 1,000 connections. Redis over HTTP, and small capped connection pools created at module scope, should be the defaults ([OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-connection-short-lived-functions/markdown)).

### API, mobile and AI caching each have one dominant hazard

**APIs.** AWS API Gateway caches GET responses for 300 seconds by default, up to 3,600. Unless "Require authorization" is enabled, any client can invalidate an entry by sending `Cache-Control: max-age=0` ([AWS](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html)).

GraphQL sent over POST defeats caches keyed by URL. Persisted queries sent as GET fix this ([Apollo APQ](https://www.apollographql.com/docs/apollo-server/performance/apq)). Apollo Server 4 reached end of life on January 26, 2026 ([Apollo migration](https://apollographql.com/docs/apollo-server/migration)).

Response caches need a per-session partition. Yoga's `useResponseCache` takes a `session` function and invalidates entries when a mutation touches them ([Yoga](https://the-guild.dev/graphql/yoga-server/docs/features/response-caching)). Grafbase scopes its entity cache by the headers it forwards ([Grafbase](https://grafbase.com/docs/gateway/performance/entity-caching)).

Two more API points:

- **DataLoader** must be created per request, since it "does not replace Redis" or other shared caches ([DataLoader](https://github.com/graphql/dataloader)). Connect RPC can serve methods marked `NO_SIDE_EFFECTS` over cacheable GET ([Connect](https://connectrpc.com/docs/go/get-requests-and-caching/)).
- **Idempotency keys** make writes safe to retry; they are not a read cache. The IETF draft for them expired in April 2026 ([IETF](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/)).

**Mobile.** Mobile clients cache whatever the server's headers allow:

- **HTTP caches.** iOS `URLCache` defaults to the protocol's cache policy ([tanaschita](https://tanaschita.com/20221031-managing-cache-when-working-with-urlsession-in-ios/)), and Android's OkHttp honors the same headers ([OkHttp](https://square.github.io/okhttp/features/caching/)).
- **Image caches** set their own expiry. Kingfisher's disk cache defaults to 7 days, and expo-image has no TTL at all, so you rotate the `cacheKey` instead ([Kingfisher](https://github.com/onevcat/Kingfisher/discussions/2087); [Expo](https://docs.expo.dev/versions/latest/sdk/image/)).
- **Old app versions** stay installed for months, so persisted cache schemas need version busters ([TanStack persist](https://tanstack.com/query/v5/docs/framework/react/plugins/persistQueryClient)).
- **Realm's Atlas Device Sync** reached end of life on September 30, 2025 ([MongoDB](https://mongodb.com/community/forums/t/atlas-device-sync-end-of-life-and-deprecation/296687)).

**AI features.** Provider prompt caching is the largest and safest lever:

| Provider | Facts the reference must carry |
|---|---|
| Anthropic | Cache writes cost **1.25×** the base input price for a 5-minute TTL and **2×** for 1 hour; reads cost about **0.1×**. At most 4 cache breakpoints per request, each looking back at most 20 blocks. Timestamps or unsorted JSON in the prefix silently break the cache ([Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)). |
| OpenAI | Automatic for prompts of 1,024 tokens or more. `prompt_cache_key` and 24-hour retention are available. Writes cost 1.25× from GPT-5.6 onward ([OpenAI](https://developers.openai.com/api/docs/guides/prompt-caching)). |
| Gemini | A 90% implicit discount on cached tokens for 2.5 and later models ([Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview)). |

Semantic caching, which returns a stored answer for a *similar* prompt, is the risky layer. Redis LangCache defaults to a 0.85 similarity threshold ([Redis LangCache](https://redis.io/docs/latest/develop/ai/context-engine/langcache/concepts/)). Yet correct and incorrect hits have "highly overlapping similarity distributions" ([vCache](https://arxiv.org/html/2502.03771v5)), and attackers can craft prompts that collide with cached keys ([arXiv 2601.23088](https://arxiv.org/pdf/2601.23088)). GPTCache has stopped adding support for new models ([GPTCache](https://github.com/zilliztech/GPTCache)).

The reference should therefore rank LLM caches in this order:

1. Exact-match caching, which is safe.
2. Embedding caches keyed by model and model version.
3. Semantic caching, last, and only for public, non-personalized questions. It must be namespaced by tenant, model, prompt version and corpus version, with a strict threshold and a verifier, following Azure's caveat ([Azure Cache-Aside](https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside)).

**Adjacent layers.** These are short but matter for security:

- **GitHub Actions** caches default to 10 GB per repo, configurable up to 25 GB. Low-trust triggers now get read-only access to default-branch caches, a new `cache-mode` setting grants least privilege, and secrets must never sit in cached paths ([GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)).
- **Docker builds** speed up with BuildKit cache mounts and external cache backends ([Docker](https://docs.docker.com/build/cache/optimize/)).
- **Turborepo** "treats logs as artifacts", so secrets printed in logs end up in the cache ([Turborepo](https://turborepo.dev/docs/core-concepts/remote-caching)).
- **Nx** recommends read-only cache tokens everywhere except protected branches ([Nx](https://github.com/nrwl/nx/blob/master/astro-docs/src/content/docs/kb/cache-security.mdoc)).
- **Next.js** needs `.next/cache` persisted between CI builds ([Next.js](https://nextjs.org/docs/app/guides/ci-build-caching)).
- **DNS** TTLs must be lowered at least one full old-TTL period before a migration ([CanSpace](https://www.canspace.ca/clients/knowledgebase/101/TTL-and-when-to-lower-it-before-a-DNS-change.html)).
- **TLS 1.3 0-RTT** is safe only for idempotent requests, because early data can be replayed ([Cloudflare](https://blog.cloudflare.com/tls-1-3-overview-and-q-and-a/)).

## Correctness lives in write ordering, stampede control and leak tests

No single invalidation strategy is enough. Production systems layer several:

- a TTL as a backstop;
- delete-on-write for object caches;
- versioned or generational keys for bulk invalidation;
- tags or surrogate keys to fan out purges at the HTTP layer;
- invalidation driven by the database's change log wherever correctness matters.

Kleppmann argues that "dual writes" from application code race and drift. His fix is to write once to the database and derive caches from its change log ([Kleppmann](https://martin.kleppmann.com/2015/05/27/logs-for-data-infrastructure.html)). Facebook runs this in production: its mcsqueal daemon tails the MySQL commit log and broadcasts memcache deletes ([summary of NSDI 2013](https://hemantkgupta.medium.com/insights-from-paper-scaling-memcache-at-facebook-1386a5956859)). For smaller teams, the transactional outbox pattern with Debezium records the data change and the intent to invalidate in one atomic write ([Debezium](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)).

At the CDN, Fastly's recommended header for content invalidated by purges pairs a one-year `max-age` with `stale-while-revalidate=60` and `stale-if-error=31536000` ([Fastly on DEV](https://dev.to/fastly/is-purging-still-the-hardest-problem-in-computer-science-339i)). Fastly's purge-all can never be soft, so the workaround is to tag every object with one constant key and soft-purge that key ([Fastly soft purges](https://www.fastly.com/documentation/guides/full-site-delivery/purging/soft-purges/)).

The canonical consistency bug is the **stale set** ([Redisson](https://redisson.pro/glossary/cache-invalidation.html)):

1. A reader misses the cache and reads the old row from the database.
2. A writer commits a new value and deletes the cache key, which is still empty.
3. The reader's delayed `set` puts the stale value back, where it stays until the TTL expires.

Fixes run from weakest to strongest:

- **Delayed double delete** is a timing heuristic ([Alibaba Cloud](https://www.alibabacloud.com/blog/exploring-cache-data-consistency_600308)).
- **Leases**, in the Facebook style, cancel a filler's write token when a delete arrives in between ([summary](https://medium.com/@meenak1996/scaling-memcache-at-facebook-a-brief-summary-a6c0f2b725ce)). One secondary account credits leases with cutting Facebook's peak database queries from 17K/s to 1.3K/s, though this could not be checked against the paper itself ([Engineer's Codex](https://read.engineerscodex.com/p/how-facebook-scaled-memcached)).
- **Measurement** beats design alone. Meta raised the cache consistency of its TAO system from **six nines to ten nines**. Its Polaris checker found bugs hiding in error-handling code, including a cache fill that read the value and its version separately ([Meta Engineering](https://engineering.fb.com/2022/06/08/core-infra/cache-made-consistent/); [recreation](https://github.com/Mayank-Sharma-27/meta-cache-made-consistent)).

Read replicas widen the stale-set window to the full replication lag. The skill should ship three tools for this:

- a recipe that pins the writing user to the primary database for N seconds ([Codemia](https://codemia.io/archive/read-your-writes-consistency));
- Lua scripts for lease-based and version-conditional cache writes;
- a small Polaris-style sampler that checks the cache against the database.

TTLs come from how much staleness the business can tolerate, not from how often data changes. The AWS Builders' Library splits a soft TTL (refresh after this point) from a hard TTL (never serve after this point, except on error) ([AWS Builders' Library](https://aws.amazon.com/builders-library/caching-challenges-and-strategies/)). Caffeine pairs `refreshAfterWrite` with `expireAfterWrite` for the same effect ([Caffeine Refresh](https://github.com/ben-manes/caffeine/wiki/Refresh)). FusionCache adds "fail-safe" reuse of expired entries when the source fails ([FusionCache](https://github.com/ZiggyCreatures/FusionCache)). Jitter, such as a random 55–65 minutes for a nominal one-hour TTL, keeps many keys from expiring at once ([Redis blog](https://redis.io/blog/how-to-tame-the-thundering-herd-problem/)).

A stampede happens when many requests miss the same key at once and all recompute it. There are four families of defense, and the skill should default to the cheapest one that works:

1. **Coalesce misses** so only one request recomputes. Go's `singleflight` makes sure "only one execution is in-flight for a given key at a time" ([singleflight](https://pkg.go.dev/golang.org/x/sync/singleflight)).
2. **Refresh early.** XFetch recomputes a value when `now − δ·β·ln(rand) ≥ expiry` ([xfetch](https://docs.rs/xfetch/)).
3. **Serve stale content** while one request refreshes it.
4. **Route each key to one node**, as Discord did ([InfoQ](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/)).

Varnish's "hit-for-pass" mechanism shows why uncacheable responses must be marked explicitly. Without the marking, requests queue up behind a fetch whose result will never be cached ([Varnish](https://www.varnish.org/docs/users-guide/increasing-your-hitrate/)). The wider failure modes map to defenses like this; the big-key row is practitioner heuristic rather than sourced.

| Failure mode | Trigger | Defense the skill prescribes |
|---|---|---|
| Avalanche | Many keys share one expiry, or a cache node is lost | TTL jitter, soft TTL with `stale-while-revalidate`, staggered warm-up, concurrency limits on database access |
| Penetration | Requests for IDs that don't exist | A short-TTL negative cache stored as a sentinel value, a Bloom filter of valid IDs, input validation |
| Breakdown | One very hot key expires | Single-flight plus `stale-while-revalidate`, XFetch, scheduled refresh-ahead for the top N keys |
| Hot key | One key saturates a shard | In-process cache with a 1–5 s TTL, key splitting (`k#0..N`), read replicas, the CDN for public data |
| Big key | Values of several megabytes | Split into chunks, cache projections, compress, delete with `UNLINK` |
| Cold start | New key prefix after a deploy, a new region, a flush | Warm from a peer cache, pre-warm the top N keys, ramp traffic gradually, bump key prefixes instead of flushing |
| Cache down | The cache cluster is unreachable | Millisecond timeouts, a circuit breaker, fail open only into a coalesced and rate-limited database path, serve stale in-process data |
| Retry storm | Clients retry cache or database errors | Retry budgets, backoff with jitter, and errors handled as errors rather than as misses |

Most of these are capacity failures in disguise: the database is sized for the healthy hit rate, so the skill should require planning for a degraded one. The incidents point to four rules:

- **Fail open only into a guarded path.** Facebook's "gutter pool", about 1% of its memcached servers, absorbs a failed node's traffic instead of rehashing it onto healthy nodes ([paper notes](https://distributed-computing-musings.com/2022/03/paper-notes-scaling-memcache-at-facebook/)).
- **Never treat an error as a miss or an invalid value.** That was the lesson of Facebook's 2010 outage.
- **Know what `stale-if-error` covers.** It applies only to 500, 502, 503 and 504, not to 404 ([RFC 5861](https://httpwg.org/specs/rfc5861.html)).
- **Plan for the CDN itself failing.** A latent Fastly bug took about 85% of its network down in June 2021, with recovery taking up to 49 minutes ([Fastly](https://www.fastly.com/blog/summary-of-june-8-outage)).

Security deserves its own reference file and a hard gate in SKILL.md. The attack families are well documented:

- **Cache poisoning** works through inputs the cache ignores but the app uses, such as `X-Forwarded-Host` ([Kettle](https://portswigger.net/kb/papers/7q1e9u9a/web-cache-poisoning.pdf)). Variants include parameter cloaking and GET requests that carry a body ([Web Cache Entanglement](https://portswigger.net/research/web-cache-entanglement)).
- **Cache deception** exploits differences in how the cache and the framework split a URL. Rails treats `.` as a delimiter and Spring treats `;` as one, so a URL like `/MyAccount.css` can get a private page cached as if it were a stylesheet ([Gotta cache 'em all](https://portswigger.net/research/gotta-cache-em-all)).
- **Cache-poisoned denial of service (CPDoS)** gets error pages cached by sending oversized headers, meta characters or method overrides ([SecurityWeek](https://www.securityweek.com/researchers-warn-new-cache-poisoned-dos-attack-method)).
- **HTTP/1.1 desync attacks** can also poison caches ([PortSwigger](https://portswigger.net/research/http1-must-die)).
- **Newer 2026 research** covers cache keys that collide because components are joined without separators ([CyberSecurityNews](https://cybersecuritynews.com/web-cache-keys-poisoning/)), and "Web Cache Overflow", which pushes legitimate entries out of the cache ([arXiv 2608.04744](https://arxiv.org/pdf/2608.04744)).

Prevalence is real but not universal. 56 of the Tranco top 1,000 sites were vulnerable to poisoning ([CCS 2024](https://dl.acm.org/doi/pdf/10.1145/3658644.3690361)), and the largest study of cache deception found 1,188 vulnerable domains ([Golinelli thesis](https://iris.unitn.it/retrieve/321462a9-e212-4e50-9525-62409b6397c6/phd_unitn_golinelli_matteo.pdf)).

Framework CVEs share one root cause: a shared cache keys on the URL without distinguishing the different responses a framework can send for it.

| Framework | Cache-variant bug |
|---|---|
| Next.js | A missing `Vary` header let RSC payloads replace HTML (CVE-2025-49005), and the two were confused again in 2026 (CVE-2026-44576) ([GitLab advisories](https://advisories.gitlab.com/npm/next/CVE-2026-44576/)) |
| React Router | An error response triggered by a request header could be cached (CVE-2025-43864) ([Vercel changelog](https://vercel.com/changelog/protection-against-react-router-and-remix-vulnerabilities-cve-2025-43864)) |
| Nuxt | The `_payload.json` data file could be cached and served to visitors in place of the page (CVE-2025-27415) ([GitLab](https://advisories.gitlab.com/npm/nuxt/CVE-2025-27415/)) |

Advisories often say apps hosted on Vercel were unaffected, because Vercel's edge already builds the cache key correctly. Moving an app off Vercel reopens these holes.

Infrastructure and multi-tenancy add their own risks:

- **Exposed Redis.** Research into the RediShell remote-code-execution bug found about 60,000 internet-exposed Redis instances with no authentication ([Wiz](https://www.wiz.io/vulnerability-database/cve/cve-2025-49844)).
- **Tenant leaks** usually come from a code path that forgets the tenant prefix, not from key collisions ([Redis blog](https://redis.io/blog/data-isolation-multi-tenant-saas/)).
- **Cloudflare's Cache Deception Armor** can be overridden by TTL rules, so correct origin headers remain the primary control ([Cloudflare](https://developers.cloudflare.com/cache/about/cache-deception-armor)).

The whole security file reduces to one invariant that can be checked: **the cache key must fully and precisely determine the response.**

Observability starts with one vocabulary. The skill should map the vendor status headers into hit, miss, stale and bypass: `cf-cache-status`, `x-vercel-cache`, Fastly's and CloudFront's `X-Cache`, and Akamai's debug output. Where a response carries the standard `Cache-Status` header from RFC 9211, the skill should prefer it, because it reports TTL, cache key and request collapsing for each hop ([RFC 9211](https://www.rfc-editor.org/rfc/rfc9211); [Cloudflare statuses](https://developers.cloudflare.com/cache/concepts/cache-responses/); [Vercel statuses](https://vercel.com/docs/caching/cache-status)).

Per-layer metrics need care:

- **Redis hit ratio** should come from deltas of the `INFO` counters, not their cumulative totals ([OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-cache-hit-ratio-optimize/markdown)). A rising `evicted_keys` means the cache is too small, unlike `expired_keys` ([Netdata](https://www.netdata.cloud/guides/redis/redis-low-keyspace-hit-rate/)).
- **OpenTelemetry** has no standard attribute for cache hits, so the plan should fix a custom one such as `cache.hit` ([OTel](https://opentelemetry.io/docs/specs/semconv/database/redis)).
- **Browser real-user monitoring** can count a local cache hit when `transferSize === 0` and `decodedBodySize > 0` ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/transferSize)).

Testing should combine these methods:

- unit tests with a fake clock for TTL logic;
- header snapshot tests per route class, which would have caught the missing-`Vary` CVE;
- a leak test with two users, run through the real CDN;
- deception probes such as `/account;.css`;
- the Web Cache Vulnerability Scanner (WCVS) in CI, which covers 9 poisoning and 3 deception techniques and outputs JSON ([WCVS](https://github.com/Hackmanit/Web-Cache-Vulnerability-Scanner));
- a self-hosted REDbot for header linting, since the public site forbids scripted use ([PyPI redbot](https://pypi.org/project/redbot/));
- load tests starting from a cold cache;
- chaos tests that kill Redis;
- a synthetic freshness probe that measures the time from purge to visible content.

## Package it as a lean router with offline scripts and fixture evals

### Six portable frontmatter fields carry a 945-character description

Portability dictates the frontmatter. The open Agent Skills standard defines six fields: `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools` ([spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)). Claude Code accepts more, but "outside Claude Code (claude.ai uploads, the Skills API, `package_skill.py`), any other field … causes a hard error" ([Claude Code skills](https://code.claude.com/docs/en/skills)). The skill-creator validator hard-codes those six fields ([quick_validate.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py)).

Two fields carry extra rules:

- **`name`** must be lowercase with hyphens, at most 64 characters, the same as the folder name, and must not contain "claude" or "anthropic" ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)).
- **`description`** is capped at 1,024 characters by the spec and the API, even though Claude Code truncates its own listing only at 1,536 ([Claude Code skills](https://code.claude.com/docs/en/skills)).

The two guides disagree on voice. The platform guide wants third person, while the agentskills guide prefers imperative phrasing and urges authors to be "pushy". Both put *what* before *when* ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); [optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx)).

The proposed description in the skeleton below is 945 characters. It lists layers and vendors as trigger vocabulary. It adds symptoms users report without saying "cache", such as slow pages and hosting costs. It also excludes near misses. `compatibility` records that live probes need network access, and `metadata` holds `version` and `last-reviewed`. The name `caching-strategy` is a noun phrase, which the guidance accepts; `optimizing-app-caching` fits its preferred gerund form.

### Safety rules sit at the top because only the first 5,000 tokens survive compaction

Progressive disclosure, where Claude loads skill content in stages, dictates the shape ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)):

- **Metadata** costs about 100 tokens and is always loaded.
- **The SKILL.md body** should stay under 500 lines and about 5,000 tokens.
- **Bundled files** cost nothing until read.

References should sit one link away from SKILL.md, because Claude may only preview nested files. Any reference longer than 100 lines needs a table of contents ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).

Two Claude Code behaviors make ordering critical ([Claude Code skills](https://code.claude.com/docs/en/skills)):

- The skill file is not re-read on later turns, so its guidance must be written as standing rules.
- After the conversation is compacted, only the first 5,000 tokens of each invoked skill survive, within a 25,000-token total.

The safety rules therefore go at the very top. The agentskills guide warns that "overly comprehensive skills can hurt more than they help" ([agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)). That argues for a router that loads only the six to ten files a given stack needs, as Cloudflare's 151-line umbrella skill does across its 139 files.

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

SKILL.md itself should hold six blocks, in this order:

1. Non-negotiable rules.
2. A workflow checklist that Claude copies into its reply and ticks off.
3. The routing table.
4. Gotchas that span layers.
5. A short glossary ("shared cache", "private cache", "staleness budget", "soft purge"), since the guide asks for consistent terminology.
6. The output contract.

The guide also recommends matching how much freedom Claude gets to how risky each task is ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)):

- **Analysis and trade-offs** get high freedom.
- **Safety rules, purges and CDN rule changes** get low freedom, plus a plan-validate-execute loop, because they are destructive.
- **Version-sensitive guidance** follows the guide's convention of a "current method" section with a collapsed "old patterns" block.

The skill should tell Claude to prefer documentation bundled in the project when it exists. Next.js 16.3+ ships its docs in `next/dist/docs` and generates an AGENTS.md file ([vercel-labs/next-skills](https://github.com/vercel-labs/next-skills)). When `next-cache-components-*`, `cloudflare`, `redis-development` or `vercel-optimize` is installed, the skill should hand implementation detail to that skill.

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

Scripts carry the deterministic work, because their code never enters the context window; only their output does. The API sandbox has "no network access" and "no runtime package installation" ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)), so everything except live probing must use only the Python standard library. The agentskills script guide adds hard requirements: no interactive prompts, a documented `--help`, structured JSON on stdout and diagnostics on stderr ([using scripts](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/using-scripts.mdx)).

| Script | Role |
|---|---|
| `detect_stack.py` | Reports framework versions, hosting, CDN, data stores and replica counts, plus the exact reference files to read. This makes routing deterministic and shrinks what SKILL.md must explain. |
| `find_cache_primitives.py` | Lists existing caches with file and line. |
| `probe_headers.py` | The only networked script. It is opt-in, read-only, limited to URLs the user supplies, and never forwards credentials. It runs the request matrix, the HIT/Age check, the 304 check, leak probes with and without cookies, and deception probes. |
| `validate_plan.py` | Validates `plan.json` against `plan.schema.json` and lints it for safety (rules below). |
| `size_cache.py` | Does the working-set and hit-ratio arithmetic. |

`validate_plan.py` fails the plan if any of the following hold:

- a row puts `public`, `s-maxage` or a CDN TTL on an authenticated data class;
- a cacheable row has no invalidation mechanism, owner or verification command;
- a TTL is longer than the stated staleness budget;
- a response carries more than 50 tags, or any uppercase tag.

Anthropic's advice to treat skills like installed software also applies ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). The portable version should omit `allowed-tools`, because Claude Code applies that field even in folders the user has never trusted ([Claude Code skills](https://code.claude.com/docs/en/skills)).

### Evals come first and run against one fixture repo per archetype

Evaluation should come first and drive what goes into the content. Anthropic's guidance has four steps ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)):

1. Run Claude on representative tasks without the skill.
2. Build at least three scenarios.
3. Write only the instructions that close the gaps you observed.
4. Test on Haiku, Sonnet and Opus.

Haiku matters most for a router, because it shows whether "read only the matching files" is actually followed.

There are two eval harnesses, and their formats "aren't interchangeable" ([Claude Code skills](https://code.claude.com/docs/en/skills)):

- **The skill-creator workflow** (`evals/evals.json`) compares runs with and without the skill, and grading requires concrete evidence ([evaluating skills](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/evaluating-skills.mdx)).
- **`claude plugin eval`** runs each case three times against a baseline without the plugin. It offers regex, tool-use, tool-order, file-existence, LLM and baseline graders, but "no custom-code graders". Its most common first finding is a score gap near zero because the skill never triggered ([plugin evals](https://code.claude.com/docs/en/plugin-evals)).

To tune triggering, use about 20 queries, roughly half that should trigger the skill and half near misses that should not. Run each three times with a fixed 60/40 train/validation split. Do not add specific keywords from failed queries, because that overfits ([optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx)). Output evals then use one fixture repo per archetype and stack:

| Fixture | Prompt | Assertions to grade |
|---|---|---|
| Next.js 16 store on Vercel with `cacheComponents: true` | "Product pages feel slow and our Vercel bill jumped" | `detect_stack` ran; uses `'use cache'` with `cacheLife` and `cacheTag`; no single-argument `revalidateTag`; cart is `private, no-cache`; checkout is `no-store` |
| Next.js 15 self-hosted on Kubernetes behind CloudFront | "revalidateTag works locally but not in production" | Names the CDN TTL as the cause; shared `cacheHandler`; CloudFront invalidation; `_rsc` in the cache key; no `'use cache'` |
| Django 6 multi-tenant SaaS with Redis | "Dashboards are slow" | No `cache_page` on authenticated views; `t:{tenant}:` key prefix; Django patch pinned; `private` plus ETag |
| Rails 8 news site on Fastly | "Breaking news takes minutes to show up" | Surrogate keys with soft purge; `stale-while-revalidate` and `stale-if-error`; purge-to-visible probe; `touch: true` |
| WordPress behind Cloudflare APO | "cf-cache-status is always BYPASS" | Traces the cause to plugins setting `Set-Cookie`; object-cache drop-in; a single page-cache layer |
| Express API with Apollo Server | "Cut database load from our GraphQL API" | Persisted queries over GET; `sessionId` set; a DataLoader per request; Apollo Server 5 |
| Expo app with a REST backend | "Users see old avatars after changing them" | Versioned `cacheKey`; ETags on the API; no long TTL hard-coded in the client |
| RAG support bot | "Our LLM bill is too high" | Stable prompt prefix first; cached-token KPI; exact-match cache before semantic cache; namespace includes tenant, model and prompt version |
| Near-miss negatives | "Implement an LRU cache for an interview", "clear my pip cache", "explain CPU L1 cache" | Skill not invoked (a `tool_used: Skill` grader with `arm: both`) |

### One repository feeds every distribution channel

Distribution must account for separate surfaces, because "Custom Skills do not sync across surfaces" ([platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)). One public repo should hold the canonical, spec-compliant folder and feed each channel.

| Surface | How to ship | Constraint |
|---|---|---|
| Other agents (Cursor, Codex, Copilot, Gemini CLI and about 40 more) | `npx skills add <org>/<repo>` ([agentskills clients](https://github.com/agentskills/agentskills/blob/HEAD/docs/snippets/clients.jsx); [next-skills](https://github.com/vercel-labs/next-skills)) | Spec fields only |
| Claude Code | `.claude-plugin/marketplace.json` in the same repo, with a `strict: false` entry that lists the skill folders. This is Anthropic's own pattern, and it avoids keeping a duplicate copy as Redis does ([anthropics/skills marketplace](https://github.com/anthropics/skills/blob/main/.claude-plugin/marketplace.json); [redis/agent-skills](https://github.com/redis/agent-skills); [plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)) | A plugin variant may add Claude Code-only fields and plugin evals |
| claude.ai | A zip built by `package_skill.py`, which leaves out a top-level `evals/` folder ([package_skill.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/package_skill.py)) | Uploaded per user, not managed by the organization |
| Claude API | `POST /v1/skills` ([Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)) | Under 30 MB uncompressed; each version is a full snapshot shared across the workspace; no network at runtime |

Versioning should combine `metadata.version`, the plugin `version` and a changelog, with a quarterly content review.

### Five open questions should be settled by evals, not assumptions

Several things remain uncertain:

- **Routing-table size.** No source says how many rows Claude navigates well before it over-reads or under-reads, so the 48-row table needs testing on Haiku.
- **Mixed-stack monorepos.** There is no official guidance for one skill handling a repo that mixes, say, Next.js and Django.
- **The open spec** was read from its GitHub source dated August 2026, not from the live agentskills.io site.
- **Vendor details.** Netlify specifics were available only from an agent context with no public URL and are omitted here. Fastly's default TTL and Akamai's current tag header remain unverified.
- **Next.js CVE ranges.** Several 2026 version ranges conflict across aggregators and must be confirmed against GitHub's security advisories before the security file quotes them.

## Conclusion

The research moves the skill's value away from facts about any single layer. Vendors increasingly ship those facts themselves, and the facts change monthly. What nobody ships is the coordination between layers:

- **A TTL ladder** that is shortest in the browser, which cannot be purged, and longest at the edge, which can.
- **A purge order** that runs from the database to the inner caches to the outer caches.
- **Tag schemes** that fit the most constrained CDN.
- **In-process TTLs** kept below shared-cache TTLs.
- **One cache-key rule** that covers poisoning, deception and tenant leaks at once.

A master skill wins by owning classification, cross-layer consistency, safety gates and verification, and by leaving syntax to version-matched vendor skills and bundled docs. That makes it smaller and longer-lived than an encyclopedia.

The skill should also be maintained the way its own advice says to run a cache. Its references are cached knowledge with a staleness budget, enforced by a `last-reviewed` date and a quarterly refresh. Its detection script acts as the version key, and its eval suite acts as the Polaris-style checker that catches silent drift.

The most durable recommendation is also the cheapest. Railway's 2026 incident repeated Steam's from 2015 because platform defaults changed underneath the apps. Ahead of any clever cache, the skill should make sure every response carries an explicit `Cache-Control` header, protected by header snapshot tests in CI.
