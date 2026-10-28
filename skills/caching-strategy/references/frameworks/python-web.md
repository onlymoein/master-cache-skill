# Python web frameworks (FastAPI, Flask, Starlette, Litestar)

Last reviewed: 2026-10-27 · Applies to: FastAPI (Starlette), Flask (+ Flask-Caching), Litestar; cashews, aiocache, fastapi-cache2; redis-py

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Flask
- Litestar
- Verify
- Sources

## When to read this

When the backend is FastAPI, Flask, Starlette or Litestar. Django has its own file (`references/frameworks/django.md`).

## How to detect

`pyproject.toml`/`requirements*.txt`/`uv.lock`/`poetry.lock` with `fastapi`, `starlette`, `flask`, `flask-caching`, `litestar`, `cashews`, `aiocache`, `fastapi-cache2`, `redis`.

## Default recipe

Set headers explicitly per route, and use an async cache-aside helper (`assets/snippets/app/cache_aside.py`) on a shared Redis/Valkey.

```python
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()

@app.middleware("http")
async def default_cache_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Cache-Control", "no-store")      # routes opt in
    return response

@app.get("/products/{pid}")
async def product(pid: int, request: Request):
    p = await get_product(pid)                                    # cache-aside: jitter, single-flight, SWR
    etag = f'"p-{p.id}-v{p.version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    return JSONResponse(p.model_dump(), headers={
        "ETag": etag,
        "Cache-Control": "no-cache",
        "CDN-Cache-Control": "max-age=300, stale-while-revalidate=3600, stale-if-error=86400",
    })
```

Function caching with cashews (tags, early refresh, locks):

```python
from cashews import cache
cache.setup("redis://localhost/0")

@cache(ttl="10m", key="shop:v3:product:{pid}", tags=["product:{pid}"])
async def get_product(pid: int): ...

await cache.delete_tags(f"product:{pid}")   # on update; verify the exact API for your cashews version
```

## Rules and gotchas

1. `fastapi-cache2` has had no release since 2024 (stalled). Prefer `cashews`, explicit redis-py, or maintained alternatives (`fastapi-cache2-fork`, FastAPI-CacheX); check maintenance before adopting.
2. Response-caching decorators must not cache authenticated endpoints unless the key includes the user; default to caching data, not responses.
3. Use `redis.asyncio` with one pool per process; don't create clients per request.
4. `functools.lru_cache` on async functions caches the coroutine object, not the result: use an async-aware cache.
5. `functools.lru_cache(maxsize=None)` is unbounded; on methods it keeps `self` alive. cachetools needs `lock=` for thread safety.
6. Multiple uvicorn/gunicorn workers each have their own in-process caches; use Redis for anything shared.

## Flask

```python
from flask_caching import Cache
cache = Cache(config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": REDIS_URL, "CACHE_DEFAULT_TIMEOUT": 300})
cache.init_app(app)

@app.get("/catalog")
@cache.cached(timeout=60, query_string=True)     # public, anonymous responses only
def catalog(): ...

@cache.memoize(timeout=300)
def expensive(x): ...
cache.delete_memoized(expensive, x)
```

Set `Cache-Control` per route (`response.cache_control.no_cache = True`, `.private = True`) and keep `@cache.cached` off authenticated views.

## Litestar

Litestar has built-in response caching (`cache=` on route handlers, stores including Redis) and `cache_control` headers config; apply the same rules. Not covered in depth by this skill's research.

## Verify

```bash
curl -s -o /dev/null -D - http://localhost:8000/products/1 | grep -iE 'cache-control|etag|cdn-cache-control'
redis-cli --scan --pattern 'shop:v3:*' | head
```

## Sources

- [FastAPI middleware](https://fastapi.tiangolo.com/tutorial/middleware/)
- [cashews](https://github.com/Krukov/cashews)
- [FastAPI-CacheX issue on fastapi-cache2 status](https://github.com/allen0099/FastAPI-CacheX/issues/423)
- [Flask-Caching](https://flask-caching.readthedocs.io/)
- [redis-py asyncio](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html)
- [Litestar caching](https://docs.litestar.dev/latest/usage/caching.html)
