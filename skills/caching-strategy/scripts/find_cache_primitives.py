#!/usr/bin/env python3
"""Inventory existing caching code and config in a repository, and flag risky patterns.

Usage:
    python scripts/find_cache_primitives.py <repo_dir> [--max-findings N] [--layer LAYER ...]

Static, line-based scan (regexes, no code execution, no network). Prints one JSON object:

    findings   [{file, line, layer, kind, snippet}]   what caching exists and where
    warnings   [{file, line, rule, severity, message, reference}]   heuristic risks to check by hand
    summary    {by_layer, by_kind, files_with_findings, warnings_by_rule}
    limits     what was skipped or truncated

Layers: http-header, cdn, proxy, framework, app-cache, in-process, distributed, db, client,
service-worker, llm, build. Warnings are heuristics: confirm each one in context before acting.
Warnings skip comment lines and test files; findings include them.

Exit codes: 0 success, 2 bad usage. Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "vendor", "dist", "build", "out", ".next", ".nuxt", ".output",
    ".svelte-kit", ".astro", ".vercel", ".netlify", ".turbo", ".cache", "coverage", "target", "__pycache__",
    ".venv", "venv", ".tox", ".mypy_cache", ".pytest_cache", "Pods", ".gradle", ".idea", ".terraform",
    "bower_components", "tmp", "obj", "_build", "deps", ".dart_tool", "DerivedData", ".expo", "wp-includes",
    "wp-admin", "storage", "public/build",
}
SOURCE_EXT = {
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx", ".vue", ".svelte", ".astro",
    ".py", ".rb", ".erb", ".haml", ".slim", ".php", ".twig", ".java", ".kt", ".kts", ".scala", ".cs", ".fs",
    ".go", ".ex", ".exs", ".heex", ".rs", ".swift", ".dart", ".lua", ".sql",
    ".conf", ".vcl", ".toml", ".yaml", ".yml", ".json", ".jsonc", ".tf", ".hcl", ".xml", ".properties",
    ".ini", ".cfg", ".liquid", ".html", ".sh",
}
SPECIAL_NAMES = {"Caddyfile", "_headers", ".htaccess", "Dockerfile", "nginx.conf", "Procfile", "redis.conf", "varnish.vcl"}
SKIP_FILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "composer.lock", "Gemfile.lock",
              "poetry.lock", "uv.lock", "Cargo.lock", "go.sum", "mix.lock", "pubspec.lock", "packages.lock.json"}
MAX_FILES = 20000
MAX_FILE_BYTES = 512 * 1024
MAX_PER_FILE = 60
DEFAULT_MAX_FINDINGS = 3000

# (regex, layer, kind). Case-sensitive unless the pattern starts with (?i).
PATTERNS: list[tuple[str, str, str]] = [
    # HTTP headers
    (r"(?i)['\"`]cache-control['\"`]|\bCache-Control:", "http-header", "cache-control"),
    (r"(?i)['\"`](cdn-cache-control|vercel-cdn-cache-control|netlify-cdn-cache-control|cloudflare-cdn-cache-control)['\"`]|\b(CDN|Vercel-CDN|Netlify-CDN|Cloudflare-CDN)-Cache-Control:", "http-header", "cdn-targeted-cache-control"),
    (r"(?i)['\"`]surrogate-(control|key)['\"`]|\bSurrogate-(Control|Key):", "http-header", "surrogate-header"),
    (r"(?i)['\"`](cache-tag|netlify-cache-tag|vercel-cache-tag|edge-cache-tag|cdn-tag|xkey)['\"`]", "http-header", "cache-tag-header"),
    (r"(?i)['\"`]etag['\"`]|\.etag\b|setETag|\beTag\(|fresh_when|stale\?\(|@etag|@condition\(|req\.fresh\b", "http-header", "validator"),
    (r"(?i)['\"`]last-modified['\"`]|@last_modified", "http-header", "validator"),
    (r"(?i)['\"`]vary['\"`]|\bVary:|vary_on_(cookie|headers)|SetVaryBy", "http-header", "vary"),
    (r"(?i)['\"`](expires|pragma)['\"`]\s*[,:]", "http-header", "legacy-header"),
    (r"(?i)['\"`]no-vary-search['\"`]|No-Vary-Search:", "http-header", "no-vary-search"),
    (r"\b(cache_control|never_cache|patch_cache_control|add_never_cache_headers)\b\(?", "http-header", "django-cache-control"),
    (r"\b(expires_in|expires_now|http_cache_forever)\b", "http-header", "rails-http-cache"),
    (r"CacheControl\.(maxAge|noCache|noStore|empty|cachePrivate|cachePublic)|ResponseEntity[\s\S]{0,40}cacheControl|ShallowEtagHeaderFilter", "http-header", "spring-cache-control"),
    (r"\[ResponseCache\(|AddResponseCaching|UseResponseCaching", "http-header", "aspnet-response-caching"),
    (r"\bsetHeaders\(\s*\{", "http-header", "sveltekit-setheaders"),
    # Next.js
    (r"['\"]use cache(: (remote|private))?['\"]", "framework", "next-use-cache"),
    (r"\b(cacheLife|cacheTag)\(", "framework", "next-cache-life-tag"),
    (r"\b(revalidateTag|revalidatePath|updateTag|unstable_expireTag|unstable_expirePath)\(", "framework", "next-invalidation"),
    (r"\bunstable_cache\(", "framework", "next-unstable-cache"),
    (r"export\s+const\s+(revalidate|dynamic|fetchCache|dynamicParams)\s*=", "framework", "next-segment-config"),
    (r"cache:\s*['\"](force-cache|no-store)['\"]|next:\s*\{\s*(revalidate|tags)", "framework", "next-fetch-cache"),
    (r"\b(cacheComponents|cacheHandlers?|cacheMaxMemorySize|staleTimes|expireTime|minimumCacheTTL)\s*:", "framework", "next-config"),
    (r"\bgetStaticProps\b|\bres\.revalidate\(", "framework", "next-pages-isr"),
    (r"\bimport\s*\{[^}]*\bcache\b[^}]*\}\s*from\s*['\"]react['\"]", "framework", "react-cache"),
    # Nuxt / Nitro
    (r"\bdefineCached(EventHandler|Function)\(", "framework", "nitro-cached"),
    (r"\brouteRules\s*:", "framework", "route-rules"),
    (r"\b(swr|isr)\s*:\s*(true|\d)", "framework", "route-rule-swr-isr"),
    (r"\buseStorage\(", "app-cache", "nitro-storage"),
    (r"\b(useAsyncData|useFetch)\(", "client", "nuxt-data-fetching"),
    # SvelteKit / React Router / Astro
    (r"export\s+const\s+prerender\s*=", "framework", "prerender"),
    (r"export\s+(function|const)\s+headers\b", "framework", "route-headers-export"),
    (r"\b(clientLoader|shouldRevalidate)\b", "client", "react-router-client-cache"),
    (r"\b(Astro|context)\.cache\.(set|invalidate)|\bcache\.invalidate\(", "framework", "astro-route-cache"),
    # Rails
    (r"\bRails\.cache\.", "app-cache", "rails-cache"),
    (r"<%\s*cache\b|\bcached:\s*true", "framework", "rails-fragment-cache"),
    (r"\bconfig\.cache_store\s*=", "app-cache", "rails-cache-store"),
    (r"\btouch:\s*true", "framework", "rails-touch"),
    (r"\brace_condition_ttl\b", "app-cache", "rails-race-condition-ttl"),
    # Django
    (r"@cache_page\b|cache_page\(", "framework", "django-cache-page"),
    (r"\b(UpdateCacheMiddleware|FetchFromCacheMiddleware|ConditionalGetMiddleware)\b", "framework", "django-cache-middleware"),
    (r"\bCACHES\s*=", "app-cache", "django-caches-setting"),
    (r"\bcache\.(get_or_set|aget_or_set|get_many|set_many|delete_many|touch)\(", "app-cache", "django-low-level"),
    (r"\{%\s*cache\b", "framework", "django-template-fragment"),
    # Laravel / PHP
    (r"\bCache::(remember|rememberForever|flexible|tags|lock|put|get|forget|flush|memo|touch|store)\b", "app-cache", "laravel-cache"),
    (r"\bcache\.headers\b", "http-header", "laravel-cache-headers"),
    (r"\bopcache\.(enable|validate_timestamps|jit|memory_consumption)", "build", "php-opcache"),
    (r"\b(wp_cache_(get|set|delete|add)|(get|set|delete)_transient)\(", "app-cache", "wordpress-cache"),
    (r"define\(\s*['\"]WP_CACHE['\"]", "framework", "wordpress-page-cache"),
    (r"#cache['\"]?\s*\]?\s*=>|Cache::invalidateTags|getCacheTags\(", "framework", "drupal-cacheability"),
    # JVM
    (r"@(Cacheable|CacheEvict|CachePut|Caching|EnableCaching|CacheConfig)\b", "app-cache", "spring-cache"),
    (r"\bspring\.cache\.", "app-cache", "spring-cache-config"),
    (r"@Cache\(\s*usage|use_second_level_cache|use_query_cache", "db", "hibernate-l2"),
    (r"\bCaffeine\.newBuilder\(|caffeine\.spec", "in-process", "caffeine"),
    (r"@(CacheResult|CacheInvalidate|CacheInvalidateAll)\b", "app-cache", "quarkus-micronaut-cache"),
    # .NET
    (r"\b(AddOutputCache|UseOutputCache|CacheOutput|EvictByTagAsync)\b|\[OutputCache", "framework", "aspnet-output-cache"),
    (r"\b(AddHybridCache|HybridCache|RemoveByTagAsync|GetOrCreateAsync)\b", "app-cache", "aspnet-hybridcache"),
    (r"\b(IMemoryCache|AddMemoryCache|MemoryCacheEntryOptions)\b", "in-process", "aspnet-memorycache"),
    (r"\b(IDistributedCache|AddStackExchangeRedisCache|AddStackExchangeRedisOutputCache)\b", "distributed", "aspnet-distributed-cache"),
    (r"\bFusionCache\b", "app-cache", "fusioncache"),
    # Node
    (r"\b(CacheModule|CacheInterceptor|CACHE_MANAGER)\b|@Cache(Key|TTL)\(", "app-cache", "nestjs-cache"),
    (r"\bnew\s+LRUCache\b|\bnew\s+LRU\(|\bnew\s+NodeCache\(|\bnew\s+QuickLRU\(|\bnew\s+TTLCache\(", "in-process", "js-memory-cache"),
    (r"\bapp\.set\(\s*['\"]etag['\"]", "http-header", "express-etag-setting"),
    (r"\bapicache\b", "app-cache", "apicache"),
    (r"\bnew\s+DataLoader\(", "app-cache", "dataloader"),
    (r"\bcreateKeyv\(|\bnew\s+Keyv\(", "distributed", "keyv"),
    # Python
    (r"@(functools\.)?lru_cache\b|@(functools\.)?cache\b|\bcachetools\b|@cached\(", "in-process", "python-memory-cache"),
    (r"@cache\(\s*ttl\s*=|\bcashews\b|\baiocache\b|FastAPICache|@cache\.(cached|memoize)", "app-cache", "python-cache-lib"),
    # Go / Elixir
    (r"\bsingleflight\.Group\b|\.Do(Chan)?\(\s*['\"`]", "app-cache", "go-singleflight"),
    (r"\b(otter|ristretto|groupcache|bigcache|freecache)\.", "in-process", "go-memory-cache"),
    (r"\bCachex\.(fetch|get|put|del|clear)|@decorate\s+(cacheable|cache_evict|cache_put)", "app-cache", "elixir-cache"),
    # Distributed caches
    (r"\bnew\s+(Redis|IORedis|Cluster)\(|\bcreateClient\(|\bredis\.(Redis|StrictRedis|from_url)\(|\bRedis::|\bredis\.NewClient\(|\bRedix\.|ConnectionMultiplexer\.Connect|\bRedis\.fromEnv\(", "distributed", "redis-client"),
    (r"(?i)\b(setex|psetex|getex|mget|mset)\b\(|\.set\([^)\n]*['\"](EX|PX)['\"]|\.set\([^)\n]*\{\s*(EX|PX|ex|px)\s*:", "distributed", "redis-ttl-write"),
    (r"(?i)\bmaxmemory(-policy)?\b", "distributed", "redis-memory-config"),
    (r"(?i)\bclient-side caching|CLIENT TRACKING|clientSideCache|client_cache\s*=", "distributed", "redis-client-side-caching"),
    (r"(?i)\b(memcache[d]?|pymemcache|dalli|memjs)\b", "distributed", "memcached"),
    # Database
    (r"(?i)\bMATERIALIZED\s+VIEW\b", "db", "materialized-view"),
    (r"(?i)\b(pgbouncer|pool_mode|prepared_statements|pgpool)\b", "db", "connection-pooling"),
    (r"(?i)\bquery_cache|cacheStrategy\s*:|\$accelerate|withAccelerate\(", "db", "query-cache"),
    # Reverse proxies
    (r"\b(proxy_cache|fastcgi_cache|uwsgi_cache|scgi_cache)(_path|_key|_valid|_lock|_use_stale|_background_update|_bypass|_revalidate)?\b", "proxy", "nginx-cache"),
    (r"\bproxy_ignore_headers\b|\bproxy_hide_header\b", "proxy", "nginx-header-handling"),
    (r"\bberesp\.(ttl|grace|keep|uncacheable)|\bvcl_(recv|backend_response|hash|deliver|hit)\b|\bxkey\b|\bban\(", "proxy", "varnish-vcl"),
    (r"^\s*(http-request\s+cache-use|http-response\s+cache-store)\b|^\s*cache\s+[\w-]+\s*$|^\s*cache\s*\{\s*$", "proxy", "haproxy-caddy-cache"),
    # CDN / edge
    (r"\bcf:\s*\{[^}]*\b(cacheTtl|cacheEverything|cacheKey|cacheTtlByStatus)|\b(cacheTtl|cacheEverything)\s*:", "cdn", "cloudflare-fetch-cache"),
    (r"\bcaches\.default\b|\bcaches\.open\(|\bcache\.(put|match)\(", "cdn", "cache-api"),
    (r"(?i)purge_cache|purge_everything|purgeCache\(|invalidateByTag|/purge\b|CreateInvalidation|create-invalidation|soft[_-]?purge", "cdn", "purge"),
    (r"\"(aws_cloudfront_cache_policy|aws_cloudfront_origin_request_policy|aws_cloudfront_distribution)\"|\b(default_ttl|max_ttl|min_ttl)\s*=", "cdn", "cloudfront-config"),
    (r"\"(cloudflare_ruleset|cloudflare_page_rule|cloudflare_tiered_cache|cloudflare_argo)\"|\bcache_level\s*=|\bedge_ttl\b|\bbrowser_ttl\b", "cdn", "cloudflare-config"),
    (r"\"fastly_service_(vcl|compute)\"|\bfastly\b.*\b(purge|surrogate)", "cdn", "fastly-config"),
    (r"\b(cache_cluster_enabled|caching_enabled|cache_ttl_in_seconds|require_authorization_for_cache_control|cache-lookup|cache-store)\b", "cdn", "api-gateway-cache"),
    (r"^\s*\[\[headers\]\]|^\s*for\s*=\s*['\"]/", "cdn", "netlify-headers"),
    (r"\"headers\"\s*:\s*\[\s*\{\s*\"source\"", "cdn", "vercel-headers"),
    # Service workers
    (r"\bworkbox\b|\bregisterRoute\(|\b(CacheFirst|NetworkFirst|StaleWhileRevalidate|NetworkOnly|CacheOnly)\b|\bprecacheAndRoute\(|\bdefaultCache\b|runtimeCaching", "service-worker", "workbox-serwist"),
    (r"addEventListener\(\s*['\"]fetch['\"]|navigator\.serviceWorker\.register\(", "service-worker", "service-worker"),
    (r"<link[^>]+rel=['\"](preload|prefetch|preconnect|modulepreload)|speculationrules|Speculation-Rules", "client", "resource-hints"),
    # Client data caches
    (r"\b(staleTime|gcTime|cacheTime|refetchOnWindowFocus|persistQueryClient|createAsyncStoragePersister|createSyncStoragePersister)\b", "client", "tanstack-query"),
    (r"\buseSWR(Immutable|Infinite)?\(|\bdedupingInterval\b", "client", "swr"),
    (r"\bnew\s+InMemoryCache\(|\bfetchPolicy\s*:|\btypePolicies\b", "client", "apollo-client"),
    (r"\bcacheExchange\b|\bgraphcache\b", "client", "urql"),
    (r"\b(keepUnusedDataFor|providesTags|invalidatesTags)\b", "client", "rtk-query"),
    # GraphQL / API
    (r"@cacheControl\b|responseCachePlugin|useResponseCache|setCacheHint|persistedQueries|useGETForHashedQueries|createPersistedQueryLink", "app-cache", "graphql-cache"),
    (r"idempotency_level\s*=\s*NO_SIDE_EFFECTS|responseMeta\s*\(", "http-header", "rpc-cache"),
    (r"(?i)['\"]idempotency-key['\"]", "app-cache", "idempotency-key"),
    # LLM
    (r"cache_control['\"]?\s*:\s*\{\s*['\"]?type['\"]?\s*:\s*['\"]ephemeral|['\"]cache_control['\"]", "llm", "anthropic-prompt-cache"),
    (r"\bprompt_cache_key\b|\bprompt_cache_retention\b|\bcached_tokens\b|\bcache_read_input_tokens\b", "llm", "llm-cache-usage"),
    (r"\bcachedContents?\b|\bCachedContent\b|caches\.create\(", "llm", "gemini-context-cache"),
    (r"(?i)semantic[_ ]?cache|GPTCache|RedisSemanticCache|set_llm_cache\(", "llm", "semantic-cache"),
    # Build / CI
    (r"\bactions/cache@|\bcache:\s*['\"]?(npm|pnpm|yarn|pip|gradle|maven)['\"]?|setup-(node|python|java)@.*\n?.*cache:", "build", "ci-cache"),
    (r"--mount=type=cache|\bcache-from\b|\bcache-to\b|type=gha", "build", "docker-cache"),
    (r"\"remoteCache\"|\bTURBO_(TOKEN|TEAM|REMOTE_CACHE)|\bnx-cloud\b|\bnxCloudAccessToken\b", "build", "monorepo-remote-cache"),
]

COMPILED = [(re.compile(p, re.M), layer, kind) for p, layer, kind in PATTERNS]
COMMENT_LINE = re.compile(r"^\s*(#|//|--|\*|/\*|<!--|;)")
TEST_FILE = re.compile(r"(^|/)(tests?|__tests__|spec|e2e)/|\.(test|spec)\.[cm]?[jt]sx?$|(^|/)test_[^/]*\.py$|_test\.(py|go|rb)$|_spec\.rb$")

# --------------------------------------------------------------------------- warnings

WARNING_RULES: list[dict] = [
    {
        "rule": "vary-cookie-or-user-agent",
        "pattern": r"(?i)(['\"`]vary['\"`]\s*[,:=]\s*['\"`][^'\"`\n]*\b(cookie|user-agent)\b|\bVary:\s*[^\n]*\b(Cookie|User-Agent)\b|vary_on_headers\([^)]*['\"](Cookie|User-Agent)['\"])",
        "severity": "medium",
        "message": "Vary on Cookie/User-Agent creates a variant per user or browser build: near-zero hit ratio, and some CDNs refuse to cache it. Bypass shared caches for personalized responses, or key on a normalized header.",
        "reference": "references/core/http-semantics.md",
    },
    {
        "rule": "vary-star",
        "pattern": r"(?i)(['\"`]vary['\"`]\s*[,:=]\s*['\"`]\*['\"`]|\bVary:\s*\*)",
        "severity": "medium",
        "message": "Vary: * makes responses unusable from caches; use Cache-Control: no-store or private instead.",
        "reference": "references/core/http-semantics.md",
    },
    {
        "rule": "kitchen-sink-cache-control",
        "pattern": r"(?i)no-cache,\s*no-store,\s*must-revalidate|max-age=0,\s*no-cache,\s*no-store|no-store,\s*no-cache,\s*must-revalidate,\s*(proxy-revalidate|max-age=0)",
        "severity": "low",
        "message": "Kitchen-sink Cache-Control: `no-store` alone is enough; the extra directives are noise (and Pragma/Expires are legacy).",
        "reference": "references/core/http-semantics.md",
    },
    {
        "rule": "private-with-s-maxage",
        "pattern": r"(?i)\bprivate\b[^'\"\n]*\bs-maxage\b|\bs-maxage\b[^'\"\n]*\bprivate\b",
        "severity": "high",
        "message": "`private` and `s-maxage` contradict each other; shared caches behave inconsistently. Decide whether the response is per-user (private) or shared.",
        "reference": "references/core/http-semantics.md",
    },
    {
        "rule": "public-cache-on-auth-path",
        "pattern": r"(?i)(public\s*,\s*(max-age|s-maxage)|s-maxage=\d+)",
        "path_pattern": r"(?i)(account|admin|dashboard|profile|checkout|cart|billing|settings|auth|login|session|/me[/._]|user)",
        "severity": "high",
        "message": "Shared-cacheable header in a file whose path looks authenticated (account/admin/cart/...). Confirm the response never depends on cookies, sessions, Authorization or tenant.",
        "reference": "references/core/security.md",
    },
    {
        "rule": "next-revalidatetag-one-arg",
        "pattern": r"\brevalidateTag\(\s*(?:[^,()]|\([^()]*\))+\)",
        "severity": "medium",
        "message": "One-argument revalidateTag(tag) is deprecated in Next.js 16 (TypeScript error; behaves like { expire: 0 }). Use revalidateTag(tag, 'max') for SWR, or { expire: 0 } in webhooks needing immediate expiry.",
        "reference": "references/frameworks/nextjs.md",
    },
    {
        "rule": "next-updatetag-in-route-handler",
        "pattern": r"\bupdateTag\(",
        "path_pattern": r"(^|/)route\.(ts|tsx|js|mjs)$",
        "severity": "high",
        "message": "updateTag works only in Server Actions and throws in Route Handlers; use revalidateTag(tag, 'max') here.",
        "reference": "references/frameworks/nextjs.md",
    },
    {
        "rule": "next-segment-config-not-literal",
        "pattern": r"export\s+const\s+revalidate\s*=\s*[^;\n]*[*+/-]",
        "severity": "medium",
        "message": "Segment config must be a static literal (600, not 60*10); expressions are ignored or rejected.",
        "reference": "references/frameworks/nextjs.md",
    },
    {
        "rule": "next-use-cache-reads-request-data",
        "pattern": r"['\"]use cache['\"]",
        "file_also": r"\b(cookies|headers)\(\)|\bsearchParams\b",
        "severity": "medium",
        "message": "File has 'use cache' and also reads cookies()/headers()/searchParams. Cached scopes can't read request data; read it outside and pass values as arguments (or use 'use cache: private').",
        "reference": "references/frameworks/nextjs.md",
    },
    {
        "rule": "next-force-cache",
        "pattern": r"cache:\s*['\"]force-cache['\"]",
        "severity": "low",
        "message": "force-cache stores whatever the fetch returns, including responses to requests with Authorization/Cookie headers. Confirm this fetch is never user-specific.",
        "reference": "references/frameworks/nextjs.md",
    },
    {
        "rule": "django-cache-page-without-vary-cookie",
        "pattern": r"@cache_page\b|cache_page\(",
        "file_lacks": r"vary_on_cookie|vary_on_headers\([^)]*['\"]Cookie",
        "path_pattern": r"\.py$",
        "severity": "medium",
        "message": "cache_page doesn't vary on cookies or Authorization: never use it on authenticated views (or add vary_on_cookie and accept per-user variants). Also patch Django to the latest 6.0.x/6.1.x (6.0.6/6.0.7 cache fixes).",
        "reference": "references/frameworks/django.md",
    },
    {
        "rule": "redis-keys-command",
        "pattern": r"(?i)\.keys\(\s*['\"`][^'\"`]*\*|\bKEYS\s+['\"]?[\w:]*\*|redis-cli[^\n]*\bkeys\b",
        "severity": "high",
        "message": "KEYS blocks Redis while it walks the whole keyspace; use SCAN (or tags/version bumps) instead.",
        "reference": "references/layers/distributed-cache.md",
    },
    {
        "rule": "redis-flush",
        "pattern": r"(?i)\bflush(all|db)\b\s*\(|\bFLUSH(ALL|DB)\b|cache:clear|optimize:clear|Rails\.cache\.clear|cache\.clear\(\)",
        "severity": "medium",
        "message": "Flushing a whole cache causes a cold-cache stampede and can wipe co-located data (sessions, queues, locks). Prefer key-version bumps or tag invalidation.",
        "reference": "references/core/invalidation-consistency.md",
    },
    {
        "rule": "redis-noeviction",
        "pattern": r"(?i)maxmemory-policy['\"]?\s*[:=]?\s*['\"]?noeviction",
        "severity": "medium",
        "message": "noeviction makes writes fail when memory is full: right for queues/sessions, wrong for a cache (use allkeys-lru or allkeys-lfu on a dedicated cache instance).",
        "reference": "references/layers/distributed-cache.md",
    },
    {
        "rule": "python-unbounded-cache",
        "pattern": r"lru_cache\(\s*maxsize\s*=\s*None\s*\)|@functools\.cache\b|^from functools import[^\n]*\bcache\b",
        "severity": "medium",
        "message": "Unbounded in-process cache: grows forever in long-lived workers (and on methods keeps `self` alive). Set maxsize or use a TTL cache.",
        "reference": "references/layers/in-process.md",
    },
    {
        "rule": "js-unbounded-lru",
        "pattern": r"new\s+LRUCache\(\s*\)|new\s+LRUCache\(\s*\{(?![^}]*\b(max|maxSize|ttl)\b)[^}]*\}\s*\)",
        "severity": "medium",
        "message": "lru-cache needs max, maxSize or ttl; without them it is unbounded (newer versions throw).",
        "reference": "references/layers/in-process.md",
    },
    {
        "rule": "module-level-dataloader",
        "pattern": r"^(export\s+)?(const|let|var)\s+\w+\s*=\s*new\s+DataLoader\(",
        "severity": "high",
        "message": "Module-level DataLoader is shared across requests: it caches results across users. Create loaders per request in the context factory.",
        "reference": "references/layers/api-graphql-rpc.md",
    },
    {
        "rule": "nestjs-global-cache-interceptor",
        "pattern": r"useGlobalInterceptors\([^)]*CacheInterceptor|provide:\s*APP_INTERCEPTOR,\s*useClass:\s*CacheInterceptor",
        "severity": "high",
        "message": "Global CacheInterceptor keys by URL and ignores auth: authenticated GETs can be served to other users. Apply it per public route or override trackBy.",
        "reference": "references/frameworks/node-backends.md",
    },
    {
        "rule": "proxy-ignores-origin-headers",
        "pattern": r"proxy_ignore_headers[^;]*(Cache-Control|Set-Cookie|Expires|Vary)",
        "severity": "high",
        "message": "The proxy ignores origin Cache-Control/Set-Cookie/Vary: personalized responses can be stored and served to others. Make sure cookie/auth requests bypass the cache.",
        "reference": "references/layers/reverse-proxies.md",
    },
    {
        "rule": "cloudflare-cache-everything",
        "pattern": r"(?i)cache_level\s*=\s*['\"]cache_everything['\"]|cacheEverything\s*:\s*true",
        "severity": "medium",
        "message": "Cache Everything caches HTML regardless of cookies; add bypass rules for session/login cookies or authenticated pages leak.",
        "reference": "references/platforms/cloudflare.md",
    },
    {
        "rule": "api-gateway-unauthenticated-invalidation",
        "pattern": r"(?i)require_authorization_for_cache_control\s*=\s*false|requireAuthorizationForCacheControl['\"]?\s*:\s*false",
        "severity": "high",
        "message": "Any client can invalidate API Gateway cache entries with Cache-Control: max-age=0 (forced misses, DoS). Require authorization and FAIL_WITH_403.",
        "reference": "references/layers/api-graphql-rpc.md",
    },
    {
        "rule": "immutable-on-unversioned-path",
        "pattern": r"(?i)immutable",
        "line_also": r"(?i)['\"]/(favicon\.ico|robots\.txt|manifest\.(json|webmanifest)|sw\.js|service-worker\.js|index\.html|\.well-known)",
        "severity": "high",
        "message": "immutable on a fixed (unversioned) URL can't be recalled from browsers. Use no-cache + ETag for fixed URLs; immutable only for fingerprinted files.",
        "reference": "references/core/http-semantics.md",
    },
    {
        "rule": "workbox-cachefirst-on-api-or-html",
        "pattern": r"(?i)(api|navigate|\.html)[^\n]{0,120}CacheFirst|CacheFirst[^\n]{0,120}(api|navigate|\.html)",
        "severity": "medium",
        "message": "CacheFirst on API responses or navigations pins stale (and possibly per-user) data on devices; use NetworkFirst or StaleWhileRevalidate with expiration.",
        "reference": "references/layers/service-workers.md",
    },
    {
        "rule": "cookie-on-every-request",
        "pattern": r"\bsetcookie\(",
        "file_also": r"add_action\(\s*['\"](init|wp|wp_loaded|template_redirect|send_headers)['\"]",
        "severity": "medium",
        "message": "A cookie set on every request (WordPress init hook) puts Set-Cookie on anonymous pages: CDNs and APO then bypass the cache (cf-cache-status BYPASS). Set it only where needed, or bucket at the edge/client.",
        "reference": "references/cms/wordpress.md",
    },
    {
        "rule": "rails-public-shared-ttl",
        "pattern": r"\b(expires_in|fresh_when|stale\?|http_cache_forever)\b[^\n]*public:\s*true",
        "severity": "low",
        "message": "public: true makes the response shared-cacheable: confirm it never depends on the session/user, and plan purges (without them the shared TTL is your staleness).",
        "reference": "references/frameworks/rails.md",
    },
    {
        "rule": "constant-key-in-user-scoped-code",
        "pattern": r"\b(cache|Rails\.cache|Cache::|redis|client)\.?\s*(get|set|fetch|get_or_set|remember|setex)\w*\(\s*[\"'][^\"'{}%$#]*[\"']",
        "file_also": r"request\.user|current_user|organization|tenant|auth\(\)|Auth::user|session\[",
        "severity": "medium",
        "message": "Constant cache key in code that reads the user/tenant: if the cached value depends on them, every tenant shares one entry (cross-tenant leak). Put the tenant/user in the key: {app}:{env}:v1:t:{tenant}:...",
        "reference": "references/core/security.md",
    },
    {
        "rule": "llm-volatile-prompt-prefix",
        "pattern": r"(datetime\.(now|utcnow)\(\)|Date\.now\(\)|new Date\(\)|time\.time\(\)|uuid\d?\(\))",
        "file_also": r"(?i)\b(anthropic|openai|messages\.create|chat\.completions|generateText|streamText)\b",
        "line_also": r"(?i)(f[\"']|`|system|prompt|\+)",
        "severity": "medium",
        "message": "A timestamp/random value in prompt text breaks prompt caching when it sits before stable content. Put stable instructions/documents first, variable values last (or in the user turn).",
        "reference": "references/layers/ai-llm.md",
    },
    {
        "rule": "llm-call-without-prompt-caching",
        "pattern": r"\bmessages\.create\(|\bmessages\.stream\(",
        "file_also": r"(?i)\banthropic\b",
        "file_lacks": r"cache_control",
        "severity": "low",
        "message": "Anthropic call without cache_control: if a long prefix (system prompt, documents, tools) repeats across requests, add a cache breakpoint after it and track cache_read_input_tokens.",
        "reference": "references/layers/ai-llm.md",
    },
    {
        "rule": "client-cache-never-stale",
        "pattern": r"\bstaleTime\s*:\s*Infinity\b",
        "severity": "low",
        "message": "staleTime: Infinity never refetches: server-side changes don't show until the query is invalidated or the app restarts. Use a finite staleTime or invalidate on the mutations that change it.",
        "reference": "references/frameworks/client-data-caches.md",
    },
    {
        "rule": "redis-set-without-ttl",
        "pattern": r"(?<![\w.])(redis|client|rdb|cache|valkey|r)\.set\(\s*[^,()\n]+,\s*[^,()\n]+\)\s*;?\s*$",
        "file_also": r"\b(ioredis|redis|Redis)\b",
        "path_pattern": r"\.(js|mjs|cjs|ts|mts|tsx|py|rb)$",
        "severity": "low",
        "message": "Cache write without a TTL (set(key, value)): entries live until evicted and stale data never self-heals. Add EX/PX (with jitter) unless this is not a cache.",
        "reference": "references/layers/distributed-cache.md",
    },
]
for rule in WARNING_RULES:
    rule["_rx"] = re.compile(rule["pattern"], re.M)
    for extra in ("path_pattern", "file_also", "file_lacks", "line_also"):
        if extra in rule:
            rule["_" + extra] = re.compile(rule[extra], re.M)


# --------------------------------------------------------------------------- scanning


def iter_files(root: Path, limits: dict):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        rel_dir = here.relative_to(root).as_posix()
        kept = []
        for d in dirnames:
            rel = d if rel_dir == "." else f"{rel_dir}/{d}"
            if d in SKIP_DIRS or rel in SKIP_DIRS or (d.startswith(".") and d not in (".github", ".circleci", ".gitlab")):
                limits["skipped_dirs"].add(d)
                continue
            kept.append(d)
        dirnames[:] = kept
        for name in filenames:
            path = here / name
            suffix = path.suffix.lower()
            if name in SKIP_FILES or name.endswith((".min.js", ".min.css", ".map")):
                continue
            if suffix not in SOURCE_EXT and name not in SPECIAL_NAMES and not name.startswith("Dockerfile"):
                continue
            count += 1
            if count > MAX_FILES:
                limits["truncated"] = True
                return
            yield path


def read_text(path: Path, limits: dict) -> str | None:
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            limits["skipped_large_files"].append(path.name)
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace")


def snippet(line: str) -> str:
    s = line.strip()
    return s if len(s) <= 160 else s[:157] + "..."


def scan(root: Path, max_findings: int, layers: set[str] | None) -> dict:
    limits = {"truncated": False, "skipped_dirs": set(), "skipped_large_files": [], "max_files": MAX_FILES,
              "max_findings": max_findings, "max_per_file": MAX_PER_FILE, "files_scanned": 0}
    findings: list[dict] = []
    warnings: list[dict] = []
    for path in iter_files(root, limits):
        text = read_text(path, limits)
        if text is None:
            continue
        limits["files_scanned"] += 1
        rel = path.relative_to(root).as_posix()
        lines = text.splitlines()
        per_file = 0
        for lineno, line in enumerate(lines, 1):
            if len(line) > 2000:
                continue
            for rx, layer, kind in COMPILED:
                if layers and layer not in layers:
                    continue
                if rx.search(line):
                    if per_file < MAX_PER_FILE and len(findings) < max_findings:
                        findings.append({"file": rel, "line": lineno, "layer": layer, "kind": kind, "snippet": snippet(line)})
                        per_file += 1
                    elif len(findings) >= max_findings:
                        limits["truncated"] = True
                    break  # one finding per line keeps the list readable
        # Warnings skip comments and test files (they assert headers, they don't serve them).
        for rule in [] if TEST_FILE.search(rel) else WARNING_RULES:
            if "_path_pattern" in rule and not rule["_path_pattern"].search(rel):
                continue
            if "_file_also" in rule and not rule["_file_also"].search(text):
                continue
            if "_file_lacks" in rule and rule["_file_lacks"].search(text):
                continue
            for lineno, line in enumerate(lines, 1):
                if len(line) > 2000 or COMMENT_LINE.match(line) or not rule["_rx"].search(line):
                    continue
                if "_line_also" in rule and not rule["_line_also"].search(line):
                    continue
                warnings.append({"file": rel, "line": lineno, "rule": rule["rule"], "severity": rule["severity"],
                                 "message": rule["message"], "reference": rule["reference"], "snippet": snippet(line)})
                if sum(1 for w in warnings if w["file"] == rel and w["rule"] == rule["rule"]) >= 5:
                    break
    order = {"high": 0, "medium": 1, "low": 2}
    warnings.sort(key=lambda w: (order[w["severity"]], w["file"], w["line"]))
    limits["skipped_dirs"] = sorted(limits["skipped_dirs"])[:40]
    limits["skipped_large_files"] = limits["skipped_large_files"][:40]
    summary = {
        "by_layer": dict(Counter(f["layer"] for f in findings).most_common()),
        "by_kind": dict(Counter(f["kind"] for f in findings).most_common()),
        "files_with_findings": len({f["file"] for f in findings}),
        "warnings_by_rule": dict(Counter(w["rule"] for w in warnings).most_common()),
        "warnings_by_severity": dict(Counter(w["severity"] for w in warnings).most_common()),
    }
    return {"repo": str(root), "findings": findings, "warnings": warnings, "summary": summary, "limits": {
        **limits, "method": "line-based regex scan; multi-line constructs and runtime config are not seen"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List caching code/config with file:line, layer and kind, plus heuristic warnings.",
        epilog="Prints JSON on stdout. Exit 0 on success, 2 on bad usage.",
    )
    parser.add_argument("repo_dir", help="path to the repository root")
    parser.add_argument("--max-findings", type=int, default=DEFAULT_MAX_FINDINGS, help=f"cap on findings (default {DEFAULT_MAX_FINDINGS})")
    parser.add_argument("--layer", action="append", choices=sorted({l for _, l, _ in PATTERNS}),
                        help="only report findings for this layer (repeatable); warnings are always reported")
    args = parser.parse_args(argv)
    root = Path(args.repo_dir).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    if args.max_findings < 1:
        print("error: --max-findings must be >= 1", file=sys.stderr)
        return 2
    json.dump(scan(root, args.max_findings, set(args.layer) if args.layer else None), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
