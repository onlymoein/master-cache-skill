# Changelog

All notable changes to the `caching-strategy` skill. Versions follow `metadata.version` in
`skills/caching-strategy/SKILL.md` and the plugin version in `.claude-plugin/marketplace.json`.

## 1.0.0 (2026-10-27)

First release.

- `SKILL.md`: ten standing rules, workflow checklist, routing table to every reference, cross-layer gotchas, glossary and output contract.
- 48 references: core method (decision tree, archetypes, HTTP semantics, invalidation, stampedes, security, observability), 12 layers, 16 frameworks, 5 CMS/commerce platforms, 8 CDN/hosting platforms. Facts reviewed 2026-10-27.
- Scripts (Python standard library): `detect_stack.py`, `find_cache_primitives.py`, `probe_headers.py`, `validate_plan.py`, `size_cache.py`.
- Assets: plan schema, example plan, plan template, per-data-class policy defaults, 23 snippets (headers middleware, CDN and proxy config, cache-aside with stampede control, Redis lease/version Lua, Next.js cache handler and CMS webhook, Workbox, CI cache, header and leak tests).
- Evals: output-quality cases with fixture repos and trigger queries with a train/validation split.

## Review cadence

Re-review time-sensitive facts quarterly (framework majors, CDN features and limits, security advisories) and bump `last-reviewed`; `tools/lint_skill.py` warns after 180 days.
