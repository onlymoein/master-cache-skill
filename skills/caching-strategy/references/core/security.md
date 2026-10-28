# Cache security

Last reviewed: 2026-10-27 · Applies to: browser, CDN, proxy, framework and app caches; Redis/Valkey/Memcached

## Contents

- When to read this
- The invariant
- Pre-ship checklist
- Rules and gotchas
- Attack classes and mitigations
- Framework cache CVEs
- Personalized and sensitive responses
- Multi-tenant app caches
- Cache server hardening
- Privacy and erasure
- Verify
- Sources

## When to read this

Always. Every plan must pass this file's checklist before anything ships. Testing tools and probes: `references/core/observability-testing.md`.

## The invariant

**The cache key must fully and precisely determine the response.** Unkeyed inputs (poisoning), path/delimiter confusion (deception), key collisions from missing separators, missing `Vary` on variant responses, and forgotten tenant prefixes all violate it. If a response depends on something that isn't in the key, either add it to the key (low cardinality only) or don't share the response.

## Pre-ship checklist

- [ ] Every response, including errors and redirects, carries an explicit `Cache-Control`. Default `no-store`; routes opt in.
- [ ] Responses that depend on cookies, sessions, `Authorization`, tenant, entitlement or A/B bucket are `private` (or `no-store`) and never carry `public`, `s-maxage`, a CDN-targeted TTL, or a CDN rule that caches them.
- [ ] No `Set-Cookie` on any shared-cacheable response.
- [ ] CDN "cache everything"/override rules are paired with explicit bypasses for authenticated paths and session cookies.
- [ ] Deception probes (`/account.css`, `/account;.css`, `/account/x.css`, `/account%00.css`) are never cached.
- [ ] Unkeyed headers (`X-Forwarded-Host`, `X-Host`, `X-Forwarded-Scheme`, `X-Original-URL`) aren't reflected, or are stripped at the edge.
- [ ] `Vary` lists every request header that changes the body (and nothing high-cardinality); framework variant headers (Next.js `rsc`) are forwarded and keyed.
- [ ] Error responses (4xx/5xx) aren't cached by the CDN beyond seconds; header-size limits are aligned between CDN and origin.
- [ ] App-cache keys include the tenant (and user, for per-user data) in one central helper.
- [ ] Redis/Valkey/Memcached aren't reachable from the internet; auth/ACLs and TLS are on.
- [ ] Framework versions are on patched releases (table below).
- [ ] Two-user leak test passes through the real CDN.

## Rules and gotchas

1. Origin headers are the primary control. CDN protections (Cloudflare Cache Deception Armor, cookie stripping) are backups: Deception Armor only acts when freshness is heuristic and can be overridden by TTL rules.
2. A shared cache may reuse a response to a request with `Authorization` only if the response has `public`, `s-maxage` or `must-revalidate`. Never add those to authenticated responses.
3. Forcing "Cache Everything" + Edge TTL on Cloudflare strips `Set-Cookie` and caches the body: personalized pages leak across users.
4. Google Cloud CDN `FORCE_CACHE_ALL` ignores `private`/`no-store`; CloudFront policies with `MinTTL > 0` can override them; Akamai ignores origin headers unless configured to honor them; Azure Front Door caches directive-less responses 1–3 days.
5. Moving a Next.js app off Vercel reopens cache CVEs that Vercel's edge masked: replicate variant keying (`rsc`/`_rsc`) on the new CDN or don't cache app routes there.
6. Emergency CDN changes under attack are high-risk (Steam 2015). Review them like code.
7. Never put raw session IDs or bearer tokens in cache keys.
8. Semantic/LLM caches must be partitioned per tenant; adversarial prompts can collide with cached entries (`references/layers/ai-llm.md`).

## Attack classes and mitigations

| Attack | How it works | Mitigation |
|---|---|---|
| Web cache poisoning (unkeyed inputs) | App reflects a header/param the cache ignores (`X-Forwarded-Host`, `X-Host`, `X-Forwarded-Scheme`, unkeyed `utm_*`); harmful response cached for everyone | Don't reflect unvalidated headers; strip them at the edge; key on everything that changes the body; `private`/`no-store` for dynamic responses |
| Parameter cloaking | Cache and origin parse query strings differently (e.g. `;` as separator) | Normalize/reject ambiguous queries at the edge; same parser semantics across hops |
| Fat GET | GET with a body; frameworks that merge body params (Rails) let the body override cached params | Reject or ignore bodies on GET at the edge |
| Cache key injection / collisions (2026) | Key components concatenated without separators collide (`/home` + `*/*` vs `/h` + `ome*/*`) | Explicit separators in custom keys (nginx `proxy_cache_key`), hash components |
| Web Cache Overflow (2026) | Imprecise keys keep redundant entries alive, evicting legitimate objects | Precise keys; allow-list query params |
| Web cache deception | Cache treats `/account.css` as static while the origin serves `/account`: Rails `.` format suffix, Spring `;` matrix variables, OpenLiteSpeed `%00`, encoded traversal after a delimiter | Origin sends `private`/`no-store` on authenticated routes regardless of extension; cache only explicit static path prefixes; Deception Armor as backup |
| CPDoS (HHO, HMC, HMO) | Oversized headers, meta characters or method-override headers make the origin return an error that the cache stores | Don't cache 4xx/5xx (or only for seconds); align max header sizes (CloudFront accepts larger headers than most origins); ignore `X-HTTP-Method-Override` on cacheable routes |
| HTTP/1.1 desync (2025) | Parser discrepancies between hops enable smuggling-based poisoning | HTTP/2 end to end where possible; patched proxies; WCVS smuggling checks |
| Framework variant confusion | HTML and RSC/JSON payloads share a URL without `Vary`/key separation | Patch frameworks; forward and key framework variant headers |

Prevalence: 56 of the Tranco top 1,000 sites were vulnerable to poisoning (CCS 2024); the largest deception study found 1,188 vulnerable domains.

## Framework cache CVEs

Keep frameworks on their latest patch release; check GitHub Security Advisories for anything newer than this table.

| CVE | Framework | Issue | Fixed in |
|---|---|---|---|
| CVE-2024-46982 | Next.js (Pages Router) | Crafted request poisons a non-dynamic SSR page | 13.5.7 / 14.2.10 |
| CVE-2025-49005 | Next.js (App Router) | Missing `Vary`: RSC payload cached in place of HTML | 15.3.3 |
| CVE-2025-57752 | Next.js (Image Optimization) | Cache-key confusion serves header-dependent images to the wrong users | 14.2.31 / 15.4.5 |
| CVE-2026-44576 | Next.js | Shared caches confuse HTML and RSC for the same URL | 15.5.16 / 16.2.5 |
| September 2026 release | Next.js | Several cache-poisoning fixes (self-hosted Pages Router, root catch-all + ISR, Draft Mode + `'use cache'`) | 16.3.8 / 15.5.27 |
| CVE-2025-43864 / CVE-2025-43865 | React Router / Remix v7 | `X-React-Router-SPA-Mode` / `X-React-Router-Prerender-Data` headers make a broken or spoofed response cacheable | 7.5.2 |
| CVE-2025-27415 | Nuxt | `/?/_payload.json` cached as the page by CDNs that ignore the query string | 3.16.0 |
| CVE-2026-48588 (and related 6.0.6 fixes) | Django | Session-cookie responses stored in the shared cache; `Authorization` not varied | 6.0.7 |
| CVE-2025-49844 ("RediShell") | Redis | Lua use-after-free → RCE for authenticated users | 8.2.2 (later 2026 fixes in 8.6.3) |

Version ranges differ across aggregators for some 2026 entries; confirm against the vendor advisory before quoting exact ranges in a plan.

## Personalized and sensitive responses

| Response | Headers |
|---|---|
| Personalized page or API | `Cache-Control: private, no-cache` + `ETag` |
| Sensitive (payment, PII, tokens) | `Cache-Control: no-store` |
| Logout response | `Clear-Site-Data: "cache", "cookies", "storage"` (plus `"prefetchCache", "prerenderCache"` in Chrome 138+). Test it first: one report saw unexpected cookie loss; Safari support is partial |

- `no-store` doesn't delete copies already stored, and Chrome may still restore `no-store` pages from bfcache (evicted when cookies change). Re-check auth on `pageshow` with `event.persisted`.
- OWASP WSTG (browser cache weaknesses) expects sensitive pages to send `no-store` so data isn't recoverable from disk or the Back button.
- Clear client data caches (TanStack Query, Apollo, IndexedDB, service worker caches) on logout and account switch.
- Draft/preview mode bypasses every cache layer.

## Multi-tenant app caches

- Leaks come from a code path that forgot the tenant prefix, not from key collisions. They're intermittent: they surface only when another tenant warmed the cache.
- Build every key through one helper that requires the tenant ID (e.g. `t:{tenant}:…`); forbid raw `cache.get(f"report:{id}")` in review.
- Redis ACLs can restrict users to key patterns (`~t:42:*`) but tenants still share memory and I/O; regulated tenants may need separate databases or clusters.
- Canary test: two tenants, unique planted data, assert neither ever sees the other's.

## Cache server hardening

- Never expose Redis/Valkey/Memcached publicly. Bind to private interfaces, keep `protected-mode on`, require auth. Official Redis container images ship with auth disabled; ~60,000 internet-exposed instances had no auth when RediShell landed.
- Use ACL users with least privilege (exclude `@dangerous`, `@admin`) instead of deprecated `rename-command`; restrict `enable-protected-configs`, `enable-debug-command`, `enable-module-command`.
- TLS with client auth where possible; run as non-root; lock down config file permissions; patch promptly.
- Disable or restrict Lua for untrusted users where the engine allows it (Valkey 9.1 moved Lua into a module that can be disabled).

## Privacy and erasure

- GDPR Art. 17 has no explicit cache carve-out. Keep personal data out of shared caches; bound app-cache TTLs on personal data; have a purge path (keys by user ID or tag) for erasure requests; document retention for caches and logs.
- CDN logs and cache keys can contain PII (URLs with emails, tokens). Strip query parameters carrying PII from keys and logs.

## Verify

```bash
# Two-session leak test through the real CDN (also: python scripts/probe_headers.py URL --cookie-a 'sid=A' --cookie-b 'sid=B')
bash assets/snippets/tests/leak-test.sh https://example.com/account 'sid=USER_A' 'sid=USER_B'

# Deception probes: none of these may return HIT/Age or public caching
for p in '/account.css' '/account;.css' '/account/x.css' '/account%00.css'; do
  curl -s -o /dev/null -D - -H 'Cookie: sid=USER_A' "https://example.com$p" | grep -iE '^(cache-control|age|cf-cache-status|x-cache|x-vercel-cache|cache-status):'
done

# Unkeyed header reflection (use a cache-buster so you don't poison real users)
curl -s "https://example.com/?cb=$RANDOM" -H 'X-Forwarded-Host: evil.example' | grep -c 'evil.example'
```

Run the Web Cache Vulnerability Scanner (WCVS) against staging in CI, only on systems you're authorized to test.

## Sources

- [PortSwigger: Practical Web Cache Poisoning](https://portswigger.net/kb/papers/7q1e9u9a/web-cache-poisoning.pdf)
- [PortSwigger: Web Cache Entanglement](https://portswigger.net/research/web-cache-entanglement)
- [PortSwigger: Gotta cache 'em all (web cache deception)](https://portswigger.net/research/gotta-cache-em-all)
- [PortSwigger: HTTP/1.1 must die](https://portswigger.net/research/http1-must-die)
- [Web Cache Overflow (arXiv 2608.04744)](https://arxiv.org/pdf/2608.04744)
- [CPDoS](https://cpdos.org/)
- [RFC 9111 §3.5 (Authorization)](https://httpwg.org/specs/rfc9111.html)
- [OWASP WSTG: browser cache weaknesses](https://owasp.org/www-project-web-security-testing-guide/stable/4-Web_Application_Security_Testing/04-Authentication_Testing/06-Testing_for_Browser_Cache_Weaknesses)
- [Cloudflare Cache Deception Armor](https://developers.cloudflare.com/cache/about/cache-deception-armor)
- [Next.js September 2026 security release](https://nextjs.org/blog/september-2026-security-release)
- [Wiz: CVE-2025-49844](https://www.wiz.io/vulnerability-database/cve/cve-2025-49844)
- [Redis: multi-tenant data isolation](https://redis.io/blog/data-isolation-multi-tenant-saas/)
