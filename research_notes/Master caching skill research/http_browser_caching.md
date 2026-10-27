# HTTP & Browser Caching (state as of late October 2026)

Research method note: the research sandbox's egress proxy blocked rfc-editor.org, developer.mozilla.org, web.dev, developer.chrome.com, caniuse.com and chromestatus.com directly, and WebFetch could not resolve hosts. Primary content was therefore read from the canonical source repositories behind those sites: `httpwg/httpwg.github.io` (the HTML of the RFCs published at httpwg.org/specs), `httpwg/http-extensions` (IETF drafts), `mdn/content` (MDN pages), `mdn/browser-compat-data` **v8.1.7, data timestamp 2026-10-22** (the data behind MDN and caniuse "mdn-*" tables), the archived `GoogleChrome/developer.chrome.com` and `GoogleChrome/web.dev` repos, `whatwg/fetch`, the Workbox **7.4.1** npm packages, `GoogleChrome/lighthouse` and `ChromeDevTools/devtools-frontend`. Citations below point to the canonical published URLs for those pages. A few items (bfcache with `no-store`, speculation-rules limits, server push removal) come from web-search snippets of developer.chrome.com pages and are marked as such. The web-search budget ran out before every item could be checked (see the Gaps sections).

Browser versions current on 2026-10-22, per BCD's release table: **Chrome 156** (released 2026-10-20; Chrome 155 on 2026-10-06), **Edge 155**, **Firefox 158** (2026-10-13), **Safari 27** (2026-09-14) — [BCD browsers data](https://github.com/mdn/browser-compat-data/tree/main/browsers).

---

## 1. What RFC 9111 and RFC 9110 say about Cache-Control: every directive, its exact meaning, and common misunderstandings

### Takeaway
RFC 9111 (June 2022) is the current HTTP caching standard. It obsoletes RFC 7234, deprecates `Pragma`, obsoletes `Warning` and adds `must-understand`. The rules that matter most in practice are these. Always send an explicit `Cache-Control`, because responses without one are cached heuristically. `no-cache` means "store, but revalidate before every reuse"; it does not mean "don't store". `no-store` is the only directive that prevents storing. `private` keeps a response out of shared caches. `must-revalidate` applies only once a response is stale. `public` is almost never needed and can be dangerous.

### Cited Findings

**Spec status and housekeeping**
- RFC 9111 obsoletes RFC 7234. It **deprecates `Pragma`** ("Because the meaning of `Pragma: no-cache` in responses was never specified, it does not provide a reliable replacement for `Cache-Control: no-cache`"), and it **obsoletes the `Warning` header**, which caches and intermediaries did not generate in practice — [RFC 9111 §5.4, §5.5, Appendix B](https://httpwg.org/specs/rfc9111.html)
- RFC 9111 introduced the `must-understand` directive: "caches are no longer required to understand the semantics of new response status codes unless it is present". It also changed invalidation of URIs in `Location`/`Content-Location` from required to allowed, and disallowed it when the origin differs — [RFC 9111 Appendix B](https://httpwg.org/specs/rfc9111.html)
- A proxy "MUST pass cache directives through in forwarded messages … It is not possible to target a directive to a specific cache". This gap is what RFC 9213's targeted fields fill (see §4) — [RFC 9111 §5.2](https://httpwg.org/specs/rfc9111.html)
- Syntax: `Cache-Control = #cache-directive`, where `cache-directive = token [ "=" ( token / quoted-string ) ]`. Directive names are case-insensitive. `max-age`, `s-maxage`, `max-stale` and `min-fresh` MUST be generated in token form (`max-age=5`, not `max-age="5"`). Qualified `no-cache` and `private` SHOULD use the quoted-string form. A cache MUST ignore directives it does not recognize — [RFC 9111 §5.2, §5.2.3](https://httpwg.org/specs/rfc9111.html)
- MDN recommends lowercase directives "because some implementations do not recognize uppercase directives" — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)

**When a cache may store a response (§3)**
- A cache MUST NOT store a response unless all of these hold: the method is understood; the status is final; if the status is 206 or 304, or `must-understand` is present, the cache understands the status; `no-store` is absent; for a shared cache, `private` is absent; for a shared cache, the request had no `Authorization` header unless a directive explicitly allows shared caching. The response must also carry at least one of `public`, `private` (private cache only), `Expires`, `max-age`, `s-maxage` (shared cache only), a cache extension that allows storage, or **a heuristically cacheable status code** — [RFC 9111 §3](https://httpwg.org/specs/rfc9111.html)
- Heuristically cacheable status codes in RFC 9110: **200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501**. "All other status codes are not heuristically cacheable", so 302, 303 and 307 are not — [RFC 9110 §15.1](https://httpwg.org/specs/rfc9110.html)
- Caches may store "redirects, negative results (e.g., 404 (Not Found)), incomplete results (e.g., 206 (Partial Content)), and responses to methods other than GET if the method's definition allows such caching" — [RFC 9111 §2](https://httpwg.org/specs/rfc9111.html)
- Authorization: a shared cache MUST NOT reuse a response to a request that carried `Authorization` unless the response has a directive that allows shared storage. **Only `must-revalidate`, `public` and `s-maxage` have that effect** — [RFC 9111 §3.5](https://httpwg.org/specs/rfc9111.html); MDN restates that `s-maxage` or `must-revalidate` "also unlock that restriction" — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)

**Freshness calculation (§4.2)**
- Freshness lifetime, first match wins: (1) `s-maxage`, if the cache is shared; (2) `max-age`; (3) `Expires` minus `Date`; (4) otherwise a heuristic may apply — [RFC 9111 §4.2.1](https://httpwg.org/specs/rfc9111.html)
- If a directive appears more than once, the cache uses the first occurrence or treats the response as stale. If directives conflict ("e.g., both max-age and no-cache are present"), **"the most restrictive directive should be honored"**. Responses with invalid freshness information, such as a non-integer max-age, are encouraged to be treated as stale — [RFC 9111 §4.2.1](https://httpwg.org/specs/rfc9111.html)
- Negative or non-integer `max-age` (e.g. `-1`, `3599.99`) has unspecified behavior; caches are encouraged to treat it as 0 — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- If a delta-seconds value overflows, the cache MUST treat it as 2147483648 (2^31, about 68 years, effectively "infinity") — [RFC 9111 §1.2.2](https://httpwg.org/specs/rfc9111.html)
- An `Expires` value that is an invalid date, "especially the value '0'", MUST be read as already expired. If both `max-age` and `Expires` are present, `max-age` wins, so `Expires` is unnecessary today — [RFC 9111 §5.3](https://httpwg.org/specs/rfc9111.html); [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- `max-age` counts from when the origin generated the response, not from when the browser received it. A downstream cache subtracts `Age`: with `max-age=604800` and `Age: 86400`, the response stays fresh for 518400 more seconds — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

**Heuristic freshness: what happens when no headers are set**
- "a cache MAY assign a heuristic expiration time when an explicit time is not specified … If the response has a Last-Modified header field … A typical setting of this fraction might be **10%**" of the time since Last-Modified. Heuristics may only be used when no explicit expiration is present — [RFC 9111 §4.2.2](https://httpwg.org/specs/rfc9111.html)
- RFC 2616 used to forbid heuristic freshness for URLs with a query string. In practice this "has not been widely implemented", so "origin servers are encouraged to send explicit directives (e.g., Cache-Control: no-cache) if they wish to prevent caching" — [RFC 9111 §4.2.2](https://httpwg.org/specs/rfc9111.html)
- `public` with no explicit freshness makes a response heuristically cacheable — [RFC 9111 §5.2.2.9](https://httpwg.org/specs/rfc9111.html)
- MDN example: a page last modified one year ago may be reused for about 0.1 year with no Cache-Control at all. MDN's advice: "basically all responses should explicitly specify a Cache-Control header", and a sensible site-wide default is `Cache-Control: no-cache` (plus `private` for personalized content) — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

**Response directives (RFC 9111 §5.2.2 plus extensions)**
- `max-age=N`: the response is stale once its age exceeds N seconds — [RFC 9111 §5.2.2.1](https://httpwg.org/specs/rfc9111.html)
- `s-maxage=N`: shared caches only; overrides `max-age` and `Expires` for them; **also carries `proxy-revalidate` semantics**, so a shared cache MUST NOT serve the response stale; permits shared caching of responses to `Authorization` requests. Private caches ignore it — [RFC 9111 §5.2.2.10](https://httpwg.org/specs/rfc9111.html)
- `no-cache` (unqualified): the response "MUST NOT be used to satisfy any other request without forwarding it for validation and receiving a successful response". It may be stored. The qualified form `no-cache="Set-Cookie"` "is often handled by caches as if an unqualified no-cache directive was received" — [RFC 9111 §5.2.2.4](https://httpwg.org/specs/rfc9111.html)
- `no-store`: no cache, private or shared, may store "any part of either the immediate request or the response". The RFC itself says it is "not a reliable or sufficient mechanism for ensuring privacy" — [RFC 9111 §5.2.2.5](https://httpwg.org/specs/rfc9111.html). It also **does not delete an already-stored response** for the same URL, so an old copy can still be reused. To guarantee freshness, use `no-cache` — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- `private` (unqualified): shared caches MUST NOT store the response. A private cache MAY store it "even if the response would not otherwise be heuristically cacheable". "This usage of the word 'private' only controls where the response can be stored; it cannot ensure the privacy of the message content." The qualified form is rarely implemented — [RFC 9111 §5.2.2.7](https://httpwg.org/specs/rfc9111.html)
- `public`: "a cache MAY store the response even if it would otherwise be prohibited". It allows shared caching of `Authorization` responses. MDN: "If a request doesn't have an Authorization header, or you are already using s-maxage or must-revalidate in the response, then you don't need to use public" — [RFC 9111 §5.2.2.9](https://httpwg.org/specs/rfc9111.html); [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- `must-revalidate`: **only once the response is stale**, the cache MUST NOT reuse it without successful validation. A disconnected cache MUST return an error (SHOULD be 504) rather than serve stale content. It "ought to be used by servers if and only if failure to validate a request could cause incorrect operation, such as a silently unexecuted financial transaction". It also permits shared caching of `Authorization` responses — [RFC 9111 §5.2.2.2](https://httpwg.org/specs/rfc9111.html)
- `proxy-revalidate`: like `must-revalidate` but for shared caches only. It does not by itself make a response cacheable — [RFC 9111 §5.2.2.8](https://httpwg.org/specs/rfc9111.html)
- `must-understand`: only caches that understand the status code's caching rules may store the response. It "SHOULD also contain the no-store directive", and a cache that implements `must-understand` ignores that `no-store`. Recipe: `Cache-Control: must-understand, no-store` — [RFC 9111 §5.2.2.3](https://httpwg.org/specs/rfc9111.html); [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- `no-transform`: an intermediary MUST NOT transform the content (for example by recompressing images) — [RFC 9111 §5.2.2.6](https://httpwg.org/specs/rfc9111.html)
- `immutable` (RFC 8246): the origin "will not update the representation … during the freshness lifetime". "Clients SHOULD NOT issue a conditional request during the response's freshness lifetime (e.g., upon a reload) unless explicitly overridden by the user (e.g., a force reload)" — [RFC 8246 §2](https://httpwg.org/specs/rfc8246.html). **Support: Firefox 49+ and Safari 11+. Chrome has never implemented it** (Edge 15–78 legacy had it) — [BCD http.headers.Cache-Control.immutable](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Cache-Control.json). Instead, "Chrome has changed its implementation so that revalidation is not performed during reloads for subresources" — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching), citing [Chromium blog 2017](https://blog.chromium.org/2017/01/reload-reloaded-faster-and-leaner-page_26.html)
- `stale-while-revalidate=N` (RFC 5861): caches "MAY serve the response … after it becomes stale, up to the indicated number of seconds", and SHOULD revalidate in the background without blocking. Once N passes without revalidation, the response is "truly" stale — [RFC 5861 §3](https://httpwg.org/specs/rfc5861.html). **Browser HTTP-cache support: Chrome 75, Firefox 68, Safari 14** — [BCD](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Cache-Control.json)
- `stale-if-error=N` (RFC 5861): a stale response MAY be used when "an error is encountered … any situation which would result in a 500, 502, 503 or 504", up to N seconds past stale — [RFC 5861 §4](https://httpwg.org/specs/rfc5861.html). The request-directive form "is not supported by any browser" — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)

**Request directives (advisory; caches "MAY implement them")**
- `max-age=0` is what browsers send on a normal reload. `no-cache` (plus `Pragma: no-cache`) is what they send on a force reload. `max-stale` and `min-fresh` are "not supported" by major browsers. `only-if-cached` returns the stored response or 504 — [RFC 9111 §5.2.1](https://httpwg.org/specs/rfc9111.html); [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- A request `no-store` "does not apply to the already stored response" if the request is served from cache — [RFC 9111 §5.2.1.5](https://httpwg.org/specs/rfc9111.html)

**History navigation is not cache reuse**
- "freshness applies only to cache operation; it cannot be used to force a user agent to refresh its display or reload a resource". "a history mechanism can display a previous representation even if it has expired" — [RFC 9111 §4.2, §6](https://httpwg.org/specs/rfc9111.html)
- `no-cache`, `must-revalidate` and `max-age` "do not guarantee revalidation for history navigations": the bfcache restores a snapshot, and even without bfcache the browser may reuse the cached response without revalidating — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)

**Invalidation and request collapsing**
- "A cache MUST invalidate the target URI … when it receives a non-error status code in response to an unsafe request method" such as POST, PUT or DELETE. It MAY also invalidate the `Location`/`Content-Location` URIs, but only for the same origin — [RFC 9111 §4.4](https://httpwg.org/specs/rfc9111.html)
- HTTP has no directive that purges an intermediary or browser. "There is no way to delete responses on an intermediate server that have been stored with a long max-age." `Clear-Site-Data: "cache"` clears only the browser — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Shared caches collapse concurrent identical requests into one origin fetch, and "even if max-age=0 or no-cache is given in the response, it will be reused" for those collapsed requests. Add `private` to personalized responses to prevent this — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

**Kitchen-sink headers and the `no-store` vs `no-cache` confusion**
- `Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate` is "basically meaningless" and is equivalent to `no-store`. `no-cache` is not a way to prevent storage — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- `max-age=0, must-revalidate` is a pre-HTTP/1.1 workaround equivalent to `no-cache`; "you should instead just use no-cache" — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- "it's not recommended to grant no-store liberally, because you lose many advantages … including the browser's back/forward cache … prefer the use of no-cache in combination with private" — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- QPACK (HTTP/3) has static-table entries for common values, each encodable in one byte: `max-age=0`, `max-age=604800`, `max-age=2592000`, `no-cache`, `no-store`, `public, max-age=31536000`. MDN notes `immutable` can go on a second `Cache-Control` line so the main value keeps its static-table encoding — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

### Inferences
- Decision rule for any response: (1) Must the response never be written to disk anywhere (banking, PII, one-time tokens)? Use `no-store`. (2) Is it personalized? Add `private`. (3) Can the URL change whenever the content changes (fingerprinted)? Use `max-age=31536000, immutable`. (4) Otherwise use `no-cache` with a validator, or a short `max-age` plus `stale-while-revalidate` if brief staleness is acceptable.
- `public` is a security footgun: it re-enables shared caching of `Authorization`-protected responses. Recommend never adding it by habit. Hashed static assets don't need it unless they are served behind HTTP auth.
- `must-revalidate` does not mean "always revalidate". People add it to `max-age=3600` expecting revalidation on every load. It only blocks serving stale content (including when the origin is down), which can turn origin outages into 504s. If resilience matters, prefer `stale-if-error` at the CDN.
- Heuristic caching applies to 404, 301 and 308 responses too. A 404 without Cache-Control can be cached for 10% of its Last-Modified age, and a 301 can be cached essentially indefinitely by browsers (see §6).

### Gaps
- I did not verify how each browser computes heuristic freshness today (for example whether Chrome or Firefox cap the 10% heuristic). The RFC leaves it to implementations, and this needs Chromium or Gecko source checks.
- `stale-if-error` support in browser HTTP caches: BCD has no response-directive support entry, so browser support is unconfirmed. Treat it as a CDN/proxy feature.

---

## 2. How validators and conditional requests work: ETag, Last-Modified, 304, and when ETags hurt

### Takeaway
Send both a strong `ETag` and `Last-Modified` on every cacheable 200 response. `If-None-Match` takes precedence and uses weak comparison. A 304 must repeat `Cache-Control`/`Expires`, `ETag`, `Vary`, `Date` and `Content-Location`. ETags break when they differ across servers or encodings, or when a proxy strips or weakens them on compression. Generate ETags from content hashes, deterministically, after encoding decisions.

### Cited Findings
- Strong vs weak: "If an origin server provides an entity tag … and the generation of that entity tag does not satisfy all of the characteristics of a strong validator … the origin server MUST mark the entity tag as weak by prefixing its opaque value with `W/`" (case-sensitive) — [RFC 9110 §8.8.3](https://httpwg.org/specs/rfc9110.html)
- How tags compare:

  | ETag 1 | ETag 2 | Strong | Weak |
  |---|---|---|---|
  | `W/"1"` | `W/"1"` | no match | match |
  | `W/"1"` | `W/"2"` | no match | no match |
  | `W/"1"` | `"1"` | no match | match |
  | `"1"` | `"1"` | match | match |

  — [RFC 9110 §8.8.3.2](https://httpwg.org/specs/rfc9110.html)
- `If-None-Match` MUST use weak comparison, so weak ETags work for cache validation. `If-Match` MUST use strong comparison (to prevent lost updates). `If-Range` requires an exact strong match — [RFC 9110 §13.1.1, §13.1.2, §13.1.5](https://httpwg.org/specs/rfc9110.html)
- "A recipient MUST ignore If-Modified-Since if the request contains an If-None-Match header field" — [RFC 9110 §13.1.3](https://httpwg.org/specs/rfc9110.html)
- A 304 MUST include any of `Content-Location`, `Date`, `ETag` and `Vary` that a 200 would have carried, plus `Cache-Control` and `Expires`. It SHOULD NOT include other representation metadata unless that metadata exists to guide cache updates (for example `Last-Modified` when there is no ETag). It has no body — [RFC 9110 §15.4.5](https://httpwg.org/specs/rfc9110.html)
- A 206 MUST also carry `Date`, `Cache-Control`, `ETag`, `Expires`, `Content-Location` and `Vary` when a 200 would have — [RFC 9110 §15.3.7](https://httpwg.org/specs/rfc9110.html)
- Different content codings are different representations and should have different ETags. RFC example: identity `ETag: "123-a"` and gzip `ETag: "123-b"`, both with `Vary: Accept-Encoding` — [RFC 9110 §8.8.3.3](https://httpwg.org/specs/rfc9110.html)
- When a cache revalidates, it synthesizes the request by copying the method, URI and the request headers named in `Vary`, then adds `If-None-Match` and/or `If-Modified-Since` from stored responses — [RFC 9111 §4.3.1](https://httpwg.org/specs/rfc9111.html)
- MDN recommends both validators, because `Last-Modified` is also used by CMSs and crawlers. During revalidation `If-None-Match` wins. Problems with `Last-Modified`: one-second resolution and "distributed servers have difficulty synchronizing file-update times" — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Weak ETags "prevent caching when byte range requests are used, but strong ETags mean range requests can still be cached". ETag values must be quoted ASCII, e.g. `ETag: "33a64df5…"`, `ETag: W/"0815"` — [MDN ETag](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag)
- nginx: since 1.7.3, strong ETags are downgraded to weak when nginx modifies the response (gzip on the fly). Before that it removed them. **Unquoted upstream ETags (`ETag: abc`) are still dropped entirely**; the fix is for the upstream to send valid quoted ETags — [nginx mailing list 2020](https://mailman.nginx.org/pipermail/nginx/2020-January/058856.html); [nginx trac #377](https://trac.nginx.org/nginx/ticket/377); [nginx list 2013](https://mailman.nginx.org/pipermail/nginx/2013-June/039319.html)
- Fetch gotcha: if JavaScript adds `If-None-Match`, `If-Modified-Since`, `If-Match`, `If-Unmodified-Since` or `If-Range` to `fetch()` itself, the request's cache mode switches from `"default"` to `"no-store"`, bypassing the browser HTTP cache — [Fetch Standard, request cache mode](https://fetch.spec.whatwg.org/#concept-request-cache-mode)
- `ETag` plus `If-Match` also prevents "mid-air collisions" on writes (412 on mismatch) — [MDN ETag](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/ETag)

### Inferences
- Multi-server mismatch: if each server in a pool derives ETags from per-machine metadata (inode, mtime that differs after deploy), the same bytes get different ETags on different servers. Revalidations behind a load balancer then miss and return full 200s. Fix: derive ETags from a content hash (the build hash for static files, a hash of the serialized body or a version number for dynamic content). Or disable ETags and rely on Last-Modified when mtimes are synchronized at deploy.
- Compute ETags after deciding on encoding, or tag per encoding (as in the RFC 9110 example), so a cache never pairs a gzip ETag with a brotli body.
- For fingerprinted assets with `immutable`/one-year `max-age`, validators matter only after expiry, eviction or a force reload. They are cheap insurance, not the main mechanism.
- For HTML with `no-cache`, a validator is what makes `no-cache` cheap (a 304 is tiny). Without one, every navigation downloads the full page.

### Gaps
- No primary source found this session for Apache `FileETag` (inode-based) defaults in 2026. The multi-server inference above is general knowledge, not checked against Apache docs.

---

## 3. How to use Vary correctly: cardinality pitfalls, Cookie, Accept-Encoding, Accept, Client Hints

### Takeaway
`Vary` adds request headers to the cache key. Every value you list multiplies the number of cache entries and lowers the hit rate. Use it only for real content negotiation, such as `Accept-Encoding`, `Accept` for image formats, `Accept-Language`, `Origin` for dynamic CORS, and low-cardinality client hints. Send the same `Vary` on every response for the URL, including 304s. Use `Cache-Control: private` instead of `Vary: Cookie` or `Vary: User-Agent`.

### Cited Findings
- `Vary` lists "the parts of the request message (aside from the method and URL) that influenced the content". "The same Vary header value should be used on all responses for a given URL, including 304 Not Modified responses and the 'default' response". `Vary: *` "implies that the response is uncacheable" — [MDN Vary](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Vary)
- "A stored response with a Vary header field value containing a member '*' always fails to match". When stored responses omit Vary (the "default" response), caches SHOULD prefer the most recent stored response that has a valid Vary — [RFC 9111 §4.1](https://httpwg.org/specs/rfc9111.html)
- An origin "SHOULD generate a Vary header field on a cacheable response when it wishes that response to be selectively reused" — [RFC 9110 §12.5.5](https://httpwg.org/specs/rfc9110.html)
- `Vary: User-Agent` "drastically reduces the chance that the cache will be reused"; use feature detection instead. "For applications that employ cookies to prevent others from reusing cached personalized content, you should specify Cache-Control: private instead of specifying a cookie for Vary" — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- CORS: if `Access-Control-Allow-Origin` is computed per request, send `Vary: Origin`. Otherwise a cached response to a non-CORS request (for example a navigation), which lacks ACAO, gets reused for a later CORS request and fails. If ACAO is `*` or a static origin, always send it, on non-CORS responses too — [Fetch Standard, "CORS protocol and HTTP caches"](https://fetch.spec.whatwg.org/#cors-protocol-and-http-caches)
- Client hints that select resources "should generally also be included in the affected response's Vary header" (e.g. `Vary: Accept, Width, ECT`). Hints whose values vary a lot make the resource "effectively … uncacheable". `Critical-CH` makes the browser retry the request with the hint, and every header in `Critical-CH` should also be in `Vary` — [MDN Client hints](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Client_hints)
- **`Accept-CH` and `Critical-CH` are Chromium-only** (Chrome 46 and 91; not in Firefox or Safari) — [BCD Accept-CH / Critical-CH](https://github.com/mdn/browser-compat-data/tree/main/http/headers)
- Dictionary-compressed responses (see §4) "must include" `Vary: accept-encoding, available-dictionary` if cacheable — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
- If service-worker navigation-preload responses differ from normal ones, the server "must set `Vary: Service-Worker-Navigation-Preload`" — [MDN NavigationPreloadManager](https://developer.mozilla.org/en-US/docs/Web/API/NavigationPreloadManager)
- The service-worker Cache API also matches on the stored response's `Vary`. "The key matching algorithm depends on the VARY header in the value" (`cache.match(req, {ignoreVary: true})` opts out) — [MDN Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)

### Inferences
- Default `Vary` per resource type:
  - Compressed text assets: `Vary: Accept-Encoding`. Most servers and CDNs add it automatically.
  - Images negotiated by format (AVIF/WebP): `Vary: Accept`. The CDN should normalize `Accept` to a few buckets, or the cache fragments.
  - Localized HTML: `Vary: Accept-Language` only when the language is negotiated; prefer locale in the URL.
  - Dynamic CORS: `Vary: Origin`.
  - Never `Vary: Cookie` or `Vary: Authorization` on shared-cacheable content. Mark it `private` instead, or strip cookies at the edge for public pages.
- `Vary: Cookie` on a site with analytics cookies is in effect `Vary: *`: every visitor has unique cookie values, so the hit rate approaches zero.
- Some CDNs handle `Vary` only for a small allowlist of headers (the CDN researcher covers this). Normalize headers before they reach the cache key.

### Gaps
- I did not verify which browsers partition their HTTP cache by `Vary` correctly for high-cardinality hints, or whether Chrome caps the number of variants per URL.

---

## 4. Which newer headers and standards are usable in late 2026, and where they are supported

### Takeaway
Safe to deploy everywhere: `stale-while-revalidate` in browsers; `Clear-Site-Data` (with caveats on `"cache"` in Chrome); 103 Early Hints over HTTP/2 or HTTP/3; `CDN-Cache-Control` and `Cache-Status`, which are CDN-side and ignored by browsers.

Progressive enhancement, mostly Chromium:
- No-Vary-Search: HTTP cache in Chrome 141+ and Firefox 154+; not Safari.
- Compression Dictionary Transport (RFC 9842): Chrome 130+; Firefox behind a flag; not Safari.
- Speculation Rules: Chromium full; Safari 26.2+ behind a flag; Firefox Nightly prefetch only.

Dead: HTTP/2 Server Push (removed from Chrome and Firefox) and `<link rel=prerender>`.

### Cited Findings

**CDN-Cache-Control and targeted cache control (RFC 9213, Proposed Standard, 2022)**
- RFC 9213 defines a convention for "targeted" response headers and one instance of it, `CDN-Cache-Control`. A cache with a target list, e.g. `[ExampleCDN-Cache-Control, CDN-Cache-Control]`, "MUST select the first … field with a valid, non-empty value … and it MUST ignore the Cache-Control and Expires header fields in that response" — [RFC 9213 §2](https://httpwg.org/specs/rfc9213.html)
- Targeted fields are **Structured Field Dictionaries**, so a strict SF parser is required. If the field is empty or fails to parse, it MUST be ignored and the cache falls back to Cache-Control. Caches using it MUST implement `max-age`, `must-revalidate`, `no-store`, `no-cache` and `private` — [RFC 9213 §2.1–2.2](https://httpwg.org/specs/rfc9213.html)
- Examples. `Cache-Control: max-age=60, s-maxage=120` + `CDN-Cache-Control: max-age=600` gives 600 s at the CDN, 120 s at other shared caches, and 60 s in browsers. `CDN-Cache-Control: max-age=600` + `Cache-Control: no-store` gives "CDN caches only". Downstream caches may see "prematurely" aged responses, so freshness interactions need care — [RFC 9213 §3.1, §2.3](https://httpwg.org/specs/rfc9213.html)

**Cache-Status (RFC 9211, Proposed Standard, 2022)**
- `Cache-Status` is a Structured-Field List with one member per cache. The first member is the cache closest to the origin, the last the cache closest to the user. Parameters:
  - `hit`
  - `fwd`, with values `bypass`, `method`, `uri-miss`, `vary-miss`, `miss`, `request`, `stale`, `partial`
  - `fwd-status`, `ttl`, `stored`, `collapsed`, `key`, `detail`

  Examples: `Cache-Status: ExampleCache; hit; ttl=376`, `ExampleCache; fwd=stale; fwd-status=304`, `OriginCache; hit; ttl=1100, "CDN Company Here"; hit; ttl=545` — [RFC 9211](https://httpwg.org/specs/rfc9211.html)

**Cache Groups (IETF draft)**
- `draft-ietf-httpbis-cache-groups` defines a `Cache-Groups: "scripts"` response header (an SF List of Strings) that tags stored responses, and `Cache-Group-Invalidation`, which lets a state-changing response invalidate whole groups in the same cache for the same origin. Caches MUST support at least 32 groups of at least 32 characters each — [draft-ietf-httpbis-cache-groups](https://httpwg.org/http-extensions/draft-ietf-httpbis-cache-groups.html)

**No-Vary-Search (IETF httpbis draft; experimental)**
- Syntax: `No-Vary-Search: key-order`, `params`, `params=("utm_source" "utm_medium")`, `params, except=("id")`. Values are an SF dictionary; list members are space-separated quoted strings, not comma-separated — [MDN No-Vary-Search](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/No-Vary-Search); [draft-ietf-httpbis-no-vary-search](https://httpwg.org/http-extensions/draft-ietf-httpbis-no-vary-search.html)
- Draft text: "cache busting … can be made ineffective by the No-Vary-Search response header field". Intermediaries MUST NOT modify it unless acting as origin — [draft-ietf-httpbis-no-vary-search](https://httpwg.org/http-extensions/draft-ietf-httpbis-no-vary-search.html)
- Support (BCD 8.1.7):
  - HTTP cache: **Chrome 141** (desktop), **Chrome Android 143**, **Firefox 154**, **Safari: no**
  - Speculation-rules prefetch: Chrome 121
  - Speculation-rules prerender: Chrome 127

  — [BCD No-Vary-Search](https://github.com/mdn/browser-compat-data/blob/main/http/headers/No-Vary-Search.json); [caniuse mdn-http_headers_no-vary-search_http_cache](https://caniuse.com/mdn-http_headers_no-vary-search_http_cache)
- Chrome's Intent to Ship for the disk cache (Sept 2025) calls No-Vary-Search "best-effort", meaning servers cannot rely on caches implementing it — [blink-dev Intent to Ship](https://groups.google.com/a/chromium.org/g/blink-dev/c/_G2dhImS2yw/m/-YLVE3vIAgAJ) (search snippet)
- In January 2026 Chrome engineers noted on the IETF list that a proposed change to the `params` syntax "potentially breaks interoperability" with deployments of the current draft syntax — [ietf-http-wg 2026JanMar/0027](https://lists.w3.org/Archives/Public/ietf-http-wg/2026JanMar/0027.html) (search snippet). **Flag: the syntax may still change.**
- With prerender, the page may first be prerendered with different query parameters, so "any code depending on them should only run after prerender activation". Speculation rules accept `"expects_no_vary_search": "params=(\"id\")"` hints — [MDN No-Vary-Search](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/No-Vary-Search)

**Compression Dictionary Transport (RFC 9842; experimental in browsers)**
- How it works:
  - A resource declares itself a dictionary: `Use-As-Dictionary: match="/js/app.*.js"` (optional `id="..."`, sent back as `Dictionary-ID`).
  - Later matching requests send `Accept-Encoding: gzip, br, zstd, dcb, dcz` and `Available-Dictionary: :<base64 SHA-256>:`.
  - The server replies `Content-Encoding: dcb` (Brotli) or `dcz` (Zstandard) and must add `Vary: accept-encoding, available-dictionary`.
  - Standalone dictionaries can be offered with `<link rel="compression-dictionary" href="/dictionary.dat">` or `Link: </dictionary.dat>; rel="compression-dictionary"`.

  — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport); [RFC 9842](https://www.rfc-editor.org/info/rfc9842/)
- **A dictionary's lifetime is its HTTP freshness.** A response with `no-store` or `no-cache` is never used as a dictionary. `max-age=0, stale-while-revalidate=N` keeps it usable for N seconds. `must-revalidate` cancels the SWR window. So HTML served `no-cache` cannot act as a dictionary for its next version, and the browser "silently drops the dictionary" (Chrome reports it in the DevTools Issues panel) — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
- Restrictions:
  - Dictionaries must be same-origin with the resources that use them.
  - Compressed resources must be same-origin or CORS.
  - Dictionaries are partitioned like the HTTP cache, so they are not shared across sites.
  - CSP `connect-src` must allow separate dictionaries.

  Build-time commands: `echo -en '\xffDCB' > f.dcb && openssl dgst -sha256 -binary dict >> f.dcb && brotli --stdout -D dict f >> f.dcb` (dcz uses an 8-byte magic header `\x5e\x2a\x4d\x18\x20\x00\x00\x00`) — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
- Support:
  - `Use-As-Dictionary` / `dcb` / `dcz`: **Chrome/Edge 130+**; **Firefox behind a flag (145) / Nightly preview**; **Safari: no**. Marked experimental — [BCD Use-As-Dictionary / Content-Encoding](https://github.com/mdn/browser-compat-data/tree/main/http/headers)
  - Plain `zstd` Content-Encoding: Chrome 123, Firefox 126, Safari 26.3 (macOS 26.3+) — [BCD Content-Encoding](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Content-Encoding.json)

**Clear-Site-Data**
- Directives must be quoted strings: `"cache"`, `"cookies"`, `"storage"` (localStorage, sessionStorage, IndexedDB, service worker registrations, OPFS), `"clientHints"`, `"executionContexts"`, `"prefetchCache"`, `"prerenderCache"`, `"*"`. Logout recipe: `Clear-Site-Data: "cache", "cookies", "storage", "executionContexts", "prefetchCache", "prerenderCache"`. `"cookies"` affects the whole registrable domain including subdomains. `"cache"` may also clear prerendered pages and the bfcache — [MDN Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- Clear-Site-Data does not affect shared or intermediate caches — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- Support:
  - Header: Chrome 61, Firefox 63, Safari 17.
  - **`"cache"` is partial in Chrome (127+)**: "Some requests may still be taken from the cache unless the tab is reloaded or the page is requested in a new tab" (crbug 364634040), and it "may cause seconds-long hangs".
  - Firefox re-enabled `"cache"` in 138.
  - `"prefetchCache"`/`"prerenderCache"`: Chrome 138, non-standard.
  - `"clientHints"`: Chrome 117.
  - `"executionContexts"`: removed (Firefox 68, Safari 18.3); never in Chrome.

  — [BCD Clear-Site-Data](https://github.com/mdn/browser-compat-data/blob/main/http/headers/Clear-Site-Data.json)

**103 Early Hints**
- Usage: `103 Early Hints` with `Link: </style.css>; rel=preload; as=style` or `Link: <https://cdn.example.com>; rel=preconnect`. A CSP can be included. "Browsers only process the first early hints response", and it is discarded on a cross-origin redirect. Send it only over HTTP/2 or later — [MDN 103](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/103)
- Support: **Chrome 103 (HTTP/2+ only), Firefox 120, Safari 17 (HTTP/2+ only)** — [BCD http.status.103](https://github.com/mdn/browser-compat-data/tree/main/http/status)

**HTTP/2 Server Push: removed**
- Chrome disabled push by default in **Chrome 106**, citing 1.25% usage and frequent performance regressions, and recommended 103 Early Hints instead. **Firefox 132 (Oct 2024)** removed support — [Chrome "Removing HTTP/2 Server Push"](https://developer.chrome.com/blog/removing-push); [Wikipedia: HTTP/2 Server Push](https://en.wikipedia.org/wiki/HTTP/2_Server_Push); [LWN](https://lwn.net/Articles/996216/) (search snippets)

**Speculation Rules API (prefetch/prerender), experimental**
- Support (BCD 8.1.7):
  - `<script type="speculationrules">`: Chrome 109+ (prerender since 105, prefetch 110).
  - Firefox: Nightly "preview" only, partial (URL-list prefetch only; eagerness `immediate`/`moderate` only).
  - Safari 26.2 behind a flag; for document rules only `conservative`, with `moderate` falling back to it.
  - `Speculation-Rules` HTTP header: Chrome 121.
  - `eagerness`: Chrome 121. `tag`: Chrome 136. `target_hint`: Chrome 138. `form_submission`: Chrome 151.

  — [BCD html.elements.script.type.speculationrules](https://github.com/mdn/browser-compat-data/blob/main/html/elements/script.json)
- Eagerness values:
  - `immediate`: as soon as possible.
  - `eager`: "any slight suggestion".
  - `moderate`: e.g. hover or focus "for some time".
  - `conservative`: on `mousedown`/`pointerdown`.

  Defaults: list (`urls`) rules → `immediate`; document (`where`) rules → `conservative`. For list rules, "`eager` has the same effect as `immediate` in current implementations" — [MDN speculationrules](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/script/type/speculationrules)
- Chrome limits: `immediate`/`eager` up to **50 prefetches and 10 prerenders**; `moderate`/`conservative` **2 each, FIFO**. In 2025 Chrome redefined `eager` to sit between `immediate` and `moderate`; one source describes a 10 ms hover on desktop and a viewport/scroll-pause heuristic on mobile — [Chrome: Prerender pages](https://developer.chrome.com/blog/prerender-pages); [Chrome: speculation rules improvements](https://developer.chrome.com/blog/speculation-rules-improvements) (search snippets; sources disagreed on exact mobile `moderate` behavior)
- Caching behavior:
  - Prefetches and prerenders live in a **per-document in-memory cache** and are discarded on navigation away; they may also populate the HTTP cache if headers allow.
  - "Chrome … caches them for 5 minutes", so users may see content up to 5 minutes old.
  - Requests carry `Sec-Purpose: prefetch` or `Sec-Purpose: prefetch;prerender`.
  - Any non-2xx response, and 204/205, cancels the speculation.
  - Cross-site prefetch only works when the user has no cookies for the target.
  - Prerender is same-origin by default; cross-origin same-site needs `Supports-Loading-Mode: credentialed-prerender`.
  - Speculation rules prerender "doesn't get blocked by Cache-Control settings".

  — [MDN Speculation Rules API](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)
- `<link rel="prerender">` is deprecated; in Chrome it only triggers NoState Prefetch — [BCD link rel=prerender](https://github.com/mdn/browser-compat-data/blob/main/html/elements/link.json)
- `Sec-Purpose` request header: Chrome 110, Firefox 115 — [BCD Sec-Purpose](https://github.com/mdn/browser-compat-data/tree/main/http/headers)

### Inferences
- For a skill recommending headers:
  - Always safe: `stale-while-revalidate`, `CDN-Cache-Control` (if the CDN supports it), `Cache-Status` for debugging, and `Clear-Site-Data` on logout.
  - Chromium-first progressive enhancements: `No-Vary-Search` for pages with tracking params, speculation rules with `moderate` on document rules, and compression dictionaries for frequently redeployed large JS bundles.
  - Avoid: Server Push.
- Speculation rules plus long HTML caching are a staleness risk (5-minute prefetch cache). Pair them with `Clear-Site-Data: "prefetchCache", "prerenderCache"` on state-changing endpoints such as logout or cart changes.
- `No-Vary-Search` and query-string cache busting conflict. If both are used, list the cache-busting parameter in `except=(...)` or switch to filename hashing.

### Gaps
- The exact Chrome 2025–2026 eagerness timings (hover ms, mobile viewport heuristic) could not be verified from the primary page; the web-search budget was exhausted.
- Which `Link` rel types each browser honors in 103 responses (for example whether Safari honors only `preconnect`) was not verified.
- Publication status of the No-Vary-Search and Cache-Groups drafts as of Oct 2026 (still Internet-Drafts or RFCs) was not verified.

---

## 5. Browser cache internals that shape strategy: memory vs disk cache, partitioning, bfcache, reload behavior

### Takeaway
Browsers key the HTTP cache by top-level site as well as URL. Chrome since 86, plus a cross-site-navigation bit added in 2025. Shared public CDN copies of libraries therefore give no cross-site cache hits; self-host them. Back/forward navigations are served from bfcache or history without revalidation. Main blockers are `unload` handlers (by default these no longer run in Chrome 155+), `Cache-Control: no-store` on the document (allowed in Chrome since 2025 under conditions; still blocking in Firefox and Safari), open connections, and `window.opener`. Normal reload revalidates the document with `max-age=0`. Chrome skips subresource revalidation on reload; Firefox and Safari honor `immutable`.

### Cited Findings

**HTTP cache partitioning**
- Since Chrome 86 the cache key is a "Network Isolation Key" (top-level site, current-frame site) plus the resource URL. Sites are `scheme://eTLD+1`, so subdomains and ports share a partition. Chrome's own example: `x.example/doge.png` loaded by `a.example` is a cache miss when `b.example` loads it. Motivation: history sniffing, cross-site search attacks and cache-based tracking — [Chrome: Gaining security and privacy by partitioning the cache](https://developer.chrome.com/blog/http-cache-partitioning)
- Feb 2025 Intent to Ship: add an "is-cross-site-main-frame-navigation" boolean to the key, to partition cross-site top-level navigations — [blink-dev Intent to Ship](https://groups.google.com/a/chromium.org/g/blink-dev/c/ZpyP6jjCUJE) (search snippet; milestone not confirmed)
- Compression dictionaries "are bound by the usual HTTP Cache partitioning and so cannot be shared between origins" — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
- Storage (IndexedDB, Cache API, OPFS) is managed per origin. Browsers may further partition third-party iframes — [MDN Storage quotas](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)

**Reload behavior**
- Normal reload sends `Cache-Control: max-age=0` plus `If-None-Match`/`If-Modified-Since` (Chrome, Edge and Firefox; Safari differs). Fetch equivalent: `fetch(url, {cache: "no-cache"})`.
- Force reload sends `Pragma: no-cache` and `Cache-Control: no-cache` with no validators. Fetch equivalent: `fetch(url, {cache: "reload"})`.

  — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Fetch cache modes:

  | Mode | Behavior |
  |---|---|
  | `default` | Uses a fresh cached response; for a `stale-while-revalidate` response, returns it and revalidates in the background; otherwise makes a conditional or normal request |
  | `no-store` | As if there were no HTTP cache |
  | `reload` | Skips the cache, then updates it |
  | `no-cache` | Always makes a conditional request |
  | `force-cache` | Uses any cached response, even stale |
  | `only-if-cached` | Same-origin only; network error if nothing is cached |

  — [Fetch Standard](https://fetch.spec.whatwg.org/#concept-request-cache-mode)
- Chrome does not revalidate subresources on normal reload (since 2017), instead of implementing `immutable` — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)

**bfcache: how pages are restored and what blocks it**
- Detect restores with `pageshow`:
  ```js
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) { /* restored from bfcache: refresh stale UI/data, re-open connections */ }
  });
  window.addEventListener('pagehide', (e) => {
    /* close IndexedDB/WebSocket here; e.persisted===true means it *may* be cached */
  });
  ```
  — [web.dev bfcache](https://web.dev/articles/bfcache)
- `unload`:
  - Chrome and Firefox desktop make pages with `unload` listeners ineligible. Use `pagehide` instead.
  - Lighthouse has a `no-unload-listeners` audit — [web.dev bfcache](https://web.dev/articles/bfcache)
  - `Permissions-Policy: unload=()` (Chrome 115+) blocks unload handlers, including those in third-party iframes. In Chrome the **default allowlist is now `()`**, so unload handlers do not run unless opted in with `Permissions-Policy: unload=self` — [MDN Permissions-Policy: unload](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/unload)
  - BCD records that from **Chrome 155** (2026-10-06) "the unload event fires only if the Permissions-Policy header's unload directive is set" — [BCD api.Window.unload_event](https://github.com/mdn/browser-compat-data/blob/main/api/Window.json)
- `beforeunload`: does not block bfcache in Chrome or Safari but does in Firefox. Add it only while there are unsaved changes and remove it afterwards — [web.dev bfcache](https://web.dev/articles/bfcache)
- Other blockers in some browsers: open IndexedDB connections, in-progress fetch/XHR, open WebSocket/WebRTC connections, and a non-null `window.opener` (use `rel="noopener"`). Close these in `pagehide` and reopen them in `pageshow` — [web.dev bfcache](https://web.dev/articles/bfcache)
- `Cache-Control: no-store` on the main document used to block bfcache in all browsers. **Chrome finished rolling out bfcache for `no-store` pages to 100% over March–April 2025**, with conditions:
  - The page is evicted if cookies or other authorization change, if it uses WebSocket, WebTransport or WebRTC, or if a fetch/XHR response had `Cache-Control: no-store`.
  - The bfcache timeout for such pages is **3 minutes instead of 10**.
  - Other browsers may still refuse.

  — [Chrome: Enabling bfcache for Cache-Control: no-store](https://developer.chrome.com/docs/web-platform/bfcache-ccns); [RUMvision](https://www.rumvision.com/blog/chrome-now-ignores-cache-control-no-store-why-you-should-care/) (search snippets)
- Diagnostics:
  - `PerformanceNavigationTiming.notRestoredReasons`: Chrome 125+, not in Firefox or Safari — [BCD NotRestoredReasons](https://github.com/mdn/browser-compat-data/blob/main/api/NotRestoredReasons.json)
  - DevTools: **Application → Back/forward cache → Run Test**.
  - Lighthouse 10+ has a bfcache audit.

  — [web.dev bfcache](https://web.dev/articles/bfcache)

### Inferences
- Shared public CDNs (cdnjs, jsDelivr, unpkg, Google Fonts) give no cross-site cache benefit under partitioning, and they add DNS, TLS and connection costs plus a third-party dependency. Recommend self-hosting fingerprinted copies on the first-party origin or CDN.
- Pages that need "no back-button snapshot" (for example after logout) should not rely on `no-store` alone, because Chrome may now bfcache them. Use `pageshow` with `event.persisted` to re-check auth, and send `Clear-Site-Data` on logout. Reserve `no-store` for truly sensitive documents.
- `Permissions-Policy: unload=()` is a cheap, high-value default header for any site that does not need unload.

### Gaps
- Memory cache vs disk cache: I could not retrieve a primary 2026 source on Chrome's in-memory cache (DevTools labels "(memory cache)" and "(disk cache)", which resources are kept in memory, and lifetimes). General knowledge, unverified here: the memory cache is per-renderer, short-lived, and serves repeat requests within a page or session, sometimes regardless of headers.
- HTTP cache partitioning in Firefox and Safari: not verified this session. General knowledge: Safari has partitioned for many years, and Firefox has had "network partitioning" since about version 85.
- Firefox and Safari's current stance on bfcache with `no-store` in 2026 was not verified beyond "may still block".

---

## 6. What headers to use per resource type

### Takeaway
Two patterns cover most sites:
1. Fingerprinted subresources: `Cache-Control: public, max-age=31536000, immutable`, or without `public` when unsure about Authorization.
2. URLs that can't be fingerprinted (HTML, manifest, favicon, `.well-known`, service worker script, APIs): `Cache-Control: no-cache` with `ETag` and `Last-Modified`, plus `private` if personalized.

Everything else is a tuned middle ground: short `max-age` plus `stale-while-revalidate`, with explicit TTLs on redirects and errors so heuristic caching never decides.

### Cited Findings
- Versioned assets:
  ```http
  # bundle.v123.js
  Cache-Control: public, max-age=31536000, immutable
  Last-Modified: Tue, 22 Feb 2022 20:20:20 GMT
  ETag: "YsAIAAAA-QG4G6kCMAMBAAAAAAAoK"
  ```
  MDN notes `public` should be used "only if there is a need to store the response when the Authorization header is set". "If you can't be certain", use `Cache-Control: max-age=2592000` — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Simplest asset rule, `/assets/*`: `Cache-Control: max-age=31536000, immutable`. If HTML is behind Basic/Digest auth, assets need `public`, `s-maxage` or `must-revalidate` to be shared-cacheable — [MDN Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- HTML (main resources can't be cache-busted):
  ```http
  Cache-Control: no-cache
  Last-Modified: …
  ETag: "AAPuIbAOdvAGEETbgAAAAAAABAAE"
  ```
  Personalized or logged-in HTML: `Cache-Control: no-cache, private`. "The same can be used for `favicon.ico`, `manifest.json`, `.well-known`, and API endpoints whose URLs cannot be changed using cache busting" — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Site-wide default when nothing else matches: `Cache-Control: no-cache`, or `no-cache, private` for apps with logins — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Sensitive or never-store content: `Cache-Control: no-store`. Do not use the kitchen-sink form. If the worry is shared caches, `Cache-Control: no-cache, private` is preferred because it keeps bfcache and similar benefits — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Aggressive HTML caching is possible only with a managed cache that can purge: a CDN purge API, or a service worker updating Cache API entries — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Service worker script: since Chrome 68 the main SW script's update checks bypass the HTTP cache by default (`updateViaCache: 'imports'`); `importScripts()` still uses the HTTP cache. Options:
  - `'all'`: HTTP cache for the main script and imports.
  - `'imports'` (default): imports only.
  - `'none'`: neither.

  `registration.update()` bypasses the HTTP cache if 24 hours have passed since the last check. Older Chrome behavior capped SW script max-age at 86400 s — [MDN ServiceWorkerContainer.register()](https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerContainer/register); [Chrome: Fresher service workers, by default](https://developer.chrome.com/blog/fresher-sw) (search snippet). `updateViaCache` support: Chrome 68, Firefox 57, Safari 11.1 — [BCD](https://github.com/mdn/browser-compat-data/blob/main/api/ServiceWorkerRegistration.json)
- Redirects:
  - 301 and 308 are heuristically cacheable; 302, 303 and 307 are not — [RFC 9110 §15.1](https://httpwg.org/specs/rfc9110.html)
  - MDN's live 301 example carries `cache-control: max-age=2592000,public` (30 days) — [MDN 301](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/301)
  - Use 308 instead of 301 to forbid method changes — [MDN 301](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/301)
- Errors:
  - 404, 405, 410, 414 and 501 are heuristically cacheable — [RFC 9110 §15.1](https://httpwg.org/specs/rfc9110.html)
  - `stale-if-error` lets caches serve the last good copy on 500/502/503/504 — [RFC 5861](https://httpwg.org/specs/rfc5861.html)
- Speculative-load requests can be identified by `Sec-Purpose: prefetch`. A non-2xx response cancels the prefetch — [MDN Speculation Rules API](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)
- Compression dictionaries need a positive freshness lifetime, e.g. `max-age=…` or `max-age=0, stale-while-revalidate=…` — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)

### Inferences
Recommended recipe table. Exact values are proposals that synthesize the sources above; "CDN" lines assume RFC 9213 support.

| Resource | Recommended response headers | Notes |
|---|---|---|
| Fingerprinted JS/CSS/fonts/images (`app.3f9a1c.js`) | `Cache-Control: public, max-age=31536000, immutable` (drop `public` if any Authorization-based auth fronts the origin) + strong `ETag` | Never reuse a hashed URL for different bytes. Fonts loaded cross-origin also need `Access-Control-Allow-Origin` and `Vary: Origin` if ACAO is dynamic |
| Non-fingerprinted static images and media (CMS uploads) | `Cache-Control: max-age=86400, stale-while-revalidate=604800` + `ETag` (CDN: `CDN-Cache-Control: max-age=2592000` + purge on change) | Or rename on edit. Avoid a one-year TTL without a hash |
| HTML, public, not personalized | `Cache-Control: no-cache` + `ETag`/`Last-Modified` (CDN: `CDN-Cache-Control: max-age=300, stale-while-revalidate=3600` or longer with purge) | Browser always revalidates (304s); the edge holds it |
| HTML, personalized or logged in | `Cache-Control: no-cache, private` (or `private, max-age=0`) + `ETag` | `no-store` only if truly sensitive. Clear on logout with `Clear-Site-Data` |
| Highly sensitive pages (banking, PII, tokens) | `Cache-Control: no-store` | Note Chrome may still bfcache them (with eviction on cookie change). Re-check auth on `pageshow` |
| Public API JSON (catalog, config) | `Cache-Control: public, max-age=60, stale-while-revalidate=300` (or `s-maxage` / CDN-Cache-Control for the edge) + `ETag`; `Vary: Accept-Encoding` (+ `Origin` if dynamic CORS) | Use `max-age` only if clients tolerate that much staleness |
| User-specific API JSON | `Cache-Control: private, no-cache` + `ETag` (or `private, max-age=0`) | Requests with `Authorization` are never shared-cached unless `public`/`s-maxage`/`must-revalidate` is present, so don't add those |
| Mutation responses (POST/PUT/DELETE) | `Cache-Control: no-store` | Caches invalidate the target URI automatically on 2xx/3xx |
| `manifest.webmanifest`, `favicon.ico`, `robots.txt`, `/.well-known/*` | `Cache-Control: no-cache` + `ETag` (or `max-age=3600–86400` if staleness is fine) | Fixed URLs; can't be fingerprinted |
| `sw.js` (service worker script) | `Cache-Control: no-cache` (or `max-age=0`) + `ETag`; register with default `updateViaCache: 'imports'`; fingerprint `importScripts` URLs | Browsers bypass the HTTP cache for the main script by default anyway |
| Import map / module entry HTML | Treat as HTML (`no-cache`) | The map points to hashed module URLs |
| 301/308 permanent redirect | Explicit `Cache-Control: max-age=86400` at first (raise to 30 days or a year once confident) | Without Cache-Control, browsers may cache 301s heuristically for a very long time and you can't recall them |
| 302/307 temporary redirect | `Cache-Control: no-store` or `no-cache` (or a short `max-age` if intended) | Not heuristically cacheable, but be explicit |
| 404/410 | `Cache-Control: max-age=60` (public) or `no-cache`; long only for truly gone URLs (410) | Prevents heuristic caching of transient 404s during deploys |
| 5xx | `Cache-Control: no-store` (or a short `max-age=5–10` at the CDN only) | Let `stale-if-error` on the previous 200 cover outages |
| Compression dictionary resource | `Cache-Control: max-age=…` or `max-age=0, stale-while-revalidate=…` (not `no-cache`/`no-store`/`must-revalidate`) | Otherwise it is silently not used |

- Never send `Set-Cookie` on responses marked shared-cacheable (`public`, `s-maxage`); many shared caches either refuse to store them or store the cookie and leak it. This is general practice, unverified this session.

### Gaps
- No primary source found for concrete recommended TTLs for 404, 5xx or redirects. The values above are reasoned defaults, not standards.
- I could not retrieve current Google Fonts or other CDN font header defaults.

---

## 7. How to version assets and bust caches: content hashes, query strings, import maps, deploy skew

### Takeaway
Put a content hash in the filename (not the query string), serve those files `immutable` for a year, and keep HTML revalidating. Then handle deployment skew: keep previous builds' assets available for days or weeks so already-open tabs and cached HTML can still load their chunks, and recover from chunk-load 404s on the client. Import maps (and their `integrity` map) let hashed module URLs change without cascading hash changes through every importer.

### Cited Findings
- MDN lists four cache-busting forms:
  - `bundle.v123.js` (version in filename)
  - `bundle.js?v=123` (version in query)
  - `bundle.YsAIAAAA-QG4G6kCMAMBAAAAAAAoK.js` (hash in filename)
  - `bundle.js?v=YsAIAAAA…` (hash in query)

  Caches key on the full URL, so any of these busts the cache — [MDN HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching)
- Query-string busting can be neutralized by `No-Vary-Search` ("cache busting … can be made ineffective") — [draft-ietf-httpbis-no-vary-search](https://httpwg.org/http-extensions/draft-ietf-httpbis-no-vary-search.html)
- Jake Archibald's rules: content that never changes at a URL gets a long max-age and a new URL when it changes. Mutable content should revalidate. "max-age on mutable content is often the wrong choice", because cached HTML and assets drift out of sync — [Jake Archibald: Caching best practices & max-age gotchas](https://jakearchibald.com/2016/caching-best-practices/); [Archibald on public-webapps 2016](https://lists.w3.org/Archives/Public/public-webapps-github/2016Aug/1843.html)
- Version skew: after a deploy deletes old hashed chunks, tabs running the old build get 404s on lazy-loaded chunks (`ChunkLoadError`). Mitigations: keep old chunks on the server or CDN after deploy; never cache HTML aggressively; catch the error and prompt a reload (or reload once, guarded by sessionStorage); or use a service worker to serve older files — [Sentry: Fixing ChunkLoadErrors](https://sentry.io/answers/chunk-load-errors-javascript); [Nuxt skew protection docs](https://nuxtseo.com/docs/skew-protection/getting-started/introduction)
- Import maps:
  - `<script type="importmap">`: Chrome 89, Firefox 108, Safari 16.4.
  - `integrity` map: Chrome 127, Firefox 138, Safari 18.
  - Multiple import maps: Chrome 133, Safari 18.4, Firefox 150 behind a flag.

  — [BCD script type importmap](https://github.com/mdn/browser-compat-data/blob/main/html/elements/script.json)
- The import map `integrity` key maps module URLs to SRI hashes for dynamically and statically imported modules — [MDN importmap](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/script/type/importmap)
- `<link rel="modulepreload">`: Chrome 66, Firefox 115, Safari 17 — [BCD link rel](https://github.com/mdn/browser-compat-data/blob/main/html/elements/link.json)
- Compression dictionaries can delta-compress a new versioned bundle against the previous version already in cache (`match="/js/app.*.js"`), cutting the cost of frequent deploys — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)
- Workbox precache entries with a `revision` are fetched with cache mode `'reload'` (bypassing the HTTP cache). Entries without `revision` trigger a warning unless the URL is already hashed — [workbox-precaching 7.4.1 (npm package source, PrecacheController.js)](https://www.npmjs.com/package/workbox-precaching)

### Inferences
- Prefer filename hashing to query-string versioning:
  1. Some proxies and CDNs ignore or strip query strings in the cache key.
  2. No-Vary-Search can collapse them.
  3. Hashed filenames make atomic and overlapping deploys natural, because old and new files coexist.
- Hash cascade: with plain ES modules, changing `util.js` changes its hash, which changes the import specifier inside `app.js`, which changes `app.js`'s hash, and so on up the graph. An import map (bare specifiers mapped to hashed URLs), or bundler "runtime chunk" or manifest indirection, contains the change to the edited file plus the map or HTML.
- Deploy order: upload new hashed assets first, then switch HTML/manifest, and retain at least the previous N builds' assets (e.g. 2–4 weeks, or longer than the maximum HTML or service worker cache age). Never deploy by overwriting a non-hashed `app.js` that has a long max-age.

### Gaps
- No first-party standard defines how long to retain old assets. Framework vendor features (Vercel/Next.js skew protection, deployment IDs) belong to the CDN/platform researcher.

---

## 8. How service workers and the Cache API fit in: lifecycle, Workbox strategies, storage quotas and eviction

### Takeaway
A service worker is a programmable cache layer in front of the HTTP cache. The Cache API never expires entries on its own, so you must version and clean it. Workbox 7.4.1 (May 2026) is current.

Pick a strategy per route:

| Strategy | Use for |
|---|---|
| CacheFirst | Hashed or immutable assets, images, fonts |
| StaleWhileRevalidate | Non-critical, frequently changing assets |
| NetworkFirst with a timeout | HTML and important API data, with an offline fallback |
| NetworkOnly | Mutations and real-time data |
| CacheOnly | Precached shell |

Enable navigation preload for NetworkFirst navigations. Storage is best-effort and evicted per origin, all at once. Call `navigator.storage.persist()` for offline-critical apps and catch `QuotaExceededError`.

### Cited Findings

**Lifecycle and updates**
- First install activates immediately, but existing pages are controlled only after reload unless the worker calls `clients.claim()`. On update, the new worker installs and then waits until all pages controlled by the old version close. `skipWaiting()` activates it immediately. Clean old caches in `activate` — [MDN Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)
- Precaching in `install` with `event.waitUntil(cache.addAll([...]))`: if caching fails, installation fails. "Service worker install time is not the same as PWA install time." The SW installs on first visit — [MDN PWA Caching guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching)
- Cache-version cleanup pattern:
  ```js
  const CURRENT = 'app-v42';
  self.addEventListener('activate', (e) => e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CURRENT).map(k => caches.delete(k))))
  ));
  ```
  — [MDN Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache); [MDN Using Service Workers](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)

**Cache API vs the HTTP cache**
- The Cache API is "a caching mechanism entirely separate from the HTTP cache". `Cache-Control` has no influence on what goes into it — [Chrome: Strategies for service worker caching](https://developer.chrome.com/docs/workbox/caching-strategies-overview)
- "Items in a Cache do not get updated unless explicitly requested; they don't expire unless deleted." You are "responsible for periodically purging cache entries" — [MDN Cache](https://developer.mozilla.org/en-US/docs/Web/API/Cache)
- Responses must be cloned before `cache.put` because bodies are streams — [MDN PWA Caching guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching)
- Support: Cache and CacheStorage in Chrome 40/43, Firefox 41, Safari 11.1 — [BCD api.Cache](https://github.com/mdn/browser-compat-data/blob/main/api/Cache.json)

**Strategies**
- CacheOnly: precached assets, never updated until the SW updates.
- NetworkOnly: don't call `respondWith`.
- CacheFirst: "great strategy to apply to all static assets … especially hash-versioned ones".
- NetworkFirst: "great for HTML or API requests" when offline access to the last version matters.
- StaleWhileRevalidate: for things that are "sort of important to keep up to date, but are not crucial", e.g. avatars.

— [Chrome: Strategies for service worker caching](https://developer.chrome.com/docs/workbox/caching-strategies-overview); MDN calls SWR "cache first with cache refresh" — [MDN PWA Caching guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching)
- Some requests must be network-only. POST requests are never cacheable, and some data (e.g. a product availability list) is better missing than stale — [MDN PWA Caching guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching)

**Workbox 7.4.1 defaults**
- `workbox-*` latest is **7.4.1, published 2026-05-04** (7.4.0 was 2025-11-19) — [npm workbox-strategies](https://www.npmjs.com/package/workbox-strategies)
- `workbox-recipes` defaults (from the 7.4.1 source):

  | Recipe | Strategy | Defaults |
  |---|---|---|
  | `pageCache()` | NetworkFirst for `request.mode === 'navigate'` | cache `pages`, `networkTimeoutSeconds: 3`, caches statuses `[0, 200]` |
  | `staticResourceCache()` | StaleWhileRevalidate for `style`, `script`, `worker` destinations | cache `static-resources` |
  | `imageCache()` | CacheFirst | `maxEntries: 60`, `maxAgeSeconds: 30 days` |
  | `googleFontsCache()` | SWR for fonts.googleapis.com stylesheets; CacheFirst for fonts.gstatic.com | fonts: 1 year, 30 entries |

  Other recipes: `offlineFallback()`, `warmStrategyCache()` — [workbox-recipes 7.4.1](https://www.npmjs.com/package/workbox-recipes); [GoogleChrome/workbox](https://github.com/GoogleChrome/workbox)
- `NetworkFirst` and `StaleWhileRevalidate` add `cacheOkAndOpaquePlugin` by default, so they cache 200 and opaque (status 0) responses. Opaque cross-origin responses carry quota padding and unknown status. `workbox-precaching` exports `precacheAndRoute`, `cleanupOutdatedCaches`, `matchPrecache`, `createHandlerBoundToURL` and `PrecacheFallbackPlugin` — [workbox-strategies / workbox-precaching 7.4.1 source](https://github.com/GoogleChrome/workbox)

**Navigation preload**
- Navigation preload runs the navigation request in parallel with SW boot. Enable it in `activate` with `self.registration.navigationPreload.enable()` and use `await event.preloadResponse` in `fetch`. Requests carry `Service-Worker-Navigation-Preload: true` (changeable via `setHeaderValue`). Support: Chrome 59, Firefox 99, Safari 15.4 — [MDN NavigationPreloadManager](https://developer.mozilla.org/en-US/docs/Web/API/NavigationPreloadManager); [BCD](https://github.com/mdn/browser-compat-data/blob/main/api/NavigationPreloadManager.json)

**Static Routing API**
- `InstallEvent.addRoutes()` lets the SW declare routes that skip SW JavaScript (e.g. go straight to network or cache). **Chrome 123, Safari 27** (Sept 2026), not Firefox — [BCD api.InstallEvent.addRoutes](https://github.com/mdn/browser-compat-data/blob/main/api/InstallEvent.json)

**Storage quotas, persistence and eviction**
- Best-effort is the default; persistent data is evicted only by the user. In Firefox, `persist()` shows a permission prompt. Chrome, Edge and Safari auto-decide based on engagement — [MDN Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
- Quotas:
  - Chromium: an origin can use up to 60% of total disk; the browser uses at most 80% overall.
  - Firefox best-effort: min(10% of disk, 10 GiB per eTLD+1 group). Persistent: 50% of disk, capped at 8 TiB.
  - Safari (macOS 14 / iOS 17+): about 60% of disk per origin for browser apps, 15% for WebView apps (60% if added to Home Screen). Cross-origin frames get about 1/10 of their parent. Overall caps are 80% and 20%.
  - localStorage and sessionStorage: 5 MiB each per origin.

  — [MDN Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
- Eviction:
  - Under storage pressure, LRU by origin; persistent origins are skipped.
  - **Safari deletes script-created data (IndexedDB, Cache API, etc.) for origins with no user interaction in the last 7 days of browser use** when cross-site tracking prevention is on.
  - Eviction deletes all of an origin's data at once.
  - Writes beyond quota throw `QuotaExceededError`.
  - `navigator.storage.estimate()` returns padded estimates.

  — [MDN Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
- `persist()` usage: `navigator.storage.persist().then(granted => …)`. Not available in workers. Support: Chrome 55, Firefox 57, Safari 15.2. `estimate()`: Chrome 61, Firefox 57, Safari 17 — [MDN persist()](https://developer.mozilla.org/en-US/docs/Web/API/StorageManager/persist); [BCD StorageManager](https://github.com/mdn/browser-compat-data/blob/main/api/StorageManager.json)
- `Clear-Site-Data: "storage"` clears localStorage, sessionStorage and IndexedDB and **unregisters service workers** — [MDN Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- Prerendering defers `ServiceWorkerContainer.register()`, `ServiceWorkerRegistration.update()` and `unregister()` until activation — [MDN Speculation Rules API](https://developer.mozilla.org/en-US/docs/Web/API/Speculation_Rules_API)

### Inferences
- Default SW plan for a typical app:
  1. Precache the app shell (hashed URLs) and use CacheFirst for it.
  2. Use `pageCache()` (NetworkFirst, 3 s timeout) plus navigation preload plus an `offlineFallback()` page for navigations.
  3. Use CacheFirst with expiration for hashed `/assets/*`, StaleWhileRevalidate for non-hashed CSS/JS, and CacheFirst with `maxEntries` for images.
  4. Use NetworkOnly for `/api/*` mutations, and NetworkFirst or SWR for read APIs that need offline support.
- A SW CacheFirst route on non-hashed URLs is the most common "stuck forever" bug: the SW never re-checks the network. Only CacheFirst hashed URLs.
- Use IndexedDB, not localStorage, for structured app-data caches: localStorage is synchronous, string-only and limited to 5 MiB. Avoid localStorage for anything big or hot-path. Never store secrets or tokens in either if XSS is a concern. Treat both as evictable caches backed by a server source of truth unless `persist()` was granted.
- Use `skipWaiting()` deliberately. Activating a new SW under an old page can mix old HTML with new precache entries (deploy skew again). Prefer an "update available, reload" prompt, or ensure both versions' assets remain reachable.

### Gaps
- I could not confirm Workbox's governance or maintenance status for 2026 (e.g. any announcement about long-term maintenance) beyond the 7.4.x releases on npm.
- Exact Chrome 2026 heuristics for granting `persist()` were not retrieved.

---

## 9. Which tools to use to inspect caching: DevTools, curl, REDbot, Lighthouse

### Takeaway
Use curl (or REDbot) to see exactly what headers the origin and CDN send, and to test conditional requests. Use the DevTools Network panel to see what the browser actually reused. Use `Cache-Status` (RFC 9211) or CDN debug headers to see what each shared cache did. Use the Lighthouse / DevTools "Use efficient cache lifetimes" insight, which replaced `uses-long-cache-ttl`, for TTL audits, and DevTools' bfcache tester plus `notRestoredReasons` for history navigations.

### Cited Findings
- Lighthouse `cache-insight` (title "Use efficient cache lifetimes") **replaces the old `uses-long-cache-ttl` audit**. It is generated from the DevTools performance-trace "Cache" insight — [Lighthouse cache-insight.js](https://github.com/GoogleChrome/lighthouse/blob/main/core/audits/insights/cache-insight.js); [DevTools Cache insight docs](https://developer.chrome.com/docs/performance/insights/cache)
- Insight logic, from the DevTools source:
  - Considers only static resource types with cacheable status codes, loaded over the network.
  - **Skips responses with `no-cache`, `no-store`, `must-revalidate` or `private`**, and `Pragma: no-cache` when there is no Cache-Control, treating them as intentionally uncached.
  - Uses `max-age`, else `Expires`.
  - **Ignores TTLs ≥ 30 days**.
  - Flags the rest when the estimated cache-hit probability (from TTL deciles of 0, 0.2, 1, 3, 8, 12, 24, 48, 72, 168, 8760 hours) is ≤ 92.5%.
  - Reports "wasted bytes".

  — [devtools-frontend Cache.ts](https://github.com/ChromeDevTools/devtools-frontend/blob/main/front_end/models/trace/insights/Cache.ts)
- bfcache testing: DevTools **Application → Back/forward cache → Run Test**, and the Lighthouse (10.0+) bfcache audit — [web.dev bfcache](https://web.dev/articles/bfcache). `notRestoredReasons` in RUM (Chrome 125+) — [BCD](https://github.com/mdn/browser-compat-data/blob/main/api/NotRestoredReasons.json)
- Partition debugging: `chrome://net-export` plus netlog-viewer (look for `SplitCacheByNetworkIsolationKey`) — [Chrome: HTTP cache partitioning](https://developer.chrome.com/blog/http-cache-partitioning)
- `Cache-Status` parameters (`hit`, `fwd=uri-miss|vary-miss|stale…`, `ttl`, `stored`, `collapsed`, `key`) are the standard way caches explain their decisions — [RFC 9211](https://httpwg.org/specs/rfc9211.html)
- Chrome DevTools Issues panel reports when a `Use-As-Dictionary` response cannot be used because of its freshness — [MDN Compression Dictionary Transport](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression_dictionary_transport)

### Inferences
- Handy curl recipes (standard curl flags):
  ```bash
  curl -sI https://example.com/app.3f9a1c.js                      # headers only (HEAD)
  curl -s -o /dev/null -D - https://example.com/                   # GET, dump response headers
  curl -sI -H 'Accept-Encoding: br' https://example.com/app.js     # check Vary / Content-Encoding / ETag per encoding
  ETAG=$(curl -sI https://example.com/ | awk -F': ' 'tolower($1)=="etag"{print $2}' | tr -d '\r')
  curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" https://example.com/   # expect 304
  curl -sI https://example.com/ | grep -iE 'cache-control|age|etag|last-modified|vary|cache-status|cdn-cache-control'
  ```
  Run the same request twice and compare `Age` and `Cache-Status` to confirm edge hits. Test with and without cookies or `Authorization` to confirm personalized responses aren't shared-cached.
- In DevTools Network, the Size column shows "(memory cache)", "(disk cache)", "(ServiceWorker)" or "(prefetch cache)" for reused responses, and a byte count for network fetches. Check "Disable cache" only when you want cold-load behavior. Headers → Response shows the `Cache-Control` the browser actually received (after CDN rewrites). This is general DevTools knowledge, not re-verified this session.
- REDbot (redbot.org, by Mark Nottingham) lints a URL's caching and validation headers, e.g. missing validators, `Vary` problems, heuristic freshness. It was not fetched this session.
- Lighthouse caveat: because the insight skips anything marked `no-cache` or `private`, a passing score does not mean HTML caching is sensible, and ≥ 30-day TTLs pass even without `immutable`.

### Gaps
- REDbot's current hosting and status in 2026, and its exact checks, could not be verified (redbot.org was not reachable from the research environment and search budget was exhausted).
- I could not verify DevTools Network panel labels for 2026 Chrome versions.
