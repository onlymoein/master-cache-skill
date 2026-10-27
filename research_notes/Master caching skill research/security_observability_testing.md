# Caching Security, Observability, Debugging & Testing (state as of October 2026)

Scope: attack patterns + mitigations, metrics, debug commands/headers, and test approaches for web/app caching across browser, CDN, and app-cache (Redis/Memcached) layers. Intended as the "security, observability & verification" reference file for a caching-design Agent Skill.

Note on sourcing: external `WebFetch` was blocked in this environment, so all findings come from `WebSearch` result summaries. Where a result flagged a source as secondary/AI-generated or where sources conflicted, that is noted inline. Primary specs (RFC 9111, RFC 9211) and vendor/CVE details should be spot-verified against the linked originals before shipping exact version numbers.

## Security: attack patterns and mitigations

### Takeaway
The dominant 2024-2026 caching threats are web cache **poisoning** (unkeyed inputs + key-normalization/parse discrepancies), web cache **deception** (path/delimiter confusion that caches private pages under static-looking URLs), **CPDoS** (caching origin error pages), framework-specific cache CVEs (a steady stream in Next.js through 2026, plus React Router/Nuxt), and infra exposure (publicly reachable Redis). The cross-cutting fix is precise cache keys + never caching authenticated/dynamic responses; the cross-cutting observation is that discrepancy attacks live in the gap between how two HTTP engines interpret the same request.

### Cited Findings

**Web cache poisoning (unkeyed inputs, fat GET, parameter cloaking, key normalization)**
- Poisoning works by getting a harmful response stored under a key that legitimate users will hit; it exploits "unkeyed" inputs (headers/params the cache ignores but the app reflects), e.g. `X-Forwarded-Host`, `X-Host`, `X-Forwarded-Scheme` — foundational technique set from James Kettle, "Practical Web Cache Poisoning" — [PortSwigger whitepaper PDF](https://portswigger.net/kb/papers/7q1e9u9a/web-cache-poisoning.pdf)
- **Parameter cloaking**: attack depends on a mismatch between how the cache and origin parse query strings; a cache oracle that reflects the full URL plus at least one query param helps find these discrepancies — [Web Cache Entanglement, PortSwigger](https://portswigger.net/research/web-cache-entanglement)
- Semicolon variant of parameter cloaking: a proxy that does not treat `;` as a separator leaves `utm_*` params (usually unkeyed) in the request so a malicious value gets cached as if safe — [Snyk: cache poisoning in open source packages](https://snyk.io/blog/cache-poisoning-in-popular-open-source-packages/)
- **Fat GET**: a GET request carrying a form body; "On every cacheable page, I could use a fat GET to poison the cache and change any parameter to a value of my choice." Root cause in Rails is that body and query params are merged, body taking priority — [Web Cache Entanglement](https://portswigger.net/research/web-cache-entanglement); [Rails discussion](https://discuss.rubyonrails.org/t/feature-request-configuration-for-separating-get-and-post-parameters/76116)
- **Akamai cache-key quirks**: debug headers can reveal three conflicting cache keys for one request (a transformed key, an extended internal key, and a "true" key); the gap between them is the attack surface — [Web Cache Entanglement](https://portswigger.net/research/web-cache-entanglement)
- Kettle's attacks "rely on misguided transformations, naive normalization, and optimistic assumptions"; key normalization is a named category — [Web Cache Entanglement](https://portswigger.net/research/web-cache-entanglement)

**Cache key injection / imprecise keys (2026 research)**
- Alex Brumen (Sept 2026) shifts focus off unkeyed inputs: attacker abuses values already in the cache key when a server joins them **without clear separators**. Nginx can build keys from scheme/host/URI/query/cookies/headers; a legit request for `/home` with `Accept: */*` can collide with an attacker request for `/h` with `Accept: ome*/*` because concatenation yields the same string. PoC bypassed an access-controlled `/admin` restricted to localhost because the key used only URI+Accept — [CyberSecurityNews coverage](https://cybersecuritynews.com/web-cache-keys-poisoning/) (secondary; primary writeup not located)
- **Web Cache Overflow (WCO)** — Matteo Golinelli et al., arXiv 2026: a cache-pollution/DoS primitive that exploits imprecise cache keys to keep redundant entries alive, raising eviction pressure on legitimate objects; can also assist poisoning. Authors conclude precise cache keys beat workarounds; tooling + PoC at github.com/Golim/web-cache-overflow — [arXiv 2608.04744](https://arxiv.org/pdf/2608.04744); [Golinelli PhD thesis, UniTN](https://iris.unitn.it/retrieve/321462a9-e212-4e50-9525-62409b6397c6/phd_unitn_golinelli_matteo.pdf)
- Academic measurement (HCache/HCache-style, CCS 2024, Liang et al.): large-scale scan of Tranco Top 1,000 found 56 websites vulnerable to cache poisoning — [ACM CCS 2024 PDF](https://dl.acm.org/doi/pdf/10.1145/3658644.3690361)

**Web cache deception (path confusion, delimiter discrepancies) — "Gotta cache 'em all" (Martin Doyhenard, PortSwigger; research page updated Jan 2026)**
- Core problem: cache and origin disagree on how a URL maps to a resource, letting an attacker get a dynamic/private response cached under a static-looking extension — [Gotta cache 'em all](https://portswigger.net/research/gotta-cache-em-all); [PortSwigger WSA: web cache deception](https://portswigger.net/web-security/web-cache-deception)
- **Spring / Java matrix variables**: `;` is a delimiter for matrix variables not treated as part of the path, so a request ending `.css` can be cached while the origin serves dynamic content — [Gotta cache 'em all PDF](https://portswigger.net/kb/papers/kapvrid/gotta-cache-em-all.pdf)
- **Ruby on Rails dot delimiter**: `.` is the format specifier; `/MyAccount.css` maps to the `/MyAccount` handler returning default HTML — [Gotta cache 'em all PDF](https://portswigger.net/kb/papers/kapvrid/gotta-cache-em-all.pdf); [HackTricks: cache poisoning via URL discrepancies](https://book.hacktricks.wiki/en/pentesting-web/cache-deception/cache-poisoning-via-url-discrepancies.html)
- **OpenLiteSpeed null-byte**: uses encoded null as a classic delimiter to truncate the path; `/MyAccount%00aaa` truncates to `/MyAccount` — [HackTricks](https://book.hacktricks.wiki/en/pentesting-web/cache-deception/cache-poisoning-via-url-discrepancies.html)
- The delimiter/path-traversal technique can hide a traversal after a delimiter that only the backend resolves — [HackTricks](https://book.hacktricks.wiki/en/pentesting-web/cache-deception/cache-poisoning-via-url-discrepancies.html)
- Largest WCD study to date (Golinelli thesis) identified **1,188 vulnerable domains**; earlier foundational work: Omer Gil introduced WCD at Black Hat 2017; Mirheidari et al. "Cached and Confused" (USENIX Security 2020) and "Web Cache Deception Escalates!" (USENIX Security 2022) — [Golinelli PhD thesis](https://iris.unitn.it/retrieve/321462a9-e212-4e50-9525-62409b6397c6/phd_unitn_golinelli_matteo.pdf)

**CPDoS (Cache-Poisoned Denial of Service) — Nguyen, Lo Iacono (Cologne), Federrath (Hamburg), 2019**
- Mechanism: a crafted request carries fields the cache ignores but the origin rejects; the cache stores the origin's error page and serves it to later visitors ("semantic gap" between two HTTP engines) — [SecurityWeek](https://www.securityweek.com/researchers-warn-new-cache-poisoned-dos-attack-method); [Gigazine](https://gigazine.net/gsc_news/en/20191024-cache-poisoned-denial-service-cpdos)
- Three variants: **HHO** (HTTP Header Oversize), **HMC** (HTTP Meta Character), **HMO** (HTTP Method Override) — [SecurityAffairs](https://securityaffairs.co/wordpress/92859/hacking/cpdos-attack-cdns.html)
- HHO relies on the cache accepting larger headers than the origin: e.g. Amazon CloudFront limit cited at 20480 bytes while most web servers cap at 8192 bytes — [SecurityWeek](https://www.securityweek.com/researchers-warn-new-cache-poisoned-dos-attack-method)
- Discovery started with CloudFront caching `400 Bad Request` by default; researchers also notified Akamai, CDN77, Fastly, Cloudflare, Varnish as affected — [SecurityWeek](https://www.securityweek.com/researchers-warn-new-cache-poisoned-dos-attack-method); [SecurityAffairs](https://securityaffairs.co/wordpress/92859/hacking/cpdos-attack-cdns.html)

**HTTP desync / parser discrepancy (2025) — James Kettle, "HTTP/1.1 Must Die: The Desync Endgame" (Black Hat USA + DEF CON 33, Aug 2025)**
- Argues upstream HTTP/1.1 is inherently insecure; research exposed tens of millions of sites via infra at Akamai, Cloudflare, Netlify. Downgrading HTTP/2→HTTP/1.1 at a CDN/proxy adds a 4th way to specify message length, more dangerous than end-to-end H1 — [PortSwigger research](https://portswigger.net/research/http1-must-die)
- New vectors can enable site takeover, credential hijacking, and **cache poisoning**; Fastly published a resilience statement — [Fastly blog](https://quic.fastly.com/blog/fastlys-resilience-to-http-1-1-desynchronization-attacks)
- Open-source toolkit released for systematic parser-discrepancy detection; >$200k bounties in two weeks cited by the paper (other coverage cites higher totals — treat exact figure as unconfirmed) — [PortSwigger research](https://portswigger.net/research/http1-must-die)

**Framework caching CVEs (Next.js, React Router, Nuxt) — 2024-2026**
- **CVE-2024-46982** (Next.js Pages Router): crafted request poisons cache of a non-dynamic SSR Pages Router route; does not affect App Router. Affected 13.5.1–14.2.9; fixed in 13.5.7 / 14.2.10. CVSS 7.5. Vector involves the `x-now-route-matches` header. Advisory GHSA-gp8f-8m3g-qvj9 — [NVD](https://nvd.nist.gov/vuln/detail/cve-2024-46982); [Tenable](https://tenable.com/cve/CVE-2024-46982)
- **CVE-2025-32421** (Next.js): bypass of CVE-2024-46982 via race between a `__nextDataRequest` query param request and an `x-now-route-matches` header request; affects >14.2.24 through <15.1.6; patched in 15.1.6 / 14.2.24 by stripping `x-now-route-matches` from incoming requests; low severity; Vercel platform unaffected — [Vercel changelog](https://vercel.com/changelog/cve-2025-32421)
- **CVE-2025-49826** (Next.js): under certain conditions a cached HTTP 204 is served to all users of a static page → DoS. CVSS 7.5. Ranges conflict across sources (NVD-based: 15.0.4-canary.51 to <15.1.8); fixed in 15.1.8 (one source says 15.2.0 with backport to 15.0.4). Triggers: ISR in `next start`/standalone, or SSR routes + a CDN configured to cache 204s. Vercel-hosted unaffected — [ZeroPath](https://zeropath.com/blog/nextjs-cache-poisoning-cve-2025-49826); [GitLab advisory](https://advisories.gitlab.com/npm/next/CVE-2025-49826/)
- **CVE-2025-49005** (Next.js App Router): missing `Vary` header → RSC payloads cached and served in place of HTML under specific middleware/redirect conditions. Affected 15.3.0–<15.3.3; fixed 15.3.3; CVSS ~3.7. On Vercel only browser cache affected; self-hosted can poison CDN if it doesn't distinguish RSC vs HTML in cache keys — [GitLab advisory](https://advisories.gitlab.com/npm/next/CVE-2025-49005/); [OSV](https://osv.dev/vulnerability/CVE-2025-49005)
- **CVE-2025-57752** (Next.js Image Optimization): cache key confusion on Image Optimization API routes → header-dependent responses cached and shown to wrong users. Affected <14.2.31 and 15.0.0–<15.4.5; fixed 14.2.31 / 15.4.5; Medium (~6.2) — [NVD](https://nvd.nist.gov/vuln/detail/CVE-2025-57752); [GitLab](https://advisories.gitlab.com/pkg/npm/next/CVE-2025-57752/)
- **CVE-2025-43864 / -43865** (React Router / Remix v7): sending `X-React-Router-SPA-Mode` to a route using a loader throws, and a cache in front can store+serve the broken response (DoS). Affected 7.2.0–<7.5.2; fixed 7.5.2. Severity disputed: Red Hat Moderate 5.3 vs Wiz 7.5 High. Related `X-React-Router-Prerender-Data` (-43865) allows content spoofing / stored XSS. Vercel stripped both headers at its firewall and purged CDN caches — [Corgea](https://corgea.com/advisories/vulnerabilities/CVE-2025-43864); [Vercel changelog](https://vercel.com/changelog/protection-against-react-router-and-remix-vulnerabilities-cve-2025-43864)
- **CVE-2025-27415** (Nuxt): `/?/_payload.json` renders as JSON; a CDN that ignores query string when deciding what to cache can serve that JSON to future visitors (availability impact only; C/I unaffected). Affected 3.0.0–<3.16.0; fixed 3.16.0. Explicitly noted as similar to Next.js CVE-2024-46982 — [GitLab advisory](https://advisories.gitlab.com/npm/nuxt/CVE-2025-27415/)
- **Next.js September 2026 Security Release** (fixes 1 High, 5 Medium, 1 Low): upgrade to **16.3.8 (Active LTS)** or **15.5.27 (Maintenance LTS)** — [nextjs.org/blog/september-2026-security-release](https://nextjs.org/blog/september-2026-security-release)
  - **CVE-2026-94543** (Pages Router, self-hosted): a cached page can be overwritten with another route's content; Vercel-hosted unaffected; fixed 16.3.8 / 15.5.27 — [DailyCVE](https://dailycve.com/nextjs-pages-router-cache-poisoning-cve-2026-94543-moderate-dc-oct2026-2837/)
  - **CVE-2026-94484** (root-level catch-all + SSG/ISR): single unauthenticated request poisons the shared response cache via too-broad cache key; CVSS 4.8 Medium; fixed 15.5.27 / 16.3.8 — [GitLab advisory](https://advisories.gitlab.com/npm/next/CVE-2026-94484/)
  - **CVE-2026-94544** (Draft Mode leak): pending `use cache` fills shared across requests for same key without distinguishing Draft Mode; limited to Cache Components / `experimental.useCache` + Draft Mode previews — [Netlify changelog](https://www.netlify.com/changelog/2026-09-30-nextjs-react-security-vulnerabilities/); [johal.in writeup](https://johal.in/next-use-cache-draft-mode-leak-shared-cache-key)
  - **CVE-2026-44576** (May 2026, CWE-436): shared caches mishandle HTML vs RSC for same URL; later visitors may get component payloads instead of HTML. Affected 14.2.0–<15.5.16 and 16.0.0–<16.2.5; fixed 15.5.16 / 16.2.5 — [GitLab advisory](https://advisories.gitlab.com/npm/next/CVE-2026-44576/)
  - **CVE-2026-44582** (cache-busting collisions in RSC): fixed 15.5.16 / 16.2.5 — [Hacktron changelog](https://www.hacktron.ai/security-changelog/nextjs)
  - (Note: some 2026 CVE IDs/dates vary across aggregators; confirm against vercel/next.js GitHub Security Advisories before quoting ranges.)

**Caching authenticated/personalized responses by mistake (RFC 9111)**
- RFC 9111 §3.5: a shared cache MUST NOT reuse a stored response to a request carrying `Authorization` **unless** the response has `must-revalidate`, `public`, or `s-maxage` — [RFC 9111](https://rfc-editor.org/rfc/rfc9111)
- Storage rule (§3): a shared cache may store only if request has no `Authorization` OR the response has a directive explicitly allowing shared caching; `private` must be absent (or allow a modified shared response) — [RFC 9111](https://rfc-editor.org/rfc/rfc9111)
- Open erratum eid9004 proposes clarifying `proxy-revalidate` is NOT in the list that authorizes storing authenticated responses (it governs revalidation after staleness, not storage) — status unconfirmed — [IETF HTTP WG list](https://lists.w3.org/Archives/Public/ietf-http-wg/2026AprJun/0077.html)
- Cloudflare: with origin cache-control ON, a `Set-Cookie` response is NOT cached, the header is kept, status = `BYPASS`; with it OFF, Cloudflare strips `Set-Cookie` and caches. If Cache Everything + explicit Edge TTL is forced, Cloudflare removes `Set-Cookie` and caches anyway → cookies can leak across users — [Cloudflare cache behavior docs](https://developers.cloudflare.com/cache/best-practices/cache-behavior/)
- Origin `Cache-Control` of `no-cache`, `max-age=0`, `private`, or `no-store` disqualifies caching under Cloudflare standard settings — [Cloudflare cache behavior](https://developers.cloudflare.com/cache/best-practices/cache-behavior/)

**Browser cache side channels / XS-Leaks → cache partitioning**
- Chrome 86 began keying cached resources by a **Network Isolation Key** (top-level site + current-frame site + resource URL); same resource from a different top-level site misses the cache. Defends against cache-based history sniffing, cross-site search, cookie-like tracking. ~4% network-usage increase measured — [Chrome developer blog: HTTP cache partitioning](https://developer.chrome.com/blog/http-cache-partitioning/); [explainer repo](https://github.com/shivanigithub/http-cache-partitioning)
- Storage partitioning enabled for all users on Chrome 115+; mitigates Timing Attacks, XS-Leaks, COSI — [Privacy Sandbox: Storage Partitioning](https://privacysandbox.google.com/cookies/storage-partitioning)

**Sensitive data on disk / logout clearing**
- OWASP WSTG-ATHN-06 (Testing for Browser Cache Weaknesses): pages with sensitive content (addresses, card details, usernames) can be recovered from cache/history incl. Back button. Expected directives: `Cache-Control: no-cache, no-store`, `Expires: 0`, `Pragma: no-cache`; v4.1 adds `Cache-Control: must-revalidate, max-age=0` to stop files persisting on disk; serve over HTTPS + `must-revalidate` for the Back button — [OWASP WSTG](https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/04-Authentication_Testing/06-Testing_for_Browser_Cache_Weaknesses)
- `Clear-Site-Data` `cache` directive tells the client to remove locally cached data for the response URL's origin; depending on browser may also clear prerendered pages, bfcache, script caches — [MDN Clear-Site-Data](https://developer.mozilla.org/docs/Web/HTTP/Headers/Clear-Site-Data)
- Chrome 138 extends `Clear-Site-Data` with `prefetchCache` and `prerenderCache` directives (via W3C TAG review). HTTPS-only; Safari does not support `Clear-Site-Data`. A ForgeRock thread reports sending the full directive set on logout caused unexpected cookie loss in Chrome 118 — test first — [MDN](https://developer.mozilla.org/docs/Web/HTTP/Headers/Clear-Site-Data); [ForgeRock community](https://community.forgerock.com/t/clear-site-data-header-on-logout-anomaly-with-the-browser-google-chrome/4498)
- Logout pattern (community guidance): send `Clear-Site-Data: "cache", "cookies", "storage", "executionContexts"` on the logout-confirmation response — [Requestly](https://requestly.com/use-case/header/clear-site-data/)

**Multi-tenant app-cache isolation**
- Put tenant ID in every key as a first-class prefix (`tenant:{id}:{key}`); partition eviction/quotas per tenant where supported; add tenant context at every layer incl. HTTP/CDN caches — [Gravitee](https://gravitee.io/corpus/gen-1205/data-storage/multi-tenant-data-isolation-patterns.html); [Sourcery](https://sourcery.ai/security/categories/tenant_aware_caching_bugs)
- Most leaks come from a read/write path missing tenant context (wrong/absent prefix), not key collisions; bug is intermittent, surfacing only when another tenant warmed the cache — [Redis blog](https://redis.io/blog/data-isolation-multi-tenant-saas/); [Sourcery](https://sourcery.ai/security/categories/tenant_aware_caching_bugs)
- Redis ACLs can restrict a user to key patterns like `tenant1:*`, but tenants still share memory/IO on one instance (not full isolation) — [Redis blog](https://redis.io/blog/data-isolation-multi-tenant-saas/)
- Centralize prefixing in the cache wrapper (e.g. Django tenant-cache patch auto-prefixes every get/set/delete) so it can't be forgotten — [django-omnitenant](https://django-omnitenant.readthedocs.io/en/latest/api/patches/cache/)
- Semantic/embedding caches must be partitioned per tenant or one tenant gets answers built from another's data — [RedFox Security](https://www.redfoxsec.com/blog/testing-multi-tenant-ai-applications-for-data-leakage)

**Redis security**
- **CVE-2025-49844 "RediShell"** (patched Oct 3, 2025): ~13-year-old use-after-free in Lua scripting (every version with Lua); authenticated user sends crafted Lua to trigger memory corruption → RCE. Affects Redis ≤8.2.1 (fixed 8.2.2). Wiz found ~330,000 internet-exposed Redis, ~60,000 with no auth; official Redis container images have auth disabled by default — anyone reaching an unauth instance can send Lua — [Wiz](https://www.wiz.io/vulnerability-database/cve/cve-2025-49844); [Help Net Security](https://www.helpnetsecurity.com/2025/10/07/redis-patches-critical-redishell-rce-vulnerability-update-asap-cve-2025-49844/)
- 2026 follow-ons (authenticated): **CVE-2026-23631** (Lua UAF on replicas with `replica-read-only` disabled, fixed 8.6.3); **CVE-2026-25243** (RESTORE command bug, needs RESTORE perm, fixed 8.6.3) — [AWS ALAS2023-2026-1748](https://alas.aws.amazon.com/AL2023/ALAS2023-2026-1748.html); [OSV AZL-86084](https://osv.dev/vulnerability/AZL-86084). Older unauth: **CVE-2025-21605** (output-buffer growth → memory exhaustion, fixed 7.4.3) — [GCVE](https://cpe.gcve.eu/cpes/1971756)
- Hardening consensus (third-party, verify against redis.io): bind to loopback/private iface + `protected-mode on` (worst combo = bind all + protected-mode off); prefer **ACLs over `rename-command`** (command renaming is deprecated — use ACL to remove commands from users); restrict risky ops via `enable-protected-configs`, `enable-debug-command`, `enable-module-command` (no/yes/local); least-privilege ACL users excluding `@dangerous`/`@admin`; TLS with client auth (or stunnel/SSH tunnel); lock down config file perms; run as non-root; patch — [OneUptime hardening](https://oneuptime.com/blog/post/2026-03-31-redis-security-hardening-best-practices/view); [Redis docs mirror (Mintlify)](https://mintlify.com/redis/redis/operations/security)

**Privacy / GDPR**
- GDPR Art. 17 has no explicit backup/cache carve-out; controller must also notify recipients of an erasure request unless impossible/disproportionate effort — [sota.io](https://sota.io/blog/gdpr-right-to-erasure-backup-retention-logs-developer-compliance-2026); [Legiscope](https://www.legiscope.com/blog/right-to-erasure-gdpr.html)
- CNIL (via secondary source): a backup set need not be deleted to honor erasure; tell the data subject the data is removed from production but a backup copy may remain until it expires, and state the retention period — [SQLServerCentral relay](https://www.sqlservercentral.com/blogs/gdpr-database-backups-and-the-right-to-be-forgotten)

### Inferences
- The recurring Next.js pattern (CVE-2024-46982 → -49005 → -57752 → 2026 cluster) is the same root class: a shared cache keying on a URL without distinguishing response variant (HTML vs RSC vs 204 vs image) or honoring `Vary`. A skill should hard-require: self-hosted Next.js must either sit behind a CDN that keys on the RSC/content-type discriminators Next.js sets, or disable CDN caching of app routes — and always track the current LTS (16.3.8 / 15.5.27 as of Oct 2026).
- "Vercel-hosted unaffected / self-hosted affected" recurs because Vercel's own edge handles the keying; the skill should flag that moving a Next.js app off Vercel re-opens these CVEs unless the CDN config is replicated.
- Deception (WCD) and the 2026 cache-key-injection/WCO work both reduce to "imprecise keys." A single skill checklist item — "the cache key must fully and precisely determine the response" — covers unkeyed inputs, delimiter confusion, and key collisions.

### Gaps
- Could not fetch the RFC 9111 Security Considerations section text directly (egress blocked); only §3/§3.5 storage rules were captured via search.
- No regulator-grade source found specifically on whether **CDN edge caches / purge APIs** count as controller-held data under GDPR erasure; only backup guidance surfaced.
- Exact patched version strings for several 2026 Next.js CVEs conflict across aggregators; the authoritative GitHub advisories were not directly fetched.
- Primary writeup for Alex Brumen's cache-key-injection research (separators) not located — only secondary coverage.

## Mitigation checklists and safe defaults

### Takeaway
Two defensive spines: (1) never let a shared cache store authenticated/personalized/dynamic responses, enforced with `Cache-Control: no-store` (or `private`) + correct `Vary`; (2) make the cache key precise and identical across every hop. Testing is done with Param Miner, WCVS, and manual curl probes guided by OWASP/PortSwigger.

### Cited Findings

**Always set on authenticated/personalized responses**
- `Cache-Control: no-store` (preferred for secrets) or at minimum `private, no-cache`; plus `Expires: 0` and legacy `Pragma: no-cache`; for disk persistence add `must-revalidate, max-age=0` — [OWASP WSTG-ATHN-06](https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/04-Authentication_Testing/06-Testing_for_Browser_Cache_Weaknesses)
- Set `Vary` correctly for any response that depends on a request header (the missing-`Vary` class is exactly CVE-2025-49005) — [GitLab advisory](https://advisories.gitlab.com/npm/next/CVE-2025-49005/)
- Do not reflect unvalidated headers like `X-Forwarded-Host`; mark dynamic responses `no-store` + `private` — [Payatu: poisoning vs deception](https://payatu.com/blog/web-cache-poisoning-vs-deception-the-dynamic-duo-of-cache-attacks/)

**Safe CDN defaults**
- Cloudflare **Cache Deception Armor**: refuses to cache when the URL's extension doesn't match the returned `Content-Type`; but it DEPENDS on origin Cache-Control and can be overridden by an origin `Cache-Control`, an Edge Cache TTL Cache Rule, or Browser Cache TTL — [Cloudflare Cache Deception Armor](https://developers.cloudflare.com/cache/about/cache-deception-armor)
- Don't force "Cache Everything" + explicit Edge TTL on paths that may set cookies (strips `Set-Cookie` and caches → cross-user leak) — [Cloudflare cache behavior](https://developers.cloudflare.com/cache/best-practices/cache-behavior/)
- Against CPDoS: do not let the CDN cache error status codes (esp. 4xx) by default; align max header size between CDN and origin (CloudFront 20480 vs typical 8192) — [SecurityWeek](https://www.securityweek.com/researchers-warn-new-cache-poisoned-dos-attack-method)
- Strip dangerous framework headers at the edge (Vercel stripped `x-now-route-matches`, `X-React-Router-SPA-Mode`, `X-React-Router-Prerender-Data` and purged caches) — [Vercel changelog](https://vercel.com/changelog/protection-against-react-router-and-remix-vulnerabilities-cve-2025-43864)

**How to test for poisoning/deception**
- **Param Miner** (Burp extension, needs Burp ≥2021.9): right-click → Guess headers / GET params / cookie params / everything; binary-search guesses up to 65,536 names/request; adds a fixed cache-buster to all Burp outbound requests so you can observe caching safely. A header is only detected if it affects the response — [PortSwigger BApp Store](https://portswigger.net/bappstore/17d2949a985c4b7ca092728dba871943); [pentestreports](https://pentestreports.com/tool/param-miner)
- **WCVS (Hackmanit Web-Cache-Vulnerability-Scanner)**, Go ≥1.21, `apt install web-cache-vulnerability-scanner` on Kali, CI/CD-friendly, analyzes/adapts to the cache first, JSON reports. **9 poisoning techniques**: unkeyed header, unkeyed param, parameter cloaking, Fat GET, HTTP response splitting, request smuggling, HHO, HMC, HMO. **3 deception categories**: Path Parameter, Path Traversal, and appending chars (newline, null, `;`, `#`, `?`, `&`) — [GitHub: Hackmanit/Web-Cache-Vulnerability-Scanner](https://github.com/Hackmanit/Web-Cache-Vulnerability-Scanner); [Help Net Security](https://www.helpnetsecurity.com/2025/01/23/web-cache-vulnerability-scanner-detecting-web-cache-poisoning/)
- Manual tenant-isolation test: provision two tenants, plant unique canary data in each, check whether one surfaces in the other's session — [RedFox](https://www.redfoxsec.com/blog/testing-multi-tenant-ai-applications-for-data-leakage)

### Inferences
- A skill's "authenticated response" lint should assert the response carries `Cache-Control: no-store` (or `private` with no shared-cache directive) AND lacks `public`/`s-maxage`/`must-revalidate` — because RFC 9111 §3.5 treats those three as the only tokens that re-permit caching an `Authorization` request.
- Cache Deception Armor is a backstop, not a fix: because it can be overridden by TTL rules, the primary control must remain correct origin `Cache-Control`.

### Gaps
- No single consolidated OWASP "Web Cache Poisoning Prevention Cheat Sheet" surfaced as a distinct document; prevention guidance is spread across WSTG and PortSwigger.

## Observability: metrics per layer

### Takeaway
Standard cache metrics are hit ratio, byte-hit ratio, miss latency, origin offload, eviction vs expiry rate, memory usage, key count, and stale-served count. Each layer surfaces them differently: browser via Resource Timing (`transferSize===0`), CDN via status headers + analytics, Redis via `INFO` counters, Memcached via `stats`. RFC 9211 `Cache-Status` is the standard cross-vendor status header; vendor debug headers remain common.

### Cited Findings

**RFC 9211 `Cache-Status`** (Proposed Standard, June 2022, Mark Nottingham/Fastly) — standard replacement for ad-hoc debug headers
- Each cache in the chain appends its own entry; the header reads left-to-right (closest to origin first). Parameters: `hit` (boolean), `fwd` (why it went forward: e.g. `uri-miss`, `vary-miss`, `miss`, `request`, `stale`, `partial`, `method`, `bypass`), `fwd-status`, `ttl`, `stored` (boolean), `collapsed` (boolean), `key`, `detail` — [RFC 9211](https://www.rfc-editor.org/rfc/rfc9211); [datatracker](https://datatracker.ietf.org/doc/rfc9211/)
- Example shape: `Cache-Status: ExampleCache; hit; ttl=376` and multi-hop `Cache-Status: OriginCache; hit; ttl=1100, "CDN Loadbalancer"; fwd=uri-miss` — [http.dev Cache-Status](https://http.dev/cache-status)

**Vendor cache-status / debug headers**
- **Cloudflare `cf-cache-status`**: HIT, MISS, EXPIRED (past TTL, fresh fetched), STALE (expired served because origin unreachable), BYPASS (origin said no-cache/private/max-age=0, or cookies present), REVALIDATED (confirmed via If-Modified-Since/If-None-Match), UPDATING (stale served during background refresh, needs stale-while-revalidate), DYNAMIC (not eligible → origin), NONE (response generated before cache logic, e.g. Worker/WAF). `Age` header present on hits — [Cloudflare cache responses](https://developers.cloudflare.com/cache/concepts/cache-responses/)
- **Vercel `x-vercel-cache`**: HIT, MISS, STALE (SWR/ISR background revalidation), PRERENDER (static storage, build-time; incl. `fallback: true` not `fallback: "blocking"`), REVALIDATED (entry deleted via revalidatePath/revalidateTag/dashboard purge → foreground regenerate), BYPASS (no-store/private/no-cache or Draft Mode) — [Vercel cache status docs](https://vercel.com/docs/caching/cache-status); [Vercel response headers](https://vercel.com/docs/headers/response-headers)
- **Fastly**: `X-Cache` = HIT/MISS from `fastly_info.state` (PASS reports as MISS; may list multiple nodes with shielding, e.g. `HIT, MISS`); `X-Served-By` lists cache nodes (two with shielding); `X-Cache-Hits` = `obj.hits` (per-server); send `Fastly-Debug: 1` to expose `Fastly-Debug-Path`, `Fastly-Debug-TTL`, surrogate keys — [Fastly: checking cache](https://www.fastly.com/documentation/guides/full-site-delivery/caching/checking-cache/); [Fastly X-Cache ref](https://docs.fastly.com/documentation/reference/http/http-headers/X-Cache/)
- **CloudFront `X-Cache`**: `Hit from cloudfront`, `Miss from cloudfront`, `RefreshHit from cloudfront` (revalidated with origin that an expired object is unmodified). Full value list not on an official CloudFront developer-guide page in results — [AWS re:Post](https://repost.aws/knowledge-center/cloudfront-custom-object-caching)
- **Akamai Pragma debug** (legacy): request `Pragma: akamai-x-cache-on, akamai-x-get-cache-key` → response `X-Cache` (TCP_HIT = fresh from disk cache, TCP_MISS = fetched from origin) and `X-Cache-Key` (serial, CP code, TTL). Also `akamai-x-get-true-cache-key` (`X-True-Cache-Key`, excludes scheme+method), `akamai-x-serial-no`. Newer **Enhanced Debug** aliases these: `Akamai-Debug: cache`; bad/expired token → `Akamai-Debug-Status` response header — [Akamai edge-diagnostics Pragma headers](https://techdocs.akamai.com/edge-diagnostics/docs/pragma-headers); [Akamai Enhanced Debug](https://techdocs.akamai.com/property-mgr/docs/enhanced-debug); [Catchpoint](https://docs.catchpoint.com/docs/akamai-debug-header)

**Browser / RUM**
- Cache-hit heuristic: `transferSize === 0` AND `decodedBodySize > 0` ⇒ served from local cache. `transferSize` is also 0 for cross-origin resources without `Timing-Allow-Origin`, so the `decodedBodySize` check is required to avoid false positives — [MDN PerformanceResourceTiming.transferSize](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming/transferSize)
- Prefer `responseStatus` where supported; use `transferSize` only as fallback. Experimental `deliveryType` indicates "cache" or "navigational-prefetch" (Chrome/Edge 117+, Firefox unsupported) — [MDN PerformanceResourceTiming](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming)
- A partial `transferSize` (>0 but < `encodedBodySize`) indicates revalidation (304) — useful third category; Safari doesn't support the heuristic so Safari cache-hit RUM isn't possible — [WebKit bug 218996](https://bugs.webkit.org/show_bug.cgi?id=218996)
- Only ~250 resource-timing entries buffered by default; use a `PerformanceObserver` or `setResourceTimingBufferSize` for high-volume RUM — [MDN](https://developer.mozilla.org/en-US/docs/Web/API/PerformanceResourceTiming)

**Redis `INFO`**
- Hit ratio = `keyspace_hits / (keyspace_hits + keyspace_misses)`; counters are cumulative since restart, so compute deltas for real-time accuracy — [OneUptime: Redis hit ratio](https://oneuptime.com/blog/post/2026-03-31-redis-cache-hit-ratio-optimize/markdown)
- `evicted_keys` (alive keys dropped under memory pressure — rising ⇒ hitting memory limit / working set > cache) vs `expired_keys` (reached TTL, intended) are different signals — [Netdata: low keyspace hit rate](https://www.netdata.cloud/guides/redis/redis-low-keyspace-hit-rate/)
- Cold-start caveat: low hit rate when `uptime_in_seconds` < ~1800 may just be a cold cache; misses are normal when Redis is a primary store/queue/session store — [OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-monitor-hit-rate-cache-effectiveness/markdown)
- `mem_fragmentation_ratio` reduces usable memory and brings eviction forward (no healthy-range number found in results) — [OneUptime INFO analysis](https://oneuptime.com/blog/post/2026-03-31-redis-debug-with-info-output-analysis/view)
- Rough convention targets (one source, not Redis guarantees): session cache >99%, page cache >90% — [OneUptime](https://oneuptime.com/blog/post/2026-03-31-redis-monitor-hit-rate-cache-effectiveness/markdown)

**Memcached `stats`**
- `get_hits` / `get_misses` (lookup found vs absent); `get_expired` (lookup hit an entry past expiry); `evictions` (items dropped to make room — distinct from expiry); `curr_items` (items held); `limit_maxbytes` (configured memory ceiling — compare with `bytes` for usage). Hit ratio = `get_hits / cmd_get`; watch `evictions` alongside `limit_maxbytes` — [Telegraf memcached plugin](https://github.com/influxdata/telegraf/blob/release-1.30/plugins/inputs/memcached/README.md); [OpenStack monitorstack](https://docs.openstack.org/monitorstack/latest/plugins-base/plugin-memcache.html)

**OpenTelemetry semantic conventions**
- Redis conventions (Development status): `db.system.name` MUST = `"redis"`; `db.operation.name` (Redis command) Required; `db.namespace` (DB index as string) conditionally required and SHOULD NOT appear in span name; span kind CLIENT — [OTel Redis semconv](https://opentelemetry.io/docs/specs/semconv/database/redis); [OTel database spans](https://opentelemetry.io/docs/specs/semconv/database/database-spans)
- There is **no standard cache hit/miss attribute** in OTel; record it as a custom attribute — [OTel Redis semconv](https://opentelemetry.io/docs/specs/semconv/database/redis); older auto-instrumentation used `db.system` / `db.redis.database_index`

### Inferences
- A layer-agnostic dashboard should normalize all status headers to a common hit/miss/stale/bypass taxonomy — e.g. map `cf-cache-status`, `x-vercel-cache`, Fastly `X-Cache`, CloudFront `X-Cache`, Akamai `X-Cache`, and RFC 9211 `Cache-Status` into one field. Prefer `Cache-Status` when present since it's the standard and carries `ttl`/`key`/`collapsed`.
- Because OTel lacks a cache-hit attribute, the skill should recommend a conventional custom attribute name (e.g. `cache.hit` boolean) applied consistently so dashboards/alerts can key off it.
- Alertable signals: hit-ratio drop (delta-based, to avoid cold-start false alarms), eviction-rate spike (`evicted_keys`/min rising = undersized cache), stale-served spike (origin health), and byte-hit vs request-hit divergence (large-object misses).

### Gaps
- No official source confirming which products implement RFC 9211 `Cache-Status` (Fastly/Cloudflare/Varnish/nginx/Akamai) — only that the author is from Fastly.
- No healthy numeric range for Redis `mem_fragmentation_ratio` found in results.
- "Byte hit ratio" and "origin offload" are standard CDN-analytics metrics but no single authoritative vendor definition was captured this pass.

## Debugging: commands and tools

### Takeaway
curl header inspection across repeated requests is the core CDN/HTTP debug loop; Chrome DevTools Network panel distinguishes memory/disk/service-worker/prefetch cache; REDbot audits cacheability from headers; redis-cli has `--bigkeys`/`--hotkeys`/`MONITOR` with real performance caveats.

### Cited Findings

**curl recipes (synthesized from the header behaviors above)**
- `curl -sI https://example.com/page` — inspect `Cache-Control`, `Age`, `Vary`, `Cache-Status`/`cf-cache-status`/`x-vercel-cache`/`X-Cache` on a single HEAD request.
- Repeat the request twice and watch `Age` increase and status flip MISS→HIT to confirm the object is being cached; a non-increasing `Age` or persistent MISS indicates it isn't — (behavior per [Cloudflare cache responses](https://developers.cloudflare.com/cache/concepts/cache-responses/))
- Cache-bust with a throwaway query param (`?cb=$RANDOM`) to force a fresh origin fetch without purging; this is also how Param Miner protects live targets with a fixed cache-buster — [PortSwigger BApp](https://portswigger.net/bappstore/17d2949a985c4b7ca092728dba871943)
- Conditional revalidation: `curl -sI -H 'If-None-Match: "<etag>"' …` to check for `304 Not Modified` / `REVALIDATED`.
- Fastly: `curl -sI -H 'Fastly-Debug: 1' …` exposes `Fastly-Debug-Path`, `Fastly-Debug-TTL`, surrogate keys — [Fastly checking cache](https://www.fastly.com/documentation/guides/full-site-delivery/caching/checking-cache/)
- Akamai: `curl -sI -H 'Pragma: akamai-x-cache-on, akamai-x-get-cache-key, akamai-x-get-true-cache-key' …` → `X-Cache` (TCP_HIT/TCP_MISS), `X-Cache-Key`, `X-True-Cache-Key`; or `-H 'Akamai-Debug: cache'` — [Akamai Pragma headers](https://techdocs.akamai.com/edge-diagnostics/docs/pragma-headers)

**Chrome DevTools Network panel**
- The Size column shows how a resource was served; cached resources appear with cache labels (`(memory cache)`, `(disk cache)`, `(prefetch cache)`, ServiceWorker). "Disable cache" checkbox simulates a first-time visitor; corresponds to CDP `Network.setCacheDisabled` — [Chrome DevTools docs (cache storage)](https://developer.chrome.com/docs/devtools/storage/cache); [Core Web Vitals DevTools settings](https://www.corewebvitals.io/pagespeed/best-chrome-devtools-network-settings-for-core-web-vitals) (note: exact Size-column label strings not found on an official page this pass — Chrome docs point to the Size column as the place to look)
- ServiceWorker-served responses can later show as memory-cache hits, which can be confusing to interpret — [WebKit bug 218996](https://bugs.webkit.org/show_bug.cgi?id=218996) (WebKit report, indicative)

**REDbot (redbot.org)**
- Tests a URL's HTTP headers and reports how caches may treat it (whether all caches may store, whether a cache may set its own freshness lifetime), points out common problems, suggests improvements. Operates at the HTTP semantic layer per RFC 9110/9111; does NOT check HTTP/2 or HTTP/3 specifics and is not a conformance tester — [REDbot about](https://redbot.org/about/); [Mike West review](https://mikewest.org/2009/05/mnots-redbot/)
- Public site prohibits automated/scripted queries — run your own instance (`pipx install redbot`, CLI available) for CI — [PyPI redbot](https://pypi.org/project/redbot/)

**redis-cli diagnostics**
- `--bigkeys` / `--memkeys` / `--hotkeys` traverse all keys (SCAN-based) and can affect performance; convenient but may have low accuracy/timeliness — [Alibaba Cloud](https://www.alibabacloud.com/help/en/redis/big-keys-and-hotkeys)
- `--hotkeys` requires an **LFU** `maxmemory-policy` (e.g. `allkeys-lfu`) or it errors out — [OneUptime --hotkeys](https://oneuptime.com/blog/post/2026-03-31-redis-cli-hotkeys-hot-keys/markdown)
- `MONITOR` streams every command from every client and is dangerous for latency; run only briefly on a low-traffic / non-production DB, or on a read replica (e.g. `timeout 5 redis-cli MONITOR`) — [Redis KB (via StackHarbor)](https://stackharbor.com/en/knowledge-base/redis-monitor-command-misuse/)
- Lower-impact alternatives to find hot keys: `OBJECT FREQ <key>` (LFU), `SLOWLOG`, `INFO commandstats` — [StackHarbor](https://stackharbor.com/en/knowledge-base/redis-monitor-command-misuse/)

### Inferences
- A good debug SOP for "is this page cached and shared across users?": (1) `curl -sI` twice, confirm `Age` climbs and status=HIT; (2) send with and without an auth cookie and confirm the authed variant is BYPASS/MISS (never HIT); (3) try a deception probe (`/page;.css`, `/page.css`, `/page%00.css`) and confirm it is NOT cached; (4) check `Vary` covers every header the body depends on.

### Gaps
- Exact Chrome DevTools Size-column label strings were not confirmed against an official Chrome page (search pointed to the Size column generally but not the label glossary).

## Testing: unit, integration, E2E, load, chaos, CI

### Takeaway
Test TTL/expiry logic with injected fake clocks; assert response headers in integration tests; run E2E checks that private data is never cached at the CDN; load-test to observe stampede behavior; chaos-test cache outages; and snapshot cache headers in CI plus synthetic monitoring post-deploy.

### Cited Findings

**Cache stampede / load behavior (what load tests should reveal and fixes to verify)**
- Stampede = a popular key expires and many concurrent requests simultaneously regenerate the value; most dangerous for expensive-to-regenerate keys — [OneUptime: Redis cache stampede](https://oneuptime.com/blog/post/2026-01-21-redis-cache-stampede/markdown)
- Fixes to assert under load: **locking / request coalescing** (one request regenerates while others wait; always set a lock timeout so a crashed holder's lock expires; a plain `DEL` can wrongly free another request's lock if yours expired first); **single-flight** in-process coalescing — [OneUptime stampede prevention](https://oneuptime.com/blog/post/2026-01-30-cache-stampede-prevention/markdown)
- **XFetch / probabilistic early expiration** (Vattani, Chierichetti, Lowenstein, VLDB 2015): store previous rebuild duration with the value, scale the refresh window so expensive entries refresh earlier; no request waits, no coordination, but guarantee is probabilistic (two nodes can still recompute). Plus `stale-while-revalidate` (logical expiry earlier than physical TTL) and jittered TTLs — [antirez: cache stampede prevention](https://redis.antirez.com/fundamental/cache-stampede-prevention.html); [OneUptime](https://oneuptime.com/blog/post/2026-01-30-cache-stampede-prevention/markdown)

**Security regression / CI testing**
- WCVS is designed for easy CI/CD integration and emits JSON reports — run it against staging on every deploy to catch poisoning/deception regressions — [GitHub: Hackmanit/WCVS](https://github.com/Hackmanit/Web-Cache-Vulnerability-Scanner)
- REDbot can run as an installed CLI (`pipx`) for header/cacheability checks in CI — [PyPI redbot](https://pypi.org/project/redbot/)
- Canary-based tenant-isolation E2E test (two tenants, unique data, assert no cross-surface) — [RedFox](https://www.redfoxsec.com/blog/testing-multi-tenant-ai-applications-for-data-leakage)

### Inferences
- Unit tests: inject a controllable clock (fake timer) so TTL expiry/`stale-while-revalidate` windows are deterministic; assert "fresh → within TTL hit, past TTL miss/revalidate" without real sleeps. (Standard practice; no single authoritative source captured, so present as a pattern not a citation.)
- Integration tests: for each route class, assert the exact `Cache-Control`/`Vary`/`Set-Cookie` headers — a "header snapshot test" that fails when a route's caching posture changes unexpectedly (this is what the Next.js missing-`Vary` CVE would have caught).
- E2E "private-never-at-CDN" check: log in, fetch an authenticated page through the real CDN, assert status header is BYPASS/MISS/DYNAMIC and never HIT, and that a second anonymous request cannot retrieve the authed body.
- Chaos test: kill/partition the cache (Redis/Memcached/CDN origin-shield) and assert graceful degradation (origin absorbs load without cascading failure; stampede protection holds) rather than total outage.
- Synthetic monitoring post-deploy: scripted requests asserting hit-ratio and correct status headers on key URLs, alerting on a hit-ratio drop or a route that flipped from BYPASS to HIT.

### Gaps
- No authoritative framework-specific source captured for "fake clock / deterministic TTL" unit-testing or for header-snapshot CI tooling; these are presented as inferred standard patterns, not cited facts.
- No cited chaos-engineering case study specific to cache outages was located this pass.
