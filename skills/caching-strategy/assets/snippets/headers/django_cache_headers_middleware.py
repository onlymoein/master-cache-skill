"""Django: every response gets an explicit Cache-Control. Default is no-store; views opt in.

settings.py
    MIDDLEWARE = [
        ...,
        "myproject.cache_headers.DefaultCacheHeadersMiddleware",   # near the top: runs last on the way out
    ]

views.py
    from myproject.cache_headers import cache_policy

    @cache_policy("public_html", tags=["page:home"])
    def home(request): ...

    @cache_policy("personalized")
    def account(request): ...

Policies match assets/policy-defaults.csv. Use the CDN's own header name if you need vendor
behavior (Cloudflare-CDN-Cache-Control, Surrogate-Control for Fastly). Keep Django patched:
6.0.6/6.0.7 fixed shared-cache bugs (mixed-case `Private`, Vary on Authorization, CVE-2026-48588).
"""

from functools import wraps

from django.conf import settings
from django.utils.cache import patch_vary_headers

POLICIES = {
    "fingerprinted": {"Cache-Control": "public, max-age=31536000, immutable"},
    "public_html": {
        "Cache-Control": "no-cache",
        "CDN-Cache-Control": "max-age=300, stale-while-revalidate=3600, stale-if-error=86400",
    },
    "public_api_volatile": {"Cache-Control": "no-cache", "CDN-Cache-Control": "max-age=5, stale-if-error=60"},
    "personalized": {"Cache-Control": "private, no-cache"},
    "sensitive": {"Cache-Control": "no-store"},
}
SHARED_HEADERS = ("CDN-Cache-Control", "Cache-Tag", "Surrogate-Control", "Surrogate-Key")


def cache_policy(name, tags=()):
    if name not in POLICIES:
        raise ValueError(f"unknown cache policy {name}")

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            response = view(request, *args, **kwargs)
            response._cache_policy = name
            response._cache_tags = list(tags)
            return response
        return wrapped
    return decorator


class DefaultCacheHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = getattr(response, "_cache_policy", None)
        if request.method not in ("GET", "HEAD") or policy is None:
            if not response.has_header("Cache-Control"):
                response["Cache-Control"] = "no-store"  # step 0 / default
            return response
        headers = dict(POLICIES[policy])
        shared = "CDN-Cache-Control" in headers
        # Check the cookie, not request.user: touching request.user loads the session, and
        # SessionMiddleware then adds `Vary: Cookie`, which fragments CDN caches.
        authenticated = settings.SESSION_COOKIE_NAME in request.COOKIES or "HTTP_AUTHORIZATION" in request.META
        if shared and (authenticated or response.cookies):
            # Never shared-cache a response for a logged-in user or one that sets cookies.
            headers = dict(POLICIES["personalized"])
            shared = False
        for k in SHARED_HEADERS:
            if k in response:
                del response[k]
        for k, v in headers.items():
            response[k] = v
        if shared and response._cache_tags:
            response["Cache-Tag"] = ",".join([*response._cache_tags, "all"])
        if not shared:
            patch_vary_headers(response, ("Cookie",))  # browser-only cache: varying on Cookie is fine here
        # If a shared-cached view (or its template) read request.user/session, SessionMiddleware added
        # `Vary: Cookie`; find that with probe_headers.py and remove the session access from public views.
        return response
