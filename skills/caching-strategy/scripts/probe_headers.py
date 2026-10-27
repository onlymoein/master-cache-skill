#!/usr/bin/env python3
"""Read-only live probe of caching behavior for URLs the user supplies.

Usage:
    python scripts/probe_headers.py <url> [<url> ...]
        [--cookie-a 'name=value; other=value'] [--cookie-b 'name=value']
        [--deception] [--repeat 2] [--timeout 10]

Only run against URLs the user owns or is authorized to test. Every request is a GET
(or a conditional GET). Cookie values are sent but never printed: output shows cookie
names only, and Set-Cookie headers are reduced to cookie names.

Per URL it reports:
    requests      repeated GETs with status, cache status (HIT/MISS/...), Age and cache headers
    vendor        CDN/proxy guessed from response headers
    conditional   If-None-Match / If-Modified-Since result (expect 304)
    findings      header problems [{severity, rule, message}]
    leak_test     with --cookie-a: does a logged-in response reach anonymous users? (and user B with --cookie-b)
    deception     with --deception: are asset-looking variants of the path served and cached?

Exit codes: 0 when probing ran (findings do not change the exit code), 2 on bad usage.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "caching-strategy-probe/1.0 (+read-only cache audit)"
BODY_LIMIT = 2 * 1024 * 1024
INTERESTING = [
    "cache-control", "cdn-cache-control", "surrogate-control", "vercel-cdn-cache-control", "netlify-cdn-cache-control",
    "cloudflare-cdn-cache-control", "expires", "pragma", "vary", "age", "etag", "last-modified", "cache-status",
    "x-cache", "x-cache-hits", "x-cache-status", "cf-cache-status", "x-vercel-cache", "x-nextjs-cache",
    "x-nextjs-stale-time", "x-nf-request-id", "x-served-by", "x-amz-cf-pop", "x-amz-cf-id", "x-azure-ref",
    "x-drupal-cache", "x-drupal-dynamic-cache", "x-magento-cache-debug", "x-litespeed-cache", "cf-apo-via",
    "x-proxy-cache", "x-varnish", "via", "server", "content-type", "content-encoding", "content-length",
    "set-cookie", "location", "no-vary-search", "speculation-rules", "x-cache-key", "x-check-cacheable",
    "surrogate-key", "cache-tag", "x-fastly-request-id", "fly-request-id", "x-render-origin-server",
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


OPENER = urllib.request.build_opener(NoRedirect())


def cookie_names(cookie: str | None) -> list[str]:
    if not cookie:
        return []
    return [part.split("=", 1)[0].strip() for part in cookie.split(";") if "=" in part]


def redact_set_cookie(values: list[str]) -> list[str]:
    return [v.split("=", 1)[0].strip() + "=<redacted>" for v in values]


def fetch(url: str, timeout: float, cookie: str | None = None, extra: dict | None = None) -> dict:
    headers = {"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Encoding": "gzip, br"}
    if cookie:
        headers["Cookie"] = cookie
    if extra:
        headers.update(extra)
    req = urllib.request.Request(url, headers=headers, method="GET")
    started = time.monotonic()
    try:
        resp = OPENER.open(req, timeout=timeout)
        status = resp.status
        raw_headers = resp.headers
        body = resp.read(BODY_LIMIT)
    except urllib.error.HTTPError as err:  # 3xx (not followed), 304, 4xx, 5xx
        status = err.code
        raw_headers = err.headers
        try:
            body = err.read(BODY_LIMIT)
        except Exception:  # noqa: BLE001
            body = b""
    except (urllib.error.URLError, OSError, ValueError) as err:
        return {"error": f"{type(err).__name__}: {getattr(err, 'reason', err)}"}
    elapsed_ms = round((time.monotonic() - started) * 1000)
    hdrs: dict[str, object] = {}
    for name in INTERESTING:
        values = raw_headers.get_all(name) if raw_headers else None
        if not values:
            continue
        hdrs[name] = redact_set_cookie(values) if name == "set-cookie" else (values[0] if len(values) == 1 else values)
    return {
        "status": status,
        "elapsed_ms": elapsed_ms,
        "headers": hdrs,
        "body_sha256": hashlib.sha256(body).hexdigest()[:16],
        "body_bytes": len(body),
        "cache_status": cache_status(hdrs),
    }


def cache_status(h: dict) -> str | None:
    for name in ("cf-cache-status", "x-vercel-cache", "x-nextjs-cache", "x-cache-status", "x-litespeed-cache", "x-proxy-cache"):
        if name in h:
            return str(h[name]).upper()
    if "x-cache" in h:
        v = str(h["x-cache"]).upper()
        if "HIT" in v:
            return "HIT"
        if "MISS" in v:
            return "MISS"
        return v
    if "cache-status" in h:  # RFC 9211
        v = str(h["cache-status"]).lower()
        if re.search(r"(^|;|,)\s*hit\b", v):
            return "HIT"
        m = re.search(r"fwd=(\w+)", v)
        if m:
            return "MISS" if m.group(1) in ("miss", "uri-miss", "vary-miss") else m.group(1).upper()
    if "x-drupal-cache" in h:
        return str(h["x-drupal-cache"]).upper()
    return None


def vendor(h: dict) -> list[str]:
    v = []
    server = str(h.get("server", "")).lower()
    via = str(h.get("via", "")).lower()
    if "cf-cache-status" in h or server == "cloudflare":
        v.append("cloudflare")
    if "x-vercel-cache" in h or server == "vercel":
        v.append("vercel")
    if "x-nf-request-id" in h or server.startswith("netlify"):
        v.append("netlify")
    if "x-amz-cf-pop" in h or "cloudfront" in via or "cloudfront" in str(h.get("x-cache", "")).lower():
        v.append("cloudfront")
    if "x-served-by" in h and "cache-" in str(h.get("x-served-by", "")) or "x-fastly-request-id" in h:
        v.append("fastly")
    if "akamaighost" in server or "x-check-cacheable" in h:
        v.append("akamai")
    if "x-azure-ref" in h:
        v.append("azure-front-door")
    if "google" in via:
        v.append("google-cloud-cdn")
    if "fly-request-id" in h:
        v.append("fly")
    if "x-varnish" in h or "varnish" in via:
        if "fastly" not in v:
            v.append("varnish")
    if "x-drupal-cache" in h or "x-drupal-dynamic-cache" in h:
        v.append("drupal")
    if "x-magento-cache-debug" in h:
        v.append("magento")
    if "x-litespeed-cache" in h:
        v.append("litespeed")
    if "x-nextjs-cache" in h:
        v.append("nextjs")
    return v


def directives(value: str | None) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for part in (value or "").split(","):
        part = part.strip()
        if not part:
            continue
        k, _, val = part.partition("=")
        out[k.strip().lower()] = val.strip().strip('"') or None
    return out


def as_int(v) -> int | None:
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


def header_findings(url: str, resp: dict, vendors: list[str]) -> list[dict]:
    f: list[dict] = []
    h = resp.get("headers", {})

    def add(sev: str, rule: str, msg: str) -> None:
        f.append({"severity": sev, "rule": rule, "message": msg})

    cc_raw = h.get("cache-control")
    cc = directives(cc_raw if isinstance(cc_raw, str) else ", ".join(cc_raw) if cc_raw else None)
    ctype = str(h.get("content-type", "")).lower()
    is_html = "text/html" in ctype
    status = resp.get("status")
    shared_targeted = any(k in h for k in ("cdn-cache-control", "surrogate-control", "vercel-cdn-cache-control",
                                           "netlify-cdn-cache-control", "cloudflare-cdn-cache-control"))
    shared_cacheable = "public" in cc or "s-maxage" in cc or shared_targeted
    has_cookie = "set-cookie" in h
    if not cc_raw:
        add("medium", "missing-cache-control",
            "No Cache-Control: caches apply heuristic freshness (often 10% of the time since Last-Modified). Set an explicit policy.")
    if cc_raw and not any(d in cc for d in ("no-store", "no-cache", "max-age", "s-maxage", "private", "public")):
        add("low", "no-freshness-directive", "Cache-Control has no freshness directive; behavior depends on heuristics.")
    if has_cookie and (shared_cacheable or resp.get("cache_status") == "HIT"):
        add("high", "set-cookie-on-shared-cacheable",
            "Response sets a cookie but is shared-cacheable (or was served as a HIT). A shared cache may store and replay it, or the CDN silently bypasses caching.")
    if "private" in cc and "s-maxage" in cc:
        add("high", "private-with-s-maxage", "`private` with `s-maxage` is contradictory.")
    if is_html and "immutable" in cc:
        add("high", "immutable-html", "`immutable` on HTML: browsers won't revalidate it, so you can't ship fixes to this URL.")
    max_age = as_int(cc.get("max-age"))
    if is_html and max_age and max_age > 3600 and "immutable" not in cc:
        add("medium", "long-browser-ttl-html", f"HTML with browser max-age={max_age}: browser copies can't be purged. Prefer no-cache + ETag and a CDN-only TTL.")
    vary = str(h.get("vary", "")).lower()
    if re.search(r"\b(cookie|user-agent)\b", vary):
        add("medium", "vary-cookie-or-user-agent", "Vary on Cookie/User-Agent: a variant per user/UA, near-zero hit ratio; some CDNs refuse to cache it.")
    if "*" in [p.strip() for p in vary.split(",")]:
        add("medium", "vary-star", "Vary: * makes the response unusable from caches.")
    if "no-store" in cc and ("no-cache" in cc or "must-revalidate" in cc) and ("max-age" in cc or "pragma" in h or "expires" in h):
        add("low", "kitchen-sink", "Kitchen-sink no-store headers: `Cache-Control: no-store` alone is enough.")
    if "cloudflare" in vendors and "stale-while-revalidate" in cc and any(d in cc for d in ("s-maxage", "must-revalidate", "proxy-revalidate", "no-cache")):
        add("medium", "cloudflare-swr-disabled",
            "Cloudflare ignores stale-while-revalidate when the same header also has s-maxage/must-revalidate/proxy-revalidate/no-cache. Put SWR in Cloudflare-CDN-Cache-Control.")
    if status in (500, 502, 503, 504) and "no-store" not in cc and (max_age or "s-maxage" in cc):
        add("high", "cacheable-5xx", "5xx response carries a cache TTL: errors can be served from cache. Use no-store (or at most 5–10 s at the CDN).")
    if status in (301, 308) and not cc_raw:
        add("medium", "headerless-permanent-redirect", "Permanent redirect without Cache-Control: browsers may cache it for a very long time. Start with an explicit max-age=86400.")
    if status in (302, 307) and shared_cacheable:
        add("medium", "cacheable-temporary-redirect", "Temporary redirect marked shared-cacheable: login/geo redirects can be replayed to other users.")
    if status == 200 and "etag" not in h and "last-modified" not in h and "no-store" not in cc:
        add("low", "no-validator", "No ETag or Last-Modified: revalidation always transfers the full body.")
    path = urllib.parse.urlsplit(url).path
    looks_hashed = bool(re.search(r"[.\-_][0-9a-f]{8,}[.\-_]|[.\-_][A-Za-z0-9_-]{8,}\.(js|css|woff2?|png|jpe?g|webp|avif|svg)$", path))
    if looks_hashed and "immutable" not in cc and not (max_age and max_age >= 31536000):
        add("low", "hashed-asset-short-ttl", "Looks like a fingerprinted asset but isn't `public, max-age=31536000, immutable`.")
    return f


def bust(url: str, token: str) -> str:
    parts = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    q.append(("__cache_probe", token))
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment))


def token() -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(10))


def leak_test(url: str, timeout: float, cookie_a: str, cookie_b: str | None) -> dict:
    """Anonymous baseline vs user A vs anonymous-after-A (and user B) on a fresh cache key."""
    result: dict = {"cache_key_param": "__cache_probe", "steps": [], "verdict": "no-leak-detected"}
    fresh_anon = bust(url, token())
    shared = bust(url, token())
    anon = fetch(fresh_anon, timeout)
    a = fetch(shared, timeout, cookie=cookie_a)
    after = fetch(shared, timeout)
    result["steps"] = [
        {"step": "anonymous baseline (fresh key)", **summarize(anon)},
        {"step": "user A (cookie names: " + ", ".join(cookie_names(cookie_a)) + ")", **summarize(a)},
        {"step": "anonymous, same key as user A", **summarize(after)},
    ]
    if any("error" in r for r in (anon, a, after)):
        result["verdict"] = "error"
        return result
    personalized = a["body_sha256"] != anon["body_sha256"]
    result["personalized_response"] = personalized
    if not personalized:
        result["note"] = "User A got the same body as an anonymous user: this URL may not be personalized (or the cookie isn't valid), so the test is inconclusive."
    if personalized and after["body_sha256"] == a["body_sha256"]:
        result["verdict"] = "LEAK: anonymous request received user A's response"
    if cookie_b:
        b_fresh = fetch(bust(url, token()), timeout, cookie=cookie_b)
        b_shared = fetch(shared, timeout, cookie=cookie_b)
        result["steps"] += [
            {"step": "user B (fresh key)", **summarize(b_fresh)},
            {"step": "user B, same key as user A", **summarize(b_shared)},
        ]
        if "error" not in b_shared and "error" not in b_fresh:
            if b_fresh["body_sha256"] != a["body_sha256"] and b_shared["body_sha256"] == a["body_sha256"]:
                result["verdict"] = "LEAK: user B received user A's response"
    result["caveat"] = ("If the cache key ignores unknown query parameters, all steps share the real cache entry; "
                        "dynamic bodies (timestamps, nonces) can hide a leak but never create a false one.")
    return result


def summarize(r: dict) -> dict:
    if "error" in r:
        return {"error": r["error"]}
    h = r["headers"]
    return {"status": r["status"], "cache_status": r["cache_status"], "age": h.get("age"),
            "cache_control": h.get("cache-control"), "set_cookie": h.get("set-cookie"), "body_sha256": r["body_sha256"]}


DECEPTION_SUFFIXES = ["/__probe.css", ";__probe.css", "%3B__probe.css", ".css", "%2F__probe.css", "%00__probe.css"]


def deception_test(url: str, timeout: float, cookie: str | None) -> dict:
    parts = urllib.parse.urlsplit(url)
    base = fetch(url, timeout, cookie=cookie)
    out: dict = {"cookie_names": cookie_names(cookie), "base": summarize(base), "variants": []}
    if "error" in base:
        return out
    path = parts.path.rstrip("/") or "/"
    for suffix in DECEPTION_SUFFIXES:
        if path == "/" and suffix.startswith((";", "%3B", ".", "%00")):
            continue
        variant = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path + suffix, parts.query, ""))
        first = fetch(variant, timeout, cookie=cookie)
        second = fetch(variant, timeout, cookie=None)  # anonymous: did the cache store the first response?
        entry = {"url_suffix": suffix, "first": summarize(first), "anonymous_repeat": summarize(second)}
        if "error" not in first and first["status"] == 200 and first["body_sha256"] == base["body_sha256"]:
            entry["finding"] = "path-confusion: origin served the page for an asset-looking path"
            entry["severity"] = "medium"
            served_from_cache = "error" not in second and (
                second["cache_status"] == "HIT" or (as_int(second["headers"].get("age")) or 0) > 0)
            if served_from_cache and second["body_sha256"] == base["body_sha256"]:
                entry["finding"] = "WEB CACHE DECEPTION: the page was cached under an asset-looking path and served again"
                entry["severity"] = "high"
        out["variants"].append(entry)
    return out


def probe(url: str, args: argparse.Namespace) -> dict:
    requests = []
    for i in range(max(1, args.repeat)):
        requests.append(fetch(url, args.timeout))
        if i + 1 < args.repeat:
            time.sleep(args.delay)
    ok = [r for r in requests if "error" not in r]
    result: dict = {"url": url, "requests": requests}
    if not ok:
        result["error"] = requests[-1].get("error")
        return result
    last = ok[-1]
    result["vendor"] = vendor(last["headers"])
    conditional = None
    if "etag" in last["headers"]:
        etag = last["headers"]["etag"]
        c = fetch(url, args.timeout, extra={"If-None-Match": etag if isinstance(etag, str) else etag[0]})
        conditional = {"sent": "If-None-Match", **summarize(c), "ok": c.get("status") == 304}
    elif "last-modified" in last["headers"]:
        c = fetch(url, args.timeout, extra={"If-Modified-Since": str(last["headers"]["last-modified"])})
        conditional = {"sent": "If-Modified-Since", **summarize(c), "ok": c.get("status") == 304}
    result["conditional"] = conditional
    findings = header_findings(url, last, result["vendor"])
    statuses = [r["cache_status"] for r in ok]
    ages = [as_int(r["headers"].get("age")) for r in ok]
    cc = directives(str(last["headers"].get("cache-control", "")))
    if len(ok) > 1 and not any(s == "HIT" for s in statuses) and not any((a or 0) > 0 for a in ages):
        if "public" in cc or "s-maxage" in cc or any(k.endswith("cdn-cache-control") for k in last["headers"]):
            findings.append({"severity": "medium", "rule": "cacheable-but-never-hit",
                             "message": "Shared-cacheable headers but no HIT/Age on repeat requests: check CDN cache rules, Set-Cookie, Vary, or query-string keys."})
    if conditional and not conditional["ok"] and conditional.get("status") == 200:
        findings.append({"severity": "low", "rule": "no-304",
                         "message": f"Conditional GET ({conditional['sent']}) returned 200, not 304: validators aren't honored."})
    result["findings"] = findings
    if args.cookie_a:
        result["leak_test"] = leak_test(url, args.timeout, args.cookie_a, args.cookie_b)
        if result["leak_test"]["verdict"].startswith("LEAK"):
            findings.insert(0, {"severity": "high", "rule": "cross-user-leak", "message": result["leak_test"]["verdict"]})
    if args.deception:
        result["deception"] = deception_test(url, args.timeout, args.cookie_a)
        for v in result["deception"]["variants"]:
            if v.get("severity") == "high":
                findings.insert(0, {"severity": "high", "rule": "web-cache-deception", "message": f"{v['finding']} ({v['url_suffix']})"})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only probe of caching headers and behavior for URLs you own or are authorized to test.",
        epilog="Prints JSON on stdout; cookie values are never printed. Exit 0 when probing ran, 2 on bad usage.",
    )
    parser.add_argument("urls", nargs="+", help="http(s) URLs to probe")
    parser.add_argument("--cookie-a", help="Cookie header for a logged-in session A (enables the leak test)")
    parser.add_argument("--cookie-b", help="Cookie header for a second session B (cross-user check)")
    parser.add_argument("--deception", action="store_true", help="probe asset-looking path variants (web cache deception)")
    parser.add_argument("--repeat", type=int, default=2, help="GETs per URL to observe MISS→HIT and Age (default 2)")
    parser.add_argument("--delay", type=float, default=1.0, help="seconds between repeats (default 1)")
    parser.add_argument("--timeout", type=float, default=10.0, help="per-request timeout in seconds (default 10)")
    args = parser.parse_args(argv)
    for u in args.urls:
        if urllib.parse.urlsplit(u).scheme not in ("http", "https"):
            print(f"error: not an http(s) URL: {u}", file=sys.stderr)
            return 2
    if args.cookie_b and not args.cookie_a:
        print("error: --cookie-b needs --cookie-a", file=sys.stderr)
        return 2
    if args.repeat < 1 or args.repeat > 10:
        print("error: --repeat must be between 1 and 10", file=sys.stderr)
        return 2
    out = {"probed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": [probe(u, args) for u in args.urls],
           "notes": ["Redirects are not followed; probe the final URL too.",
                     "Hit ratio and status vocabulary differ by vendor: see references/core/observability-testing.md."]}
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
