# Authoring Claude Agent Skills (state as of Oct 2026) and a survey of caching and web-performance skills

Scope note: I fetched the official docs live on 2026-10-27. These were code.claude.com skills, plugin-evals and plugin-marketplaces, plus platform.claude.com overview, best-practices and skills-guide. agentskills.io did not resolve from the research sandbox. Its docs are therefore cited from the source repo github.com/agentskills/agentskills (commit dated 2026-08-09), which is the source of that site. I read the ecosystem repos from shallow clones of the default branch. Their last commits were: anthropics/skills 2026-10-09, cloudflare/skills 2026-10-15, vercel-labs/agent-skills 2026-10-26, redis/agent-skills 2026-09-08, addyosmani/web-quality-skills 2026-08-24, anthropics/claude-plugins-official 2026-10-26.

## Q1. Skill format: SKILL.md location and structure, frontmatter fields, naming rules, descriptions

### Takeaway
A skill is a directory with a `SKILL.md`: YAML frontmatter followed by a Markdown body. The open standard defines exactly six frontmatter fields (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`). Claude Code accepts many more fields, but claude.ai uploads, the Skills API and `package_skill.py` reject any field outside those six with a hard error. A master caching skill meant for every surface should therefore use only the six spec fields. Claude Code-only behaviour belongs in a separate plugin variant. The `description` (max 1,024 chars per spec/API) is the only thing Claude sees before triggering, so it must state both what the skill does and when to use it, with domain keywords.

### Cited Findings
**Spec (Agent Skills open standard):**
- Directory layout: `skill-name/SKILL.md` (required), plus optional `scripts/`, `references/`, `assets/`, and "any additional files or directories". — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx) (published at https://agentskills.io/specification)
- `name` rules: required, 1–64 chars, only lowercase `a-z`, `0-9` and `-`, must not start or end with `-`, no consecutive hyphens (`--`), and **it must match the parent directory name**. — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)
- `description` rules: required, 1–1024 chars. It "Should describe both what the skill does and when to use it" and "Should include specific keywords that help agents identify relevant tasks." — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)
- `license` is optional and short (a license name or a bundled file, e.g. `Proprietary. LICENSE.txt has complete terms`). `compatibility` is optional, 1–500 chars, and records environment requirements, e.g. "Requires git, docker, jq, and access to the internet". The spec adds that "Most skills do not need" it. `metadata` is an optional string→string map with "reasonably unique" keys (e.g. `author`, `version: "1.0"`). `allowed-tools` is an optional, space-separated, "Experimental" field whose support varies by agent (e.g. `Bash(git:*) Bash(jq:*) Read`). — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)
- The body has no format restrictions. Recommended content is step-by-step instructions, input/output examples and edge cases. "the agent will load this entire file once it's decided to activate a skill." — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)
- Validation: `skills-ref validate ./my-skill` checks frontmatter and naming. — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)

**Anthropic platform (API / claude.ai) rules:**
- `name`: max 64 chars, lowercase letters/numbers/hyphens only, no XML tags, and it cannot contain the reserved words "anthropic" or "claude". `description`: non-empty, max 1,024 chars, no XML tags. — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview); [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- The Skills API upload also accepts an optional `display_name` of up to 255 chars, which need not be unique. — [Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- Anthropic's skill-creator validator hard-codes `ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}` and fails on any other key. — [quick_validate.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/quick_validate.py)
- "Outside Claude Code (claude.ai uploads, the Skills API, `package_skill.py`), any other field, such as `argument-hint`, causes a hard error at packaging or upload. Claude Code accepts all fields, so spec-compliant frontmatter loads unchanged." — [Claude Code skills docs](https://code.claude.com/docs/en/skills)

**Claude Code frontmatter (Claude Code only unless noted):**
- In Claude Code every field is optional and only `description` is recommended. `name` defaults to the directory name. Unrecognized fields are silently ignored. If the YAML fails to parse, the skill still loads with no fields set. Frontmatter is read only when the opening `---` is the file's first line. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Fields Claude Code supports:
  - `name`, `description`
  - `when_to_use`: extra trigger text, appended to the description
  - `argument-hint`, e.g. `[issue-number]`
  - `arguments`: named positional args for `$name`
  - `disable-model-invocation` (default false): when true, only the user can invoke the skill, and it is not preloaded into subagents
  - `user-invocable` (default true): false hides the skill from the `/` menu
  - `allowed-tools`: pre-approves tools for the invoking turn only
  - `disallowed-tools`
  - `model`: override for the rest of the turn, or `inherit`
  - `effort`: `low|medium|high|xhigh|max`
  - `context: fork`: run in a subagent
  - `agent`: subagent type, e.g. `Explore`, `Plan`, `general-purpose` or a custom agent
  - `background` (default true with fork)
  - `hooks`
  - `paths`: glob(s) that limit automatic activation
  - `shell`: `bash|powershell`
  - `metadata`, `license` and `compatibility` (max 500): accepted but not acted on

  — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- In Claude Code's skill listing, `description` + `when_to_use` are truncated at **1,536 characters**, so "Put the key use case first." — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- The listing has a total character budget that "scales at 1% of the model's context window". When it overflows, Claude Code drops descriptions, starting with the skills invoked least. `/doctor` estimates the listing cost and `/skill-doctor` reports per-skill cost and usage. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Claude Code string substitutions:
  - `$ARGUMENTS`, `$ARGUMENTS[N]`/`$N`, `$name`
  - `${CLAUDE_SESSION_ID}`, `${CLAUDE_EFFORT}`, `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}`
  - `${CLAUDE_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_DATA}` (plugin skills only)

  Dynamic context injection (`` !`cmd` `` or a ```` ```! ```` block) runs before Claude sees the skill. A command that fails (non-zero exit, except exit 1 from search commands) aborts the whole invocation. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- `${CLAUDE_SKILL_DIR}` is substituted in both the body and the `allowed-tools` Bash rules. This lets a skill run its own bundled script without a permission prompt, e.g. `allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/render.sh *)`. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Claude Code reserves the folder name `synced` and the `anthropic-skills` namespace. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)

**Naming and descriptions (guidance):**
- The platform guide suggests gerund names (`processing-pdfs`, `analyzing-spreadsheets`). Noun phrases (`pdf-processing`) and action forms (`process-pdfs`) are acceptable. Avoid vague names (`helper`, `utils`), generic ones (`documents`, `data`) and reserved words. — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Descriptions should be in "**Always write in third person**" ("Processes Excel files…", not "I can help you…") "The description is injected into the system prompt". Claude uses it "to choose the right Skill from potentially 100+ available Skills". Good pattern: "Extract text and tables from PDF files, fill forms, merge documents. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction." — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- The agentskills guide recommends "imperative phrasing" ("Use this skill when…"), focusing on user intent rather than implementation, and "Err on the side of being pushy": list contexts where the skill applies "even if they don't explicitly mention" the domain. Keep it to "a few sentences to a short paragraph". — [Optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx). These two sources differ on voice: third-person "Processes…" in the platform guide ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)) versus imperative "Use this skill when…" in the agentskills guide. Both put the "what" first and the "when" second.
- Agents "typically only consult skills for tasks that require knowledge or capabilities beyond what they can handle alone"; simple one-step requests may not trigger even a perfectly matching description. — [Optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx); same point in [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- Real-world large-skill description (Vercel): "Use for Vercel cost and performance optimization on deployed projects, especially Next.js, SvelteKit, Nuxt… Trigger for Vercel bill reduction, slow or expensive routes, caching opportunities, Function Invocations, … Core Web Vitals…". It also carries `metadata: version: "1.2.0"`. — [vercel-optimize SKILL.md](https://github.com/vercel-labs/agent-skills/blob/HEAD/skills/vercel-optimize/SKILL.md)
- Real-world router-skill description (Cloudflare): "Discover and choose Cloudflare products… Use for architecture and product selection, including when the user describes a need without naming a Cloudflare product; then find the relevant skill or documentation." — [cloudflare SKILL.md](https://github.com/cloudflare/skills/blob/HEAD/skills/cloudflare/SKILL.md)

### Inferences
- For portability, the frontmatter should contain only `name`, `description`, `license`, `compatibility` and `metadata` (with `version`, `author`, and perhaps `last-reviewed`). Leave out `allowed-tools`, since it is experimental and handled differently by each agent. Claude Code extras (`when_to_use`, `argument-hint`, `context`, `paths`) would break claude.ai and API uploads, so put them only in a Claude Code plugin variant if they are needed.
- Keep `description` ≤1,024 chars; that limit is binding for the spec and API even though Claude Code allows 1,536. Front-load the "what" plus trigger vocabulary: Cache-Control, CDN, edge cache, Redis/Memcached, ISR/revalidate, `use cache`, stale-while-revalidate, ETag, service worker, query/ORM caching, cache invalidation, slow pages/TTFB, high origin load or bill. Add a "even if the user doesn't say 'cache'" clause (e.g. "site is slow", "reduce database load"), plus a boundary clause that excludes non-HTTP CPU caches and LLM prompt caching if those are out of scope.
- The name must match the directory and avoid "claude"/"anthropic". Candidates: `caching-strategy`, `optimizing-app-caching` (gerund), `app-caching`.

### Gaps
- agentskills.io could not be fetched directly (DNS failure in the sandbox). The spec text comes from its GitHub source, dated 2026-08-09, and the live site may have changed since.
- The Skills API guide page I read did not show which beta headers are required (the examples showed only `anthropic-version: 2023-06-01`). It did not say whether unknown frontmatter fields are rejected at upload; that statement comes from the Claude Code docs instead.

## Q2. Progressive disclosure: loading model, size limits, references/scripts/assets organization, linking

### Takeaway
Skills load in three levels:
1. Name and description, about 100 tokens per skill, always in context.
2. The `SKILL.md` body, under 500 lines and about 5k tokens, loaded when the skill triggers.
3. Bundled files, read or executed on demand at zero cost until accessed.

A large multi-domain skill should therefore be a thin router: workflow, routing table and gotchas in `SKILL.md`, with domain-specific `references/` files linked directly from `SKILL.md`, each with an explicit "read this when…" condition. Deterministic work belongs in `scripts/`, whose code never enters context; only its output does.

### Cited Findings
- Loading levels: Level 1 metadata is "Always (at startup)" at "~100 tokens per Skill". Level 2 is the `SKILL.md` body "When Skill is triggered", "Under 5k tokens". Level 3+ is resources "As needed", costing "None until accessed… Scripts run through bash, and only their output enters context." — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- "No practical limit on bundled content: Files don't consume context until accessed, so Skills can include comprehensive API documentation, large datasets, or extensive examples." — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- The spec gives metadata at about 100 tokens and instructions at "< 5000 tokens recommended", and says "Keep your main `SKILL.md` under 500 lines". — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx); "Keep the `SKILL.md` body under 500 lines for optimal performance" — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- skill-creator describes the metadata as "~100 words" (not tokens) and calls the counts "approximate… feel free to go longer if needed". If a skill approaches 500 lines, "add an additional layer of hierarchy along with clear pointers about where the model using the skill should go next". — [skill-creator SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- **Keep references one level deep.** "Claude might partially read files when they're referenced from other referenced files… might use commands such as `head -100` to preview… Keep references one level deep from `SKILL.md`. All reference files should link directly from `SKILL.md`." — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); the spec says the same ("Avoid deeply nested reference chains") — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx)
- Table-of-contents thresholds differ. The platform guide says to add one to reference files over **100 lines** "so Claude can see the full scope… even when previewing with partial reads" ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). skill-creator says "For large reference files (>300 lines), include a table of contents" ([skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)).
- Pattern 2, domain-specific organization: `bigquery-skill/SKILL.md` plus `reference/finance.md`, `sales.md`, `product.md`, `marketing.md`. "When a user asks about sales metrics, Claude only needs to read sales-related schemas". It also suggests grep for quick search (`grep -i "revenue" reference/finance.md`). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Variant organization: "When a skill supports multiple domains/frameworks, organize by variant: `cloud-deploy/SKILL.md (workflow + selection)`, `references/aws.md`, `gcp.md`, `azure.md`… Claude reads only the relevant reference file." — [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- Telling the agent *when* to load a file matters. "Read `references/api-errors.md` if the API returns a non-200 status code" works better than "see references/ for details." — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Directory roles: `scripts/` holds executable code ("run, not loaded"), `references/` holds docs loaded as needed ("Keep individual reference files focused… smaller files mean less use of context"), and `assets/` holds templates, images and data files such as lookup tables and schemas. — [Agent Skills spec](https://github.com/agentskills/agentskills/blob/HEAD/docs/specification.mdx); skill-creator describes assets as "Files used in output (templates, icons, fonts)" — [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- Paths are relative to the skill root, use forward slashes, and have descriptive names (`form_validation_rules.md`, not `doc2.md`). Organize by domain (`reference/finance.md`, not `docs/file1.md`). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices); "script execution paths (in code blocks) are relative to the skill directory root" even inside `references/*.md` — [Using scripts](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/using-scripts.mdx)
- Make the intent clear: "Run `analyze_form.py` to extract fields" (execute) versus "See `analyze_form.py` for the algorithm" (read). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Claude Code context lifecycle:
  - The rendered `SKILL.md` "enters the conversation as a single message and stays there across later turns". Claude Code "does not re-read the skill file on later turns, so write guidance that should apply throughout a task as standing instructions rather than one-time steps".
  - After compaction it re-attaches the most recent invocation of each skill, "keeping the first 5,000 tokens of each", within "a combined budget of 25,000 tokens", so "put the most important instructions near the top of `SKILL.md`".

  — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Real large multi-domain example: Cloudflare's umbrella `cloudflare` skill has a 151-line `SKILL.md` and 139 files in its directory. Its bundled `references/<product>/README.md` folders cover ai-gateway, d1, kv, r2, queues, workflows, waf, static-assets and others. The `SKILL.md` routes through a "What you need to do | Product | When to choose it | Skill or reference" table and tells the agent: "Read the linked reference or docs before implementing; load named skills when installed." — [cloudflare/skills](https://github.com/cloudflare/skills/blob/HEAD/skills/cloudflare/SKILL.md) (structure observed in clone)
- Real script-heavy pipeline example: Vercel's `vercel-optimize` has a 322-line `SKILL.md`, 15 `.mjs` scripts (collect-signals, scan-codebase, gate-investigations, verify-finding, check-citations, render-report…) and `references/` (doctrine, playbooks, scoring, verification, docs-library.json). Its rule is "Do not inspect source files until `signals.json` exists and a deterministic gate points to a route, file, or project setting." — [vercel-optimize](https://github.com/vercel-labs/agent-skills/tree/HEAD/skills/vercel-optimize)

### Inferences
- "One level deep" constrains link chains (SKILL.md → file), not folder depth. Pattern 2 and Cloudflare both use subfolders such as `references/frameworks/nextjs.md`. With 40+ reference files, linking each individually from `SKILL.md` could exceed the budget. A compact routing table (detected signal → file) linked directly from `SKILL.md` stays one hop. Do not create a chain where a `references/index.md` points to further files.
- Keep cross-cutting must-knows inside `SKILL.md` and near the top, because only the first 5k tokens survive compaction in Claude Code. These are the workflow checklist, the "never cache personalized/authenticated responses publicly" rule, Vary/cache-key and poisoning gotchas, and the plan template pointer.
- Stack detection should be a script in `scripts/` that emits JSON, not prose instructions. That saves tokens and makes routing deterministic.

### Recommended directory tree for the master caching skill (inference, built from the cited patterns)
```
caching-strategy/                      # name must equal dir name; no "claude"/"anthropic"
├── SKILL.md                           # ≤500 lines / ≲5k tokens; critical rules in first ~5k tokens
│                                      #  1) checklist workflow  2) run detect script  3) routing table
│                                      #  4) cross-layer gotchas  5) plan template pointer  6) verify loop
├── LICENSE.txt
├── references/                        # each file linked DIRECTLY from SKILL.md routing table; TOC if >100 lines
│   ├── http-caching-fundamentals.md   # Cache-Control, Vary, ETag/Last-Modified, SWR/SIE, heuristics
│   ├── invalidation-and-keys.md       # tags/surrogate keys, purge, versioned URLs, key design
│   ├── cache-security.md              # poisoning, deception, private data, auth/cookies, Vary
│   ├── layers/
│   │   ├── browser-and-service-worker.md
│   │   ├── cdn-generic.md             # shared-cache semantics, s-maxage, surrogate-control
│   │   ├── reverse-proxy.md           # nginx, Varnish, HAProxy
│   │   ├── app-in-memory.md           # LRU, memoization, request coalescing
│   │   ├── distributed-cache.md       # Redis/Valkey/Memcached patterns, stampede protection
│   │   ├── database-and-orm.md        # query caches, materialized views, read replicas
│   │   └── build-and-ci-cache.md      # Turborepo/Nx/Docker layer/CI caches
│   ├── frameworks/                    # read ONLY the one(s) detect_stack.py reports
│   │   ├── nextjs.md  nuxt.md  sveltekit.md  remix-react-router.md  astro.md
│   │   ├── rails.md  django.md  laravel.md  spring.md  express-fastify.md  go.md  dotnet.md
│   └── platforms/
│       ├── vercel.md  cloudflare.md  netlify.md  aws-cloudfront.md  fastly.md  akamai.md
├── scripts/                           # executed, not loaded; stdlib-only for API sandbox (no network)
│   ├── detect_stack.py                # --help; JSON to stdout, diagnostics to stderr; no prompts
│   ├── audit_headers.py               # optional live check (needs network → Claude Code/claude.ai only)
│   └── validate_plan.py               # plan-validate-execute gate against assets/plan.schema.json
├── assets/
│   ├── caching-plan.template.md       # strict output template for the app-specific plan
│   ├── plan.schema.json
│   └── snippets/                      # config templates (nginx, vercel.json, _headers, next.config…)
└── evals/                             # excluded from .skill packages by package_skill.py (root "evals")
    ├── evals.json                     # skill-creator / agentskills output-quality format
    ├── trigger_queries.json           # ~20 should/should-not-trigger queries
    └── files/                         # fixture repos (Next.js app, Django app, Rails app, …)
```
A Claude Code plugin wrapper, if used, adds `.claude-plugin/plugin.json` and `skills/caching-strategy/…`, plus `evals/<case>/prompt.md` and `graders/*.md` for `claude plugin eval`. The plugin-eval format is not interchangeable with `evals/evals.json`.

### Gaps
- There is no official numeric cap on the number or size of reference files beyond the 30 MB API upload limit (see Q5). I found no guidance on how many entries a routing table can hold before Claude navigates it poorly. This needs empirical testing.

## Q3. Writing guidance: degrees of freedom, checklists, feedback loops, conditional workflows, time-sensitivity, terminology, examples, anti-patterns

### Takeaway
Write only what Claude doesn't already know. Pick defaults rather than offering menus. Match prescriptiveness to fragility: give freedom for analysis, use exact scripts for fragile steps. Structure multi-step work as copyable checklists with validation loops or plan-validate-execute. Branch with explicit conditionals ("If X → read Y"). Keep gotchas inline, isolate version-specific content in "old patterns" sections, and use consistent terms.

### Cited Findings
- "**Default assumption:** Claude is already very smart. Only add context Claude doesn't already have." Ask "Does this paragraph justify its token cost?" — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices). For each item, ask "Would the agent get this wrong without this instruction? If the answer is no, cut it." — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Degrees of freedom:
  - High (text heuristics) when multiple approaches are valid.
  - Medium (pseudocode or parameterized scripts) when a preferred pattern exists.
  - Low ("Run exactly this script… Do not modify the command") when operations are fragile or sequence-critical.
  - The analogy is a "narrow bridge with cliffs" versus an "open field".

  — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices). "Most skills have a mix. Calibrate each part independently." — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- "Provide defaults, not menus": pick one default and give an escape hatch. — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx); "Avoid offering too many options" — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- "Favor procedures over declarations": teach how to approach a class of problems, not the answer to one instance. — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- "Aim for moderate detail": "Overly comprehensive skills can hurt more than they help — the agent struggles to extract what's relevant and may pursue unproductive paths triggered by instructions that don't apply to the current task." — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- On scope, "Skills scoped too narrowly force multiple skills to load for a single task… Skills scoped too broadly become hard to activate precisely." — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Gotchas sections are "The highest-value content in many skills": concrete environment facts that defy reasonable assumptions. "Keep gotchas in `SKILL.md` where the agent reads them before encountering the situation." When the agent makes a mistake you have to correct, add it to the gotchas. — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Checklists: "provide a checklist that Claude can copy into its response and check off as it progresses" (e.g. `- [ ] Step 1: Analyze the form (run analyze_form.py)`). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Feedback loops ("Run validator → fix errors → repeat") "greatly improves output quality". A reference doc such as STYLE_GUIDE.md can serve as the validator. — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Plan-validate-execute: "analyze → **create plan file** → **validate plan** → execute → verify". Use it for "Batch operations, destructive changes, complex validation rules, high-stakes operations". Validators should give verbose errors ("Field 'signature_date' not found. Available fields: …"). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Conditional workflow pattern: "**Creating new content?** → Follow 'Creation workflow'… **Editing existing content?** → …". "If workflows become large… push them into separate files and tell Claude to read the appropriate file based on the current task." — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Time-sensitive info: avoid "If you're doing this before August 2025, use the old API". Instead give a "Current method" section plus an "Old patterns" `<details>` block ("Legacy v1 API (deprecated 2025-08)"). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Consistent terminology: always "API endpoint", never a mix of "URL/API route/path". — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Templates: strict ("ALWAYS use this exact template") or flexible ("sensible default… use your best judgment"). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices). Longer templates "store them in `assets/`… so they only load when needed". — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Examples pattern: input/output pairs "convey the desired style and level of detail… more clearly than descriptions alone". — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Scripts:
  - "Solve, don't defer": handle errors in the script.
  - No "voodoo constants": justify every value.
  - Prefer pre-made utility scripts, which are more reliable, save tokens and stay consistent.
  - List required packages.
  - Use fully qualified MCP tool names (`ServerName:tool_name`).
  - Use forward-slash paths.

  — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Agentic script design:
  - "Avoid interactive prompts… a hard requirement".
  - Document `--help`.
  - Write errors that say what was expected and what to try.
  - "Prefer structured formats — JSON, CSV, TSV".
  - "send structured data to stdout and progress messages… to stderr".
  - Pin versions (`npx eslint@9.0.0`), use inline deps (PEP 723 with `uv run`), and state prerequisites via `compatibility`.

  — [Using scripts](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/using-scripts.mdx)
- Writing style in skill-creator: "Prefer using the imperative form", and "explain to the model why things are important in lieu of heavy-handed musty MUSTs". — [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md). The platform guide's iteration example instead suggests stronger language ("MUST filter" instead of "always filter") when a rule is missed ([Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)). Read together: explain why by default, and escalate emphasis only where evals show a rule being skipped.
- Start from real expertise. Generic LLM-written skills yield vague procedures. Synthesize from runbooks, incident reports, code review comments and VCS fixes. — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Version drift in caching docs is an observed problem. Vercel moved Next.js agent skills into the Next.js repo "so they stay version-matched with the framework instead of drifting in a separate repo". Reference knowledge now ships as bundled docs (`next/dist/docs/`) and the `AGENTS.md`/`CLAUDE.md` that `next dev` generates (Next.js 16.3+). For older versions, `npx @next/codemod@canary agents-md` pulls the docs into `.next-docs/`. — [vercel-labs/next-skills README](https://github.com/vercel-labs/next-skills)

### Inferences
- Caching semantics change between framework versions; Next.js caching defaults and APIs changed across major versions, which is why Vercel version-locked its skills. The skill should therefore run a version-detection step first. Each `frameworks/*.md` should give a "current method" keyed to version ranges, put superseded APIs in an "old patterns" `<details>` block, and tell Claude to prefer project-bundled docs (`node_modules/next/dist/docs/`, `.next-docs/`) when present over the skill's own text.
- Suggested SKILL.md workflow checklist:
  1. Run `scripts/detect_stack.py`, which outputs JSON with framework+version, hosting/CDN, data stores and existing cache config.
  2. Read only the matching `references/frameworks/*` and `platforms/*` files.
  3. Inventory routes and data by cacheability class (public static, public dynamic, per-user, real-time).
  4. Draft the plan from `assets/caching-plan.template.md`, written as a JSON plus Markdown plan file.
  5. Run `validate_plan.py` (plan-validate-execute).
  6. Implement.
  7. Verify headers and behaviour by checking response headers, running tests and confirming no private data is cached.
  8. Report.
- Use high freedom for analysis and trade-offs and low freedom for security-critical rules: auth'd responses must be `private`/`no-store`, keep Set-Cookie off shared caches, and include `Vary` correctness.
- Pick one glossary and use it throughout, e.g. "shared cache" (CDN/proxy) versus "private cache" (browser), "TTL", "revalidation", "invalidation/purge", "cache key".

### Gaps
- I found no official guidance on how a single skill should handle multiple detected stacks at once, such as a monorepo with Next.js plus Django. This is an authoring decision to test with evals.

## Q4. Evaluation and iteration: evaluation-driven development, multi-model testing, skill-creator, `claude plugin eval`

### Takeaway
Anthropic recommends building evaluations before writing much skill content. Measure a no-skill baseline, write the minimal instructions that close observed gaps, and iterate with a Claude A (author) / Claude B (user) loop, testing on Haiku, Sonnet and Opus. Three tools exist:
- the agentskills/skill-creator `evals/evals.json` workflow, which compares with-skill against without-skill and grades assertions;
- skill-creator's automated description-trigger optimizer, which uses train/validation splits;
- Claude Code's `claude plugin eval`, which gives CI-gateable, baseline-compared plugin evals.

The `claude plugin eval` file format differs from `evals/evals.json`.

### Cited Findings
- Evaluation-driven development:
  1. Identify gaps by running Claude on representative tasks without the skill.
  2. Build three scenarios.
  3. Establish a baseline.
  4. Write minimal instructions.
  5. Iterate.

  Example eval JSON: `{"skills": ["pdf-processing"], "query": "...", "files": ["test-files/document.pdf"], "expected_behavior": ["...", "..."]}`. The guide notes "There is not currently a built-in way to run these evaluations." — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices). The Claude Code `claude plugin eval` command described below now provides a runner for skills shipped in plugins ([Plugin evals](https://code.claude.com/docs/en/plugin-evals)).
- Test across models. For Haiku, ask "Does the Skill provide enough guidance?"; for Sonnet, "Is the Skill clear and efficient?"; for Opus, "Does the Skill avoid over-explaining?". The checklist asks for "At least three evaluations created" and "Tested with Haiku, Sonnet, and Opus". — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Claude A/Claude B iteration. Watch for unexpected exploration paths, missed connections, overreliance on one file (it may belong in SKILL.md) and ignored files (they may be unnecessary or poorly signaled). — [Best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- "Read agent execution traces, not just final outputs." Wasted steps usually point to vague instructions, inapplicable instructions or too many options. — [agentskills best practices](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/best-practices.mdx)
- Output-quality eval format:
  - Cases go in `evals/evals.json` as `{ "skill_name", "evals": [{ "id", "prompt", "expected_output", "files", "assertions": [...] }] }`.
  - Start with 2–3 cases, vary the phrasing and include an edge case. Add assertions after the first run.
  - The workspace is `<skill>-workspace/iteration-N/eval-<name>/{with_skill,without_skill}/{outputs/,timing.json,grading.json}` plus `benchmark.json`. When improving an existing skill, the baseline is `old_skill/` (a snapshot).
  - Grading requires "concrete evidence for a PASS". Use scripts for mechanical checks and blind LLM comparison for holistic quality.
  - `timing.json` records `total_tokens` and `duration_ms`.

  — [Evaluating skills](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/evaluating-skills.mdx)
- Trigger-eval method:
  - About 20 queries: 8–10 should-trigger and 8–10 should-not-trigger, with "near-misses" as the most valuable negatives.
  - Run each query 3 times and compute a trigger rate; a 0.5 threshold is the default.
  - Split about 60% train / 40% validation and keep the split fixed. "Avoid adding specific keywords from failed queries — that's overfitting". About five iterations, choosing the best by validation pass rate.
  - Sample detector: `claude -p "$query" --output-format json | jq … .type == "tool_use" and .name == "Skill" and .input.skill == $skill`.

  — [Optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx)
- skill-creator automates this loop "end-to-end: it splits the eval set, evaluates trigger rates in parallel, proposes description improvements using Claude, and generates a live HTML report". — [Optimizing descriptions](https://github.com/agentskills/agentskills/blob/HEAD/docs/skill-creation/optimizing-descriptions.mdx). Its repo contains `scripts/run_eval.py`, `run_loop.py`, `improve_description.py`, `aggregate_benchmark.py`, `package_skill.py`, `quick_validate.py`, `agents/grader.md`, `comparator.md`, `analyzer.md` and `eval-viewer/`. — [skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator)
- In Claude Code, install it with `/plugin install skill-creator@claude-plugins-official` (add the marketplace first with `/plugin marketplace add anthropics/claude-plugins-official` if needed). Then ask, e.g., "evaluate my summarize-changes skill with skill-creator". — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- `claude plugin eval` basics:
  - It "runs your plugin against a suite of test cases and scores the results".
  - `claude plugin eval init` interviews you and writes cases and graders; `--bare <case>` writes a blank template instead.
  - A suite lives in `evals/` inside the plugin. Each case is a directory with `prompt.md` (frontmatter such as `max_turns`, `allowed_tools`, `timeout_seconds`, `model`, `tags`), `graders/*.md` and an optional `case.yaml` (`schema_version: "1.1"`, `name`, `context.*`, e.g. `history_file`).
  - "each case runs three times by default"; a case's score is the mean across runs.
  - The command also runs a no-plugin baseline and reports `WITH`, `W/OUT`, `Δ` and `COST`.

  — [Plugin evals](https://code.claude.com/docs/en/plugin-evals)
- `claude plugin eval` grader types:
  - `regex` (`pattern`, `flags`, `match: not_contains|count:N`, `target`)
  - `tool_used` (`tool`, `input_match`, `min`, `max`)
  - `tool_order`
  - `file_exists`
  - `llm` (a judge votes PASS in at least 2 of 3)
  - `baseline` (compared against a reference `.jsonl` transcript)

  "There are no custom-code graders." A `tool_used` grader on `Skill` is excluded from the without-arm score. Set `arm: both` to get a "must not invoke the skill" check. — [Plugin evals](https://code.claude.com/docs/en/plugin-evals)
- `claude plugin eval` CLI and CI:
  - Flags: `--threshold <0..1>` (default `1.0`; any case below it makes the command exit 1), `--model` (pin it in CI), `--judge-model sonnet`, `--runs`, `--case`, `--ablation none` (single arm, half the cost), `--json`, `--trust-plugin` (skips the first-run trust prompt in CI) and `--eval-dir`. The eval directory can also be set with `"experimental": {"evals": "quality/evals"}` in plugin.json.
  - Runs are isolated, fresh, non-interactive sessions with only the plugin loaded. They allow only the read-only tools listed in `allowed_tools`.
  - Recommendation: grade long outputs with regex and short outputs with LLM rubrics, and pair a result grader with a process grader (`tool_used`/`tool_order`).
  - "The most common first finding is a `Δ` near zero with the case's `tool_used: Skill` grader failing", meaning the description doesn't trigger.

  — [Plugin evals](https://code.claude.com/docs/en/plugin-evals)
- The skill-creator `evals/evals.json` format and `claude plugin eval` "aren't interchangeable". — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- `claude plugin validate .claude/skills` (v2.1.233+) finds `SKILL.md` files whose frontmatter doesn't parse. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Real eval example: Vercel ships a `packages/vercel-optimize-tests/` package and `packages/react-best-practices-build/test-cases.json` alongside its skills. — [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) (observed in clone)

### Inferences
- For the master caching skill:
  - Trigger evals: about 20 queries with near-miss negatives, e.g. "clear my npm cache", "explain CPU L1 cache", "Anthropic prompt caching" (unless in scope), and "my browser shows an old version of the page" (possibly a positive).
  - Output evals: one fixture repo per major stack (Next.js on Vercel, Django+Redis, Rails+CloudFront, SPA+Cloudflare, Express+nginx). Use assertions that can be checked by regex or script: correct `Cache-Control` per route class, no `public` on authenticated routes, invalidation hooked to writes, and a plan file that validates against the schema.
  - If shipped as a Claude Code plugin, pair `tool_used: Skill` graders with a `tool_used` grader whose `input_match` is `detect_stack` to confirm the routing step ran.
- Test on Haiku as well. A large router skill depends on the model following "read only the matching file", and weaker models may over-read or under-read.

### Gaps
- I found no official, cross-surface eval runner for claude.ai or API-uploaded skills. Outside Claude Code plugins, you script it yourself or use skill-creator.

## Q5. Distribution: Claude Code locations, plugins and marketplaces, claude.ai upload, API Skills, the open standard and cross-agent compatibility, versioning

### Takeaway
Skills do not sync across surfaces. Claude Code uses the filesystem (`~/.claude/skills`, `.claude/skills`, plugins via marketplaces), claude.ai takes per-user zip uploads, and the API uses workspace-wide `/v1/skills` uploads with versioned snapshots. A Claude Code plugin marketplace is a git repo with `.claude-plugin/marketplace.json`. The same spec-compliant `SKILL.md` folder is read by about 46 other agent clients via the Agent Skills standard, and the `npx skills add` CLI is a common cross-agent installer.

### Cited Findings
**Claude Code:**
- Skill locations:
  - Enterprise (managed settings dir)
  - Personal: `~/.claude/skills/<name>/SKILL.md`
  - Project: `.claude/skills/<name>/SKILL.md`
  - Nested: `<subdir>/.claude/skills/`, loaded on demand when Claude touches files there
  - `--add-dir` directories
  - Plugin: `<plugin>/skills/<name>/SKILL.md`, invoked as `/plugin-name:skill-name`
  - claude.ai account sync to `~/.claude/skills/synced/`

  Precedence is enterprise > personal > project. Plugin skills are namespaced, so they coexist with local skills of the same name. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- The pre-built document skills (pptx/xlsx/docx/pdf) are not available in Claude Code. The open-source Claude API skill is bundled with it. — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Marketplace basics: "A plugin marketplace is a directory or repository with a `.claude-plugin/marketplace.json`". It requires `name`, `owner` and a `plugins` array, and each entry needs `name` and `source`. Example:

  ```json
  {"name":"my-marketplace","description":"Plugins for my team","owner":{"name":"Your Name"},"plugins":[{"name":"my-first-plugin","source":"./plugins/my-first-plugin","description":"…"}]}
  ```

  — [Create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- Marketplace sources and rules:
  - Source types: a relative path (written from the marketplace root, `..` not allowed), `github` (`{"source":"github","repo":"org/repo"}`), `git-subdir` (`{"source":"git-subdir","url":"org/monorepo","path":"tools/x"}`), `url`, `archive` (HTTPS zip), `npm` and `command`. Git sources can be pinned with `ref`/`sha`.
  - Keep the entry `name` equal to the `name` in `plugin.json`.
  - Reserved official names such as `claude-plugins-official` are refused.

  — [Create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- Marketplace workflow:
  - Validate with `claude plugin validate ./my-marketplace`.
  - Install with `claude plugin marketplace add <owner>/<repo>` (or a URL or local path), then `claude plugin install <plugin>@<marketplace>`.
  - In-session equivalents are `/plugin marketplace add …` and `/plugin install …`. Local relative-path plugins pick up edits at the next session start or after `/reload-plugins` "with no change to the plugin's `version`". Hosted installs get a copy in the plugin cache.

  — [Create a marketplace](https://code.claude.com/docs/en/plugin-marketplaces)
- Example `plugin.json` (Cloudflare): `{"name":"cloudflare","description":"…","version":"1.0.2","mcpServers":"./.mcp.json","author":{…},"homepage":…,"repository":"https://github.com/cloudflare/skills","license":"Apache-2.0","keywords":[…]}`. Its marketplace.json uses `"$schema": "https://code.claude.com/schemas/marketplace.json"`. — [cloudflare/skills .claude-plugin](https://github.com/cloudflare/skills/tree/HEAD/.claude-plugin)
- Anthropic's own marketplace lists plugin entries with `"source": "./"`, `"strict": false` and a `"skills": ["./skills/xlsx", …]` array. That lets one repo expose groups of skill folders as plugins without a per-plugin `plugin.json`. — [anthropics/skills marketplace.json](https://github.com/anthropics/skills/blob/main/.claude-plugin/marketplace.json)
- Plugin skills can reference `${CLAUDE_PLUGIN_ROOT}` (the install dir) and `${CLAUDE_PLUGIN_DATA}` (a persistent data dir that "survives plugin updates", for installed dependencies and caches). — [Claude Code skills docs](https://code.claude.com/docs/en/skills)

**claude.ai:**
- Upload as a zip via Settings > Features. Available on Pro, Max, Team and Enterprise with code execution enabled. Uploads are "individual to each user… not shared organization-wide and cannot be centrally managed by admins." — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- skill-creator's `package_skill.py` creates a distributable `.skill` (zip) file. It excludes `__pycache__`, `node_modules`, `*.pyc`, `.DS_Store` and a root-level `evals/` dir. — [package_skill.py](https://github.com/anthropics/skills/blob/main/skills/skill-creator/scripts/package_skill.py)

**API (`/v1/skills`):**
- API Skills run in the code execution tool container (`code_execution_20250825`). Use `container.skills: [{"type":"anthropic"|"custom","skill_id":…,"version":"latest"|…}]`, with "up to 20 Skills for each request". Anthropic skill IDs are `pptx`, `xlsx`, `docx` and `pdf`, with date versions such as `20251013`. Custom skill IDs look like `skill_01…`, with versions `skver_01…` or `latest`. — [Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- Upload with `POST /v1/skills` (multipart `files[]`). `SKILL.md` must be at the upload root or the top of a single enclosing folder. "Total upload size must be under 30 MB (uncompressed)". — [Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- Versions come from `POST /v1/skills/{id}/versions`. Each is "a complete snapshot, not a delta". The `name` must match the existing skill. Skills are mounted at `/skills/{skill-name}/`. — [Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)
- API custom skills are "accessible to your entire workspace"; use one workspace per tenant for isolation. — [Skills API guide](https://platform.claude.com/docs/en/build-with-claude/skills-guide)

**Cross-surface:**
- "Custom Skills do not sync across surfaces." Upload separately to claude.ai and the API. Claude Code is filesystem-based and separate from both. — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Runtime per surface:
  - claude.ai: "Varying network access".
  - API: "No network access" and "No runtime package installation"; only pre-installed packages.
  - Claude Code: "Full network access"; "Global package installation discouraged".

  — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Claude Platform on AWS and Microsoft Foundry (Hosted on Anthropic deployment) behave like the API for skills. Uploads go through the Skills API. Foundry does not support the version-download endpoint. — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Through the Agent SDK or `claude -p`, Claude Code loads only the first skill named at the start of a prompt. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)

**Open standard and other agents:**
- Claude Code "skills follow the Agent Skills open standard, which works across multiple AI tools", and extends it with invocation control, subagent execution and dynamic context injection. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- The agentskills client showcase lists about 46 clients, including Claude Code, Claude, ChatGPT & Codex, Cursor, GitHub Copilot, VS Code, Gemini CLI, OpenCode, OpenHands, Goose, Amp, Roo Code, Kiro, Junie, Factory, TRAE, Tabnine, Qodo, Letta, Spring AI, Mistral AI Vibe, Snowflake Cortex Code, Databricks Genie Code, Laravel Boost, Pulumi Neo and others. — [agentskills clients](https://github.com/agentskills/agentskills/blob/HEAD/docs/snippets/clients.jsx) (published at agentskills.io/clients)
- Cross-agent install CLI: `npx skills add vercel/next.js` or `npx skills add vercel/next.js --skill next-cache-components-optimizer`. — [vercel-labs/next-skills README](https://github.com/vercel-labs/next-skills). Supabase's MCP server instructions also point to `npx skills add supabase/agent-skills` (Supabase MCP server instructions, observed in-session; corroborated by the URL it cites, https://supabase.com/docs/guides/getting-started/ai-skills.md, which I did not fetch).
- Versioning conventions observed:
  - `metadata.version` in SKILL.md: Redis `"0.1.0"`/`"1.0.0"` ([redis/agent-skills](https://github.com/redis/agent-skills)); Vercel `"1.2.0"` ([vercel-optimize](https://github.com/vercel-labs/agent-skills/blob/HEAD/skills/vercel-optimize/SKILL.md)).
  - A side-car `metadata.json` (`version`, `organization`, `date`, `abstract`, `references`) in Vercel's skills ([vercel-optimize metadata.json](https://github.com/vercel-labs/agent-skills/blob/HEAD/skills/vercel-optimize/metadata.json)).
  - `version` in `plugin.json` (Cloudflare `1.0.2`).
- Redis ships the same skills both at `skills/` (for `npx skills`/other agents) and duplicated under `plugins/redis-development/skills/` (for the Claude Code plugin). — [redis/agent-skills](https://github.com/redis/agent-skills) (observed in clone)

### Inferences
- Recommended distribution:
  1. One canonical spec-compliant skill folder in a public repo, installable with `npx skills add <org>/<repo>` and by other agents.
  2. A `.claude-plugin/marketplace.json` in the same repo. Use a `strict: false` + `skills: [...]` entry to avoid duplicating files, unlike Redis's copy approach.
  3. A packaged `.skill`/zip for claude.ai upload and `POST /v1/skills` for API workspaces.
- Version with `metadata.version` (semver string) plus a plugin `version`, and keep a CHANGELOG.
- Because the API sandbox has no network and no package installs, `detect_stack.py` and `validate_plan.py` must be stdlib-only and must not need the internet. Live header auditing (`audit_headers.py`) should be documented as "Claude Code / networked claude.ai only", with a fallback to static config analysis.

### Gaps
- I did not fetch the plugin manifest reference or "Host and maintain a marketplace" pages, so the full `plugin.json` field list and the auto-update and version-resolution semantics for hosted marketplaces are not verified here.
- I did not verify Agent SDK skill loading options (e.g. `settingSources`, `"Skill"` in allowed tools). The relevant page is code.claude.com/docs/en/agent-sdk/skills, linked from the skills docs but not read.
- I did not verify the awesome-lists (e.g. "awesome-claude-skills") or the skills.sh registry contents.

## Q6. Security considerations for skills

### Takeaway
Treat skills like installed software. They can direct tool calls and run code, so audit every bundled file, distrust skills that fetch external URLs at runtime, and grant the least tool access possible. Claude Code-specific risks include project skills self-granting `allowed-tools` without workspace trust and `!` command injection. Admins can mitigate these with `disableSkillShellExecution`, `allowManagedPermissionRulesOnly` and `Skill(...)` permission rules.

### Cited Findings
- "Use Skills only from trusted sources… a malicious Skill can direct Claude to call tools or run code in ways that don't match the Skill's stated purpose." The key considerations are: audit thoroughly (SKILL.md, scripts, images, resources); "Skills that fetch data from external URLs pose particular risk"; tool misuse; data exposure; and "Treat like installing software". — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Claude Enterprise can enable skill content scanning for custom skills uploaded in claude.ai and Cowork. Scanning "doesn't cover Skills uploaded through the Skills API or the Claude Console". — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- Agent Skills are "not covered by ZDR arrangements". — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- `allowed-tools` grants permissions only for the invoking turn and "does not restrict which tools are available". "Workspace trust doesn't gate this field… applies a project skill's `allowed-tools` even in a `-p` run in a folder you've never trusted… review the `allowed-tools` of skills checked into a repository." — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Injected `!` commands "never prompt for permission while the skill renders". They are checked against permission rules, and a deny or non-allow result aborts the invocation outside auto mode. `"disableSkillShellExecution": true` disables injection for user, project, plugin and additional-dir skills. `allowManagedPermissionRulesOnly` (v2.1.282+) makes Claude Code ignore `allowed-tools` in project and personal skills. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- Skill-level permission rules: `Skill(name)` for an exact match and `Skill(name *)` for a prefix match. Deny the Skill tool to disable all skills. — [Claude Code skills docs](https://code.claude.com/docs/en/skills)
- `claude plugin eval` has a first-run trust prompt, bypassed in CI with `--trust-plugin`. — [Plugin evals](https://code.claude.com/docs/en/plugin-evals)
- The "Principle of Lack of Surprise": skills "must not contain malware, exploit code… A skill's contents should not surprise the user in their intent if described." — [skill-creator](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md)
- Claude Code skills should install packages locally, not globally. — [Platform overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)

### Inferences
- For the caching skill:
  - Ship no network-calling scripts by default. Make `audit_headers.py` opt-in, only against URLs the user supplies, read-only (HEAD/GET), with no credential forwarding.
  - Never instruct purging production CDNs without explicit confirmation. Purge is destructive and belongs under plan-validate-execute.
  - Avoid `allowed-tools` in the portable version.
  - Include a `cache-security.md` reference and inline gotchas covering web cache poisoning and deception, caching `Set-Cookie`/authenticated responses in shared caches, and unkeyed headers. Wrong caching changes are a data-leak risk, not just a performance bug.

### Gaps
- I found no official guidance specific to skills that modify CDN or infrastructure config, beyond the general plan-validate-execute advice for "destructive changes".

## Q7. Ecosystem survey: existing caching, web-performance, CDN, Next.js, Redis, Cloudflare and Vercel skills, and the gaps a master caching skill would fill

### Takeaway
Caching guidance exists only in vendor- or layer-specific pieces:
- Next.js Cache Components workflow skills, which Vercel maintains in the next.js repo.
- Vercel's metrics-first `vercel-optimize`.
- Cloudflare's product-router and `web-perf` skills.
- Redis's data-structure, client-side-cache and semantic-cache skills.
- Addy Osmani's generic `performance` skill, with a Cache-Control and service-worker section.
- Several community Next.js caching skills of uneven quality.

None of these detects an arbitrary stack and designs a coordinated, multi-layer caching plan across browser, CDN, proxy, application, distributed cache and database for non-JS frameworks (Rails, Django, Laravel, Spring, Go, .NET) and non-Vercel/Cloudflare CDNs. That cross-layer, stack-aware planning plus implementation and verification is the gap.

### Cited Findings
- **Next.js (official, Vercel):**
  - `vercel/next.js` `skills/` contains `next-cache-components-adoption`, `next-cache-components-optimizer`, `next-partial-prefetching-adoption`, `next-partial-prefetching-optimizer`, `next-bundle-optimizer` and `next-dev-loop`, plus a `.claude-plugin` folder. — [vercel/next.js skills](https://github.com/vercel/next.js/tree/canary/skills)
  - The old `next-cache-components` skill "moved to two workflow skills". `next-best-practices` and `next-upgrade` are no longer skills; their knowledge moved to bundled docs and an auto-generated AGENTS.md/CLAUDE.md (Next.js 16.3+). — [vercel-labs/next-skills README](https://github.com/vercel-labs/next-skills)
  - A Tessl registry listing describes the Vercel `cache-components` skill as covering the `use cache` directive, cache lifetimes, cache tags and invalidation, activating when `cacheComponents: true` is set. Tessl reports a 92% quality-review score. — [Tessl registry](https://tessl.io/registry/skills/github/vercel/next.js/cache-components/review); [Smithery](https://smithery.ai/skills/vercel/cache-components). This is an aggregator summary, not verified against the skill file.
- **Vercel:** `vercel-optimize` (v1.2.0, "May 2026") does cost and performance optimization for Next.js, SvelteKit, Nuxt and limited Astro apps on Vercel. It is "observability-first", collecting Vercel metrics, usage and config before any code inspection, and its triggers include "caching opportunities". It cites a curated docs allow-list and avoids invented URLs and precise dollar projections. — [vercel-optimize SKILL.md](https://github.com/vercel-labs/agent-skills/blob/HEAD/skills/vercel-optimize/SKILL.md); [metadata.json](https://github.com/vercel-labs/agent-skills/blob/HEAD/skills/vercel-optimize/metadata.json)
- **Cloudflare:**
  - `cloudflare/skills` contains about 20 skills: `cloudflare` (umbrella router), `web-perf`, `workers-best-practices`, `wrangler`, `cf-cli`, `durable-objects`, `agents-sdk`, `nextjs-on-cloudflare` (vinext), sandbox skills and others. It is shipped as a Claude Code plugin (v1.0.2) with an MCP server. — [cloudflare/skills](https://github.com/cloudflare/skills)
  - `web-perf` (201 lines) audits Core Web Vitals and Lighthouse and flags "Caching issues: Missing or weak `Cache-Control`, `ETag`, or `Last-Modified` headers". — [web-perf SKILL.md](https://github.com/cloudflare/skills/blob/HEAD/skills/web-perf/SKILL.md)
  - The umbrella skill's bundled reference folders (ai-gateway, kv, r2, d1, hyperdrive, waf, static-assets, workers-ai…) include no dedicated CDN cache-rules or Cache API reference folder (observed in clone). — [cloudflare skill](https://github.com/cloudflare/skills/tree/HEAD/skills/cloudflare)
- **Redis:** `redis/agent-skills` (MIT, `metadata.author: Redis, Inc.`) includes:
  - `redis-core` ("caching objects… session stores", key naming)
  - `redis-connections` ("client-side caching with RESP3", pooling, pipelining, avoiding KEYS/HGETALL)
  - `redis-semantic-cache` (LangCache semantic caching of LLM responses, similarity threshold tuning)
  - `redis-clustering`, `redis-observability` ("hit ratio" metrics), `redis-security`, `redis-search` and `iris-development`

  The official marketplace lists it as plugin `redis-development`: "data structures, query engine, vector search, caching, and performance optimization". — [redis/agent-skills](https://github.com/redis/agent-skills); [claude-plugins-official marketplace](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)
- **Generic web performance:** `addyosmani/web-quality-skills` has `performance` (399 lines, with a "Caching strategy" section). Its recipes: `no-cache, must-revalidate` for HTML, `public, max-age=31536000, immutable` for hashed assets, `stale-while-revalidate`, `private, max-age=0` for user data, plus "Service worker caching". It also has `core-web-vitals`, `web-quality-audit`, `best-practices`, `seo` and `accessibility`. — [web-quality-skills](https://github.com/addyosmani/web-quality-skills)
- **Official Claude Code marketplace:** `anthropics/claude-plugins-official` lists third-party plugins including `cloudflare` ("…Wrangler CLI, and web performance"), `redis-development`, a Chrome DevTools plugin for performance traces and network analysis, CodSpeed (performance testing) and New Relic (APM). I found no plugin dedicated to multi-layer caching in that listing (grep for cache/perf). — [claude-plugins-official marketplace.json](https://github.com/anthropics/claude-plugins-official/blob/main/.claude-plugin/marketplace.json)
- **Community Next.js caching skills** (via aggregator listings):
  - `laguagu` cache-components covers pass-through/interleaving, GET Route Handler caching and `use cache: private`. — [TypingMind listing](https://www.typingmind.com/skills/laguagu-cache-components)
  - `mohamed-hossam1/nextjs-cache-architecture` (Next.js 16+) prescribes a centralized tag registry (`lib/cache/tags.ts`) and revalidation utils. — [skillselion](https://skillselion.com/skills/mohamed-hossam1/nextjs-cache-architecture)
  - `goncy` nextjs-caching. — [agentskills.so](https://agentskills.so/skills/goncy-skills-nextjs-caching)
  - Skillshub nextjs-caching, which still calls `'use cache'` experimental, a sign of version drift. — [openskillindex](https://openskillindex.com/skills/comeonoliver-skillshub-nextjs-caching)
  - `f0rr0/next-cache-components`. — [Smithery](https://smithery.ai/skills/f0rr0/next-cache-components)

  The quality of these community skills is unverified.
- Anthropic's own `anthropics/skills` repo has no caching or web-performance skill. Its skills include skill-creator, claude-api, mcp-builder, webapp-testing, web-artifacts-builder, document skills and others. — [anthropics/skills](https://github.com/anthropics/skills)

### Inferences
- Gaps a master caching skill can fill:
  1. **Stack detection and routing** across frameworks and hosts. Existing skills assume you already know you're on Next.js, Vercel, Cloudflare or Redis.
  2. **Cross-layer coherence.** TTLs, invalidation and cache keys must agree between browser, CDN, app and data caches. Examples: purge or tag propagation on writes, and `s-maxage` versus `max-age` interplay.
  3. **Non-JS frameworks** (Rails, Django, Laravel, Spring, ASP.NET, Go) and **other CDNs/proxies** (CloudFront, Fastly, Akamai, nginx, Varnish), which are absent from the surveyed official skills.
  4. **Cache security** (poisoning, deception, private-data leakage) as first-class gotchas.
  5. **An app-specific plan artifact plus verification loop**, borrowing Vercel's "evidence first, then deterministic gate, then investigate" doctrine.
- The master skill can defer to vendor skills rather than duplicate them: "if `next-cache-components-*` or the `cloudflare` skill is installed, load it for implementation details". Cloudflare already uses this pattern ("load named skills when installed").
- Pick up Vercel's lesson on drift: prefer the project's version-matched framework docs when they exist, and keep the skill's framework files short and focused on cross-layer decisions.

### Gaps
- I could not open the contents of Vercel's `next-cache-components-adoption`/`-optimizer` SKILL.md files; only their names and aggregator summaries were available. Their exact coverage is unverified.
- I did not survey the awesome-claude-skills lists, the skills.sh registry, Netlify, Fastly, Akamai, AWS or Varnish vendor skills, or Cursor rules / AGENTS.md files for caching. Vendor skills may exist for those platforms; I neither found nor ruled them out.
- I did not check whether community caching skills on Smithery, Tessl or TypingMind publish evals.
