# CDN, Edge & Reverse-Proxy Caching (state as of October 2026)

> Research method note: vendor doc sites were not directly fetchable from this sandbox (WebFetch DNS failures; egress proxy 403 for developers.cloudflare.com / docs.fastly.com). Primary sources used: (a) Cloudflare's official docs search MCP (returned live doc text, many pages "Last updated" Aug–Oct 2026), (b) Vercel's official docs search MCP, (c) Netlify's official `netlify-caching` agent context via the Netlify MCP server, (d) web search summaries of official docs for Fastly, AWS CloudFront, Akamai, Google Cloud CDN, Azure Front Door, bunny.net, Fly.io, nginx, Varnish, Souin, HAProxy. Web-search-derived items are summaries of the cited pages, not verbatim reads; where a summary came from a third-party page, that is flagged. Config snippets in "Inferences" sections are composed by the researcher from the cited directives and must be verified before shipping.

---

## 1. Core CDN concepts per vendor: cache keys, default cacheability, honoring origin vs. overrides, CDN-specific headers

### Takeaway
Every major CDN now supports "targeted" CDN-only cache headers with a strict precedence (`<Vendor>-CDN-Cache-Control` > `CDN-Cache-Control` > `Cache-Control`; Fastly/Akamai use `Surrogate-Control`/`s-maxage`), but defaults differ sharply: Cloudflare caches by file extension only (never HTML/JSON by default), Netlify and Vercel cache nothing dynamic unless headers opt in, Google Cloud CDN defaults to CACHE_ALL_STATIC, Akamai ignores origin Cache-Control unless the Caching behavior enables it, and Azure Front Door caches 1–3 days when origin sends no directive. The skill should always ask "which CDN?" before recommending headers.

### Cited Findings

**Cloudflare – default cacheability**
- Cloudflare caches based on file extension, not MIME type; HTML and JSON are NOT cached by default. — [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior)
- Default cached extensions: `7z, avi, avif, apk, bin, bmp, bz2, class, css, csv, doc, docx, dmg, ejs, eot, eps, exe, flac, gif, gz, ico, iso, jar, jpg, jpeg, js, mid, midi, mkv, mp3, mp4, ogg, otf, pdf, pict, pls, png, ppt, pptx, ps, rar, svg, svgz, swf, tar, tif, tiff, ttf, webm, webp, woff, woff2, xls, xlsx, zip, zst`. — [Cloudflare Page Rules migration](https://developers.cloudflare.com/cache/how-to/cache-rules/page-rules-migration/)
- Default edge TTLs when origin sends no Cache-Control/Expires: 200/206/301 → 120 min; 302/303 → 20 min; 404/410 → 3 min; all other status codes not cached. — [Cloudflare cache by status code](https://developers.cloudflare.com/cache/how-to/configure-cache-status-code/)
- Max cacheable object: 512 MB on Free/Pro/Business; 5 GB default on Enterprise (raisable). Origin Range Requests check the full `Content-Range` size against this limit. — [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/); [Range requests](https://developers.cloudflare.com/cache/reference/range-requests/)
- URL limit 16 KB, request headers 128 KB total, response headers 128 KB total. — [Cloudflare connection limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/)
- Not cached (BYPASS) when: response > size limit; `no-store` or bare `private` in `Cloudflare-CDN-Cache-Control`/`CDN-Cache-Control`/`Cache-Control`; `Set-Cookie` present (default config); `Vary: *`; request has `Authorization` and Origin Cache Control (OCC) is on, unless Cache-Control also has `public`, `s-maxage`, or `must-revalidate`. — [Cloudflare cache responses](https://developers.cloudflare.com/cache/concepts/cache-responses/); [Investigating uncached responses](https://developers.cloudflare.com/cache/troubleshooting/investigating-uncached-responses/)
- `no-cache`, `max-age=0`, `s-maxage=0` → with OCC on (default and non-disableable on Free/Pro/Business) Cloudflare caches and revalidates (REVALIDATED/EXPIRED); with OCC off (Enterprise default) they produce BYPASS. — [Cloudflare cache responses](https://developers.cloudflare.com/cache/concepts/cache-responses/); [Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/)
- `Cache-Control: private="Set-Cookie"` / `no-cache="Set-Cookie"` keeps the response cacheable and drops only the named header; an Edge TTL rule "Ignore cache-control header and use this TTL" overrides `no-store`/`private` and strips `Set-Cookie`. — [Investigating uncached responses](https://developers.cloudflare.com/cache/troubleshooting/investigating-uncached-responses/)
- `max-age`, `s-maxage`, `stale-while-revalidate` must be integers; docs say floats are ignored and may cause bypass — but the cache changelog for Cloudflare's new cache proxy architecture says floats are now rounded down. **Conflict between pages; recommend integers.** — [Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/); contradicted by [Cloudflare cache changelog](https://developers.cloudflare.com/changelog/product/cache/)
- New cache-proxy behavior changes: `Vary: *` always bypasses; `Set-Cookie` now stripped on MISS and EXPIRED (not only HIT) for cacheable assets; uncacheable bypass responses are streamed unbuffered. — [Cloudflare cache changelog](https://developers.cloudflare.com/changelog/product/cache/)
- Since May 26 2026, `BYPASS` is returned consistently whenever a response is not cacheable (previously some cases, e.g. oversized objects, showed `MISS` forever). `MISS` now means cacheable-but-absent; `DYNAMIC` means ineligible at request time (no cache lookup). — [BYPASS changelog](https://developers.cloudflare.com/changelog/post/2026-05-26-bypass-status-for-uncacheable-responses/); [Cache responses](https://developers.cloudflare.com/cache/concepts/cache-responses/)

**Cloudflare – Cache Rules (Page Rules replacement), overrides**
- Cache Rules are the configuration surface; when migrating from Page Rules note that "Eligible for cache" enables Cache Everything by default (Page Rules required opting in). To mimic old behavior, create rule 1 "bypass everything" then rule 2 "eligible for cache" for the default extension list. Multiple matching Cache Rules stack. — [Page Rules migration](https://developers.cloudflare.com/cache/how-to/cache-rules/page-rules-migration/)
- Cache Rule matching fields include `http.request.uri.path`, `http.request.uri.query`, `http.cookie`, `http.host`, `http.request.headers`, `http.request.cookies`, `http.request.uri.path.extension`, `ip.src.asnum`, bot-management fields; operators include wildcard, matches regex, starts with, is in, is in list (Enterprise for hostname lists). — [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
- Cache Response Rules (launched Mar 24 2026) run on the origin response (phase `http_response_cache_settings`): modify Cache-Control directives (`set_cache_control`, optional `cloudflare_only`), manage cache tags (including converting another CDN's tag header during migration), strip `Set-Cookie` before caching. On conflict they win over Cache Rules; their Cache-Control beats origin `CDN-Cache-Control`/`Cloudflare-CDN-Cache-Control`; if any matches, OCC defaults on; last matching rule wins. They can make cacheable content `no-store` but only Cache Rules decide eligibility. — [Cache Response Rules](https://developers.cloudflare.com/cache/how-to/cache-response-rules/); [changelog](https://developers.cloudflare.com/changelog/post/2026-03-24-cache-response-rules/)
- Response Header Transform Rules that modify `cache-control`/`CDN-Cache-Control`/`Cloudflare-CDN-Cache-Control` do NOT change caching (cache decision happens first) — use Cache Rules/Cache Response Rules. — [Response header modification](https://developers.cloudflare.com/rules/transform/response-header-modification/)
- Workers `fetch()` can override Cache Rules per request via the `cf` object (since Apr 2025). — [Cloudflare cache changelog](https://developers.cloudflare.com/changelog/product/cache/)

**Cloudflare – cache keys**
- Key option availability: Cache Deception Armor, Cache by device type, Ignore query string, Sort query string — all plans; custom Query string include/exclude, Headers, Cookie, Host, User features (device/geo/lang) — Enterprise only ("Ignore query string" also for pay-as-you-go). — [Cloudflare cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/); [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
- Query string: `include: "*"` (default) or `exclude: "*"` (ignore all); exactly one of include/exclude; max 100 query params in a custom key; Sort query string is off by default and can break order-dependent endpoints (e.g., `/wp-admin/load-scripts.php`). — [Cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/); [Query String Sort](https://developers.cloudflare.com/cache/advanced-configuration/query-string-sort/)
- Restricted headers in custom keys (`accept`, `accept-charset`, `accept-encoding`, `accept-datetime`, `accept-language`, `referer`, `user-agent`) require 1–3 specific values; `__cf*` cookies cannot be included; "Check presence of" option includes presence without value. — [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/); [Cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/)
- User features: `device_type` (mobile/desktop/tablet from UA), `geo` (country), `lang` (first language in Accept-Language). With URL normalization on, also enable "Normalize URLs to origin" when using custom keys/device type to prevent poisoning. — [Cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/)
- API shape (`set_cache_settings` action_parameters):
  ```json
  "cache": true,
  "cache_key": {
    "ignore_query_strings_order": true,
    "cache_deception_armor": true,
    "custom_key": {
      "query_string": { "include": ["*"] },
      "header": { "include": ["header1"], "check_presence": ["header_1"], "contains": { "accept-encoding": ["br","zstd"] } },
      "cookie": { "include": ["cookieName1"], "check_presence": ["cookie_1"] },
      "user": { "device_type": true, "geo": true, "lang": true },
      "host": { "resolved": false }
    }
  }
  ```
  — [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
- Terraform example with `edge_ttl { mode = "override_origin", default = 60, status_code_ttl = [...] }`, `browser_ttl { mode = "respect_origin" }`, `serve_stale { disable_stale_while_updating = true }`, `respect_strong_etags = true`, custom key. — [Cache Rules Terraform example](https://developers.cloudflare.com/cache/how-to/cache-rules/terraform-example/)
- Prefetch URLs always use the default cache key → incompatible with custom cache keys. Cloudflare Trace (Nov 2025) shows the exact computed cache key. — [Cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/); [changelog](https://developers.cloudflare.com/changelog/product-group/application-performance/3/)
- Vary in Cache Rules (Jul 2 2026, all plans): origin's `Vary` header names become key components; per-header action `normalize` (e.g., `Accept-Language: en-US, fr;q=0.8` and `fr;q=0.8, en-GB` → same key `en,fr`), `passthrough` (raw value), or `bypass`. `default` required. `accept.media_types` ≤10, `accept-language.languages` ≤20, ≤50 header entries. Normalized `Accept`/`Accept-Language` (and `Accept-Encoding` with Respect Strong ETags) are also rewritten on the origin request. Workers subrequests: `cf.vary` (Jun 2026) takes precedence. — [Cloudflare Vary](https://developers.cloudflare.com/cache/concepts/vary/); [Vary changelog](https://developers.cloudflare.com/changelog/post/2026-07-02-vary-for-cache-rules/); [Request cf.vary](https://developers.cloudflare.com/workers/runtime-apis/request/); [cf.vary changelog](https://developers.cloudflare.com/changelog/post/2026-06-28-cf-vary-request-option/)

**Cloudflare – CDN-specific headers**
- Precedence: `Cloudflare-CDN-Cache-Control` (consumed and stripped, never sent downstream) > `CDN-Cache-Control` (respected and passed downstream to other CDNs) > `Cache-Control` (passed to clients). Use `Cloudflare-CDN-Cache-Control` for a longer edge TTL without leaking it downstream. — [Workers cache configuration – header precedence](https://developers.cloudflare.com/workers/cache/configuration/); [Investigating uncached responses](https://developers.cloudflare.com/cache/troubleshooting/investigating-uncached-responses/)
- Setting `Cloudflare-CDN-Cache-Control` turns OCC on regardless of setting, so Authorization-header logic applies (only `s-maxage`, `must-revalidate`, `public` allowed, else BYPASS). — [Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/)
- `Cache-Tag` header: comma-separated, whitespace trimmed, duplicate/trailing commas removed; stripped before reaching visitors; aggregate header ≤16 KB (~1,000 tags); purge API tag ≤1,024 chars; printable ASCII, no spaces; case-insensitive. — [Purge by cache-tags](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/)

**Vercel**
- `Vercel-CDN-Cache-Control` (Vercel only, not forwarded) > `CDN-Cache-Control` (Vercel + downstream CDNs) > `Cache-Control` (all, incl. browser). Example: `Cache-Control: max-age=10`, `CDN-Cache-Control: max-age=60`, `Vercel-CDN-Cache-Control: max-age=3600`. — [Vercel CDN cache](https://vercel.com/docs/caching/cdn-cache); [Vercel cache-control headers](https://vercel.com/docs/caching/cache-control-headers)
- `s-maxage` range on Vercel CDN: 1 s to 31,536,000 s (1 year). Vercel's proxy consumes `stale-while-revalidate` and `stale-if-error` and strips them from the client response. — [Vercel cache-control headers](https://vercel.com/docs/caching/cache-control-headers)
- External rewrites: projects created before April 6, 2026 must opt in with `x-vercel-enable-rewrite-caching: 1` to cache external rewrite responses (respecting upstream `cache-control`/`CDN-Cache-Control`/`Vercel-CDN-Cache-Control`); `0` opts out; you can set `CDN-Cache-Control` in `vercel.json` `headers` when the upstream can't be changed. (Implies newer projects cache external rewrites by default.) — [Vercel rewrites](https://vercel.com/docs/rewrites)
  ```json
  {
    "rewrites": [{ "source": "/api/:path*", "destination": "https://api.example.com/:path*" }],
    "headers": [{ "source": "/api/:path*", "headers": [
      { "key": "x-vercel-enable-rewrite-caching", "value": "1" },
      { "key": "CDN-Cache-Control", "value": "max-age=60" }
    ]}]
  }
  ```

**Netlify**
- Dynamic responses (Functions, Edge Functions, proxies) are NOT cached by default; opt in with `Netlify-CDN-Cache-Control` (Netlify only) > `CDN-Cache-Control` > `Cache-Control` (latter two pass downstream). Defaults: static `Netlify-CDN-Cache-Control: public, s-maxage=31536000, must-revalidate`; dynamic `Cache-Control: public, max-age=0, must-revalidate`. Static assets are fresh ≤1 year and a shorter max-age is ignored (change only on deploy or purge). Only GET is cached. Basic-auth on ANY page disables caching for the entire site. `netlify dev` does not emulate the CDN cache. — Netlify official `netlify-caching` agent context retrieved via Netlify MCP server (Oct 2026; no public URL returned)
- `Netlify-Vary: query=item_id|page, country=es+de|us, cookie=ab_test|is_logged_in, language=en|es+pt, header=Device-Type`. Without `query=`, the full query string is the key (utm_*, fbclid fragment the cache). Cannot vary by header on `Accept*`, `Cache-Control`, `Connection`, `Content-Length`, `Cookie`, `Host`, `If-*`, `Range`, `Referer`, `Upgrade`, `User-Agent`. A URL must return the same `Netlify-Vary` on every response — first cached response's instructions win. — Netlify `netlify-caching` agent context (Netlify MCP)
- `durable` directive (serverless only, not Edge Functions) stores in Netlify's shared durable cache so other edge nodes reuse it instead of re-invoking the function; eventually consistent; co-located with functions region; Next Runtime ≥5.5.0 uses it automatically. — Netlify `netlify-caching` agent context (Netlify MCP)

**Fastly**
- TTL precedence: `Surrogate-Control` > `Cache-Control: s-maxage` > `Cache-Control: max-age` > `Expires`; Fastly strips `Surrogate-Control` before sending to end users; VCL `beresp.ttl` overrides headers. — [Fastly about cache control headers](https://fastly.com/documentation/guides/full-site-delivery/caching/about-cache-control-headers); [Fastly Surrogate-Control reference](https://developer.fastly.com/reference/http-headers/Surrogate-Control/); [Fastly community thread](https://community.fastly.com/t/unexpected-ttl-fastly-debug-ttl/3623) (forum, not official)
- `Cache-Control: private` means "don't store" at Fastly. — [Fastly about cache control headers](https://quic.fastly.com/documentation/guides/full-site-delivery/caching/about-cache-control-headers)
- Fastly by default accepts and caches any syntactically valid HTTP response, including errors. — [Fastly serving stale tutorial](https://www.fastly.com/documentation/solutions/tutorials/full-site-delivery/serving-stale/)

**AWS CloudFront**
- Cache policies define cache key (query strings, headers, cookies) + TTLs; origin request policies define what is forwarded to origin without entering the key. Legacy `ForwardedValues`/`QueryStringCacheKeys` are deprecated in favor of these policies. Headers listed in an origin request policy are forwarded even when the cache policy's HeaderBehavior is `none`. With compression enabled in the cache policy, don't also list `Accept-Encoding` in the origin request policy. — [CloudFront API ForwardedValues](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_ForwardedValues.html); [boto3 create_cache_policy](https://boto3.readthedocs.io/reference/services/cloudfront/client/create_cache_policy.html)
- Managed `CachingOptimized` policy (ID `658327ea-f89d-4fab-a63d-7e88639e58f6`): min TTL 1 s, default 86,400 s, max 31,536,000 s; no query strings or cookies in key; only normalized Accept-Encoding header. AWS warns that policies with min TTL > 0 can override origin `no-cache`/`no-store`/`private`. — [CloudFront managed cache policies (es)](https://docs.aws.amazon.com/es_es/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html); [(zh)](https://docs.aws.amazon.com/zh_cn/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
- Forwarding/caching on all query strings increases origin requests. — [CloudFront API ForwardedValues](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_ForwardedValues.html)

**Akamai**
- By default Akamai edge servers do NOT honor origin `Cache-Control`/`Expires`; enable per object via the Caching behavior with options `MAX_AGE`, `CACHE_CONTROL`, `EXPIRES`, `CACHE_CONTROL_AND_EXPIRES`. Cache-Control wins over Expires on conflict; origin `NO_STORE`/`BYPASS_CACHE` override. Supports `s-maxage` (RFC 7234) to instruct downstream CDNs; on conflict Akamai caches using s-maxage and sends both directives downstream. — [Akamai: Learn about caching](https://techdocs.akamai.com/property-mgr/docs/know-caching); [Akamai Caching behavior (GA)](https://techdocs.akamai.com/property-mgr/reference/ga-caching)

**Google Cloud CDN**
- `cdnPolicy.cacheMode` defaults to `CACHE_ALL_STATIC` (images, video, audio, JS, CSS; HTML/dynamic not cached). `USE_ORIGIN_HEADERS`: responses without cache headers are not cached. `FORCE_CACHE_ALL`: caches everything, ignores `private`/`no-store`/`no-cache` (risk of caching per-user content); `defaultTtl` overwrites response TTLs. Default TTL 3,600 s (CACHE_ALL_STATIC and FORCE_CACHE_ALL; not settable in USE_ORIGIN_HEADERS); max TTL 31,622,400 s. — [Google Compute CachePolicy reference](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy); [BackendBucketCdnPolicy](https://docs.cloud.google.com/dotnet/docs/reference/Google.Cloud.Compute.V1/3.22.0/Google.Cloud.Compute.V1.BackendBucketCdnPolicy)

**Azure Front Door**
- Query-string modes: Ignore Query String; Use Query String (each unique URL is its own entry; parameter order doesn't matter); Ignore Specified / Include Specified. "Honor origin" always honors origin directives — and if origin sends no directive, Front Door caches content anywhere from 1 to 3 days. "Override always" replaces origin TTL only if the response is cacheable. — [Azure Front Door caching](https://learn.microsoft.com/azure/frontdoor/front-door-caching)
- Edge compression unsupported with chunked transfer encoding; byte-range requests with Accept-Encoding that yield differing origin content-lengths cause 503 — disable origin compression or strip Accept-Encoding for range requests via Rules Engine. — [Azure Front Door caching](https://learn.microsoft.com/azure/frontdoor/front-door-caching)

### Inferences
- Portable header recipe (works on Cloudflare, Vercel, Netlify, and any RFC 9213-aware CDN): `Cache-Control: public, max-age=0, must-revalidate` (browser) + `CDN-Cache-Control: max-age=300, stale-while-revalidate=86400` (shared CDNs) + optional vendor-specific header for a longer edge-only TTL. **Exception: on Cloudflare do not use `s-maxage` with SWR** (see §3) — use `max-age` in CDN-Cache-Control.
- Decision rule "is HTML cached on my CDN by default?": Cloudflare no (needs Cache Rule "Eligible for cache"); Netlify/Vercel dynamic no (needs header); GCP CACHE_ALL_STATIC no; Azure Front Door **yes, 1–3 days if no directive** (always send explicit Cache-Control from origin behind AFD); Akamai depends on property TTL rules, not origin headers, unless Caching behavior honors origin.
- Cache-key hygiene rule: strip/ignore marketing params (`utm_*`, `fbclid`, `gclid`) at the edge (Cloudflare exclude list on Enterprise or a Snippet/Worker URL rewrite on other plans; Netlify `Netlify-Vary: query=<allowlist>`; CloudFront cache policy QueryStringBehavior `whitelist`), and never put high-cardinality cookies/headers in the key.
- Illustrative Cloudflare Cache Rule expression (verify syntax) to cache anonymous HTML only:
  `(http.host eq "www.example.com" and not starts_with(http.request.uri.path, "/account") and not http.cookie contains "session=")` → Eligible for cache, Edge TTL "Use cache-control header if present, else 300s".
- Illustrative CloudFront `CachePolicyConfig` (schema per boto3 `create_cache_policy`; verify):
  ```json
  { "Name": "html-anon", "MinTTL": 0, "DefaultTTL": 300, "MaxTTL": 86400,
    "ParametersInCacheKeyAndForwardedToOrigin": {
      "EnableAcceptEncodingGzip": true, "EnableAcceptEncodingBrotli": true,
      "HeadersConfig": { "HeaderBehavior": "none" },
      "CookiesConfig": { "CookieBehavior": "none" },
      "QueryStringsConfig": { "QueryStringBehavior": "whitelist", "QueryStrings": { "Quantity": 2, "Items": ["page","q"] } } } }
  ```
  Use `MinTTL: 0` when origin may send `no-store`/`private`, otherwise CloudFront may override them.

### Gaps
- Fastly default TTL when no headers (commonly cited as 3,600 s) was not confirmed in this session.
- Vercel CDN default cache-key composition (query string/header handling) and max cacheable object size were not found in Vercel docs search.
- Akamai Cache ID Modification (cache-key customization) and Akamai default TTL behavior were not retrieved.
- Google Media CDN specifics were not researched (no results retrieved).

---

## 2. Purging / invalidation per vendor (URL, tag, prefix, everything; soft vs hard; latency; limits)

### Takeaway
2026 brought soft-purge/"invalidate" parity: Cloudflare added `invalidate_cache` (Sep 2026), Vercel distinguishes `invalidateByTag` (serve stale) from `dangerouslyDeleteByTag`, Fastly has `Fastly-Soft-Purge: 1`, Akamai has invalidate vs delete, and CloudFront finally added tag-based invalidation (Apr 2026). Tag/surrogate-key purging should be the default invalidation design; URL purge only for one-offs; prefer soft purge unless content must never be served again (legal/security).

### Cited Findings

**Cloudflare**
- All purge methods (URL, hostname, tag, prefix, everything) available on all plans since Apr 2025. — [Cloudflare purge-for-all changelog](https://developers.cloudflare.com/changelog/post/2025-04-01-purge-for-all/)
- Per-account limits (hostname/tag/prefix/everything): Free 5 req/min (bucket 25); Pro 5 req/s (bucket 25); Business 10 req/s (bucket 50); Enterprise 50 req/s (bucket 500); max 100 operations per request. Single-file: Free 800 URLs/s, Pro/Business 1,500 URLs/s, Enterprise 3,000 URLs/s; 100 URLs/request (Enterprise 500). Limits shared across same-plan zones in an account; token bucket. — [Cloudflare purge cache](https://developers.cloudflare.com/cache/how-to/purge-cache/)
- Instant Purge propagates globally in ~150 ms. — [Cloudflare distributed web performance reference architecture](https://developers.cloudflare.com/reference-architecture/diagrams/content-delivery/distributed-web-performance-architecture/)
- Invalidate (soft purge, Sep 28 2026): `POST /zones/{zone_id}/invalidate_cache` with same body as purge (`files`, `tags`, `hosts`, `prefixes`, `purge_everything`); marks stale; next request revalidates (304 reuses body; requires origin ETag/Last-Modified); can serve stale while revalidating or on origin 5xx/unreachable; counts against purge limits. Use purge when content must not be served again. — [Cloudflare invalidate cache](https://developers.cloudflare.com/cache/guides/invalidate-cache/); [changelog](https://developers.cloudflare.com/changelog/post/2026-09-28-cache-invalidation/)
  ```bash
  curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/invalidate_cache" \
    -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
    --data '{"tags":["product-images"]}'
  ```
- If the cache key includes headers, URL purge/invalidate must include them: `{"files":[{"url":"https://www.example.com/images/product.jpg","headers":{"CF-Device-Type":"desktop","CF-IPCountry":"US"}}]}`; missing headers are treated as empty values. — [Cloudflare invalidate cache](https://developers.cloudflare.com/cache/guides/invalidate-cache/); [Purge by single-file](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-single-file/)
- Single-file purge gotchas: dashboard can't purge entries whose custom key includes headers/cookies; Cache Rules matching only `GET` don't match purge — add `http.request.method eq "PURGE"`; purging a 301/302 URL purges the redirect, not the destination; no wildcards; with URL-rewriting Transform Rules use the end-user URL for single-file purge but the post-transform (origin) URL for prefix purge; host lowercased, path case-sensitive. — [Purge by single-file](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-single-file/); [Purge by prefix](https://developers.cloudflare.com/cache/how-to/purge-cache/purge_by_prefix/)
- Prefix purge works on path-separator boundaries (e.g., `www.example.com/foo/bar`), 100 prefixes/request; hostname purge 100 hosts/request; tag purge 100 tags/request. With Tiered Cache, post-purge status may be EXPIRED (lower tier revalidates with upper tier). — [Purge by prefix](https://developers.cloudflare.com/cache/how-to/purge-cache/purge_by_prefix/); [Purge by hostname](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-hostname/); [Purge by tags](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/)
- Cache API (`caches.default.put`) entries: `cache.delete` only purges the local data center; URLs with Worker-set custom cache keys cannot be purged by URL — use purge everything/tag/host/prefix. — [How the cache works (Workers)](https://developers.cloudflare.com/workers/reference/how-the-cache-works/)

**Vercel**
- Tag via response header `Vercel-Cache-Tag: product-123,products` (case-sensitive, no commas inside a tag) or `addCacheTag()` from `@vercel/functions` (≤128 tags per cached response, ≤256 bytes per tag). — [Vercel CDN purge](https://vercel.com/docs/caching/cdn-cache/purge); [@vercel/functions reference](https://vercel.com/docs/functions/functions-api-reference/vercel-functions-package)
- `invalidateByTag()` / `invalidateBySrcImage()` = serve stale, refresh in background; `dangerouslyDeleteByTag()` / `dangerouslyDeleteBySrcImage()` = delete, regenerate in foreground. REST: `POST /v1/edge-cache/invalidate-by-tags`, `/v1/edge-cache/dangerously-delete-by-tags`. CLI: `vercel cache invalidate --tag a,b`, `vercel cache dangerously-delete --tag a`, `vercel cache purge [--type cdn|data]`, `vercel cache invalidate --srcimg /images/hero.png`. — [Vercel CDN purge](https://vercel.com/docs/caching/cdn-cache/purge); [Vercel CLI cache](https://vercel.com/docs/cli/cache); [REST API](https://vercel.com/docs/rest-api); [Debug cache issues](https://vercel.com/docs/caching/cdn-cache/debug-cache-issues)
- Next.js on Vercel: `revalidateTag('products')`, `revalidatePath('/products')`; `fetch(url, { next: { tags: ['blog'] } })`; Next 16 `'use cache: remote'` + `cacheTag()` + `cacheLife({ expire: 3600 })`. — [Vercel runtime cache](https://vercel.com/docs/caching/runtime-cache)
- Blob `del()` may take up to one minute to clear from Vercel CDN cache. — [Vercel Blob SDK](https://vercel.com/docs/vercel-blob/using-blob-sdk)

**Netlify**
- `Netlify-Cache-Tag: tag1,tag2` (wins over `Cache-Tag`, which passes downstream; set both when proxying through another CDN that strips Cache-Tag); case-insensitive, ≤1,024 chars/tag, ≤500 tags/response. `purgeCache()` from `@netlify/functions` (no args = whole site; `{ tags, deployAlias, domain }`); API `POST https://api.netlify.com/api/v1/purge` with `site_id`/`site_slug`, `cache_tags`. Omitting `cache_tags` purges the site; an empty `cache_tags` list purges nothing. Rate limit: each tag or site purgeable only twice per 5 s (429 beyond). Atomic deploys auto-invalidate; `Netlify-Cache-ID` opts responses out (≤500 IDs, auto-registered as tags). Cache API deletes are eventually consistent. — Netlify `netlify-caching` agent context (Netlify MCP)

**Fastly**
- Purge rate limit: average 100,000 purges/hour/customer, separately for surrogate-key and URL purges; each key counts once regardless of objects tagged. Forum answer: hard and soft purges share the limit. — [Fastly purging with surrogate keys](https://www.fastly.com/documentation/ja/guides/full-site-delivery/purging/purging-with-surrogate-keys/); [Fastly community](https://community.fastly.com/t/soft-purge-rate-limits/2843) (forum)
- Surrogate-Key limits: individual key ≤1 KB (exceeding → purge API failure; key dropped); `Surrogate-Key` header ≤16 KB (exceeding → no error, keys past the limit silently dropped and never purgeable). — [Fastly purging with surrogate keys](https://www.fastly.com/documentation/ja/guides/full-site-delivery/purging/purging-with-surrogate-keys/); [Fastly resource limits](https://docs.fastly.com/ja/guides/resource-limits)
- API: `POST /service/{service_id}/purge/{surrogate_key}` (single key); `POST /service/{service_id}/purge` with up to 256 keys in JSON body or `Surrogate-Key: key_1 key_2 key_3` request header; soft purge via `Fastly-Soft-Purge: 1` (single URL, key, bulk key — not purge-all). To soft-purge everything, tag all objects with a constant key (e.g., `all`) and soft-purge it. Token scopes: `purge_select` (URL/key) vs `purge_all`. — [Fastly purging API](https://fastly.com/documentation/reference/api/purging/); [Fastly soft purges](https://docs.fastly.com/en/guides/soft-purges); [Kestra Fastly plugin](https://kestra.io/plugins/io.kestra.plugin.fastly.purge.Key) (third-party)
- Soft purge marks stale: next user gets stale while origin is refetched. Purge-all overrides stale-if-error — avoid purge-all during 503 incidents. — [Fastly purging with surrogate keys](https://www.fastly.com/documentation/ja/guides/full-site-delivery/purging/purging-with-surrogate-keys/); [Fastly serving stale](https://docs.fastly.com/en/guides/serving-stale-content)

**AWS CloudFront**
- First 1,000 invalidation paths/month free (account-wide across distributions); each path beyond is billed; `/*`-style wildcard path counts as one path; bundling paths in one request doesn't reduce count. Third-party sources cite $0.005/path overage (verify on AWS pricing page). — [CloudFront paying for invalidation](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PayingForInvalidation.md); [sparanoid CloudFront cost note](https://sparanoid.com/note/cloudfront-cost-control/) (third-party)
- NEW (Apr 29 2026): tag-based invalidation. Opt in by adding `CacheTagConfig` naming the origin header carrying tags (distributions without it ignore tag headers); origin sends comma-separated tags; invalidate with `#` prefix e.g. `aws cloudfront create-invalidation --paths "#brand:acme"`; ≤50 tags stored per object; each tag billed as one path (shares the 1,000 free allowance); not in China regions; supported for distribution tenants via `CreateInvalidationForDistributionTenant`. — [CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md); [AWS What's New Apr 2026](https://aws.amazon.com/id/about-aws/whats-new/2026/04/cloudfront-invalidation-cache-tag/); [AWS blog](https://aws.amazon.com/blogs/networking-and-content-delivery/tag-based-invalidation-in-amazon-cloudfront)
- Concurrency limits are reported inconsistently by third parties (150 paths-or-tags/s and 1 wildcard/s vs. 3,000 in-progress paths / 15 wildcard invalidations). — [Packagist silverstripe-purge-cloudfront](https://packagist.org/packages/blueo/silverstripe-purge-cloudfront); contradicted by [sparanoid](https://sparanoid.com/note/cloudfront-cost-control/)

**Akamai**
- Fast Purge "invalidate" marks stale (revalidate next request; can serve stale if origin unreachable) vs "delete" (full refetch, more origin load; recommended for compliance/copyright takedowns). ECCU (Enhanced Content Control Utility) only invalidates. Tag-based endpoints exist for both invalidate and delete, plus a rate-limit status endpoint. — [Akamai purge methods](https://techdocs.akamai.com/purge-cache/docs/purge-methods); [Akamai Fast Purge API summary](https://techdocs.akamai.com/purge-cache/reference/api-summary)
- Fast Purge propagation ≈5 s (Akamai Terraform doc for the now-deprecated fast-invalidate behavior; older analyst note). — [Akamai Terraform ga-fast-invalidate](https://techdocs.akamai.com/terraform/docs/ga-fast-invalidate); [Frost & Sullivan](https://store.frost.com/industries/entertainment-and-media/akamai-introduces-fast-purge-solution-despite-concerns-over-speed-and-scale.html)
- Edge-Cache-Tag header limits reported secondhand as 8,192 characters and 128 tags/page. — [Drupal purge_akamai_optimizer](https://drupal.org/project/purge_akamai_optimizer) (third-party)

**Azure Front Door**
- Purge is query-string agnostic (purging a URL purges all its query variants); wildcard paths like `/*` supported; wildcard domains not supported directly (list subdomains); propagation up to 10 minutes. — [Azure Front Door cache purge](https://learn.microsoft.com/azure/frontdoor/cache-purge)

**bunny.net**
- Tag purging via origin response header `CDN-Tag`; purge API accepts `CacheTag` on the pull zone purgeCache endpoint. With Perma-Cache enabled, wildcard and tag purging do NOT work; single-URL purge deletes from Perma-Cache storage first; full pull-zone purge switches to a new storage directory (old folder must be deleted manually). Unverified third-party claim: bunny stores the whole CDN-Tag value as a single tag (no comma split). — [bunny.net purge cache](https://docs.bunny.net/cdn/purge-cache); [bunny Perma-Cache](https://bunny.net/docs/cdn/perma-cache); [bunny tag purge blog](https://bunny.net/blog/introducing-tag-based-cdn-cache-purging/); [sulu-bunny-cdn-bundle](https://packagist.org/packages/alengo/sulu-bunny-cdn-bundle) (third-party)

### Inferences
- Tag-limit lowest common denominator for a multi-CDN design: CloudFront stores only 50 tags/object, Vercel 128, Akamai ~128 (secondhand), Netlify 500, Cloudflare ~1,000 (16 KB), Fastly 16 KB header. Design tag schemes with ≤50 tags per response (e.g., `product:123`, `category:9`, `tpl:pdp`) and hash long IDs (Drupal's CloudFront module hashes tags to 6 chars) if you might move CDNs.
- Tag case sensitivity differs (Vercel case-sensitive; Cloudflare/Netlify case-insensitive) — normalize tags to lowercase in app code.
- Default to soft purge/invalidate for content updates (Cloudflare `invalidate_cache`, Vercel `invalidateByTag`, Fastly `Fastly-Soft-Purge: 1`, Akamai invalidate) because it preserves stale-if-error protection and 304 revalidation; use hard purge/delete for legal takedowns, leaked secrets, or wrong-content incidents.
- Purge ordering rule: update origin/DB first, then purge (Cloudflare explicitly warns the next request can re-cache the old version otherwise); with a two-layer setup (CDN + reverse proxy, or CDN + app data cache), purge inner layer first, then outer.
- Purge rate limits matter for CMS webhooks: Cloudflare Free allows only 5 tag purges/min — batch tags (100 per request) and debounce; Netlify 2 purges/5 s per tag.

### Gaps
- Fastly and Vercel purge propagation latency figures were not found (Fastly commonly cited ~150 ms; unverified here).
- Azure Front Door tag-based purge support: not found (a Microsoft Q&A thread asks about it; answer not retrieved).
- Exact current CloudFront invalidation overage price from AWS's pricing page not retrieved (only third-party $0.005/path).

---

## 3. Tiered caching / origin shield, request collapsing, serving stale, persistent cache, cache warming

### Takeaway
Turn on the vendor's shield tier (Cloudflare Smart Tiered Cache — free on all plans; CloudFront Origin Shield; Fastly shielding; Akamai Tiered Distribution; bunny Origin Shield) and rely on built-in request collapsing; add stale-while-revalidate + stale-if-error at the edge. Cloudflare's SWR became fully asynchronous in Feb 2026 but is silently disabled by `s-maxage`, `must-revalidate`, `proxy-revalidate`, and `no-cache`. Persistent tiers (Cloudflare Cache Reserve, Netlify durable cache, bunny Perma-Cache) protect long-tail content from LRU eviction.

### Cited Findings

**Cloudflare Tiered Cache**
- Availability: Tiered Cache and Smart Topology on all plans; Generic Global Topology, Regional Tiered Cache, Custom Topology Enterprise only. Enable via `PATCH /zones/$ZONE_ID/argo/tiered_caching {"value":"on"}`. Tiered Cache applies only to requests eligible at request time; `CacheTieredFill` log field confirms use. — [Cloudflare Tiered Cache](https://developers.cloudflare.com/cache/how-to/tiered-cache/)
- Smart Tiered Cache now falls back to Generic Tiered Cache when origin location can't be determined (Anycast-masked origins) (Aug 2025); cloud region hint (Apr 17 2026, all plans, AWS/GCP/Azure/Oracle) e.g. `aws/us-east-1` selects a primary upper tier near the cloud region plus a fallback; R2 origins get an automatic upper tier near the bucket. — [Smart Tiered fallback changelog](https://developers.cloudflare.com/changelog/post/2025-08-29-smart-tiered-cache-fallback-to-generic/); [Smart Tiered for public cloud](https://developers.cloudflare.com/changelog/post/2026-04-17-smart-tiered-cache-for-public-cloud/); [Smart Tiered for R2](https://developers.cloudflare.com/changelog/post/2024-11-20-smart-tiered-cache-for-r2/)
- Smart Tiered Cache, Regional Tiered Cache, and Cache Reserve are now packaged under "Smart Shield". Smart Tiered Cache is incompatible with Regional Services (data localization); only Generic Global and Custom respect it. — [Cloudflare Tiered Cache](https://developers.cloudflare.com/cache/how-to/tiered-cache/); [Regional Tiered Cache](https://developers.cloudflare.com/smart-shield/configuration/regional-tiered-cache/); [Data localization cache](https://developers.cloudflare.com/data-localization/how-to/cache/)
- `caches.default.put` (Workers Cache API) is not compatible with tiered caching and does not collapse requests; `fetch()` subrequests do go through Tiered Cache. — [Workers Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/); [Cache interaction with Workers](https://developers.cloudflare.com/cache/interaction-cloudflare-products/workers/)

**Cloudflare stale serving**
- Asynchronous SWR (Feb 26 2026; all Free/Pro/Business, Enterprise rolling): first request after expiry gets stale content with `UPDATING` status while background revalidation runs; then `HIT`. Requires origin `stale-while-revalidate`. — [Async SWR changelog](https://developers.cloudflare.com/changelog/post/2026-02-26-async-stale-while-revalidate/); [Cloudflare revalidation](https://developers.cloudflare.com/cache/concepts/revalidation/)
- With OCC on, `must-revalidate`, `proxy-revalidate`, `s-maxage` (implies proxy-revalidate), or `no-cache` alongside SWR disable stale serving (`EXPIRED` instead of `UPDATING`). Workaround for different edge/browser TTLs: send `max-age` + `stale-while-revalidate` from origin and set Edge Cache TTL via Cache Rule. — [Cloudflare revalidation](https://developers.cloudflare.com/cache/concepts/revalidation/)
- If Always Online is enabled, `stale-while-revalidate` and `stale-if-error` are ignored; SWR is not supported with Cache API `match`/`put`. — [Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/)
- Cache Rule `serve_stale { disable_stale_while_updating = true }` can turn off stale-while-updating. — [Cache Rules Terraform example](https://developers.cloudflare.com/cache/how-to/cache-rules/terraform-example/)
- Logpush HTTP requests dataset gained `CacheLockWaitedMs` (Jul 2026), i.e., time spent waiting on cache lock (collapsing). — [Cloudflare changelog](https://developers.cloudflare.com/changelog/17/)

**Cloudflare Cache Reserve (persistent)**
- R2-backed persistent "ultimate upper tier"; freshness from Edge TTL or origin headers; retention 30 days by default, reset on each request; paid add-on, pausable. Eligibility: cacheable, freshness TTL ≥10 hours, `Content-Length` present; image-transformation variants not eligible (originals are). Cache Rule `cache_reserve: { eligible: true, minimum_file_size: 100000 }`. Origin Range Requests not supported with Cache Reserve. — [Cache Reserve](https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/); [Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/); [Range requests](https://developers.cloudflare.com/cache/reference/range-requests/)
- Purge forces a full miss for Cache Reserve content; `invalidate_cache` lets a 304 reuse stored content (reduces origin egress, but the update is still a Class A operation; URL invalidation also triggers a Class A op). — [Cache Reserve](https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/); [Cache Reserve purge behavior changelog](https://developers.cloudflare.com/changelog/post/2026-09-28-cache-reserve-purge-behavior/)
- Cloudflare positions Cache Reserve for large, infrequently accessed assets (images, archived video, software updates, AI models) to avoid LRU eviction. — [Reference architecture](https://developers.cloudflare.com/reference-architecture/diagrams/content-delivery/distributed-web-performance-architecture/)

**Cache warming**
- Cloudflare Prefetch URLs can pre-populate cache from manifest files (incompatible with custom cache keys). Workers Caching has no pre-warm API — use Static Assets for build-time content. — [Reference architecture](https://developers.cloudflare.com/reference-architecture/diagrams/content-delivery/distributed-web-performance-architecture/); [Workers cache limitations](https://developers.cloudflare.com/workers/cache/limitations/)
- Netlify: each request may hit a different cache instance; without production traffic or `durable`, expect several misses before a hit. — Netlify `netlify-caching` agent context (Netlify MCP)

**Fastly**
- Request collapsing is enabled by default. `beresp.stale_if_error` ≡ `beresp.grace`; VCL grace overrides `stale-if-error` in Cache-Control/Surrogate-Control. Grace is not configured by default; the UI "serve stale" setting defaults to 43,200 s (12 h) and conflicts with custom-VCL stale-if-error (use one). Pattern: in `vcl_fetch` on 5xx, deliver stale if available, else cache the error for 1 s so collapsed waiters are served. If origin is unreachable Fastly goes straight to `vcl_error`. Consider shielding before customizing error behavior. — [Fastly serving stale](https://www.fastly.com/documentation/solutions/tutorials/full-site-delivery/serving-stale/); [Fastly serving stale content guide](https://docs.fastly.com/en/guides/serving-stale-content); [Fastly staleness and revalidation](https://developer.fastly.com/learning/concepts/stale)

**CloudFront Origin Shield**
- Origin Shield increases hit rate and adds `OriginShieldHit` entries to logs; minimize cache-key variation via cache policy. (Third-party summary.) — [oneuptime Origin Shield post](https://oneuptime.com/blog/post/2026-02-12-cloudfront-origin-shield-cache-optimization/view) (third-party)

**Akamai**
- Tiered Distribution lets edge servers fetch from Akamai parent servers instead of origin (reduces origin load, faster refresh); GA in GA rule format (Beta in "latest"). — [Akamai Tiered Distribution](https://techdocs.akamai.com/property-mgr/reference/ga-tiered-distribution)

**Google Cloud CDN**
- `requestCoalescing: true` merges concurrent cache fills into a small number of origin requests; `serve_while_stale` field exists (default not confirmed); negative caching defaults: 300/301/308 → 10 min; 404/410/451 → 120 s; 405/421/501 → 60 s; a custom `negative_caching_policy` replaces all defaults. — [Ruby BackendServiceCdnPolicy](https://googleapis.dev/ruby/google-apis-compute_v1/v0.105.0/Google/Apis/ComputeV1/BackendServiceCdnPolicy.html); [Google CachePolicy](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy)

**Netlify / Vercel**
- Netlify supports `stale-while-revalidate=N`; `Cache-Status` header (RFC 9211) shows `"Netlify Edge"; hit; fwd=stale` for SWR, `"Netlify Durable"; fwd=uri-miss; stored=true; ttl=3600` etc. — Netlify `netlify-caching` agent context (Netlify MCP)
- Vercel: `Cache-Control: s-maxage=1, stale-while-revalidate=59` serves stale and updates asynchronously; `max-age=604800, stale-if-error=86400` serves stale on revalidation error. — [Vercel cache-control headers](https://vercel.com/docs/caching/cache-control-headers)

### Inferences
- Shield checklist: Cloudflare → enable Smart Tiered Cache and, for cloud origins, set the cloud region hint; CloudFront → enable Origin Shield in the region nearest origin; Fastly → set a shield POP near origin; Akamai → Tiered Distribution. Multi-CDN or CDN-in-front-of-Vercel/Netlify setups effectively create two shield layers — avoid double-shielding with conflicting TTLs by using vendor-specific headers per layer.
- Stale-serving cross-vendor rule: emit `stale-while-revalidate` and `stale-if-error` in `CDN-Cache-Control` (or vendor header) but avoid `s-maxage`/`must-revalidate` in the same header for Cloudflare. A safe universal edge header: `CDN-Cache-Control: max-age=300, stale-while-revalidate=3600, stale-if-error=86400`.
- Request collapsing is automatic on Cloudflare zone cache, Workers Caching, Fastly, Google (opt-in flag), Netlify durable (partial), nginx (`proxy_cache_lock`), Varnish (built-in waitinglist) — but NOT the Cloudflare Workers Cache API or Netlify Cache API: implement your own lock (e.g., Durable Object) if using those primitives for expensive misses.

### Gaps
- Cache Reserve pricing (per-GB storage, Class A/B operation prices) not retrieved.
- Fastly shielding configuration details (shield POP selection, `req.backend.is_shield`, double-execution of VCL) not retrieved.
- CloudFront Origin Shield pricing and official docs not retrieved (only third-party summary).
- Google `serveWhileStale` default (commonly 86,400 s) unconfirmed.
- bunny.net Origin Shield / request coalescing docs not retrieved.

---

## 4. Vendor quick reference (Cloudflare, Fastly, Akamai, CloudFront, GCP, Azure, Vercel, Netlify, bunny.net, Fly.io)

### Takeaway
A compact matrix the skill can use to pick the right header names, purge mechanism, and gotcha per vendor.

### Cited Findings
| Vendor | Edge-only TTL header | Tag header | Soft purge | Notable 2025–26 change |
|---|---|---|---|---|
| Cloudflare | `Cloudflare-CDN-Cache-Control` (stripped) / `CDN-Cache-Control` | `Cache-Tag` | `invalidate_cache` endpoint | Cache Response Rules (Mar 26), async SWR (Feb 26), Vary in Cache Rules (Jul 26), invalidate (Sep 26), Workers Caching |
| Vercel | `Vercel-CDN-Cache-Control` | `Vercel-Cache-Tag` / `addCacheTag()` | `invalidateByTag()` | external rewrite caching default for projects after Apr 6 2026 |
| Netlify | `Netlify-CDN-Cache-Control` | `Netlify-Cache-Tag` | (purge only) | `durable`, `Netlify-Vary`, `@netlify/cache` |
| Fastly | `Surrogate-Control` | `Surrogate-Key` | `Fastly-Soft-Purge: 1` | Compute ESI library |
| CloudFront | `s-maxage` + cache policy TTLs | configurable via `CacheTagConfig` | — | tag invalidation (Apr 2026) |
| Akamai | `s-maxage` (when Caching behavior honors origin) | `Edge-Cache-Tag` (name per training; limits secondhand) | invalidate vs delete | fast-invalidate behavior deprecated |

Sources: [Cloudflare Workers cache config](https://developers.cloudflare.com/workers/cache/configuration/); [Cloudflare purge by tags](https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-tags/); [Cloudflare invalidate](https://developers.cloudflare.com/cache/guides/invalidate-cache/); [Vercel CDN cache](https://vercel.com/docs/caching/cdn-cache); [Vercel purge](https://vercel.com/docs/caching/cdn-cache/purge); [Vercel rewrites](https://vercel.com/docs/rewrites); Netlify `netlify-caching` agent context (Netlify MCP); [Fastly Surrogate-Control](https://developer.fastly.com/reference/http-headers/Surrogate-Control/); [Fastly soft purges](https://docs.fastly.com/en/guides/soft-purges); [CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md); [Akamai caching](https://techdocs.akamai.com/property-mgr/docs/know-caching); [Akamai purge methods](https://techdocs.akamai.com/purge-cache/docs/purge-methods); [Akamai Terraform fast-invalidate](https://techdocs.akamai.com/terraform/docs/ga-fast-invalidate)

- **Fly.io**: Fly Proxy handles routing, load balancing, TLS, autostop/autostart — not HTTP response caching. `fly-replay` "replay caching" (path-based or session-based via cookie/header) caches routing decisions only, is an optimization not a guarantee, and works only within the same Fly organization. — [Fly Proxy](https://fly.io/docs/reference/fly-proxy/); [Fly dynamic request routing](https://fly.io/docs/networking/dynamic-request-routing/); [Fly blog: how to fly-replay](https://fly.io/blog/how-to-fly-replay.md)
- **Azure Front Door**: no-directive responses cached 1–3 days; purge ≤10 min; query-string-agnostic purge. — [AFD caching](https://learn.microsoft.com/azure/frontdoor/front-door-caching); [AFD purge](https://learn.microsoft.com/azure/frontdoor/cache-purge)
- **bunny.net**: `CDN-Tag` tags; Perma-Cache disables tag/wildcard purge. — [bunny purge](https://docs.bunny.net/cdn/purge-cache); [bunny Perma-Cache](https://bunny.net/docs/cdn/perma-cache)

### Inferences
- On Fly.io, the skill should recommend either fronting with an external CDN (Cloudflare/Fastly/bunny) or running Varnish/nginx as a Fly app in front of the app machines; there is no platform HTTP cache to configure.
- On Azure Front Door, always send explicit `Cache-Control` from origin for dynamic routes (`private, no-store` for personalized), because the "no directive → 1–3 days" default is a correctness hazard.

### Gaps
- Akamai's current official cache-tag header name and limits were not retrieved from techdocs (only secondhand).
- Google Media CDN, Akamai Ion/Adaptive Media Delivery, and bunny "Smart Cache" specifics were not researched.

---

## 5. Edge compute + edge data caches: when to use Workers Cache vs Cache API vs KV vs D1/DO, Vercel Edge Config/Runtime Cache, Fastly KV/Config Store, Netlify Cache API

### Takeaway
Use the platform's read-through HTTP cache in front of compute (Cloudflare Workers Caching, Vercel CDN, Netlify durable) for whole responses; use programmatic caches (Cloudflare Cache API, Netlify Cache API, Vercel Runtime Cache) for fragments/subrequests; use globally replicated KV/config stores (Workers KV, Fastly KV/Config Store, Vercel Edge Config) for read-mostly data tolerant of ~60 s staleness; use Durable Objects/D1 for strongly consistent state (and cache their outputs behind Workers Caching).

### Cited Findings

**Cloudflare Workers Caching (new, 2026)**
- Opt in with Wrangler `"cache": { "enabled": true }`; per-entrypoint control via `"exports": { "default": { "type": "worker", "cache": { "enabled": false } }, "CachedAPI": { ... "enabled": true } }` (Wrangler ≥4.107.0). Cache is checked before the Worker runs; hits skip execution and CPU. — [Workers Cache](https://developers.cloudflare.com/workers/cache/); [Workers cache configuration](https://developers.cloudflare.com/workers/cache/configuration/)
- Cache key = target entrypoint + path + query (order-sensitive; trailing slash matters) + Worker version (default; `cache.cross_version_cache` shares across versions) + `ctx.props`; host is NOT in the key (same cache across all domains/service bindings); `cf.cacheKey` custom keys stay scoped to entrypoint + ctx.props. — [Workers cache keys](https://developers.cloudflare.com/workers/cache/cache-keys/)
- Tiered by default (lower + upper tier); request collapsing per cache key per data center including streaming bodies; no collapsing for uncacheable responses. — [Workers Cache](https://developers.cloudflare.com/workers/cache/)
- Zone Cache Rules, Cache Response Rules, Page Rules, default-extensions list, custom tiered topologies do NOT apply; `Cache-Control` (RFC 9111), `Vary` (verbatim values, no normalization), `Cache-Tag` are the config surface. `ctx.cache.purge({ tags | pathPrefixes | purgeEverything })` and `ctx.cache.invalidate()` (Sep 29 2026) — scoped per entrypoint, Instant Purge propagation, always Free-tier purge rate limits; at launch all responses limited to Free-plan size (512 MB). No pre-warm API. — [Workers cache limitations](https://developers.cloudflare.com/workers/cache/limitations/); [Workers cache purge](https://developers.cloudflare.com/workers/cache/purge/); [invalidate changelog](https://developers.cloudflare.com/changelog/post/2026-09-29-workers-cache-invalidate/)
- Cache API (`caches.default`/`caches.open`) is independent: not read-through (explicit `put`), no request collapsing, no tiered cache, data-center local; prefer Workers Caching for new Workers. — [Workers cache limitations](https://developers.cloudflare.com/workers/cache/limitations/); [Workers Cache API](https://developers.cloudflare.com/workers/runtime-apis/cache/)
- Durable Objects are never cached directly; wrap them behind a cached named entrypoint (e.g., leaderboard with `max-age=30`, `Cache-Tag: leaderboard`, purge on write). — [Workers cache examples](https://developers.cloudflare.com/workers/cache/examples/)

**Workers KV**
- Eventually consistent: writes visible immediately in the same location, up to 60 s (or `cacheTtl`) elsewhere; last write wins; ~1 write/s per key; hot reads ~500 µs–10 ms; negative lookups cached. `cacheTtl` minimum lowered to 30 s (Jan 30 2026), default 60 s. KV persists to central stores (unlike ephemeral, DC-local Cache API). Recommended for session data, API keys, config. — [KV write](https://developers.cloudflare.com/kv/api/write-key-value-pairs/); [KV read cacheTtl](https://developers.cloudflare.com/kv/api/read-key-value-pairs/); [KV cacheTtl changelog](https://developers.cloudflare.com/changelog/post/2026-01-30-kv-reduced-minimum-cachettl/); [Storage options](https://developers.cloudflare.com/workers/platform/storage-options/); [Cache data with KV](https://developers.cloudflare.com/kv/examples/cache-data-with-workers-kv/)

**Fastly**
- KV Store: globally available, durable, eventually consistent, read/write at edge and via API; reads may take up to 300 ms for recently changed/unreplicated data. Config Store: small text config, Compute-only, read-only at edge (writes via API), cached in all POPs, ~1 ms reads. — [Fastly about edge data stores](https://www.fastly.com/documentation/guides/compute/edge-data-storage/about-edge-data-stores/); [Fastly dynamic config](https://www.fastly.com/documentation/guides/concepts/dynamic-config)

**Vercel**
- Edge Config: most reads <15 ms at P99, often <1 ms; for frequently-read, rarely-updated data. — [Vercel Edge Config](https://vercel.com/docs/edge-config)
- Runtime Cache `getCache()` from `@vercel/functions`: `cache.get/set(key, value, { ttl, tags })`, max item 2 MB, ≤128 tags; regional; Next.js `'use cache: remote'`. Pattern: CDN `s-maxage=60` on the response + 1 h regional data cache. — [Vercel runtime cache](https://vercel.com/docs/caching/runtime-cache); [Vercel llms-full](https://vercel.com/docs/llms-full.txt)

**Netlify**
- Cache API (`caches.open/match/put`): `match/put/delete` only inside the handler; per invocation ≤100 lookups and ≤20 insertions/deletions; per-region, not replicated; auto-invalidated on redeploy; can't cache 206, `Vary: *`, non-GET; requires `max-age`/`s-maxage` ≥1 s, `public`, 2xx. `@netlify/cache`: `fetchWithCache(url, opts, { ttl, swr, tags, vary, durable })`, `cacheHeaders()`, `getCacheStatus()`, `needsRevalidation()`. — Netlify `netlify-caching` agent context (Netlify MCP)

**Cloudflare Snippets**
- Snippets can serve cached Worker output via `caches.default` with a shared custom cache key to avoid running Workers before cache. — [Snippets when to use](https://developers.cloudflare.com/rules/snippets/when-to-use/)

### Inferences
- Decision table for the skill:
  - Whole HTTP responses from edge compute → platform read-through cache (Workers Caching / Vercel CDN headers / Netlify `durable`).
  - Expensive subrequest or fragment reused across routes → Cache API (Cloudflare/Netlify) or Vercel Runtime Cache / `fetchWithCache`; add your own collapsing if miss cost is high.
  - Feature flags, redirects, A/B allocations read on every request → Vercel Edge Config / Fastly Config Store / Workers KV (accept ≤60 s propagation).
  - Per-user/session writes needing read-your-writes → Durable Objects/D1 (Cloudflare) or origin DB; never KV for counters.
- Workers Caching's "version in key by default" means each deploy starts cold; for high-traffic sites enable `cross_version_cache` and tag responses with a version tag (`v:${versionId}`) so rollback can purge just that version.

### Gaps
- Vercel Edge Config propagation/consistency timing not found.
- Cloudflare Workers Caching pricing and exact GA/launch date not confirmed.
- Fastly Compute "simple cache"/Core Cache API details not retrieved.

---

## 6. ESI, fragment caching, and personalized pages at the edge (cookie variants, A/B tests, geo, device)

### Takeaway
Classic ESI is effectively a Fastly/Akamai/Varnish feature (Fastly VCL ESI is limited to include/comment/remove, sequential, ≤256 fragments, uncompressed bodies only); on Cloudflare/Vercel/Netlify, personalization is done by edge functions + cache-key variants (Netlify-Vary cookie/country/language, Cloudflare custom keys/Vary normalize, Workers `ctx.props`). Keep variant cardinality tiny (bucketed cookies, normalized languages, country groups).

### Cited Findings
- Fastly VCL ESI supports only `include`, `comment`, `remove`; ESI runs after `vcl_deliver`, so origin-compressed or statically edge-compressed bodies can't be parsed (dynamic delivery compression is fine); tags processed sequentially; max 256 include fragments per request. Fastly's Compute ESI library adds `esi:choose`, `esi:try`, variables (features previously Akamai-only). Akamai introduced ESI. — [Fastly ESI VCL statement](https://www.fastly.com/documentation/reference/vcl/statements/esi/); [Fastly using ESI](https://docs.fastly.com/guides/performance-tuning/using-edge-side-includes); [Fastly blog: ESI libraries](https://www.fastly.com/blog/esi-and-the-story-of-libraries-built-for-the-edge) (vendor blog)
- Netlify cache variants: `Netlify-Vary: cookie=ab_test|is_logged_in` targets specific cookie keys rather than the whole Cookie header; `country=us|es+pt` (GeoIP, `+` groups), `language=en|es+pt` (quality-weighted Accept-Language). `cacheHeaders({ vary: { cookie: ["ab_test_name","ab_test_bucket"], country: ["us",["es","pt"]] } })`. — Netlify `netlify-caching` agent context (Netlify MCP)
- Cloudflare: custom key cookie include / check presence, user features (device_type/geo/lang) are Enterprise; Cache by device type on all plans; Vary normalize for Accept-Language on all plans; high-cardinality cookie/header keys shard the cache. — [Cloudflare cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/); [Investigating uncached responses](https://developers.cloudflare.com/cache/troubleshooting/investigating-uncached-responses/); [Cloudflare Vary](https://developers.cloudflare.com/cache/concepts/vary/)
- Cloudflare Workers Caching: for white-label tenants on the same path, pass tenant ID via `ctx.props` (part of the key) from a gateway Worker; for per-user caching pass the user ID via `ctx.props` so one user can never get another's entry. — [Workers cache keys](https://developers.cloudflare.com/workers/cache/cache-keys/); [Workers cache examples](https://developers.cloudflare.com/workers/cache/examples/)
- Variants of a URL share one purge identity in Workers Caching — all variants must use the same `Cache-Tag` values. — [Workers cache configuration](https://developers.cloudflare.com/workers/cache/configuration/)

### Inferences
- Pattern "cache the shell, personalize at the edge": cache anonymous HTML keyed only on URL (+ bucketed A/B cookie), then inject user-specific bits client-side or via an edge function (Cloudflare HTMLRewriter / Vercel middleware / Netlify Edge Function) on top of the cached response. This avoids per-user cache entries entirely.
- A/B tests: assign bucket in an edge function, set a small cookie (`ab=b`), and vary on that cookie only (Netlify `cookie=ab`; Cloudflare Enterprise custom key cookie include; elsewhere rewrite URL to `/variant-b/...` so the bucket lives in the path — works on every CDN, including non-Enterprise Cloudflare).
- Geo: group countries (`country=us|ca+mx|eu-group`) rather than per-country keys; prefer URL-based locale (`/en-gb/`) over Accept-Language variance for SEO and hit ratio.
- Never vary on `User-Agent` raw; use device-type classification (Cloudflare `device_type`, or a header your edge function sets with 3 values).

### Gaps
- Cloudflare's lack of native ESI and HTMLRewriter-based fragment caching patterns were not confirmed by a retrieved source in this session.
- Akamai's current ESI feature set and pricing not retrieved.
- Vercel middleware/edge personalization caching specifics (e.g., `Vary` support on Vercel CDN) not retrieved.

---

## 7. Reverse proxies: Varnish, Nginx proxy_cache / FastCGI cache / microcaching, Caddy (Souin), Apache mod_cache, Squid, Traefik, HAProxy

### Takeaway
For self-hosted origin caching: nginx `proxy_cache` with `proxy_cache_lock` + `proxy_cache_use_stale updating` + `proxy_cache_background_update` (1 s microcaching for dynamic anonymous pages) is the default recommendation; Varnish for complex logic, grace, and tag invalidation (xkey with soft purge); Souin for Caddy/Traefik (RFC-compliant, surrogate keys, CDN-provider integrations, but plugin maturity caveats); HAProxy's cache is small, in-memory, limited Vary support.

### Cited Findings

**Nginx**
- Microcaching pattern: `proxy_cache_valid 200 301 302 1s;` with `proxy_cache_use_stale updating error timeout` and `proxy_cache_background_update on` (background subrequest, available since nginx 1.11.10) so refreshes don't block; `proxy_cache_lock` lets only the first request for a missing entry go to origin while others wait (tunable `proxy_cache_lock_timeout`, `proxy_cache_lock_age`). Only for responses shared across clients — usually anonymous GET/HEAD. — [F5 NGINX caching guide](https://www.f5.com/pt_br/company/blog/nginx/nginx-caching-guide); [GetPageSpeed nginx microcaching](https://www.getpagespeed.com/server-setup/nginx/nginx-microcaching); [simplified.guide microcaching](https://www.simplified.guide/_export/xhtml/nginx/enable-microcaching)

**Varnish**
- `beresp.grace` sets how long objects may be served past TTL; `req.grace` set in `vcl_recv` can cap effective grace when the backend is healthy (e.g., 10 s) while allowing long grace when sick. — [Varnish grace mode and keep (6.2)](https://varnish-cache.org/docs/6.2/users-guide/vcl-grace.html); [Varnish users guide: grace](https://www.varnish.org/docs/users-guide/vcl-grace/)
- Hard PURGE/BAN removes objects immediately, so grace no longer applies; soft purge resets TTL to 0 but keeps the object for its grace period. xkey vmod adds secondary keys (tags) for fast purging of all objects with a tag; `xkey.softpurge()` expires but keeps for grace. — [Varnish cache invalidation tutorial](https://www.varnish.org/docs/tutorials/cache-invalidation/); [GetPageSpeed Varnish 5.2 grace](https://getpagespeed.com/server-setup/varnish/varnish-5-2-grace-mode)

**Caddy / Souin**
- `caddyserver/cache-handler` (Souin-based): `ttl` and `stale` directives set default TTL and stale period; CDN provider integrations `akamai`, `cloudflare`, `fastly`, `souin`; `surrogate_keys` groups by header/URL; `dynamic` stores backend-returned keys. Since Souin v1.7.0 only one storage backend is built in; others need xcaddy builds. A GitHub issue reported surrogate keys not stored with the default provider unless `dynamic` was enabled. — [caddyserver/cache-handler](https://github.com/caddyserver/cache-handler); [Souin configuration](https://docs.souin.io/docs/configuration/); [Souin issue #306](https://github.com/darkweak/souin/issues/306)
- Souin is RFC 7234-oriented: Vary, request coalescing, stale directives. Traefik has no native HTTP cache; Souin runs as a Traefik plugin (`moduleName: github.com/darkweak/souin`, v1.7.8 in docs) but the Yaegi plugin loader breaks often and compatibility isn't guaranteed. — [Souin GitHub](https://github.com/redocly/souin); [Souin Traefik middleware docs](https://docs.souin.io/docs/middlewares/tr%C3%A6fik/); [Traefik plugin catalog: Souin](https://plugins.traefik.io/plugins/6294728cffc0cd18356a97c2/souin)

**HAProxy**
- `cache` section: `total-max-size` max 4,095 MB; `max-object-size` ≤ half of total; `max-age` caps TTL (lowest of s-maxage/max-age and this value); `process-vary` (HAProxy ≥2.4, default off) handles Vary only if it lists `accept-encoding`, `referer`, and/or `origin` — with it off, any response with Vary is never cached; `max-secondary-entries` for Vary variants. In-memory only, lost on reload; caches only 200 responses (older docs). — [HAProxy caching tutorial](https://www.haproxy.com/documentation/haproxy-configuration-tutorials/performance/caching); [HAPEE 1.7 caching](https://www.haproxy.com/documentation/hapee/1-7r2/load-balancing/caching/)

### Inferences
- Illustrative nginx config (directive names standard; values composed — verify against nginx.org):
  ```nginx
  proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=app:100m max_size=10g inactive=7d use_temp_path=off;
  map $http_cookie $skip_cache { default 0; ~*(session|wordpress_logged_in) 1; }
  server {
    location / {
      proxy_cache app;
      proxy_cache_key "$scheme$host$request_uri";
      proxy_cache_valid 200 301 302 1s;          # microcache dynamic HTML
      proxy_cache_use_stale updating error timeout http_500 http_502 http_503 http_504;
      proxy_cache_background_update on;
      proxy_cache_lock on;
      proxy_cache_bypass $skip_cache; proxy_no_cache $skip_cache;
      add_header X-Cache-Status $upstream_cache_status;
      proxy_pass http://app_upstream;
    }
  }
  ```
  For PHP-FPM the same pattern uses `fastcgi_cache_path`/`fastcgi_cache`/`fastcgi_cache_key`/`fastcgi_cache_use_stale`/`fastcgi_cache_lock`/`fastcgi_cache_background_update`. Note: nginx by default won't cache responses with `Set-Cookie` or `Cache-Control: private/no-cache` unless `proxy_ignore_headers` is used — strip cookies for anonymous pages instead of ignoring headers globally (training knowledge; verify).
- Illustrative Varnish VCL (Varnish 6/7 + xkey; verify module availability):
  ```vcl
  vcl 4.1;
  import xkey;
  sub vcl_recv {
    if (req.method == "PURGE") {
      if (client.ip !~ purgers) { return (synth(403)); }
      set req.http.n-gone = xkey.softpurge(req.http.xkey);   # soft: keep for grace
      return (synth(200, "Invalidated " + req.http.n-gone));
    }
    if (std.healthy(req.backend_hint)) { set req.grace = 10s; }
  }
  sub vcl_backend_response {
    set beresp.grace = 24h;   # serve stale up to 24h if backend fails
    set beresp.keep = 1h;     # keep for conditional revalidation
  }
  ```
  Origin sets `xkey: product-123 category-9` response header. Prefer xkey soft purge over bans for tag invalidation (bans accumulate on the ban list and are evaluated lazily — training knowledge).
- Decision rule: if a CDN with tag purge is already in front, an origin reverse proxy mainly adds request collapsing + microcaching + stale-if-error; keep its TTL short (1–10 s) to avoid a second invalidation problem, or wire purges to both layers (inner first).

### Gaps
- Apache `mod_cache` (CacheQuickHandler, CacheLock) and Squid were not covered by retrieved sources.
- Varnish 7.x-specific default VCL grace changes and Varnish Enterprise (MSE, Ykey) not retrieved.
- nginx.org primary docs were not fetched; directive defaults (e.g., `proxy_cache_lock_timeout 5s`) unverified in this session.

---

## 8. Media / image caching: image CDNs, on-the-fly transforms, format negotiation (Accept: image/avif,webp) and cache keys

### Takeaway
Format negotiation multiplies cache entries (format × width × quality); every image CDN keys on a normalized Accept-derived format, not raw Accept. Cloudflare caches resized variants under the source URL (purge the source to purge all variants), Next.js 16 raised `minimumCacheTTL` to 4 h and restricts qualities to `[75]` by default. Prefer explicit allowlists of widths/qualities/formats to bound cardinality and cost.

### Cited Findings
- Cloudflare Images `format=auto` serves the best format the browser supports (default for hosted images); AVIF encoding can be much slower and may fall back to WebP/JPEG for large images; custom Workers must parse `Accept` themselves (`/image\/avif/` → avif, else webp). — [Cloudflare Images features](https://developers.cloudflare.com/images/optimization/features/); [Transform via Workers](https://developers.cloudflare.com/images/optimization/transformations/transform-via-workers/)
- Resized variants are cached as variants under the full-size source image's cache entry; don't put resizing options in `cacheKey`; purging the source URL purges all optimized versions; `/cdn-cgi/` URLs cannot be purged; optimized images follow the original's caching rules with a minimum of 1 hour (add `must-revalidate` + ETag for faster updates). Image origin requests are anonymized (no cookies/auth/custom headers). — [Cloudflare Images features](https://developers.cloudflare.com/images/optimization/features/); [Images troubleshooting](https://developers.cloudflare.com/images/reference/troubleshooting/); [Transform via Workers](https://developers.cloudflare.com/images/optimization/transformations/transform-via-workers/)
- Billing: each unique source+parameters combination is billed once per calendar month; Images binding moved to per-unique-transformation billing Jul 1 2026; binding responses are not auto-cached — enable Workers Cache and set `Cache-Control` (e.g., `public, max-age=3600, stale-while-revalidate=86400`). — [Cloudflare transformations overview](https://developers.cloudflare.com/images/optimization/transformations/overview/); [Images binding](https://developers.cloudflare.com/images/optimization/binding/); [Images changelog](https://developers.cloudflare.com/changelog/product/images/)
- Cloudflare "Vary for Images" (Pro+): origin sends `Vary: Accept`; configure per-extension variants via `PATCH /zones/$ZONE_ID/cache/variants {"value":{"jpg":["image/webp","image/avif"]}}`; if origin sends `Vary: Accept` but doesn't serve a configured variant → BYPASS. Vary is ignored on Polish/Image Resizing outputs. — [Vary for images](https://developers.cloudflare.com/cache/advanced-configuration/vary-for-images/); [Workers Cache](https://developers.cloudflare.com/workers/cache/)
- Next.js 16: `minimumCacheTTL` default 4 h (14,400 s), up from 60 s in Next 15; effective TTL = max(minimumCacheTTL, upstream Cache-Control age); default `qualities` is `[75]` (other values fall back); `formats` default `['image/webp']`, order matters (AVIF-first recommended); variants = sources × qualities × widths × formats (1 image × 2 formats × 2 qualities × 8 widths = 32 cache entries). — [Vercel KB: reduce image optimization costs](https://vercel.com/kb/guide/reduce-image-optimization-costs-on-vercel); [Vercel Academy image optimization](https://vercel.com/academy/optimize-your-vercel-account/image-optimization); [DEV: serving AI images on Next.js](https://dev.to/casanovalabs/serving-ai-generated-images-at-scale-on-nextjs-formats-cache-and-the-app-router-traps-19c6) (third-party)
- Older Vercel docs list the image cache key as quality, width, source URL, and normalized Accept header (and the outdated 60 s default). — [zeit.co image optimization (older docs)](https://zeit.co/docs/image-optimization)
- Vercel: `vercel cache invalidate --srcimg /images/hero.png` / `invalidateBySrcImage()` invalidates all optimized variants of a source. — [Vercel debug cache issues](https://vercel.com/docs/caching/cdn-cache/debug-cache-issues); [Vercel purge](https://vercel.com/docs/caching/cdn-cache/purge)

### Inferences
- Rules for the skill: (1) never cache images keyed on raw `Accept` — use vendor format negotiation or normalize to {avif, webp, original}; (2) bound widths to a fixed set (e.g., 8 breakpoints) and qualities to 1–2 values; (3) version or content-hash source URLs so source changes don't require purges; (4) put originals in Cache Reserve/persistent tier, not the variants (Cloudflare explicitly excludes variants).
- For a standalone origin serving `Vary: Accept` to a CDN that doesn't normalize (e.g., Workers Caching, Fastly without VCL), add a normalization step that rewrites Accept to one of 3 canonical values before cache lookup.

### Gaps
- imgix and Cloudinary caching/purge specifics (e.g., Cloudinary invalidation, imgix purge API, `auto=format` Vary behavior) were not researched in this session.
- Netlify Image CDN cache behavior not retrieved.

---

## 9. Caching API responses and authenticated content at the edge safely

### Takeaway
The safe default everywhere is: authenticated/personalized responses are `private`/`no-store`; shared API responses use explicit `public` + CDN-only TTL. Where many authenticated users receive identical data, authenticate at the edge and cache the shared response separately (Cloudflare Workers Caching gateway pattern), or use signed URLs/cookies (CloudFront) so the credential is checked at the edge but not part of the key.

### Cited Findings
- Cloudflare (OCC on): requests with `Authorization` are cached only if the response has `public`, `s-maxage`, or `must-revalidate`. — [Cloudflare Origin Cache Control](https://developers.cloudflare.com/cache/concepts/cache-control/)
- Cloudflare Workers Caching authenticated pattern: default entrypoint (cache disabled) authenticates, strips `Authorization` (otherwise the automatic bypass triggers), forwards via `ctx.exports.CachedAPI.fetch(forwarded)` to a cached entrypoint returning `Cache-Control: public, max-age=60`; for per-user data pass the user ID through `ctx.props` (part of the key). — [Workers cache examples](https://developers.cloudflare.com/workers/cache/examples/)
- Cloudflare Images anonymizes origin image fetches (no cookies/auth) because resized images share one public cache. — [Images troubleshooting](https://developers.cloudflare.com/images/reference/troubleshooting/)
- CloudFront: signed URLs for individual files or cookie-less clients; signed cookies for many files (e.g., HLS segments) or to keep URLs unchanged; trusted key groups recommended over trusted signers; signed URLs take precedence over cookies; URLs containing `Expires`, `Policy`, `Signature`, or `Key-Pair-Id` are treated as signed URLs. — [CloudFront: choose signed URLs or cookies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-choosing-signed-urls-cookies.html); [CloudFront private content](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PrivateContent.html)
- Netlify: basic auth anywhere disables caching sitewide; never opt sensitive content out of automatic deploy invalidation (could stay publicly cached after deploys/firewall changes); `private` = browser-only. — Netlify `netlify-caching` agent context (Netlify MCP)
- Vercel Blob private files: serve via function with `Cache-Control: private, no-cache` + ETag/304 to avoid CDN caching of private blobs; `useCache: false` reads directly from origin storage. — [Vercel Blob private storage](https://vercel.com/docs/vercel-blob/private-storage); [Vercel signed URLs](https://vercel.com/docs/vercel-blob/vercel-signed-urls)
- Google Cloud CDN `FORCE_CACHE_ALL` ignores `private`/`no-store`/`no-cache` and can cache per-user content; CloudFront policies with min TTL > 0 can override origin no-cache/no-store/private. — [Google CachePolicy](https://docs.cloud.google.com/python/docs/reference/compute/latest/google.cloud.compute_v1.types.CachePolicy); [CloudFront managed cache policies](https://docs.aws.amazon.com/es_es/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
- Cloudflare Cache Deception Armor is available on all plans as a cache-key option; it only activates when freshness is inferred heuristically (explicit Cache-Control skips it). — [Cloudflare cache keys](https://developers.cloudflare.com/cache/how-to/cache-keys/); [Workers cache configuration](https://developers.cloudflare.com/workers/cache/configuration/)
- Only GET is cached on Netlify (POST never) — expose cacheable data on GET routes; Cloudflare caches only GET by default. — Netlify `netlify-caching` agent context (Netlify MCP); [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior)

### Inferences
- Safety rules for the skill: (1) any "cache everything"/force mode (Cloudflare Edge TTL override, GCP FORCE_CACHE_ALL, CloudFront MinTTL>0, Akamai TTL rules) must be paired with an explicit bypass for authenticated paths/cookies; (2) never include a raw bearer token or session ID in a cache key — it's both a hit-ratio killer and a leakage risk if logs/keys are exposed; use a stable user ID via ctx.props/custom key only when per-user edge caching is truly needed; (3) strip `Set-Cookie` from cacheable responses at origin rather than relying on CDN stripping; (4) enable Cache Deception Armor (Cloudflare) or equivalent path/extension checks when using extension-based caching rules.
- For GraphQL/POST APIs: convert cacheable queries to GET with persisted-query hashes in the URL so CDNs can cache them.

### Gaps
- CloudFront cache-key behavior with signed URL query params (whether signature params are stripped from the key) was not confirmed.
- Fastly/Akamai token-auth (Edge Auth tokens) patterns not retrieved.

---

## 10. Cost and performance considerations: hit ratio targets, egress reduction, invalidation pricing

### Takeaway
Invalidation is free (rate-limited) on Cloudflare, Vercel, Netlify, Fastly; CloudFront charges beyond 1,000 paths/month (tags billed as paths). Main cost levers are origin egress (shield tiers, persistent cache), compute invocations avoided by caching in front of functions, and image-variant cardinality. No authoritative cross-vendor "hit ratio target" was found.

### Cited Findings
- CloudFront: 1,000 free invalidation paths/month per account; wildcard = 1 path; tags = 1 path each; overage reportedly $0.005/path (third-party). — [CloudFront paying for invalidation](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PayingForInvalidation.md); [CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md); [sparanoid](https://sparanoid.com/note/cloudfront-cost-control/) (third-party)
- Cloudflare: purges free on all plans subject to rate limits; invalidation shares the same limits. — [Cloudflare purge cache](https://developers.cloudflare.com/cache/how-to/purge-cache/); [Cloudflare invalidate](https://developers.cloudflare.com/cache/guides/invalidate-cache/)
- Tiered Cache reduces origin connections and egress; Smart Tiered Cache with R2 lowers R2 egress; Cache Reserve shields origin from egress fees but invalidation/updates incur R2 Class A operations. — [Cloudflare Tiered Cache](https://developers.cloudflare.com/cache/how-to/tiered-cache/); [Smart Tiered for R2](https://developers.cloudflare.com/changelog/post/2024-11-20-smart-tiered-cache-for-r2/); [Cache Reserve](https://developers.cloudflare.com/cache/advanced-configuration/cache-reserve/); [Cache Reserve purge behavior](https://developers.cloudflare.com/changelog/post/2026-09-28-cache-reserve-purge-behavior/)
- Workers Caching hits skip Worker execution, reducing latency and CPU billing. — [Reference architecture](https://developers.cloudflare.com/reference-architecture/diagrams/content-delivery/distributed-web-performance-architecture/)
- Netlify `durable` reduces function invocations across edge nodes. — Netlify `netlify-caching` agent context (Netlify MCP)
- Image transformations billed per unique variant per month (Cloudflare); Next.js variant explosion drives Vercel image costs. — [Cloudflare transformations overview](https://developers.cloudflare.com/images/optimization/transformations/overview/); [Vercel KB image costs](https://vercel.com/kb/guide/reduce-image-optimization-costs-on-vercel)
- Anecdotal third-party claim: fixing cache rules raised a Cloudflare hit rate from ~30% to ~90% (query-string normalization, caching HTML, Set-Cookie fixes). — [eastondev blog](https://eastondev.com/blog/en/posts/dev/20251201-cloudflare-cache-rules-guide/) (third-party, low authority)

### Inferences
- Practical targets the skill can propose (researcher judgment, not sourced): static hashed assets ≥95–99% edge hit ratio; anonymous HTML with SWR 80–95%; public APIs 50–90% depending on key cardinality; measure "origin offload" (bytes) separately from request hit ratio because large files dominate egress.
- Cost-control rules: prefer tag/prefix/wildcard invalidation on CloudFront (1 path each) over per-URL lists; on Cloudflare Free batch up to 100 tags per call to fit 5 calls/min; use immutable content-hashed URLs for assets so they never need purging.

### Gaps
- No authoritative per-vendor hit-ratio benchmarks or recommended targets found.
- Egress pricing per vendor (CloudFront per-GB tiers, Fastly, Akamai, bunny per-GB) not retrieved.
- Cache Reserve, Fastly, and Akamai purge pricing/plan inclusions not retrieved.
