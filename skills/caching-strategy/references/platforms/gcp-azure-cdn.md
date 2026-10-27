# Google Cloud CDN and Azure Front Door

Last reviewed: 2026-10-27 · Applies to: Google Cloud CDN (backend services/buckets), Azure Front Door (Standard/Premium)

## Contents

- When to read this
- How to detect
- Google Cloud CDN
- Azure Front Door
- Verify
- Sources

## When to read this

When the app sits behind Google Cloud CDN or Azure Front Door. Vendor-neutral concepts: `references/layers/cdn-concepts.md`. Google Media CDN wasn't covered by this skill's research; check its docs.

## How to detect

Terraform `google_compute_backend_service`/`google_compute_backend_bucket` with `enable_cdn = true` and `cdn_policy`, `google_network_services_edge_cache_*` (Media CDN); Terraform `azurerm_cdn_frontdoor_*`, Bicep/ARM `Microsoft.Cdn/profiles`; response headers `via: 1.1 google`, `x-azure-ref`, `x-cache` on Front Door.

## Google Cloud CDN

### Default recipe

```hcl
resource "google_compute_backend_service" "web" {
  # ...
  enable_cdn = true
  cdn_policy {
    cache_mode         = "USE_ORIGIN_HEADERS"   # origin decides per route
    serve_while_stale  = 86400
    request_coalescing = true
    negative_caching   = true
    cache_key_policy {
      include_host           = true
      include_protocol       = true
      include_query_string   = true
      query_string_whitelist = ["page", "q"]
    }
  }
}
```

### Rules and gotchas

1. Cache modes: `CACHE_ALL_STATIC` (default; images, video, audio, JS, CSS; no HTML), `USE_ORIGIN_HEADERS` (responses without cache headers aren't cached), `FORCE_CACHE_ALL` (caches everything and ignores `private`/`no-store`/`no-cache`; never use it on apps with personalized responses).
2. Default TTL 3,600 s in `CACHE_ALL_STATIC` and `FORCE_CACHE_ALL` (not settable in `USE_ORIGIN_HEADERS`); max TTL 31,622,400 s.
3. `request_coalescing` merges concurrent fills; turn it on.
4. Negative caching defaults: 300/301/308 → 10 min; 404/410/451 → 120 s; 405/421/501 → 60 s. A custom `negative_caching_policy` replaces all defaults.
5. `serve_while_stale` exists; its default (commonly 86,400 s) wasn't confirmed. Set it explicitly.
6. Use signed URLs/cookies for private content rather than caching per user.

## Azure Front Door

### Default recipe

- Origin sends explicit `Cache-Control` on every response, especially dynamic routes (`private, no-cache` or `no-store` for personalized).
- Route caching: query string behavior "Include specified" with an allow-list for public pages; "Ignore query string" for hashed assets.
- Rules Engine: bypass cache when a session cookie or `Authorization` is present.

### Rules and gotchas

1. With "honor origin", a response with no cache directive is cached anywhere from 1 to 3 days. Every dynamic route must send explicit headers.
2. "Override always" replaces the origin TTL only if the response is cacheable.
3. Query string modes: Ignore, Use (each unique URL cached; parameter order doesn't matter), Ignore specified, Include specified.
4. Purge is query-string agnostic (purging a URL purges all its query variants); wildcard paths like `/*` work; wildcard domains don't (list subdomains); propagation up to 10 minutes. Tag-based purge wasn't confirmed.
5. Edge compression doesn't work with chunked transfer encoding. Range requests with `Accept-Encoding` where the origin returns differing lengths cause 503s: disable origin compression or strip `Accept-Encoding` for range requests.

## Verify

```bash
curl -s -o /dev/null -D - https://www.example.com/page | grep -iE 'age|cache-control|x-cache|via'
gcloud compute backend-services describe web --global --format='yaml(cdnPolicy)'
az afd route show --profile-name P --endpoint-name E --route-name R -g RG --query 'cacheConfiguration'
```

## Sources

- [Google Cloud CDN CachePolicy reference](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy)
- [Google BackendServiceCdnPolicy](https://googleapis.dev/ruby/google-apis-compute_v1/v0.105.0/Google/Apis/ComputeV1/BackendServiceCdnPolicy.html)
- [Azure Front Door caching](https://learn.microsoft.com/azure/frontdoor/front-door-caching)
- [Azure Front Door cache purge](https://learn.microsoft.com/azure/frontdoor/cache-purge)
- [Azure CDN guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/cdn)
