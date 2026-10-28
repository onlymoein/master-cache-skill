# Fastly (VCL): surrogate keys, soft purge, grace / stale-if-error, cookie bypass.
# Add as custom VCL snippets (recv / fetch / error) or merge into custom VCL. The #FASTLY macros
# must stay in place in full custom VCL.
#
# Origin headers:
#   Cache-Control: no-cache                                     (browsers revalidate)
#   Surrogate-Control: max-age=31536000, stale-while-revalidate=60, stale-if-error=31536000
#   Surrogate-Key: product-123 category-9 all                  (space-separated, lowercase, <= 50)
# Fastly strips Surrogate-Control before responding to clients.
#
# Purge on change (soft: mark stale, revalidate; keeps serving stale if the origin is down):
#   curl -X POST "https://api.fastly.com/service/$SERVICE_ID/purge/product-123" \
#        -H "Fastly-Key: $FASTLY_API_TOKEN" -H "Fastly-Soft-Purge: 1"

sub vcl_recv {
#FASTLY recv
  # Never cache personalized requests: pass when a session cookie or Authorization is present.
  if (req.http.Authorization || req.http.Cookie ~ "(^|;\s*)(session|sid|auth)[^=]*=") {
    return(pass);
  }
  # Unsafe methods never touch the cache.
  if (req.method != "GET" && req.method != "HEAD" && req.method != "FASTLYPURGE") {
    return(pass);
  }
  # Drop tracking params so they don't fragment the key (keep an allow-list if you can).
  set req.url = querystring.regfilter(req.url, "^(utm_[a-z]+|gclid|fbclid)$");
  set req.url = querystring.sort(req.url);
  return(lookup);
}

sub vcl_fetch {
#FASTLY fetch
  # Responses that set cookies are per-user: don't store them.
  if (beresp.http.Set-Cookie) {
    set beresp.ttl = 0s;
    return(pass);
  }
  # Serve stale on errors if a stale copy exists; otherwise cache the error briefly so
  # collapsed waiters get an answer instead of all hitting the origin.
  if (beresp.status >= 500 && beresp.status < 600) {
    if (stale.exists) {
      return(deliver_stale);
    }
    set beresp.ttl = 1s;
    set beresp.grace = 0s;
    return(deliver);
  }
  # Fallbacks when the origin forgot Surrogate-Control (prefer fixing the origin).
  if (!beresp.http.Surrogate-Control && !beresp.http.Cache-Control) {
    set beresp.ttl = 60s;
  }
  set beresp.stale_while_revalidate = 60s;
  set beresp.stale_if_error = 86400s;
  return(deliver);
}

sub vcl_error {
#FASTLY error
  # Origin unreachable: Fastly comes straight here; serve stale if we have it.
  if (obj.status >= 500 && obj.status < 600 && stale.exists) {
    return(deliver_stale);
  }
}

sub vcl_deliver {
#FASTLY deliver
  # Don't leak internal keys to clients (keep them when debugging with Fastly-Debug).
  if (!req.http.Fastly-Debug) {
    unset resp.http.Surrogate-Key;
  }
  return(deliver);
}
