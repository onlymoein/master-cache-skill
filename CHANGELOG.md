# Changelog

All notable changes to the `caching-strategy` skill. Versions follow `metadata.version` in
`skills/caching-strategy/SKILL.md` and the plugin version in `.claude-plugin/marketplace.json`.

## 1.1.0 (2026-10-28)

Fixes from running the skill end to end on the Next.js 16 eval fixture (built and served with real Next.js 16.4.3) and walking every eval through its routed references.

- `detect_stack.py` reports the instance count (Kubernetes replicas and HPAs, Helm `replicaCount`, compose `deploy.replicas`, Fly, Render, ECS, serverless hosts). It warns when several self-hosted Next.js instances run without a shared `cacheHandler`.
- `nextjs.md`: set `partialPrefetching` explicitly; the Cache Components build check (`<Suspense>`, `'use cache'` or `instant = false`); one request-data read makes the HTML `private, no-store`; `'use cache'` caches "not found" results.
- `rails.md`: CDN purge from `after_commit` through a background job (Fastly soft purge), plus a publish-to-visible check.
- `netlify.md`: fingerprinted assets need an explicit `immutable` rule; browsers get `max-age=0, must-revalidate` by default.
- `validate_plan.py` and `probe_headers.py` no longer report Next.js's own dynamic `Cache-Control` as kitchen-sink headers.
- Evals: a reference solution for eval 1 (plan, findings, code changes, verification log) and an expectation covering the Cache Components build check.

## 1.0.0 (2026-10-27)

First release.

- `SKILL.md`: ten standing rules, workflow checklist, routing table to every reference, cross-layer gotchas, glossary and output contract.
- 48 references: core method (decision tree, archetypes, HTTP semantics, invalidation, stampedes, security, observability), 12 layers, 16 frameworks, 5 CMS/commerce platforms, 8 CDN/hosting platforms. Facts reviewed 2026-10-27.
- Scripts (Python standard library): `detect_stack.py`, `find_cache_primitives.py`, `probe_headers.py`, `validate_plan.py`, `size_cache.py`.
- Assets: plan schema, example plan, plan template, per-data-class policy defaults, 23 snippets (headers middleware, CDN and proxy config, cache-aside with stampede control, Redis lease/version Lua, Next.js cache handler and CMS webhook, Workbox, CI cache, header and leak tests).
- Evals: output-quality cases with fixture repos and trigger queries with a train/validation split.

## Review cadence

Re-review time-sensitive facts quarterly (framework majors, CDN features and limits, security advisories) and bump `last-reviewed`; `tools/lint_skill.py` warns after 180 days.
