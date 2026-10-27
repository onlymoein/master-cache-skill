# Cloudflare Cache Rules: cache public HTML, bypass sessions

Rules run in order; the later matching rule's settings win for overlapping fields. Put the
bypass rule **last** so it always wins. Verify field names against the current Rulesets API docs.

## 1. Rule expressions

| Order | Name | Expression | Action |
|---|---|---|---|
| 1 | cache public html | `(http.host eq "www.example.com" and http.request.method in {"GET" "HEAD"} and not starts_with(http.request.uri.path, "/api/"))` | Eligible for cache; Edge TTL: use origin cache-control if present, else 0 (bypass); Browser TTL: respect origin; cache key: sort query string, ignore `utm_*`; Cache Deception Armor on; serve stale while revalidating on |
| 2 | cache public api | `(starts_with(http.request.uri.path, "/api/catalog/") and http.request.method eq "GET")` | Eligible for cache; Edge TTL: respect origin |
| 3 | bypass private | `(http.cookie contains "session=" or http.cookie contains "wordpress_logged_in" or any(http.request.headers.names[*] eq "authorization") or starts_with(http.request.uri.path, "/account") or starts_with(http.request.uri.path, "/checkout") or starts_with(http.request.uri.path, "/api/me"))` | Bypass cache |

Origin headers stay the source of truth:

```http
Cache-Control: no-cache
Cloudflare-CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400
Cache-Tag: page:home,section:news,all
ETag: "v42"
```

Don't put `stale-while-revalidate` in a header that also has `s-maxage`, `must-revalidate`,
`proxy-revalidate` or `no-cache`: Cloudflare then disables stale serving (`EXPIRED`, not `UPDATING`).

## 2. Terraform (cloudflare provider v4 block syntax; v5 takes `rules = [{ ... }]` lists: check your provider's `cloudflare_ruleset` schema)

```hcl
resource "cloudflare_ruleset" "cache" {
  zone_id = var.zone_id
  name    = "cache rules"
  kind    = "zone"
  phase   = "http_request_cache_settings"

  rules {
    description = "cache public html"
    expression  = "(http.host eq \"www.example.com\" and http.request.method in {\"GET\" \"HEAD\"} and not starts_with(http.request.uri.path, \"/api/\"))"
    action      = "set_cache_settings"
    action_parameters {
      cache = true
      edge_ttl {
        mode = "respect_origin"
      }
      browser_ttl {
        mode = "respect_origin"
      }
      serve_stale {
        disable_stale_while_updating = false
      }
      respect_strong_etags = true
      cache_key {
        cache_deception_armor = true
        custom_key {
          query_string {
            exclude = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"]
          }
        }
      }
    }
  }

  rules {
    description = "bypass private (last: wins over earlier rules)"
    expression  = "(http.cookie contains \"session=\" or any(http.request.headers.names[*] eq \"authorization\") or starts_with(http.request.uri.path, \"/account\") or starts_with(http.request.uri.path, \"/checkout\"))"
    action      = "set_cache_settings"
    action_parameters {
      cache = false
    }
  }
}
```

## 3. Purge and invalidate (API)

```bash
# Soft purge (invalidate): mark stale, next request revalidates (304 reuses the body). Prefer this.
curl -sS -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/invalidate_cache" \
  -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
  --data '{"tags":["product:123"]}'

# Hard purge: content must never be served again (legal takedown, leaked data).
curl -sS -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/purge_cache" \
  -H "Authorization: Bearer $CF_API_TOKEN" -H "Content-Type: application/json" \
  --data '{"tags":["product:123"]}'
```

Purges are rate limited per plan (Free 5 requests/min) with 100 items per request: batch and
debounce webhook-driven purges.

## 4. Verify

```bash
for i in 1 2; do curl -s -o /dev/null -D - https://www.example.com/ | grep -iE 'cf-cache-status|age|cache-control'; done   # MISS then HIT
curl -s -o /dev/null -D - -H 'Cookie: session=x' https://www.example.com/ | grep -i cf-cache-status                       # BYPASS
curl -s -o /dev/null -D - https://www.example.com/account/x.css | grep -iE 'cf-cache-status|cache-control'                # never HIT
```
