# Caching plan: {{app name}}

Generated {{YYYY-MM-DD}} · Archetype: {{primary}} (+ {{secondary}}) · Stack: {{framework@version, hosting, CDN, data stores}}
Machine-readable version: `plan.json` (validated with `scripts/validate_plan.py`: {{valid / N warnings}})

## 1. Summary

- **Biggest risks found:** {{e.g. /account cached by the CDN for 10 min (cross-user leak); no Cache-Control on HTML}}
- **Biggest wins:** {{e.g. CDN for product pages with tag purge: origin RPS −70 %, TTFB p75 1.4 s → 0.3 s (estimate)}}
- **Freshness promise:** {{e.g. product edits visible within 60 s; prices within 10 s}}
- **Decisions needed from you:** {{list, or "none"}}

## 2. Findings

Safety issues first. Each finding cites evidence (`file:line`, probe output, dashboard export).

| # | Severity | Finding | Evidence | Fix (phase) |
|---|---|---|---|---|
| F1 | high | {{personalized page shared-cacheable}} | {{app/account/route.ts:4 — `public, s-maxage=600`}} | {{private, no-cache (phase 0)}} |
| F2 | medium | {{...}} | {{...}} | {{...}} |

Baseline (dated, with source): {{CDN hit ratio excluding BYPASS, origin RPS, p95 per route, Redis hit ratio/evictions, TTFB/LCP p75}}.
Unknown inputs and the assumption used instead: {{...}}.

## 3. Route and data classification

One row per route or data type; `no-store` rows stay in the table to document the decision.
Decision step = the step of `references/core/decision-framework.md` that decided the row.

| ID | Route / data | Class · audience | Budget S | Browser `Cache-Control` | Shared layer · header | Key / `Vary` | App cache | Tags | Invalidation → propagation | Step | Owner |
|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `/_next/static/*` | fingerprinted-asset · public | versioned | `public, max-age=31536000, immutable` | CDN · same | path only | — | — | new URL per build → 0 s | 3 | platform |
| R2 | `/products/[slug]` | public-html-volatile · public | 60 s | `no-cache` | CDN · `CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400` | allow `variant`; strip `utm_*` | framework (`cacheTag`) | `product:{id}`, `all` | product.updated → tag purge → 30 s | 5 | storefront |
| R3 | `/account/*` | personalized · personalized | 0 | `private, no-cache` | none | — | L2 `shop:prod:v1:user:{id}:orders` | — | delete on write → 0 s | 2 | accounts |

## 4. Invalidation map

| Event | Entities | Keys / tags cleared | Order | Mechanism | Propagation | Owner |
|---|---|---|---|---|---|---|
| product.updated | product | `product:{id}`, `section:catalog` | DB commit → app cache delete → CDN soft purge | webhook → `revalidateTag` + purge API | 30 s | storefront |

Ordering rule: delete or purge **after** the commit; purge inner layers before outer ones (app cache → proxy → CDN). Missed purges are bounded by the TTL backstop.

## 5. Stampede and failure handling

| Hot key / route | Protection | On origin failure |
|---|---|---|
| {{product page}} | {{CDN request collapsing + SWR; app single-flight}} | {{stale-if-error 1 day}} |
| {{homepage data}} | {{XFetch / soft TTL refresh}} | {{serve stale; breaker opens after 5 errors}} |

Cache outage behavior: {{fail open to origin with timeouts + breaker; origin capacity at 0 % hit ratio is N RPS}}.

## 6. Security checks

- [ ] No shared caching (CDN, proxy, gateway, framework full-route cache) of responses that depend on cookies, sessions, `Authorization`, tenant, entitlement or A/B bucket
- [ ] Public cacheable responses never `Set-Cookie`
- [ ] Cache keys include every input that changes the response (host, allowed query params, `Accept-Encoding`, language) and nothing user-specific
- [ ] Unkeyed headers that change responses (`X-Forwarded-Host`, `X-Original-URL`, …) are ignored or keyed (poisoning)
- [ ] Asset-extension cache rules can't match dynamic paths (`/account/x.css`, `;`, `%2F`) (deception)
- [ ] Errors (5xx) aren't cached; 404 only briefly (CPDoS)
- [ ] Framework patched for known cache advisories ({{framework}} {{version}} → {{patched version}})
- [ ] Purge endpoints and webhooks are authenticated and rate limited
- [ ] Leak test passes: `python scripts/probe_headers.py <url> --cookie-a … --cookie-b …`

## 7. Rollout

| Phase | Work | Routes | Canary / exit criteria | Rollback |
|---|---|---|---|---|
| 0 | Safety fixes | R3, R4 | leak test passes on staging and production | revert header middleware |
| 1 | {{...}} | {{...}} | {{...}} | {{...}} |

Every phase: canary first, load test (a new cache can move the bottleneck), watch the metrics below for one business cycle.

## 8. Monitoring and verification

| Metric | Target | Source | Alert |
|---|---|---|---|
| CDN hit ratio over cacheable requests (exclude BYPASS) | ≥ {{0.90}} | {{CDN analytics}} | < {{0.80}} for 15 min |
| Origin RPS / p95 per route | {{−70 %}} / {{< 300 ms}} | APM | {{...}} |
| App cache hit ratio, evictions, memory | ≥ {{0.85}}, evictions flat | `INFO stats` | {{...}} |
| Publish-to-fresh latency | p95 ≤ {{60 s}} | synthetic check | {{...}} |
| Cross-user leak canary | 0 | scheduled leak test | any failure pages on-call |

Verification commands per route: see the `verify` field of each row in `plan.json`.

## 9. Open questions and assumptions

- {{e.g. Traffic share per route unknown: assumed product pages ≈ 60 % of GETs.}}
- {{e.g. Is the CDN in front of /api/*? Probe showed no CDN headers.}}
