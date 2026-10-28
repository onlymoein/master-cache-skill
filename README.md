# master-cache-skill

`caching-strategy` is an Agent Skill that designs, audits and implements caching for a **specific** website or app, across every layer: HTTP/browser headers, service workers, CDNs and edge platforms, reverse proxies, in-process and distributed caches, databases and ORMs, framework caches, CMS and commerce platforms, APIs (REST, GraphQL, RPC, gateways), mobile clients, LLM prompt/semantic caching and CI build caches.

It detects the stack and versions, classifies every route with one decision tree, and produces a caching plan that passes a safety validator. The plan covers invalidation, stampede protection, cache security (no cross-user leaks, poisoning or deception) and verification.

## Install

**Claude Code** (plugin marketplace in this repo):

```text
/plugin marketplace add onlymoein/master-cache-skill
/plugin install caching-strategy@master-cache-skill
```

**Other agents that read Agent Skills** (Cursor, Codex, Gemini CLI, Copilot and others):

```bash
npx skills add onlymoein/master-cache-skill
```

**claude.ai**: zip the skill folder and upload it under Settings → Capabilities → Skills:

```bash
cd skills && zip -r caching-strategy.zip caching-strategy -x '*/__pycache__/*'
```

**Claude API**: upload the same folder with the Skills API (`POST /v1/skills`). The skill is under 1 MB and needs no network except for the optional live header probe.

## What it does

Ask things like "our product pages are slow and the hosting bill doubled", "revalidateTag works locally but not in production", "set up Redis caching for this API" or "audit our CDN config". The skill then:

1. Runs `scripts/detect_stack.py` to fingerprint frameworks (with lockfile versions), hosting/CDN, proxies, data stores, CMS, API, mobile and AI usage, then reads only the references that stack needs.
2. Runs `scripts/find_cache_primitives.py` to list existing caching code with `file:line` and flag risky patterns.
3. Optionally probes live URLs you give it with `scripts/probe_headers.py`: MISS→HIT, `Age`, 304s, a two-session leak test and web cache deception probes. Cookie values are never printed.
4. Confirms archetype, staleness budgets, tenancy and instance count with you.
5. Classifies each route or data type (decision tree steps 0–9) and writes a plan from `assets/caching-plan.template.md`, plus `plan.json`.
6. Validates the plan with `scripts/validate_plan.py`. It blocks shared caching of personalized data, TTLs over the staleness budget, missing invalidation and similar mistakes.
7. Implements the plan in phases, safety fixes first, and verifies headers, hit behavior and leak tests.

## Layout

```text
skills/caching-strategy/
├── SKILL.md                 rules, workflow, routing table, gotchas, glossary, output contract
├── references/              48 files loaded on demand
│   ├── core/                decision framework, archetypes, HTTP semantics, invalidation, stampedes, security, observability
│   ├── layers/              browser, service workers, CDN, proxies, in-process, distributed, DB/ORM, serverless/edge, APIs, mobile, AI/LLM, build/CI
│   ├── frameworks/          Next.js, Nuxt/Nitro, SvelteKit, React Router/Remix, Astro, other frontends, client data caches,
│   │                        Rails, Django, Laravel/PHP, Spring/JVM, ASP.NET Core, Node backends, Python web, Go, Elixir
│   ├── cms/                 WordPress, Drupal, Shopify Hydrogen, Magento, headless CMS
│   └── platforms/           Cloudflare, Vercel, Netlify, Fastly, CloudFront, Akamai, GCP/Azure CDN, other hosts
├── scripts/                 detect_stack, find_cache_primitives, probe_headers, validate_plan, size_cache (stdlib Python)
└── assets/                  plan schema, example plan, plan template, policy defaults, 23 snippets
evals/                       output-quality evals with fixture repos, trigger queries (not shipped with the skill)
tests/                       unit tests for the scripts
tools/lint_skill.py          spec and convention linter
```

## Development

```bash
python tools/lint_skill.py                     # frontmatter, links, reference structure, paths, scripts
python -m unittest discover -s tests -v        # script tests (fixture repos, fake leaky CDN for the probe)
python skills/caching-strategy/scripts/validate_plan.py skills/caching-strategy/assets/plan.example.json
```

The scripts and tests need Python 3.9+ and nothing else. CI runs all three on Python 3.9 and 3.13.

Evals: see [evals/README.md](evals/README.md). Run them with and without the skill, and on Haiku, Sonnet and Opus. Haiku shows whether the router reads only the files it should.

### Updating content

- Facts come with a `Last reviewed` date per reference and `metadata.last-reviewed` in `SKILL.md`. Review time-sensitive facts quarterly: framework majors, CDN features and limits, security advisories.
- Put current guidance first. Superseded APIs go in each reference's "Old patterns" block.
- When a fact can't be verified, say so ("verify against current docs") instead of stating it as settled.
- Bump `metadata.version` in `SKILL.md`, the plugin version in `.claude-plugin/marketplace.json`, and `CHANGELOG.md` together.

## License

MIT. See [LICENSE](LICENSE).
