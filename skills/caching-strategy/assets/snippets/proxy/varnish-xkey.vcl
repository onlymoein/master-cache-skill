vcl 4.1;
# Varnish 6/7 with the xkey vmod (varnish-modules): grace, xkey soft purge, cookie bypass,
# hit-for-miss for uncacheable responses.
#
# Origin headers for cacheable pages:
#   Cache-Control: max-age=0, s-maxage=300          (Varnish takes its TTL from s-maxage; browsers revalidate)
#   xkey: product-123 category-9 all                (space-separated keys)
# Responses with private, no-store, no-cache or Set-Cookie are never stored.
# This VCL returns from every sub, so Varnish's built-in VCL doesn't run: the checks below replace it.
#
# Purge (soft: objects stay usable for grace while refreshing):
#   curl -X PURGE -H 'xkey: product-123' http://varnish:6081/

import std;
import xkey;

backend default {
    .host = "app";
    .port = "3000";
    .probe = {
        .url = "/healthz";
        .interval = 5s;
        .timeout = 2s;
        .window = 5;
        .threshold = 3;
    }
}

acl purgers {
    "127.0.0.1";
    "10.0.0.0"/8;
}

sub vcl_recv {
    if (req.method == "PURGE") {
        if (client.ip !~ purgers) {
            return (synth(403, "Forbidden"));
        }
        if (req.http.xkey) {
            set req.http.n-gone = xkey.softpurge(req.http.xkey);
            return (synth(200, "Invalidated " + req.http.n-gone + " objects"));
        }
        return (purge);   # single URL hard purge
    }
    if (req.method != "GET" && req.method != "HEAD") {
        return (pass);
    }
    if (req.http.Authorization || req.http.Cookie ~ "(^|;\s*)(session|sid|_session|auth)[^=]*=") {
        return (pass);
    }
    # Anonymous request: drop cookies (analytics etc.) so they don't block caching. Only do this
    # if cacheable pages never read other cookies (locale, CSRF); otherwise allow-list cookies.
    unset req.http.Cookie;
    # Strip tracking params from the key.
    set req.url = regsuball(req.url, "(?<=[?&])(utm_[a-z]+|gclid|fbclid)=[^&]*&?", "");
    set req.url = regsub(req.url, "[?&]$", "");
    set req.url = std.querysort(req.url);
    # Short grace while the backend is healthy, long grace (beresp.grace) when it's sick.
    if (std.healthy(req.backend_hint)) {
        set req.grace = 10s;
    }
    return (hash);
}

sub vcl_backend_response {
    set beresp.grace = 24h;   # stale-if-error horizon
    set beresp.keep = 1h;     # keep objects for conditional revalidation (304s)
    if (beresp.http.Set-Cookie || beresp.http.Cache-Control ~ "(private|no-store|no-cache)" || beresp.http.Vary == "*" || beresp.ttl <= 0s) {
        # hit-for-miss: concurrent requests don't queue behind a fetch that will never be cached
        set beresp.uncacheable = true;
        set beresp.ttl = 120s;
        return (deliver);
    }
    if (beresp.status >= 500) {
        # Don't store errors; grace serves the previous good object while the backend is sick
        return (abandon);
    }
    if (!beresp.http.Cache-Control) {
        set beresp.ttl = 10s;   # micro-cache fallback when the origin sends nothing
    }
    return (deliver);
}

sub vcl_deliver {
    if (obj.hits > 0) {
        set resp.http.X-Cache = "HIT";
    } else {
        set resp.http.X-Cache = "MISS";
    }
    unset resp.http.xkey;
    return (deliver);
}
