# Evals for `caching-strategy`

This folder is not part of the shipped skill (packaging leaves out a root-level `evals/`).

## Output-quality evals (`evals.json`)

The skill-creator format: each case has a `prompt`, an `expected_output` description, input `files` (paths relative to this folder) and `expectations` that a grader checks against concrete evidence in the transcript and outputs.

| ID | Fixture | What it tests |
|---|---|---|
| 1 | `fixtures/next16-vercel-store` | Next.js 16 Cache Components APIs, one-argument `revalidateTag`, private cart / `no-store` checkout |
| 2 | `fixtures/next15-k8s-cloudfront` | "Works locally, stale in production": per-pod caches, CloudFront TTL, shared `cacheHandler`, no Next 16 APIs on Next 15 |
| 3 | `fixtures/django-saas-redis` | `cache_page` on authenticated views, cross-tenant key, stampede control, Django patch level |
| 4 | `fixtures/rails-news-fastly` | Purge-driven freshness with surrogate keys, `touch: true`, SWR/SIE |
| 5 | `fixtures/wordpress-apo` | `Set-Cookie` causing BYPASS, one page-cache layer, object cache |
| 6 | `fixtures/express-apollo-graphql` | Module-level DataLoader leak, Apollo Server 5, cache hints, persisted queries |
| 7 | `fixtures/expo-avatars` | Stable URL with changing content, versioned keys, server-driven freshness |
| 8 | `fixtures/rag-support-bot` | Prompt-cache prefix order, cached-token KPI, tenant-scoped response caching |
| 9 | none | A narrow question gets a direct answer, not a full audit |

Run each case with and without the skill (baseline), on Haiku, Sonnet and Opus. Haiku shows whether the router reads only the references `detect_stack.py` lists. Grade only on evidence; a missing expectation fails even if the answer is otherwise good.

Fixture sanity is unit-tested: `tests/test_evals.py` checks that `detect_stack.py` gives each fixture the intended archetype and references, and that the eval files are well-formed.

## Trigger evals (`trigger_queries.json`)

22 queries: 12 should trigger the skill (several never say "cache"), 10 near misses that should not (LRU interview code, pip/npm/browser caches, CPU caches, a Redis job queue). Splits are fixed at roughly 60/40 train/validation. Tune the description on `train` only and report `validation`. Run each query 3 times. Don't add keywords copied from failed queries; that overfits.

## Adding a case

1. Add a small fixture repo under `fixtures/` (only the files that matter: manifests, lockfile, config, the code with the problem).
2. Add the case to `evals.json` with concrete, checkable expectations.
3. Add the fixture's expected archetype to `tests/test_evals.py`.
4. Run `python tools/lint_skill.py` and `python -m unittest discover -s tests`.
