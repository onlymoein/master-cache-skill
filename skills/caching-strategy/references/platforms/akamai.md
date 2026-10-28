# Akamai

Last reviewed: 2026-10-27 · Applies to: Akamai Property Manager (Ion/DSA), Fast Purge API

## When to read this

When the app is behind Akamai. Vendor-neutral concepts: `references/layers/cdn-concepts.md`. Several Akamai specifics (tag header limits, default TTLs, cache-key customization) weren't verified in this skill's research; confirm them in the customer's property before relying on them.

## How to detect

Terraform `akamai_property`/`akamai_property_rules`, `.edgerc`, property rule-tree JSON in the repo, response headers when debug Pragma is sent (`X-Cache`, `X-Check-Cacheable`, `X-Cache-Key`), `server: AkamaiGHost`.

## Default recipe

1. In the property, set the **Caching** behavior for HTML/API paths to honor origin headers (`CACHE_CONTROL` or `CACHE_CONTROL_AND_EXPIRES`), so the origin's per-route policy applies.
2. Origin sends explicit headers per route: `Cache-Control: no-cache` + `s-maxage=…` for public HTML; `private, no-cache` or `no-store` for personalized/sensitive.
3. Add a rule that bypasses cache (`NO_STORE`/`BYPASS_CACHE`) for authenticated paths and session cookies.
4. Turn on Tiered Distribution.
5. Use Fast Purge **invalidate** by tag for content changes; **delete** only for takedowns.

## Rules and gotchas

1. By default Akamai does not honor origin `Cache-Control`/`Expires`; property TTL rules decide. A property with a long TTL rule on `/*` will cache personalized pages regardless of origin headers. Audit the rule tree.
2. When honoring origin headers, `Cache-Control` wins over `Expires`; origin `no-store`/bypass directives override.
3. Akamai supports `s-maxage` for downstream CDNs: on conflict it caches using `s-maxage` and forwards both directives.
4. Fast Purge: **invalidate** marks stale (revalidate next request; can serve stale if origin is unreachable); **delete** forces a full refetch (more origin load; use for compliance/copyright takedowns). ECCU only invalidates.
5. Cache tags: Akamai uses an `Edge-Cache-Tag` response header; secondhand sources cite limits of 8,192 characters and 128 tags per object. Verify in current docs and stay ≤ 50 lowercase tags.
6. Fast Purge propagation is commonly cited at about 5 s.
7. The "fast invalidate" behavior is deprecated; use the Fast Purge API.

## Purge API

Fast Purge v3 endpoints exist for invalidate and delete by URL, CP code and cache tag, plus a rate-limit status endpoint. Use the Akamai CLI (`akamai purge invalidate --tag product-123`) or EdgeGrid-signed API calls from the CMS webhook handler; batch tags per request.

## Status headers

Send `Pragma: akamai-x-cache-on, akamai-x-cache-remote-on, akamai-x-check-cacheable, akamai-x-get-cache-key, akamai-x-get-true-cache-key` to get `X-Cache` (`TCP_HIT`, `TCP_MISS`, `TCP_REFRESH_HIT`, …), `X-Check-Cacheable` and the cache key. Restrict debug Pragma handling in production if the property allows it.

## Version notes

- Fast-invalidate property behavior deprecated in favor of Fast Purge.
- Tiered Distribution is GA in the GA rule format.

## Verify

```bash
curl -s -o /dev/null -D - -H 'Pragma: akamai-x-cache-on, akamai-x-check-cacheable, akamai-x-get-cache-key' \
  https://www.example.com/page | grep -iE 'x-cache|x-check-cacheable|x-cache-key|cache-control'
curl -s -o /dev/null -D - -H 'Cookie: session=x' -H 'Pragma: akamai-x-cache-on' https://www.example.com/account | grep -i x-cache
```

## Sources

- [Akamai: learn about caching](https://techdocs.akamai.com/property-mgr/docs/know-caching)
- [Akamai Caching behavior](https://techdocs.akamai.com/property-mgr/reference/ga-caching)
- [Akamai purge methods](https://techdocs.akamai.com/purge-cache/docs/purge-methods)
- [Akamai Fast Purge API](https://techdocs.akamai.com/purge-cache/reference/api-summary)
- [Akamai Tiered Distribution](https://techdocs.akamai.com/property-mgr/reference/ga-tiered-distribution)
- [Akamai Terraform: fast invalidate (deprecated)](https://techdocs.akamai.com/terraform/docs/ga-fast-invalidate)
