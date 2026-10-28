# Other hosts and small CDNs

Last reviewed: 2026-10-27 · Applies to: Fly.io, Railway, Render, Heroku, Firebase Hosting, AWS Amplify, GitHub Pages, bunny.net

## When to read this

When the app is deployed to one of these platforms. For most of them the advice is the same: send explicit `Cache-Control` on every response and, if HTML or API caching is needed, put a real CDN (Cloudflare, Fastly, bunny, CloudFront) in front. Vendor-neutral concepts: `references/layers/cdn-concepts.md`.

## How to detect

`fly.toml`, `railway.json`/`railway.toml`, `render.yaml`, `Procfile` (Heroku), `firebase.json`, `amplify.yml`, `.github/workflows/*pages*` or a `gh-pages` branch, bunny pull-zone settings or `CDN-Tag` headers in code.

## Rules and gotchas

1. **Always send explicit `Cache-Control`.** On 2026-03-30 a Railway change tied to a Surrogate Keys rollout enabled caching for domains whose CDN was off; for 52 minutes most GET responses without explicit cache headers were cached by default, exposing authenticated data. Platform defaults change without notice; your headers are the only stable control.
2. **Fly.io has no HTTP response cache.** Fly Proxy does routing, load balancing, TLS and autostart/stop. `fly-replay` "replay caching" caches routing decisions only (same organization, best effort). For caching, put a CDN in front or run nginx/Varnish as a Fly app ahead of the app machines (`references/layers/reverse-proxies.md`).
3. **bunny.net:** tags via the `CDN-Tag` response header and the pull zone purge API (`CacheTag`). With Perma-Cache enabled, wildcard and tag purges don't work; a single-URL purge deletes from Perma-Cache storage first; a full pull-zone purge switches to a new storage directory (delete the old one manually). One third-party source says bunny treats the whole `CDN-Tag` value as one tag (no comma split); verify before designing multi-tag schemes. Enable Origin Shield.
4. **Firebase Hosting, Amplify, Render, Heroku, GitHub Pages:** their CDN and header behavior wasn't covered in this skill's research. Configure headers in the platform's config (`firebase.json` `headers`, Amplify custom headers, Render headers) per `references/core/http-semantics.md`, and verify with curl. Hashed assets get `immutable`; HTML `no-cache`.
5. Heroku and Render dynos/instances are ephemeral and often multiple: in-process caches drift and vanish on restart. Use a managed Redis/Valkey for shared app caching.

## Default recipe

```http
# HTML and APIs from the app
Cache-Control: no-cache                 # or private, no-cache / no-store per the decision tree
ETag: "<hash>"

# Hashed assets
Cache-Control: public, max-age=31536000, immutable
```

If a CDN is added in front, follow that CDN's platform reference for edge TTLs and purge.

## Verify

```bash
curl -s -o /dev/null -D - https://app.example.com/ | grep -iE 'cache-control|age|via|server|x-cache|cdn-cache'
# Logged-in request: no Age, no HIT
curl -s -o /dev/null -D - -H 'Cookie: session=x' https://app.example.com/dashboard | grep -iE 'cache-control|age'
```

## Sources

- [Fly Proxy](https://fly.io/docs/reference/fly-proxy/)
- [Fly dynamic request routing (fly-replay)](https://fly.io/docs/networking/dynamic-request-routing/)
- [Railway incident report, 2026-03-30](https://blog.railway.com/p/incident-report-march-30-2026-authenticated-user-data-cached)
- [bunny.net purge cache](https://docs.bunny.net/cdn/purge-cache)
- [bunny.net Perma-Cache](https://bunny.net/docs/cdn/perma-cache)
- [Firebase Hosting configuration](https://firebase.google.com/docs/hosting/full-config)
