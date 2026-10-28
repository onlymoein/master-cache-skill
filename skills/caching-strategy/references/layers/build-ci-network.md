# Build, CI and network-level caching

Last reviewed: 2026-10-27 · Applies to: GitHub Actions cache, Docker BuildKit, Turborepo, Nx, framework build caches, DNS, TLS 1.3, connection reuse

## Contents

- When to read this
- Default recipe (GitHub Actions)
- Rules and gotchas
- Build cache by layer
- DNS
- TLS and connections
- OS page cache
- Version notes
- Verify
- Sources

## When to read this

Only when the user asks about build/CI speed, deploy caches, DNS changes, TLS or connection overhead. These are adjacent to app caching: a parallel track in the plan, not part of the route policy matrix.

## Default recipe (GitHub Actions)

Full example: `assets/snippets/ci/github-actions-cache.yml`.

```yaml
- uses: pnpm/action-setup@v4        # pnpm must exist before setup-node's pnpm cache
- uses: actions/setup-node@v4
  with:
    node-version: 22
    cache: pnpm                     # built-in dependency cache keyed on the lockfile
- uses: actions/cache@v4
  with:
    path: .next/cache               # framework build cache
    key: nextjs-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}-${{ hashFiles('**/*.[jt]s', '**/*.[jt]sx') }}
    restore-keys: |
      nextjs-${{ runner.os }}-${{ hashFiles('pnpm-lock.yaml') }}-
```

In workflows triggered by untrusted events (`pull_request` from forks, `pull_request_target`, `issue_comment`), restore only: use `actions/cache/restore` or `cache-mode: read`.

## Rules and gotchas

1. A cache is a supply-chain input. Never put tokens, credentials or `.env` files in cached paths; anyone who can open a PR can read caches.
2. GitHub Actions (current docs): only `push`, `workflow_dispatch`, `repository_dispatch`, `delete`, `registry_package`, `page_build` and `schedule` can write default-branch caches; other triggers on the default branch get read-only access. The `cache-mode` key (`read` | `write` | `write-only`, workflow or job level) grants least privilege. Explicit `write` on untrusted triggers reintroduces cache poisoning.
3. Key = OS + tool version + lockfile hash, with `restore-keys` prefixes as fallback. Never cache `node_modules` across Node versions.
4. Turborepo "treats logs as artifacts": anything printed by a task (including secrets) lands in the remote cache.
5. Nx: read-write cache tokens only on protected branches; read-only everywhere else; never put CI tokens in `nx.json`.
6. Remote caches must only be written from trusted CI. Separate caches for release builds.
7. Lower DNS TTLs at least one full old-TTL period before a migration; the TTL change itself is cached under the old TTL.
8. TLS 1.3 0-RTT data can be replayed: allow it only for idempotent requests (GET/HEAD).

## Build cache by layer

| Layer | Key / config | Notes |
|---|---|---|
| Package managers | `setup-node` `cache: npm|yarn|pnpm`; `setup-python` `cache: pip|pipenv|poetry`; Go `~/go/pkg/mod` + `~/.cache/go-build`; Maven `~/.m2/repository`; Gradle `gradle/actions/setup-gradle`; Cargo registry + `target/` or sccache | Lockfile-hash keys |
| Docker BuildKit | Order layers least-changing first (copy lockfile → install → copy source); `.dockerignore`; `RUN --mount=type=cache,target=/root/.npm`; external cache `cache-from/cache-to: type=gha,mode=max` or `type=registry,ref=…:buildcache,mode=max` | Backends: `inline`, `registry`, `local`, `gha`, `s3`, `azblob`; all but the local cache must be exported/imported explicitly; `mode=min` is default |
| Monorepo task caches | Turborepo `turbo.json` `inputs`/`outputs`, env hashing, `TURBO_TOKEN`/`TURBO_TEAM`; Nx `namedInputs`, Nx Cloud or self-hosted | Without a remote cache Turborepo caches only on the local filesystem. Verify outputs are deterministic |
| Framework build caches | Next.js `.next/cache` (otherwise "No Cache Detected"); Gatsby `.cache` + `public`; Astro `node_modules/.astro`; Vite `node_modules/.vite` | Vercel/Netlify persist these on their platforms |
| Bazel | `--remote_cache=…` / `--disk_cache` | Upload only from trusted CI |

GitHub Actions limits: 10 GB per repository by default, configurable up to 25 GB; eviction by last access, oldest first. `key` matches exactly, then by prefix, then `restore-keys` in order; the current branch is searched before the default branch; PR caches are scoped to the merge ref.

## DNS

- Steady-state TTL 1 h–1 day for stable records; 60–300 s for records behind failover or health-checked load balancing.
- Migration: lower to ~300 s at least one old-TTL period ahead (commonly 24–48 h), switch, verify, then restore to ≥ 3600 s. These are conventions, not a standard.
- Cloudflare proxied records are fixed at Auto (300 s); DNS-only records allow 30 s (Enterprise) or 60 s up to 1 day. Resolvers may hold records longer than the TTL.
- `dns-prefetch`/`preconnect` for critical third-party origins; avoid long CNAME chains.

## TLS and connections

- Enable TLS session resumption (tickets/PSK with rotated keys) at the CDN and origin; prefer TLS 1.3 and HTTP/2 or HTTP/3.
- 0-RTT: GET/HEAD only. Proxies may forward early data unmarked; configure an `Early-Data` header and reject non-idempotent early requests with 425.
- Reuse connections: nginx `keepalive` in upstreams, HTTP agents with keep-alive in Node, DB poolers (PgBouncer, RDS Proxy, Hyperdrive), one long-lived Redis client per process. Cold connection setup often dominates TTFB on cache misses.

## OS page cache

- nginx/Varnish static serving benefits from RAM above the hot working set (`sendfile`, `open_file_cache`).
- Databases rely on the page cache plus their buffer pool; don't starve it with oversized in-process caches in the same container. Page cache counts toward cgroup memory but is reclaimable.

## Version notes

- GitHub Actions 2026: read-only default-branch caches for low-trust triggers and the `cache-mode` key.
- Turborepo Remote Caching via Vercel is free on all plans (self-hostable).

## Verify

- CI logs: cache hit/miss lines per step; Turborepo/Nx run summaries show cache hits.
- `docker buildx build --progress=plain …` shows `CACHED` per step.
- `dig +nocmd +noall +answer example.com` shows the remaining TTL.
- `openssl s_client -connect example.com:443 -sess_out s.pem` then `-sess_in s.pem` to confirm resumption ("Reused").

## Sources

- [GitHub Actions dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [Docker build cache optimization](https://docs.docker.com/build/cache/optimize/)
- [Docker cache backends](https://docs.docker.com/build/cache/backends/)
- [Turborepo remote caching](https://turborepo.dev/docs/core-concepts/remote-caching)
- [Nx cache security (docs source)](https://github.com/nrwl/nx/blob/master/astro-docs/src/content/docs/kb/cache-security.mdoc)
- [Next.js CI build caching](https://nextjs.org/docs/app/guides/ci-build-caching)
- [Cloudflare DNS TTL](https://developers.cloudflare.com/dns/manage-dns-records/reference/ttl/)
- [Cloudflare: TLS 1.3 overview (0-RTT)](https://blog.cloudflare.com/tls-1-3-overview-and-q-and-a/)
