# Django

Last reviewed: 2026-10-27 · Applies to: Django 6.1 (released 2026-08-05) and 6.0.x; 5.2 LTS similar

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Caching layers
- Version notes
- Verify
- Sources

## When to read this

When the app is Django. The biggest real-world risk is personalization leaks: `cache_page` and the per-site cache don't vary on cookies or authentication by default.

## How to detect

`manage.py`; `django` in `requirements*.txt`/`pyproject.toml`/`Pipfile`; `settings.py` with `INSTALLED_APPS`. Inspect `CACHES` and `MIDDLEWARE`. `django-redis` = third-party backend (pattern deletes, extras) instead of the built-in one.

## Default recipe

```python
# settings.py
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",   # built-in since 4.0
        "LOCATION": os.environ["REDIS_URL"],
        "TIMEOUT": 300,            # None = forever, 0 = don't cache
        "KEY_PREFIX": "myapp",
    }
}
```

```python
from django.core.cache import cache
from django.views.decorators.cache import cache_control, never_cache, cache_page
from django.views.decorators.vary import vary_on_cookie
from django.views.decorators.http import condition

top = cache.get_or_set("v3:top_products", compute_top_products, timeout=300)   # low-level cache-aside

@cache_control(no_cache=True)                       # browsers revalidate; set CDN TTL separately
def public_page(request): ...

@cache_page(60 * 15)                                # server-side + Cache-Control max-age
def anonymous_landing(request): ...                 # ONLY for responses identical for everyone

@condition(etag_func=lambda req, pk: Product.objects.values_list("version", flat=True).get(pk=pk))
def product_detail(request, pk): ...                # 304s from a version column

@never_cache
def account(request): ...
```

Default headers for every response: `assets/snippets/headers/django_cache_headers_middleware.py`.

## Rules and gotchas

1. Pin the latest patch release. Django 6.0.6 (2026-06) fixed: mixed-case `Private` directives being cached by `UpdateCacheMiddleware`/`cache_page`; `Authorization` requests not varying the cached response; whitespace-padded `Vary` letting `Vary: *` responses be cached. 6.0.7 fixed CVE-2026-48588: a response that sets a session cookie could be stored in the shared cache when the request carried an unrelated cookie.
2. `cache_page` and the per-site cache don't vary on cookies/auth. Never use them on authenticated views; if you must, add `vary_on_cookie` (and understand it fragments the cache per user).
3. Middleware order: `UpdateCacheMiddleware` first (response phase runs in reverse, so it must precede anything that adds `Vary`: Session, GZip, Locale), `FetchFromCacheMiddleware` last. `ConditionalGetMiddleware` after GZip, before middleware that changes the response.
4. Per-view decorators run before CSRF adds its `Vary`; views needing a CSRF token apply `csrf_protect` first.
5. `LocMemCache` (the default) is per process: not shared across gunicorn/uvicorn workers. Use Redis or Memcached in production.
6. `cache.get_or_set` has no lock: add a Redis lock or single-flight for hot, expensive keys (`references/core/stampede-failure.md`).
7. Template fragment keys need every variant argument: `{% cache 500 sidebar request.user.id LANGUAGE_CODE %}`.
8. Multi-tenant: put the tenant in every key via a central `KEY_FUNCTION` or wrapper, not ad hoc strings.

## Caching layers

| Layer | API | Use for |
|---|---|---|
| Low-level | `cache.get/set/get_or_set/delete/set_many/touch/incr`, async `aget/aset` | Expensive queries and computations (default) |
| Template fragments | `{% load cache %}{% cache 500 name vary_args %}` | Shared fragments |
| Per-view | `@cache_page` | Anonymous/public pages only |
| Per-site | `UpdateCacheMiddleware` + `FetchFromCacheMiddleware` | Fully public sites only |
| HTTP | `@cache_control`, `@never_cache`, `@condition`/`@etag`/`@last_modified`, `ConditionalGetMiddleware` | Browser/CDN headers and 304s |

Backends: `redis.RedisCache`, `memcached.PyMemcacheCache`/`PyLibMCCache`, `db.DatabaseCache`, `filebased.FileBasedCache`, `locmem.LocMemCache`, `dummy.DummyCache`.

## Version notes

- 6.1 has no headline cache features. Security fixes 6.0.6/6.0.7 (mid-2026) changed shared-cache behavior; backports to 5.2 weren't verified.

<details><summary>Old patterns</summary>

- `django-redis` only because there was no built-in Redis backend (built in since 4.0).
- `MemcachedCache` (python-memcached) backend, removed.

</details>

## Verify

```bash
python -m django --version
python manage.py shell -c "from django.core.cache import cache; cache.set('probe', 1, 5); print(cache.get('probe'))"
curl -s -o /dev/null -D - https://example.com/ | grep -iE 'cache-control|vary|etag|set-cookie'
curl -s -o /dev/null -D - -H 'Cookie: sessionid=x' https://example.com/account/ | grep -iE 'cache-control|age'
```

## Sources

- [Django cache framework](https://docs.djangoproject.com/en/6.0/topics/cache/)
- [Conditional view processing](https://docs.djangoproject.com/en/6.0/topics/conditional-view-processing/)
- [Django 6.0.6 release notes](https://django.readthedocs.io/en/6.0.x/releases/6.0.6.html)
- [Django 6.0.7 release notes (CVE-2026-48588)](https://django.readthedocs.io/en/stable/_sources/releases/6.0.7.txt)
- [Django 6.1 release notes](https://docs.djangoproject.com/en/dev/releases/6.1)
- [Middleware ordering](https://docs.djangoproject.com/en/6.0/ref/middleware/)
