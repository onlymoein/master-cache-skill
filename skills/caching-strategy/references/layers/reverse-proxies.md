# Reverse proxy caching

Last reviewed: 2026-10-27 · Applies to: nginx (proxy_cache, fastcgi_cache), Varnish 6/7 with xkey, HAProxy 2.4+, Caddy cache-handler (Souin), Traefik

## Contents

- When to read this
- Default recipe (nginx micro-cache)
- Rules and gotchas
- Varnish
- HAProxy
- Caddy, Traefik and others
- Version notes
- Verify
- Sources

## When to read this

When the origin runs nginx, Varnish, HAProxy, Caddy or Traefik in front of the app, or when a self-hosted origin needs request collapsing and stale serving. Without a CDN, the proxy is the shared cache; with a tag-purging CDN in front, keep the proxy as a 1–10 s micro-cache that mainly adds collapsing and SIE.

## Default recipe (nginx micro-cache)

Full file: `assets/snippets/proxy/nginx-microcache.conf`. Verify directive values against nginx.org for the installed version.

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=app:100m max_size=10g inactive=7d use_temp_path=off;

map $http_cookie $skip_cache {
  default 0;
  ~*(session|sid|auth|wordpress_logged_in|woocommerce_items_in_cart) 1;
}
map $http_authorization $skip_auth { default 1; "" 0; }

server {
  location / {
    proxy_cache                  app;
    proxy_cache_key              "$scheme$host$request_uri";
    proxy_cache_methods          GET HEAD;
    proxy_cache_valid            200 301 1s;      # micro-cache dynamic HTML
    proxy_cache_use_stale        updating error timeout http_500 http_502 http_503 http_504;
    proxy_cache_background_update on;
    proxy_cache_lock             on;              # one request per key goes upstream
    proxy_cache_bypass           $skip_cache $skip_auth;
    proxy_no_cache               $skip_cache $skip_auth;
    add_header X-Cache-Status    $upstream_cache_status always;
    proxy_pass http://app_upstream;
  }
}
```

PHP-FPM uses the same pattern with `fastcgi_cache_path`, `fastcgi_cache`, `fastcgi_cache_key`, `fastcgi_cache_use_stale`, `fastcgi_cache_lock`, `fastcgi_cache_background_update`.

## Rules and gotchas

1. Only cache responses that are identical for every client (usually anonymous GET/HEAD). Bypass on session cookies and `Authorization`, both for lookup (`*_cache_bypass`) and storage (`*_no_cache`).
2. nginx honors `Cache-Control`, `Expires` and `Set-Cookie` from upstream: it won't cache `private`/`no-cache`/`no-store` or responses with `Set-Cookie`. Don't paper over that with a global `proxy_ignore_headers Set-Cookie Cache-Control`; strip cookies on anonymous routes at the app instead. When public pages send `Cache-Control: no-cache` for browsers, give nginx its own TTL with `X-Accel-Expires: <seconds>` (takes priority over `Cache-Control`, not passed to clients; verify for your version).
3. `proxy_cache_lock` gives request collapsing; `proxy_cache_use_stale updating` + `proxy_cache_background_update` gives SWR; `use_stale error timeout http_5xx` gives SIE.
4. nginx turns strong upstream ETags weak when it gzips, and drops unquoted ETags. Send quoted ETags.
5. Varnish: mark uncacheable responses hit-for-pass/hit-for-miss explicitly, or concurrent requests queue behind a fetch that will never be cached.
6. A proxy cache behind a CDN is a second invalidation layer: purge it before the CDN, or keep its TTL at 1–10 s.
7. Protect purge endpoints (PURGE method, xkey headers) with an ACL.
8. Include the host in the key when one proxy serves several domains or tenants.

## Varnish

```vcl
vcl 4.1;
import std;
import xkey;

acl purgers { "127.0.0.1"; "10.0.0.0"/8; }

sub vcl_recv {
  if (req.method == "PURGE") {
    if (client.ip !~ purgers) { return (synth(403)); }
    set req.http.n-gone = xkey.softpurge(req.http.xkey);   # soft: keep for grace
    return (synth(200, "Invalidated " + req.http.n-gone));
  }
  if (req.http.Authorization || req.http.Cookie ~ "(^|; )(session|sid)=") { return (pass); }
  if (std.healthy(req.backend_hint)) { set req.grace = 10s; }   # short grace while healthy
}

sub vcl_backend_response {
  set beresp.grace = 24h;   # serve stale up to 24 h if the backend is sick
  set beresp.keep  = 1h;    # keep for conditional revalidation
  if (beresp.http.Set-Cookie || beresp.http.Cache-Control ~ "private|no-store") {
    set beresp.uncacheable = true;   # hit-for-miss, no queueing
    set beresp.ttl = 120s;
    return (deliver);
  }
}
```

- The origin sends `xkey: product-123 category-9` (space-separated) per response.
- Prefer xkey soft purge over bans for tag invalidation; bans accumulate on the ban list and are evaluated lazily.
- Hard PURGE/BAN removes objects so grace no longer applies; soft purge keeps them for grace.
- Full file: `assets/snippets/proxy/varnish-xkey.vcl`.

## HAProxy

- In-memory only, lost on reload. `total-max-size` up to 4,095 MB; `max-object-size` ≤ half of it; `max-age` caps the TTL.
- With `process-vary` off (default), any response carrying `Vary` is not cached. `process-vary on` (2.4+) handles `Vary` only on `accept-encoding`, `referer` and/or `origin`.
- Good for a tiny hot-object cache; use nginx/Varnish or a CDN for real page caching.

## Caddy, Traefik and others

- Caddy: `caddyserver/cache-handler` (Souin-based) with `ttl`, `stale`, `surrogate_keys`, CDN-provider integrations. Since Souin v1.7.0 only one storage backend is built in; others need custom `xcaddy` builds. Surrogate keys may need `dynamic` enabled.
- Traefik has no native HTTP cache; Souin runs as a Traefik plugin, but the plugin loader breaks often. Prefer a CDN or a dedicated proxy.
- Apache `mod_cache` and Squid: not covered in this skill's research; apply the same rules (anonymous only, explicit headers, bypass on cookies) and check their current docs.

## Version notes

- `proxy_cache_background_update` exists since nginx 1.11.10.
- HAProxy `process-vary` since 2.4.
- Souin storage backend change in v1.7.0.

<details><summary>Old patterns</summary>

- `proxy_ignore_headers Cache-Control Set-Cookie` site-wide to force caching.
- Varnish bans for every content update instead of xkey/surrogate keys.

</details>

## Verify

```bash
for i in 1 2 3; do curl -s -o /dev/null -D - https://example.com/ | grep -iE 'x-cache-status|age|cache-control'; done
# nginx: MISS → HIT (or UPDATING/STALE during refresh). Varnish: X-Varnish shows two IDs on a hit; Age > 0.
curl -s -o /dev/null -D - -H 'Cookie: session=abc' https://example.com/ | grep -i x-cache-status   # expect BYPASS
varnishlog -g request -q 'ReqMethod eq "PURGE"'   # watch purges
```

Load test with the cache cold to confirm `proxy_cache_lock` keeps upstream requests at one per key.

## Sources

- [F5 NGINX caching guide](https://www.f5.com/company/blog/nginx/nginx-caching-guide)
- [nginx ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- [Varnish grace mode](https://www.varnish.org/docs/users-guide/vcl-grace/)
- [Varnish cache invalidation tutorial](https://www.varnish.org/docs/tutorials/cache-invalidation/)
- [Varnish: increasing your hit rate (hit-for-pass)](https://www.varnish.org/docs/users-guide/increasing-your-hitrate/)
- [HAProxy caching](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/performance/caching)
- [caddyserver/cache-handler](https://github.com/caddyserver/cache-handler)
- [Souin configuration](https://docs.souin.io/docs/configuration/)
- [nginx trac #377 (ETags)](https://trac.nginx.org/nginx/ticket/377)
