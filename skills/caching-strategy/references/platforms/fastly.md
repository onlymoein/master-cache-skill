# Fastly

Last reviewed: 2026-10-27 · Applies to: Fastly Deliver (VCL) and Compute

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- TTLs and headers
- Purging
- Stale serving, collapsing, shielding
- ESI and edge data
- Status headers
- Version notes
- Verify
- Sources

## When to read this

When the app is fronted by Fastly (including Adobe Commerce Cloud and other platforms that bundle it). Vendor-neutral concepts: `references/layers/cdn-concepts.md`.

## How to detect

`fastly.toml` (Compute), Terraform `fastly_service_vcl`/`fastly_service_compute`, `Surrogate-Key`/`Surrogate-Control` in code, response headers `x-served-by: cache-…`, `x-cache`, `x-cache-hits`, `via: 1.1 varnish`.

## Default recipe

```http
# Purge-driven content: long edge TTL, soft purge on change, SWR/SIE for resilience
Cache-Control: no-cache
Surrogate-Control: max-age=31536000, stale-while-revalidate=60, stale-if-error=31536000
Surrogate-Key: product-123 category-9 all
ETag: "<hash>"

# Personalized
Cache-Control: private, no-cache
```

Soft purge on change:

```bash
curl -X POST "https://api.fastly.com/service/$SERVICE_ID/purge/product-123" \
  -H "Fastly-Key: $FASTLY_API_TOKEN" -H "Fastly-Soft-Purge: 1"
```

VCL details: `assets/snippets/cdn/fastly-surrogate-keys.vcl`.

## Rules and gotchas

1. Fastly caches any syntactically valid response by default, including errors. Set explicit `Cache-Control`/`Surrogate-Control` on errors, or handle 5xx in VCL (serve stale, else cache the error for ~1 s so collapsed waiters get an answer).
2. `Cache-Control: private` means "don't store" at Fastly.
3. Purge-all can't be soft, and it overrides stale-if-error. Tag every object with a constant `all` key and soft-purge that instead; avoid purge-all during origin incidents.
4. `Surrogate-Key` header limit is 16 KB; keys past the limit are silently dropped and can never be purged. Individual keys ≤ 1 KB. Keep ≤ 50 lowercase keys per response.
5. Grace isn't configured by default. The UI "serve stale" setting defaults to 43,200 s (12 h) and conflicts with custom-VCL stale-if-error; use one or the other.
6. If the origin is unreachable, Fastly goes straight to `vcl_error`; serve stale there too.
7. Purge rate: about 100,000 purges/hour/customer, counted separately for key and URL purges (soft and hard reportedly share the limit). One key purge counts once regardless of objects tagged.
8. Use purge-scoped API tokens (`purge_select` for URL/key; `purge_all` only where needed).

## TTLs and headers

- Precedence: `Surrogate-Control` > `Cache-Control: s-maxage` > `Cache-Control: max-age` > `Expires`. VCL `beresp.ttl` overrides headers.
- Fastly strips `Surrogate-Control` before responding to clients, so browsers only see `Cache-Control`.
- Default TTL when the origin sends nothing is commonly cited as 3,600 s; verify for the service, and don't rely on it: always send explicit headers.

## Purging

| Type | API |
|---|---|
| Single key | `POST /service/{service_id}/purge/{surrogate_key}` |
| Many keys | `POST /service/{service_id}/purge` with up to 256 keys (JSON body or `Surrogate-Key: k1 k2` request header) |
| URL | `PURGE https://www.example.com/path` (or API) |
| Everything | `POST /service/{service_id}/purge_all` (hard only) |

Add `Fastly-Soft-Purge: 1` to key and URL purges to mark stale instead of deleting: the next user gets stale while the origin is refetched.

## Stale serving, collapsing, shielding

- Request collapsing is on by default.
- `beresp.stale_if_error` is equivalent to `beresp.grace`; VCL grace overrides `stale-if-error` in headers.
- Pattern in `vcl_fetch`: on 5xx, `return(deliver_stale)` if a stale object exists; otherwise cache the error for 1 s.
- Configure a shield POP near the origin to collapse fills across POPs. Shielding runs VCL twice (edge and shield); account for that in custom logic (details not covered here; check Fastly docs).

## ESI and edge data

- VCL ESI supports only `include`, `comment`, `remove`; tags are processed sequentially; max 256 includes per request; ESI can't parse origin-compressed bodies.
- Fastly's Compute ESI library adds `esi:choose`, `esi:try` and variables.
- KV Store: durable, eventually consistent; recently changed keys can take up to ~300 ms to read. Config Store: small, Compute-only, read-only at the edge, ~1 ms reads. See `references/layers/serverless-edge-data.md`.

## Status headers

- `X-Cache: HIT|MISS` (one value per cache in the path, e.g. `MISS, HIT` with shielding), `X-Cache-Hits`, `X-Served-By` (POP IDs), `Age`.
- Send `Fastly-Debug: 1` on a request to get extra debug headers (TTL, state); keep it to testing.

## Version notes

- Compute ESI library extends ESI beyond VCL's subset.

<details><summary>Old patterns</summary>

- Purge-all on every deploy (can't be soft; drops stale-if-error protection).
- Relying on the dashboard "serve stale" toggle and custom grace VCL at the same time.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://www.example.com/p/123 | grep -iE 'x-cache|x-served-by|age|cache-control'
curl -s -o /dev/null -D - -H 'Fastly-Debug: 1' https://www.example.com/p/123 | grep -iE 'fastly|surrogate'
# Soft purge, then request: expect stale served while refetching, then fresh content
```

## Sources

- [Fastly: about cache control headers](https://www.fastly.com/documentation/guides/full-site-delivery/caching/about-cache-control-headers)
- [Fastly Surrogate-Control](https://developer.fastly.com/reference/http-headers/Surrogate-Control/)
- [Fastly purging with surrogate keys](https://www.fastly.com/documentation/guides/full-site-delivery/purging/purging-with-surrogate-keys/)
- [Fastly soft purges](https://docs.fastly.com/en/guides/soft-purges)
- [Fastly purging API](https://www.fastly.com/documentation/reference/api/purging/)
- [Fastly serving stale](https://www.fastly.com/documentation/solutions/tutorials/full-site-delivery/serving-stale/)
- [Fastly ESI](https://www.fastly.com/documentation/reference/vcl/statements/esi/)
- [Fastly edge data stores](https://www.fastly.com/documentation/guides/compute/edge-data-storage/about-edge-data-stores/)
