# Caching in Backend Frameworks, CMS/Commerce, API/GraphQL Layers, and Mobile/Native Apps (as of Oct 2026)

How these notes were made: in this session the network proxy blocked direct page fetches (WebFetch and curl returned DNS/403 errors for guides.rubyonrails.org, laravel.com, learn.microsoft.com and docs.djangoproject.com). Every finding therefore comes from web-search results, which return summaries and excerpts of the cited pages. Official docs were preferred wherever the search surfaced them.

The code snippets show the canonical API shape of each framework, taken from its official documentation as I know it and cited to that doc's URL. I could not re-fetch those pages in this session, so check exact signatures against the version a repo actually uses. The Inferences sections hold synthesis, such as stack-detection heuristics and recommendations; they are not sourced facts.

Version snapshot as of 2026-10-27, from cited findings below:
- Rails 8.1.x (8.1.3 plus security patch 8.1.3.1). No Rails 8.2 release was found.
- Django 6.1, released 2026-08-05.
- Laravel 13, which requires PHP 8.3.
- Spring Boot 4.1.1 on Spring Framework 7.0.x.
- .NET 10 (LTS) with HybridCache GA.
- Apollo Server 5. Apollo Server 4 reached end of life on 2026-01-26.
- PHP 8.5, where OPcache is always compiled in.
- Adobe Commerce 2.4.8, which uses Valkey instead of Redis.
- MongoDB Atlas Device Sync reached end of life on 2025-09-30.

---

## Ruby on Rails: Rails.cache stores (Solid Cache default), fragment/Russian-doll/collection caching, cache_key_with_version, low-level caching, HTTP caching helpers, race_condition_ttl

### Takeaway
Rails 8.x ships Solid Cache, a database-backed store, as the default production `Rails.cache`. Redis and Memcached remain supported alternatives. Rails's caching model is key-based expiry: `cache_key_with_version` combined with `touch: true` drives Russian-doll invalidation. That means you seldom delete keys explicitly. You add `race_condition_ttl` for stampede protection and `fresh_when`/`stale?` for 304s. As of Oct 2026 the current line is Rails 8.1.x, and no 8.2 release was found.

### Cited Findings
**Versions and recent changes**
- Rails 8.1 was released around 2025-10-22. — [This Week in Rails, 2025-10-24](https://rubyonrails.org/2025/10/24/this-week-in-rails)
- Rails 8.1.2 (2026-01-22) implemented a LocalCache strategy on `ActiveSupport::Cache::MemoryStore` so that it "respond[s] to the same interface as other cache stores (e.g. NullStore)". — [Rails 8.1.2 release](https://rubyonrails.org/2026/1/22/rails-version-8-1-2-has-been-released); [newreleases.io 8.1.2](https://newreleases.io/project/gems/rails/release/8.1.2)
- Rails 8.1 added a namespace setter and getter on Active Support cache stores, so the namespace can be inspected or changed after initialization. — [This Week in Rails (8.1 beta)](https://world.hey.com/this.week.in.rails/rendering-markdown-is-real-plus-new-database-connection-pool-options-6e083ffd)
- Rails 8.0.5 and 8.1.3 shipped on 2026-03-24. The 8.1 series receives bug fixes until October 2026, and 8.0 moved to security-only in May 2026. — [rubyonrails.org](https://rubyonrails.org/2026/3/24/Rails-Versions-8-0-5-and-8-1-3-have-been-released)
- A July 2026 advisory covers CVE-2026-66066, an Active Storage issue fixed in 8.0.5.1, 8.1.3.1 and 7.2.3.2. It is not cache-related, but it marks the current patch level. — [Canadian Centre for Cyber Security AV26-767](https://www.cyber.gc.ca/fr/alertes-avis/bulletin-securite-rails-av26-767)
- No Rails 8.2 release appeared in search results as of Oct 2026. — [search: rubyonrails.org posts](https://rubyonrails.org/2026/3/24/Rails-Versions-8-0-5-and-8-1-3-have-been-released)

**Solid Cache (Rails 8 default)**
- Solid Cache is the default production cache store in Rails 8 and is preconfigured in new apps. On existing apps (Rails 7.1+) you add the gem and run its install task, and a dedicated cache database is recommended (SQLite or PostgreSQL). — [Saeloun, 2026-05-26](https://blog.saeloun.com/2026/05/26/rails-8-solid-cache-database-backed-caching/)
- After 37signals moved from Redis to Solid Cache, its cache grew to more than 10 TB, because disk-backed storage allows much larger caches than RAM-based Redis or Memcached. — [Honeybadger: Rails 8](https://www.honeybadger.io/blog/rails-8/)
- The official guide sets `max_age` and `max_size` under `store_options` in `config/cache.yml`, for example 60 days and 256 MB. Expiry is triggered by writes: each write increments a counter, and when it reaches 50% of `expiry_batch_size` a background expiry task runs. — [Rails Guides: Caching](https://guides.rubyonrails.org/caching_with_rails.html); [guide source](https://github.com/rails/rails/blob/main/guides/source/caching_with_rails.md)
- Sources disagree on the eviction algorithm. Some third-party posts call Solid Cache FIFO, others describe size-based LRU, and the official guide doesn't settle it in the excerpts seen. One blog also gives `max_size` units as KB, which conflicts with the official `256.megabytes`. — [nsinenko.com](https://nsinenko.com/rails/performance/caching/2025/12/12/solid-cache-rails-8-database-backed-caching/); [sharpskill.dev](https://sharpskill.dev/en/blog/ruby-on-rails/solid-queue-solid-cache-rails-8-guide); contradicted by [Rails Guides](https://guides.rubyonrails.org/caching_with_rails.html)

**Stampede protection, Russian doll caching, HTTP caching**
- `race_condition_ttl` limits cache stampedes. The first process to hit a recently expired entry bumps its expiry by `race_condition_ttl` seconds, so other processes keep serving the stale value while it regenerates. Keep the value small. It applies only when the entry expired recently; otherwise a fresh value is generated. — [Rails Guides](https://guides.rubyonrails.org/caching_with_rails.html); [ActiveSupport::Cache::Store API](https://api.rubyonrails.org/classes/ActiveSupport/Cache/Store.html)
- In Russian doll caching, nested fragments are reused when the outer fragment regenerates. Updating a child doesn't expire the parent unless you add `belongs_to :product, touch: true`. — [Rails Guides](https://guides.rubyonrails.org/caching_with_rails.html)
- `fresh_when` and `stale?` take an ETag and/or Last-Modified. When you pass a model, Rails uses `updated_at` for Last-Modified and `cache_key_with_version` for the ETag. `public: true` makes the response cacheable by shared caches. — [ActionController::ConditionalGet](https://api.rubyonrails.org/classes/ActionController/ConditionalGet.html); [Heroku: HTTP caching in Rails](https://devcenter.heroku.com/articles/http-caching-ruby-rails)
- PR #52274 (2024) added `config.action_dispatch.strict_freshness`. When it is true, the ETag (If-None-Match) takes precedence over Last-Modified, per RFC 7232. — [rails/rails#52274](https://github.com/rails/rails/pull/52274)

**Canonical snippets** (API shapes per [Rails Guides: Caching](https://guides.rubyonrails.org/caching_with_rails.html) and [ConditionalGet API](https://api.rubyonrails.org/classes/ActionController/ConditionalGet.html))
```ruby
# config/environments/production.rb  (Rails 8 default)
config.cache_store = :solid_cache_store
# Alternatives:
# config.cache_store = :redis_cache_store, { url: ENV["REDIS_URL"] }
# config.cache_store = :mem_cache_store, "cache-1.example.com"   # dalli gem
```
```yaml
# config/cache.yml
default: &default
  store_options:
    max_age: <%= 60.days.to_i %>
    max_size: <%= 256.megabytes %>
    namespace: <%= Rails.env %>
production:
  database: cache          # separate DB entry in config/database.yml
  <<: *default
```
```erb
<%# fragment + Russian doll %>
<% cache @product do %>
  <%= render @product.variants %>   <%# inner cache blocks per variant %>
<% end %>
<%# collection caching: multi-read of all fragments in one round trip %>
<%= render partial: "products/product", collection: @products, cached: true %>
```
```ruby
class Variant < ApplicationRecord
  belongs_to :product, touch: true   # child update bumps parent's updated_at → new cache key
end

# low-level
Rails.cache.fetch([product, "competing_price"], expires_in: 12.hours, race_condition_ttl: 10.seconds) do
  Competitor::API.find_price(product.id)
end

# HTTP conditional GET
def show
  @article = Article.find(params[:id])
  fresh_when @article, public: true          # sets ETag/Last-Modified, renders 304 if fresh
end
def index
  @articles = Article.recent
  if stale?(@articles)                       # collection etag
    render json: @articles
  end
end
expires_in 5.minutes, public: true           # Cache-Control: max-age=300, public
http_cache_forever(public: true) { render }  # for immutable resources
```
- Development: `bin/rails dev:cache` toggles caching in development. — [Rails Guides](https://guides.rubyonrails.org/caching_with_rails.html)

### Inferences
- **Detecting Rails:**
  - `Gemfile` / `Gemfile.lock` containing `rails`, plus `config/application.rb` and `bin/rails`.
  - The cache store is set in `config/environments/production.rb` (`config.cache_store`).
  - Solid Cache shows up as `solid_cache` in the Gemfile, `config/cache.yml`, a `cache:` database in `config/database.yml`, and `db/cache_schema.rb`.
  - Redis shows up as `redis` / `hiredis-client` gems. Memcached shows up as the `dalli` gem.
- **Recommendation logic:**
  - Keep Solid Cache for most Rails 8 apps, since it is the default and needs no extra infrastructure.
  - Choose Redis or Memcached when you need sub-millisecond latency at very high request rates, or when Redis is already running for other jobs.
  - Choose Solid Cache when the cache is large or the working set exceeds affordable RAM, as in the 37signals case.
- **Pitfalls to encode:**
  - A missing `touch: true` leaves Russian-doll parents stale.
  - Cache keys that omit locale, currency, or user role leak content across variants.
  - `fresh_when` combined with `public: true` on a personalized page leaks data through CDNs.
  - Without `race_condition_ttl` or a lock, a hot key causes a stampede.
  - Collection caching with `cached: true` needs partials that don't depend on per-request state.
  - Rails's default `MemoryStore` in multi-process servers such as Puma workers gives every process its own cache, so it isn't shared.
- If you use Redis as the Rails cache, configure an eviction policy such as `allkeys-lru` and keep it separate from a Redis instance used for Sidekiq queues, so queue data isn't evicted. This is standard practice but wasn't re-verified this session.

### Gaps
- I couldn't confirm Solid Cache's exact eviction algorithm (FIFO vs LRU) or the 8.1 changelog entries for `solid_cache`, because the official pages couldn't be fetched.
- I didn't verify whether `load_defaults 8.x` turns `strict_freshness` on by default.
- I didn't find Rails 8.2 release status or timeline. None was found as of Oct 2026.

---

## Django: cache backends (built-in Redis since 4.0), per-site/per-view caching, template fragment caching, low-level API, cache_control/vary_on_*, ConditionalGetMiddleware, ETags

### Takeaway
Django's cache framework ships with backends for Redis, Memcached, the database, files and local memory. It layers per-site middleware, the per-view `cache_page`, the template `{% cache %}` tag, and the low-level `cache` API. The biggest real-world risks are personalization leaks: `cache_page` doesn't vary on cookies or authentication by default. Django patched several such cache-leak bugs in 6.0.6 and 6.0.7 (mid-2026), so stay on the latest patch release. Django 6.1 is the current feature release (2026-08-05).

### Cited Findings
- Django 6.1 was released on 2026-08-05, and 6.0 left mainstream support at that point. The 6.1 highlights listed (model field fetch modes, database-level `on_delete`, dict-based email settings) contain no headline cache features. — [Django weblog](https://djangoproject.com/weblog/2026/aug/05/django-61-released); [6.1 release notes](https://docs.djangoproject.com/en/dev/releases/6.1)
- **6.0.6 (2026-06-03) security fixes touching the cache:**
  - `UpdateCacheMiddleware` and `cache_page()` cached responses that had a manually set, mixed-case `Private` Cache-Control directive.
  - Requests carrying an `Authorization` header now make the cached response vary on that header.
  - Whitespace-padded `Vary` headers could let a `Vary: *` response be cached.
  - — [Django 6.0.6 notes](https://docs.djangoproject.com/pt-br/6.1/releases/6.0.6/); [readthedocs mirror](https://django.readthedocs.io/en/6.0.x/releases/6.0.6.html)
- **6.0.7 (2026-07-07), CVE-2026-48588:** a response that sets a session cookie could be stored in the shared cache when the incoming request already carried some unrelated cookie. — [Django 6.0.7 notes](https://django.readthedocs.io/en/stable/_sources/releases/6.0.7.txt)
- `django.core.cache.backends.redis.RedisCache` is a built-in backend and a recommended choice for cache-based sessions. — [Django settings reference](https://docs.djangoproject.com/en/6.0/ref/settings/)
- Per-view caching does not automatically vary by authentication, sessions or cookies; apply `vary_on_cookie()` when the response depends on them. Per-view decorators also run before the CSRF middleware adds its Vary header, so views that need a CSRF token should apply `csrf_protect` first. — [Django cache framework](https://docs.djangoproject.com/en/6.0/topics/cache/)
- **Middleware order:**
  - `UpdateCacheMiddleware` runs in the response phase, which processes middleware in reverse, so it must come before any middleware that adds to `Vary` (SessionMiddleware, GZipMiddleware, LocaleMiddleware).
  - `FetchFromCacheMiddleware` must come after them.
  - `ConditionalGetMiddleware` goes before any middleware that may change the response and after GZipMiddleware.
  - — [Django cache framework](https://docs.djangoproject.com/en/6.0/topics/cache/); [Middleware reference](https://docs.djangoproject.com/en/6.0/ref/middleware/)

**Canonical snippets** (per [Django cache framework docs](https://docs.djangoproject.com/en/6.0/topics/cache/) and [conditional view processing](https://docs.djangoproject.com/en/6.0/topics/conditional-view-processing/))
```python
# settings.py
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379",
        "TIMEOUT": 300,               # default; None = forever, 0 = don't cache
        "KEY_PREFIX": "myapp",
    }
}
# Other built-ins: memcached.PyMemcacheCache / PyLibMCCache, db.DatabaseCache,
# filebased.FileBasedCache, locmem.LocMemCache (default; per-process), dummy.DummyCache

MIDDLEWARE = [
    "django.middleware.cache.UpdateCacheMiddleware",     # first
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    # ...
    "django.middleware.cache.FetchFromCacheMiddleware",  # last
]
CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 600
CACHE_MIDDLEWARE_KEY_PREFIX = "site"
```
```python
from django.views.decorators.cache import cache_page, cache_control, never_cache
from django.views.decorators.vary import vary_on_cookie, vary_on_headers
from django.views.decorators.http import condition, etag, last_modified
from django.core.cache import cache

@cache_page(60 * 15)            # per-view, server-side + sets Cache-Control max-age
@vary_on_cookie
def product_list(request): ...

@cache_control(public=True, max_age=3600)   # HTTP-only, no server storage
def public_page(request): ...

@condition(etag_func=lambda req, pk: Product.objects.get(pk=pk).version_hash)
def product_detail(request, pk): ...

val = cache.get_or_set("top_products", compute_top_products, timeout=300)
cache.set_many({"a": 1, "b": 2}); cache.delete_many(["a", "b"]); cache.touch("k", 60); cache.incr("hits")
val = await cache.aget("k")       # async variants (aget/aset/...) exist since 4.0
```
```django
{% load cache %}
{% cache 500 sidebar request.user.username %} ... {% endcache %}
```

### Inferences
- **Detecting Django:** `manage.py`; `django` in `requirements*.txt`, `pyproject.toml` or `Pipfile`; `settings.py` with `INSTALLED_APPS`. Inspect `CACHES` and `MIDDLEWARE`. `django-redis` in the dependencies means the third-party backend (it offers extra features such as pattern deletes) rather than the built-in one.
- **Defaults:** `LocMemCache` is per-process and not shared across gunicorn or uvicorn workers, so production should use Redis or Memcached.
- **Recommendation logic:**
  - Low-level `get_or_set` around expensive queries.
  - Template fragment caching for shared fragments.
  - `cache_page` only for anonymous or public pages.
  - `cache_control` / `ConditionalGetMiddleware` for CDN and browser caching.
  - Pin to the latest 6.0.x/6.1.x patch for the cache-leak fixes.
- **Pitfalls to encode:**
  - Per-site cache combined with sessions/auth leaks personalized pages. The default behavior was only hardened in 6.0.6/6.0.7.
  - Wrong middleware order means `Vary` is ignored.
  - Template fragment keys need per-user or per-locale vary arguments.
  - `cache.get_or_set` has no lock, so add one for stampede protection, for example via a Redis lock.

### Gaps
- I couldn't fetch the official cache page to verify every snippet (fetch was blocked). I found no cache-specific changes in Django 6.1.
- The 6.0.x security fixes were presumably also backported to 5.2 LTS, but I didn't verify that.

---

## Laravel: Cache facade drivers, remember/flexible (SWR), tags, memo, touch, failover, artisan optimize, Octane cache, response-cache packages

### Takeaway
Laravel 13 (PHP 8.3+) has the richest built-in application-cache API in this survey:
- `Cache::remember` and `Cache::flexible` (stale-while-revalidate with deferred refresh)
- atomic locks and tags (on Redis and Memcached)
- `Cache::memo()`, a request-scoped memoization layer (12.9+, with tags support in 13.33)
- the `failover` driver (12.35+)
- `Cache::touch()`

Production apps should also run `php artisan optimize` to cache config, routes, views and events.

### Cited Findings
- Laravel 13 requires PHP 8.3+ (dropping 8.2). It gets bug fixes through Q3 2027 and security fixes through Q1 2028. — [Laravel News: Laravel 13 released](https://laravel-news.com/index.php/laravel-13-released)
- `Cache::touch()` extends an item's TTL without reading or rewriting the value. It accepts seconds, a DateTime, or null (no expiry), returns false if the key is missing, maps to a single native command per backend, and works on all built-in drivers. — [Laravel News: Laravel 13](https://laravel-news.com/laravel-13)
- Laravel 13.33.0 added `tags()` to the memoized store. Reads hit the backend once per request and are then served from memory; writes and tag flushes clear the memoized entries. — [Laravel News 13.33.0](https://laravel-news.com/laravel-13-33-0)
- `Cache::memo()` arrived in 12.9.0 as a decorator that keeps retrieved values in memory for the rest of the request. It can wrap a named store (`Cache::memo('redis')`), and writes clear that key's memoized value. — [nabilhassen.com](https://nabilhassen.com/laravel-129-introduces-memoized-cache-driver); [Laravel News 12.9.0](https://laravel-news.com/laravel-12-9-0)
- Laravel 12.35.0 added a `failover` cache driver that tries stores in order when the primary fails, configured as `'failover' => ['driver' => 'failover', 'stores' => ['database', 'array']]`. It only takes effect when the default store points at it. The 13.x API includes `FailoverStore extends TaggableStore implements LockProvider`. — [Laravel News 12.35.0](https://laravel-news.com/laravel-12-35-0); [FailoverStore API 13.x](https://api.laravel.com/docs/13.x/Illuminate/Cache/FailoverStore.html)
- **`Cache::flexible`** implements stale-while-revalidate with three phases:
  - **Fresh:** within the first value, the cached value is returned immediately.
  - **Stale:** between the two values, the stale value is served and a deferred function refreshes it after the response is sent.
  - **Expired:** after the second value, the value is recalculated immediately.
  - The API reference shows `$lock` and `$alwaysDefer` parameters.
  - — [Laravel 12.x Cache docs](https://laravel.com/docs/12.x/cache); [Laravel 11.x Cache docs](https://laravel.com/docs/11.x/cache); [Repository API](https://api.laravel.com/docs/12.x/Illuminate/Cache/Repository.html)
- One secondary source says `flexible` creates three keys per entry, so clearing only one leaves stale metadata. — [Laravel News: Cache smart invalidation](https://laravel-news.com/cache-smart-invalidation-laravel-in-practice-ep10)
- Cache tags are not supported on the `file`, `dynamodb` or `database` drivers (stated in 9.x docs; I didn't re-verify the 13.x wording). — [Laravel 9.x Cache docs](https://laravel.com/docs/9.x/cache)
- **`artisan optimize`:** a 2026 guide says `php artisan optimize` runs config, event, route and view caching together in Laravel 12+, while older posts say it caches only config and routes, with `event:cache` run separately. `optimize:clear` also calls `cache:clear`, which flushes real application data from the default store. Calling `env()` outside config files breaks once config is cached. — [kokil.com.np 2026](https://kokil.com.np/blog/laravel-caching-strategies-config-route-view-and-data); [benjamincrozat.com](https://benjamincrozat.com/laravel-clear-cache); contrasting [freek.dev](https://freek.dev/2300-making-sure-routes-config-and-events-of-your-laravel-app-are-cached-in-production)

**Canonical snippets** (per [Laravel Cache docs](https://laravel.com/docs/12.x/cache))
```php
use Illuminate\Support\Facades\Cache;

$users = Cache::remember('users', 600, fn () => DB::table('users')->get());     // TTL seconds
$users = Cache::rememberForever('users', fn () => DB::table('users')->get());
$users = Cache::flexible('users', [5, 10], fn () => DB::table('users')->get()); // fresh 5s, stale until 10s

Cache::tags(['people', 'artists'])->put('John', $john, 600);   // redis/memcached only
Cache::tags(['artists'])->flush();

$lock = Cache::lock('report:build', 10);                      // atomic lock
if ($lock->get()) { try { /* build */ } finally { $lock->release(); } }

Cache::memo()->get('settings');        // request-scoped memo over default store
Cache::touch('session:abc', 3600);     // Laravel 13
Cache::add('key', 'v', 60);            // only if absent
Cache::increment('hits');
```
```php
// config/cache.php
'default' => env('CACHE_STORE', 'database'),   // Laravel 11+ skeleton default is database
'stores' => [
    'redis'    => ['driver' => 'redis', 'connection' => 'cache', 'lock_connection' => 'default'],
    'failover' => ['driver' => 'failover', 'stores' => ['redis', 'database']],
],
```
```bash
php artisan optimize          # config:cache + route:cache + view:cache + event:cache (11+)
php artisan optimize:clear    # NOTE: also clears application cache
```

### Inferences
- **Detecting Laravel:** `composer.json` with `laravel/framework`; `artisan` at the root; `config/cache.php`; the `CACHE_STORE` env var (Laravel 11+ renamed it from `CACHE_DRIVER`). Octane shows up as `laravel/octane` plus `config/octane.php`. Response-cache packages show up as `spatie/laravel-responsecache`.
- **Recommendation logic:**
  - Redis or Valkey for tags and locks.
  - `flexible` for expensive dashboards.
  - `memo()` for repeated reads within a request (settings, feature flags).
  - `failover` to survive a Redis outage.
  - `optimize` in the deploy script.
  - Never put `cache:clear` / `optimize:clear` in a deploy if the default store holds sessions, locks, or rate-limiter counters.
- **Octane (from knowledge, not verified this session):** the Octane cache driver (`Cache::store('octane')`) uses Swoole tables. It is very fast but per-server, so it is only for Swoole deployments. Under Octane, singletons and static state persist across requests, which makes accidental in-process caching a correctness risk.
- The database driver is the skeleton default. It works with no extra infrastructure but adds DB load and doesn't support tags.

### Gaps
- I couldn't fetch the 13.x cache docs to confirm the exact tag-support matrix, whether `flexible` works with tags, the Octane cache driver details, or `spatie/laravel-responsecache` v7 features (no search results for those).

---

## Spring Boot: Spring Cache abstraction (@Cacheable/@CacheEvict/@CachePut), Caffeine and Redis providers, HTTP caching (CacheControl, ETag filters), Hibernate second-level cache

### Takeaway
Spring Boot 4.x on Spring Framework 7 keeps the same declarative cache abstraction:
- `@EnableCaching` with `@Cacheable`, `@CachePut`, `@CacheEvict` and `@Caching`
- auto-configured providers (Caffeine for local, Redis for distributed)

Boot 4 modularized auto-configuration into a separate `spring-boot-cache` artifact. The main pitfalls are self-invocation (proxy mode) and the restrictions of `sync=true`. Hibernate 7's second-level cache via JCache/Ehcache 3 is a separate entity-level layer.

### Cited Findings
- Spring Boot 4.1.0 went GA around 2026-06-11 and 4.1.1 shipped on 2026-08-20; the 4.1.1 notes contain no cache-specific changes. — [spring.io blog 4.1.1](https://spring.io/blog/2026/08/20/spring-boot-4-1-1-available-now/); [Maven Central spring-boot-starter-cache](https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-cache)
- Boot 4 publishes a separate `org.springframework.boot:spring-boot-cache` module, at 4.0.x and 4.1.0. — [mvnrepository spring-boot-cache](https://mvnrepository.com/artifact/org.springframework.boot/spring-boot-cache); [javadoc.io 4.1.0](https://javadoc.io/doc/org.springframework.boot/spring-boot-cache/4.1.0/index.html)
- The latest stable Spring Framework is 7.0.9; the 7.1 reference is still in development. — [Spring Framework 7.1 cache reference](https://docs.spring.io/spring/reference/7.1/integration/cache.html); [Cacheable Javadoc 7.0.9](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- Boot auto-configures cache infrastructure once `@EnableCaching` is present. Don't put it on the main application class, because that makes caching mandatory even in tests. — [Spring Boot 4.0.4 caching docs](https://docs.spring.io/spring-boot/4.0.4/reference/io/caching.html)
- Boot 4.0 Redis changes: auto-configuration for static master/replica setups (Lettuce only), and tracing via MicrometerTracing instead of MicrometerCommandLatencyRecorder. — [Spring Boot 4.0 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes)
- A property for enabling Caffeine's async cache mode (#51844) appears in the Boot releases listing; I couldn't tell which version line it belongs to. — [spring-boot releases](https://github.com/spring-projects/spring-boot/releases)
- **`sync=true`** tells the provider to lock the entry while the value is computed. All core `CacheManager` implementations support it. It has three restrictions:
  - `unless` is not supported.
  - Only one cache may be named.
  - It can't be combined with other cache operations.
  - — [Spring Framework: Declarative annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html); [Cacheable Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Cacheable.html)
- In the default proxy mode, self-invocation (one method of a bean calling another on the same bean) bypasses caching. The docs strongly discourage putting `@CachePut` and `@Cacheable` on the same method. `@CacheEvict` works on void methods. — [Spring Framework cache annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- Caffeine is auto-configured when the cache starter and Caffeine are both present, and `spring.cache.caffeine.spec` sets a shared spec. — [coddykit (course)](https://www.coddykit.com/courses/spring_boot/in-memory-caching-with-caffeine-tuning-9299045)
- In two-level designs, `CompositeCacheManager` returns the first manager that has a cache for a name; it does not read Caffeine and then fall back to Redis. — [devops-monk 2026](https://blog.devops-monk.com/2026/05/spring-boot-caching-caffeine-redis/); [oneuptime multi-level](https://oneuptime.com/blog/post/2026-01-29-multi-level-caching-spring-boot/view)
- With Infinispan in Boot 4, `InfinispanConfigurationCustomizer` was removed in favor of `InfinispanCacheConfigurer`, and the artifacts moved from spring6 to spring7. — [Red Hat Data Grid 8.6](https://docs.redhat.com/es/documentation/red_hat_data_grid/8.6/html/using_data_grid_with_spring/spring-cache-provider)
- **Hibernate 7 second-level cache:**
  - It is disabled by default.
  - Set `hibernate.cache.use_second_level_cache=true` with region factory `org.hibernate.cache.jcache.internal.JCacheRegionFactory`, plus `hibernate-jcache` and Ehcache 3 (jakarta classifier).
  - Mark entities with `@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)`.
  - Strategies are READ_ONLY (throws on update), NONSTRICT_READ_WRITE, READ_WRITE, and TRANSACTIONAL (JTA).
  - — [ankurm.com Hibernate 7 L2](https://ankurm.com/mastering-hibernate-7-second-level-cache-boosting-performance-for-modern-java-apps/); [Baeldung](https://www.baeldung.com/hibernate-second-level-cache)

**Canonical snippets** (per [Spring Framework cache docs](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html), [Spring Boot caching](https://docs.spring.io/spring-boot/reference/io/caching.html), [Spring MVC HTTP caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html))
```java
@Configuration
@EnableCaching
class CacheConfig {}

@Service
class BookService {
  @Cacheable(cacheNames = "books", key = "#isbn", unless = "#result == null")
  public Book find(String isbn) { ... }

  @Cacheable(cacheNames = "bookStats", sync = true)   // stampede lock; no `unless`
  public Stats stats(String isbn) { ... }

  @CachePut(cacheNames = "books", key = "#book.isbn")
  public Book update(Book book) { ... }

  @CacheEvict(cacheNames = "books", allEntries = true)
  public void reload() { }

  @Caching(evict = { @CacheEvict("primary"), @CacheEvict(cacheNames = "secondary", key = "#p0") })
  public Book importBooks(String deposit) { ... }
}
```
```properties
# application.properties
spring.cache.type=caffeine
spring.cache.cache-names=books,bookStats
spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=10m
# or Redis:
# spring.cache.type=redis
# spring.cache.redis.time-to-live=10m
# spring.cache.redis.key-prefix=myapp:
# spring.data.redis.host=localhost
```
```java
// HTTP caching in Spring MVC
@GetMapping("/books/{id}")
ResponseEntity<Book> book(@PathVariable Long id) {
  Book b = repo.findById(id).orElseThrow();
  return ResponseEntity.ok()
      .cacheControl(CacheControl.maxAge(30, TimeUnit.MINUTES).cachePublic())
      .eTag(String.valueOf(b.getVersion()))      // 304 handled automatically on If-None-Match
      .body(b);
}
// Shallow ETag (hash of body; saves bandwidth, not server work):
@Bean FilterRegistrationBean<ShallowEtagHeaderFilter> etag() { return new FilterRegistrationBean<>(new ShallowEtagHeaderFilter()); }
```

### Inferences
- **Detecting Spring Boot:**
  - `pom.xml` / `build.gradle(.kts)` with `org.springframework.boot` (parent or plugin) and `spring-boot-starter-cache`.
  - `application.properties` / `application.yml` with `spring.cache.*`.
  - Providers show up as `com.github.ben-manes.caffeine:caffeine`, `spring-boot-starter-data-redis`, `org.hibernate.orm:hibernate-jcache`, `org.ehcache:ehcache`.
  - Find annotation usage by grepping for `@Cacheable`.
- **Recommendation logic:**
  - Caffeine for per-instance hot data.
  - Redis (`RedisCacheManager`) for shared data or data that must survive restarts.
  - Two-level setups need a custom `CacheManager` or a library; `CompositeCacheManager` isn't one.
  - Always set a TTL (Redis has none by default unless `time-to-live` is set).
  - Make cached DTOs serializable (JSON serializer recommended over JDK serialization).
- **Pitfalls to encode:**
  - Self-invocation.
  - `@Cacheable` on private methods (not proxied).
  - Caching JPA entities with lazy associations (LazyInitializationException after deserialization).
  - `sync=true` + `unless` is a startup error.
  - L2 cache plus native SQL or bulk updates gives stale entities.
  - `ShallowEtagHeaderFilter` doesn't save server computation.

### Gaps
- No official "what's new in caching" for Spring Framework 7 / Boot 4 surfaced. Reactive caching (`@Cacheable` on `Mono`/`Flux`/`CompletableFuture`, supported since Framework 6.1 from knowledge) wasn't verified this session.
- I couldn't confirm which release introduced the Caffeine async-mode property.

---

## ASP.NET Core: Output Caching (.NET 7+), Response Caching differences, IMemoryCache, IDistributedCache, HybridCache (.NET 9+), tag eviction

### Takeaway
On .NET 10 (LTS), use:
- Output Caching (server-side, policy-driven, tag eviction, Redis store since .NET 8) for whole responses
- HybridCache (`Microsoft.Extensions.Caching.Hybrid`: L1 memory plus optional L2 `IDistributedCache`, stampede protection, tags) for data

Response Caching middleware is the older, header-driven, client-hint-respecting option. Output caching's safe defaults (no auth, no Set-Cookie, only 200 GET/HEAD) must be overridden deliberately for per-user caching.

### Cited Findings
- Output caching defaults: only HTTP 200, only GET/HEAD, no responses that set cookies, no authenticated requests. — [MS Learn: Output caching middleware (aspnetcore-10.0)](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output?view=aspnetcore-10.0); [AspNetCore.Docs output.md](https://github.com/dotnet/AspNetCore.Docs/blob/main/aspnetcore/performance/caching/output.md)
- A custom `IOutputCacheStore` lacks the atomic operations tagging needs; use the built-in Redis support or a store that handles atomicity. `EvictByTagAsync` is output-cache only. — [MS Learn: Output caching](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output?view=aspnetcore-10.0); [c-sharpcorner comparison](https://www.c-sharpcorner.com/article/output-caching-vs-response-caching-in-asp-net-co-whats-the-difference/)
- Redis output-cache store since .NET 8: the `Microsoft.AspNetCore.OutputCaching.StackExchangeRedis` package and `AddStackExchangeRedisOutputCache`. — [dotnet-guide.com](https://www.dotnet-guide.com/tutorials/aspnet-core/caching-outputcache-redis-invalidation/); [antondevtips](https://antondevtips.com/blog/aspnetcore-output-cache-how-to-speed-up-your-api-with-in-memory-cache-and-redis)
- Response Caching relies on HTTP headers and client/proxy caches and honors client `Cache-Control`. Output Caching stores on the server, is controlled by policies, and ignores client hints. — [codingdroplets 2026](https://codingdroplets.com/output-caching-vs-response-caching-in-asp-net-core-which-should-your-team-use-in-2026); [c-sharpcorner](https://www.c-sharpcorner.com/article/output-caching-vs-response-caching-in-asp-net-co-whats-the-difference/)
- To cache authenticated responses, define a custom policy (excluding the default policy), vary by the user ID from `ClaimsPrincipal` (`SetVaryByValue`), and never share across users. — [dotnet-guide.com](https://www.dotnet-guide.com/tutorials/aspnet-core/caching-outputcache-redis-invalidation/)
- HybridCache started as a preview in .NET 9 and is fully supported as the `Microsoft.Extensions.Caching.Hybrid` package. It has two levels (L1 in-memory, optional L2 distributed such as Redis or SQL Server) and stampede protection. — [Milan Jovanović](https://milanjovanovic.tech/blog/hybrid-cache-in-aspnetcore-new-caching-library); [codewithmukesh (.NET 10)](https://codewithmukesh.com/blog/hybridcache-in-aspnet-core/)
- `GetOrCreateAsync` handles misses, serialization and storage. `LocalCacheExpiration` sets the L1 lifetime and `Expiration` the L2 lifetime. Tags are passed in `GetOrCreateAsync`, and `RemoveByTagAsync` invalidates by tag. — [MS Learn: Caching in .NET](https://learn.microsoft.com/en-us/dotnet/core/extensions/caching); [coding-luggage.com](https://coding-luggage.com/hybridcache-in-dotnet); [codewithmukesh](https://codewithmukesh.com/blog/hybridcache-in-aspnet-core/)

**Canonical snippets** (per [MS Learn Output caching](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output), [HybridCache](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/hybrid), [Caching in .NET](https://learn.microsoft.com/en-us/dotnet/core/extensions/caching))
```csharp
// Program.cs — Output caching
builder.Services.AddOutputCache(o =>
{
    o.AddBasePolicy(b => b.Expire(TimeSpan.FromSeconds(30)));
    o.AddPolicy("Products", b => b.Expire(TimeSpan.FromMinutes(5))
                                  .SetVaryByQuery("page", "sort")
                                  .Tag("products"));
});
builder.Services.AddStackExchangeRedisOutputCache(o => o.Configuration = "localhost:6379"); // shared store
var app = builder.Build();
app.UseCors(); app.UseRouting();   // UseOutputCache must come after these when used
app.UseOutputCache();
app.MapGet("/products", GetProducts).CacheOutput("Products");
app.MapPost("/products", async (Product p, IOutputCacheStore store, CancellationToken ct) =>
{
    /* save */ await store.EvictByTagAsync("products", ct); return Results.Created();
});
```
```csharp
// HybridCache (data caching)
builder.Services.AddStackExchangeRedisCache(o => o.Configuration = "localhost:6379"); // becomes L2
builder.Services.AddHybridCache(o =>
{
    o.MaximumPayloadBytes = 1024 * 1024;
    o.DefaultEntryOptions = new HybridCacheEntryOptions
    {
        Expiration = TimeSpan.FromMinutes(10),          // L2
        LocalCacheExpiration = TimeSpan.FromMinutes(2)  // L1
    };
});

public async Task<Product> Get(int id, HybridCache cache, CancellationToken ct) =>
    await cache.GetOrCreateAsync($"product:{id}",
        async token => await db.Products.FindAsync([id], token),
        tags: ["products", $"product:{id}"], cancellationToken: ct);

await cache.RemoveByTagAsync("products");
```
```csharp
// IMemoryCache (in-process; no stampede protection)
var v = await memoryCache.GetOrCreateAsync(key, e => { e.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5); e.Size = 1; return LoadAsync(); });
```

### Inferences
- **Detecting ASP.NET Core:** `*.csproj` with `Sdk="Microsoft.NET.Sdk.Web"`; `Program.cs` with `WebApplication.CreateBuilder`; `<TargetFramework>net10.0</TargetFramework>`. Packages to look for: `Microsoft.Extensions.Caching.Hybrid`, `Microsoft.Extensions.Caching.StackExchangeRedis`, `Microsoft.AspNetCore.OutputCaching.StackExchangeRedis`, and third-party `ZiggyCreatures.FusionCache` / `EasyCaching`.
- **Recommendation logic:**
  - New code uses HybridCache instead of raw `IDistributedCache` (which gives byte arrays and no stampede protection) or `IMemoryCache` (single node).
  - Output caching for public GET endpoints, with tag eviction on writes.
  - Response Caching middleware only when you specifically want to emit HTTP cache headers for downstream caches. Even then, setting headers directly or via `[ResponseCache]` is often enough.
- Multi-node L1 coherence: HybridCache's L1 is per-node, so after an update other nodes can serve stale L1 data until `LocalCacheExpiration`. I didn't verify whether built-in cross-node invalidation exists; keep L1 TTLs short, or consider FusionCache's backplane.
- **Pitfalls:**
  - Output cache with the in-memory store in multi-instance deployments (inconsistent eviction).
  - Forgetting `SetVaryByValue`/`VaryByHeader` when overriding auth exclusions.
  - Middleware order.
  - Caching EF entities with tracking or proxies.

### Gaps
- I couldn't fetch the official HybridCache page to confirm exact option names (`MaximumPayloadBytes`, `MaximumKeyLength`), the `RemoveByTagAsync("*")` semantics, or the HybridCache-related .NET 10 changes. The .NET 11 previews (due November 2026) weren't checked.

---

## Node backends (Express, Fastify, NestJS, apicache), Python FastAPI, Go (groupcache, ristretto), Phoenix/Elixir (Cachex, Nebulex)

### Takeaway
Node frameworks have no built-in data cache. NestJS's `@nestjs/cache-manager` (v3, Keyv-based stores since NestJS 11) is the standard. Express generates weak ETags by default. Fastify relies on `@fastify/etag` / `@fastify/caching`. In FastAPI the `fastapi-cache2` package has stalled, with `cashews` and FastAPI-CacheX as alternatives. Go uses ristretto v2 or otter in-process and groupcache-go for distributed fill-once. Elixir uses Cachex and Nebulex 3.

### Cited Findings
**NestJS**
- The current install is `npm install @nestjs/cache-manager cache-manager @keyv/redis keyv`. cache-manager now uses Keyv stores, so `@keyv/redis` is the Redis adapter, passed as `stores: [createKeyv('redis://localhost:6379')]` or `new KeyvRedis(...)`. — [oneuptime 2026-02](https://oneuptime.com/blog/post/2026-02-02-nestjs-caching/view); [DEV: keyv/redis](https://dev.to/mukesh_rajbanshi/implementing-redis-caching-in-nestjs-using-docker-and-keyvredis-1gmn)
- `CacheModule.register()` with no arguments gives in-memory caching. NestJS 11 uses Keyv internally. One secondary source says cached values use a new `{"value","expires"}` shape, so you should flush the store after upgrading from NestJS 10. — [Stanza course](https://www.stanza.dev/courses/nestjs-performance/database-performance/nestjs-performance-caching-strategies)
- The older `cache-manager-redis-store` + `CacheModule.register({ store: redisStore })` pattern predates the Keyv migration and is outdated. — [LogRocket (outdated example)](https://blog.logrocket.com/add-redis-cache-nestjs-app/)

**Express**
- Express defaults to weak ETags. `app.set('etag', ...)` accepts `'weak'`, `'strong'`, `false`, or a function, and the tag is computed from the body. A GitHub issue notes that weak ETags can collide for different bodies of 1 KB or less. — [expressjs/express#2667](https://github.com/expressjs/express/issues/2667); [webapplog](https://webapplog.com/secret-express-js-settings/)
- When the body contains per-request data (timestamps, nonces), the default hash changes every request, so 304s never happen. Set `app.set('etag', false)` and emit a content/version-based ETag yourself. — [DEV: ETag, Last-Modified and 304s](https://dev.to/indexerpal/etag-last-modified-and-304s-let-googlebot-recrawl-what-actually-changed-2dk4)

**FastAPI**
- **fastapi-cache2:** a FastAPI-CacheX issue opened 2026-10-02 says fastapi-cache2's last release was in 2024, and a FastAPI-CacheX PR lists fastapi-cache2 0.2.2, cashews 7.6.0 and aiocache 0.12.3 as the latest PyPI releases. A msgspec-based `fastapi-cache2-fork` released 2.3.0 on 2026-01-28. — [FastAPI-CacheX #423](https://github.com/allen0099/FastAPI-CacheX/issues/423); [FastAPI-CacheX PR #449](https://github.com/allen0099/FastAPI-CacheX/pull/449); [piwheels fork](https://www.piwheels.org/project/fastapi-cache2-fork/)
- **cashews** suits function caching with early refresh, tags and metrics. A March 2026 issue requested a fastapi-cache2-style `key_builder`. — [FastAPI-CacheX PR #449](https://github.com/allen0099/FastAPI-CacheX/pull/449); [cashews #424](https://github.com/Krukov/cashews/issues/424)

**Go**
- **ristretto v2** (`github.com/dgraph-io/ristretto/v2`) is a memory-bound cache with generic keys. A `Set` of a new item is not guaranteed to be stored, because admission or buffer drops can discard it. — [pkg.go.dev ristretto](https://pkg.go.dev/github.com/dgraph-io/ristretto)
- **groupcache-go** is the maintained fork: only one load per key across a replicated set of processes populates the cache, there are no versioned values, and the import path is `github.com/groupcache/groupcache-go/v3`. — [groupcache-go](https://github.com/groupcache/groupcache-go)
- **otter** is a lockless high-performance cache (Awesome Go shows an update on 2026-06-19). **gocache** wraps multiple stores. — [Awesome Go: otter](https://awesome-go.com/caches/otter-maypok86-github/); [eko/gocache](https://github.com/eko/gocache)

**Elixir**
- Nebulex 3.0.x needs the `:decorator` dependency for caching decorators, plus an adapter such as `:nebulex_local`; it can sit on Redis, Memcached or Cachex. The 2.x decorator syntax is `@decorate cacheable(cache: Cache, key: {User, id}, opts: [ttl: @ttl])`, with `cache_put` and `cache_evict`. — [Nebulex 3.0.4 README](https://repo.hex.pm/preview/nebulex/3.0.4/README.md); [Nebulex 3.0.3](https://readme.hex.pm/nebulex/3.0.3)

**Canonical snippets** (NestJS per [NestJS caching docs](https://docs.nestjs.com/techniques/caching); others per the cited READMEs)
```ts
// NestJS 11 + @nestjs/cache-manager v3 (Keyv stores; TTL in milliseconds)
import { CacheModule, CacheInterceptor, CacheKey, CacheTTL } from '@nestjs/cache-manager';
import { createKeyv } from '@keyv/redis';
@Module({
  imports: [CacheModule.registerAsync({
    isGlobal: true,
    useFactory: async () => ({ stores: [createKeyv(process.env.REDIS_URL)], ttl: 60_000 }),
  })],
  providers: [{ provide: APP_INTERCEPTOR, useClass: CacheInterceptor }], // auto-caches GET handlers
})
export class AppModule {}

@Controller('products')
export class ProductsController {
  constructor(@Inject(CACHE_MANAGER) private cache: Cache) {}
  @Get() @CacheKey('products:all') @CacheTTL(30_000) findAll() { ... }
  async update() { /* ... */ await this.cache.del('products:all'); }
}
```
```js
// Express
app.set('etag', 'strong');                 // or false and set your own ETag
res.set('Cache-Control', 'public, max-age=60, stale-while-revalidate=300');
if (req.fresh) return res.status(304).end(); // req.fresh compares ETag/Last-Modified
```
```python
# FastAPI + fastapi-cache2 (stalled; see cashews)
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache
FastAPICache.init(RedisBackend(redis), prefix="api-cache")   # in lifespan
@app.get("/items/{id}")
@cache(expire=60)
async def get_item(id: int): ...
```
```go
// Go: ristretto v2
c, _ := ristretto.NewCache(&ristretto.Config[string, []byte]{NumCounters: 1e7, MaxCost: 1 << 30, BufferItems: 64})
c.SetWithTTL("k", v, int64(len(v)), 5*time.Minute); c.Wait() // Set may be dropped
// Go HTTP: w.Header().Set("Cache-Control", "public, max-age=60"); http.ServeContent handles If-Modified-Since/If-None-Match (when ETag header set)
```
```elixir
# Cachex
Cachex.fetch(:my_cache, key, fn k -> {:commit, load(k), expire: :timer.minutes(5)} end)
```

### Inferences
- **Detection, Node:** `package.json` dependencies: `@nestjs/core` + `@nestjs/cache-manager`; `express`; `fastify` + `@fastify/caching` / `@fastify/etag`; `apicache`; `keyv` / `@keyv/redis`; `ioredis` / `redis`.
- **Detection, Python:** `fastapi`, `fastapi-cache2`, `cashews`, `aiocache` in `pyproject.toml` / `requirements.txt`.
- **Detection, Go:** `go.mod` with `github.com/dgraph-io/ristretto/v2`, `github.com/maypok86/otter`, `github.com/groupcache/groupcache-go`, `github.com/redis/go-redis/v9`.
- **Detection, Elixir:** `mix.exs` with `:phoenix`, `:cachex`, `:nebulex`.
- **NestJS pitfalls:**
  - TTL units changed between cache-manager v4 (seconds) and v5+ (milliseconds), a common bug.
  - `CacheInterceptor` keys by URL and ignores auth, so don't apply it globally to authenticated routes without a custom `trackBy`.
- **apicache:** treat it as legacy (little recent maintenance, from knowledge). Recommend an explicit Redis cache-aside or a reverse proxy/CDN instead.
- **Go:** prefer explicit `Cache-Control`/`ETag` headers plus `http.ServeContent` for conditional GETs. Use `singleflight` (`golang.org/x/sync/singleflight`) for stampede protection with any cache.

### Gaps
- No search results covered `@fastify/caching` / `@fastify/etag` current versions, apicache's maintenance status, Cachex's latest API (v4), or Phoenix-specific HTTP caching.
- The NestJS cache-manager v6/v7 version numbers weren't confirmed from official docs.

---

## CMS & commerce: WordPress, Drupal, Shopify/Hydrogen, Magento/Adobe Commerce, headless CMSs, webhook revalidation

### Takeaway
- **WordPress:** needs three things added: a page cache (plugin or edge, e.g. Cloudflare APO), a persistent object cache via an `object-cache.php` drop-in (Redis), and OPcache.
- **Drupal:** has the most principled built-in system (cache tags, contexts and max-age bubbling through render arrays; Internal Page Cache; Dynamic Page Cache; BigPipe).
- **Shopify Hydrogen:** exposes explicit sub-request cache strategies (CacheLong/CacheShort/CacheNone/CacheCustom).
- **Magento:** Varnish (on-prem) or Fastly (Cloud) for full-page cache, and Valkey replacing Redis for the app cache in 2.4.8+ patches.
- **Headless CMSs:** put a CDN in front of the content API. Pair it with webhook-driven tag revalidation in the frontend framework.

### Cited Findings
**WordPress**
- WordPress has no built-in persistent backend. A drop-in at `wp-content/object-cache.php` connects `WP_Object_Cache` to Redis; installing Redis alone does nothing. — [Hostinger: object cache](https://www.hostinger.com/tutorials/what-is-object-cache/); [kokil.com.np 2026](https://kokil.com.np/blog/wordpress-object-cache-with-redis-setup)
- With a persistent object cache active, transients are stored in Redis/Memcached instead of `wp_options`; without one they go to the DB. — [belovdigital 2026](https://belovdigital.agency/redis-object-caching/); [Elementor](https://elementor.com/blog/what-is-object-cache-and-how-to-enable-it/)
- The Redis Object Cache plugin (rhubarbgroup) is at 3.0.0 (bundled Predis 2.4.1). It supports Predis, PhpRedis, Relay, replication, Sentinel, cluster, and WP-CLI (`wp redis status`, `wp redis enable`). — [WordPress.org: Redis Object Cache](https://wordpress.org/plugins/redis-cache/); [GitHub rhubarbgroup/redis-cache](https://github.com/rhubarbgroup/redis-cache); [CyberPanel](https://cyberpanel.net/blog/redis-object-cache)
- **Cloudflare APO:**
  - Login, comment-author and WooCommerce session cookies bypass the cache.
  - Plugins that set a unique cookie on first visit (WooCommerce, A/B testing, some analytics) can make every visitor bypass it.
  - Any `Set-Cookie` keeps a page uncached.
  - LSCache and APO conflict if both do full-page caching.
  - Verify with `cf-cache-status`.
  - — [StackHarbor: APO deep config](https://stackharbor.com/en/knowledge-base/wp-cdn-cloudflare-apo-deep-config/); [StackHarbor: cookies cache bypass](https://stackharbor.com/en/knowledge-base/cfops-cookies-cache-bypass/); [WP Rocket: using APO](https://docs.wp-rocket.me/article/1444-using-cloudflare-apo-with-wp-rocket)

**Drupal**
- Render arrays carry `#cache` metadata: tags (invalidation), contexts (variation) and max-age (default permanent; 0 = uncacheable). All three bubble up to the response. — [Drupal.org: Cacheability of render arrays](https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays)
- Internal Page Cache (anonymous users) has one setting, "Page cache maximum age", which sets the Cache-Control max-age. That system-wide value applies to all anonymous responses unless code overrides it. — [Lullabot: max-age pitfalls](https://www.lullabot.com/articles/common-max-age-pitfalls-with-drupal-cache); [QED42](https://www.qed42.com/insights/mastering-page-and-block-caching-in-drupal)
- Dynamic Page Cache caches the page minus personalized parts, which are placeholdered. A child with max-age 0 can stop the page from being cached. The debug headers are `X-Drupal-Cache-Tags`, `X-Drupal-Cache-Contexts` and `X-Drupal-Cache-Max-Age`. — [weeklydrupal](https://weeklydrupal.com/blog/caching-system-dynamic-page-cache); [drupalatyourfingertips](https://www.drupalatyourfingertips.com/caching)
- BigPipe: auto-placeholdering swaps overly dynamic content (`#lazy_builder` + `#create_placeholder`) for placeholders and streams them via chunked transfer encoding after the skeleton is sent. A placeholder fix (#3564880) landed in 11.x / 11.3.x. — [Droptica: BigPipe lazy builders](https://droptica.com/blog/drupal-bigpipe-using-lazy-builders-2023); [drupal.org #3564880](https://www.drupal.org/i/3564880); [drupal.org #3441137](https://www.drupal.org/project/drupal/issues/3441137)

**Shopify Hydrogen**
- **CacheLong** is `max-age=3600, stale-while-revalidate=82800` (1 hour fresh plus 23 hours SWR), and the values are "subject to change". **CacheShort** totals 10 seconds. **CacheNone** is for carts and other per-user data. Storefront queries get a default cache automatically. — [Hydrogen CacheLong API](https://shopify.dev/docs/api/hydrogen/latest/utilities/caching/cachelong); [Hydrogen caching guide](https://shopify.dev/docs/storefronts/headless/hydrogen/caching); [Hydrogen data loading](https://shopify.dev/docs/storefronts/headless/hydrogen/performance/data-loading)
- Third-party API data uses `withCache` (e.g. `withCache(key, storefront.CacheLong(), fn)`). Choosing a strategy dynamically based on response data was discussed in the community. — [Hydrogen: caching third-party data](https://shopify.dev/docs/storefronts/headless/hydrogen/caching/third-party); [Hydrogen discussion #2558](https://github.com/Shopify/hydrogen/discussions/2558)

**Magento / Adobe Commerce**
- On-prem uses Varnish for full-page cache; Cloud uses Fastly with no separate Varnish. FPC is configured separately from the app (low-level) cache. — [Experience League: Cache options](https://experienceleague.adobe.com/en/docs/commerce-operations/configuration-guide/cache/cache-options); [Caching overview](https://experienceleague.adobe.com/en/docs/commerce-operations/configuration-guide/cache/caching-overview)
- The Adobe Commerce 2.4.8 release notes list Varnish 7.6.x; a third-party page for 2.4.8-p5 lists Varnish 8. These conflict, so check the system requirements for your patch level. — [Adobe Commerce 2.4.8 release notes](https://experienceleague.adobe.com/en/docs/commerce-operations/release/notes/adobe-commerce/2-4-8?lang=en); contradicted by [magento.watch 2.4.8-p5](https://magento.watch/versions/magento-commerce/2.4.8-p5)
- Redis isn't supported in 2.4.9 or in later patches of 2.4.5–2.4.8; Valkey replaces it for the app cache and sessions. — [Experience League: Valkey/Redis best practices](https://experienceleague.adobe.com/en/docs/commerce-operations/implementation-playbook/best-practices/planning/redis-valkey-service-configuration); [Cache options](https://experienceleague.adobe.com/en/docs/commerce-operations/configuration-guide/cache/cache-options)

**Headless CMS**
- **Sanity:**
  - The API CDN is a stale-while-revalidate cache with about 10-minute (600 s) cache times.
  - Mutations always go to `api.sanity.io`.
  - Drafts and authenticated reads need the live API (`useCdn: false`).
  - The Live CDN uses "Sync Tags" for precise invalidation.
  - Next.js's `revalidate` controls only the Next.js Data Cache, not Sanity's CDN.
  - — [Sanity answers: CDN vs API](https://www.sanity.io/answers/difference-between-api-requests-and-cdn-requests-in-sanity-io-); [Sanity Live CDN](https://www.sanity.io/live-cdn); [contentarchitecture.dev](https://www.contentarchitecture.dev/blog/stale-sanity-content-nextjs-caching-revalidation)
- **Contentful + Next.js 16:**
  - Webhooks on publish/unpublish carry `sys.id`, which works as a cache tag; tag by `sys.id`, not slug, because slugs change.
  - Protect the webhook with a shared secret.
  - `revalidateTag(tag, 'max')` takes a cacheLife profile in Next.js 16; the single-argument form is deprecated.
  - `updateTag` is Server-Action-only, so webhook route handlers must use `revalidateTag`.
  - — [Contentful: Next.js cache components](https://www.contentful.com/blog/nextjs-cache-components/); [Next.js: Revalidating](https://nextjs.org/docs/app/getting-started/revalidating); [danholloran.me](https://danholloran.me/posts/revalidatetag-vs-updatetag-nextjs-split-cache-invalidation-in-two)

**Canonical snippets** (WordPress per [WP Object Cache docs](https://developer.wordpress.org/reference/classes/wp_object_cache/) and [Transients API](https://developer.wordpress.org/apis/transients/); Drupal per [Cache API](https://www.drupal.org/docs/drupal-apis/cache-api); Hydrogen per [shopify.dev](https://shopify.dev/docs/storefronts/headless/hydrogen/caching))
```php
// WordPress
$data = wp_cache_get('top_posts', 'myplugin');
if (false === $data) { $data = expensive_query(); wp_cache_set('top_posts', $data, 'myplugin', 300); }
set_transient('remote_feed', $feed, HOUR_IN_SECONDS);   // persists in DB if no object cache
$feed = get_transient('remote_feed');
// wp-config.php (Redis Object Cache plugin)
define('WP_REDIS_HOST', '127.0.0.1'); define('WP_CACHE_KEY_SALT', 'site1_'); define('WP_CACHE', true); // WP_CACHE enables advanced-cache.php page-cache drop-in
```
```php
// Drupal render array
$build['list'] = [
  '#theme' => 'item_list', '#items' => $items,
  '#cache' => ['tags' => ['node_list:article'], 'contexts' => ['user.roles', 'url.query_args:page'], 'max-age' => 3600],
];
\Drupal\Core\Cache\Cache::invalidateTags(['node:42']);
$build['cart'] = ['#lazy_builder' => ['mymodule.cart:render', []], '#create_placeholder' => TRUE]; // BigPipe-friendly
```
```ts
// Hydrogen (Remix/React Router loader)
const {product} = await context.storefront.query(PRODUCT_QUERY, {variables, cache: context.storefront.CacheLong()});
const {cart}    = await context.storefront.query(CART_QUERY, {cache: context.storefront.CacheNone()});
const reviews   = await context.withCache(['reviews', handle], CacheCustom({mode: 'public', maxAge: 60, staleWhileRevalidate: 600}), () => fetch(url).then(r => r.json()));
```
```bash
# Magento
bin/magento cache:status; bin/magento cache:clean full_page; bin/magento cache:flush
bin/magento setup:config:set --http-cache-hosts=varnish:6081
bin/magento varnish:vcl:generate --export-version=7 > default.vcl
```

### Inferences
- **Detecting the platform:**
  - **WordPress:** `wp-config.php`, `wp-content/`, `wp-includes/`. Drop-ins `wp-content/object-cache.php` (object cache) and `advanced-cache.php` (page cache). Plugins in `wp-content/plugins/{wp-rocket,w3-total-cache,litespeed-cache,redis-cache}`.
  - **Drupal:** `composer.json` with `drupal/core-recommended`, `web/core/`, `*.info.yml`, `settings.php` (look for `$settings['cache']['default'] = 'cache.backend.redis'`).
  - **Hydrogen:** `package.json` with `@shopify/hydrogen`, plus `server.ts` / `oxygen`.
  - **Magento:** `composer.json` with `magento/product-community-edition` or `magento/magento2-base`, `app/etc/env.php` (check `cache` / `page_cache` / `http_cache_hosts`), `bin/magento`.
  - **Headless:** `@sanity/client`, `next-sanity`, `contentful`, `@strapi/strapi`, `payload` in `package.json`.
- **WordPress layering:**
  1. Edge/page cache (APO, a host's Varnish/Nginx FastCGI cache, or a plugin).
  2. Redis object cache.
  3. OPcache.
  4. A browser asset caching plugin.
  - Use only one full-page-cache layer to avoid double caching and purge mismatch.
- **Drupal pitfall** (well known, consistent with the Lullabot article's framing): Internal Page Cache ignores bubbled max-age and invalidates only via tags. So a block with max-age=60 doesn't make anonymous pages expire after 60 s. Use the Page Cache Kill Switch or tags, or disable Internal Page Cache when relying on a CDN.
- **Shopify Liquid (Online Store 2.0) storefronts:** the platform (Shopify's CDN) manages caching and the merchant can't configure it; only Hydrogen/Oxygen exposes strategies. I found no source for this.

### Gaps
- No current sources on WP Rocket / W3TC / LiteSpeed Cache 2026 versions or features, or on the WordPress Site Health "persistent object cache" check.
- None for Drupal's Redis module specifics, Strapi v5 caching plugins, or Payload CMS caching.
- None for Shopify Liquid platform caching.
- I couldn't confirm Sanity's exact CDN invalidation timing (sources conflict between "seconds" and "up to 10 minutes").

---

## PHP runtime: OPcache, JIT, preloading (plus JVM warm-up interplay)

### Takeaway
OPcache (bytecode cache) is mandatory for any PHP production app, and since PHP 8.5 it is always compiled in. JIT has been off by default since PHP 8.4 (`opcache.jit=disable`). It helps CPU-bound code, not typical I/O-bound web requests, and there are anecdotal miscompile reports in long-lived workers. Preloading (`opcache.preload`) trades deploy complexity for small gains.

### Cited Findings
- Since PHP 8.5, OPcache is always compiled into core and can still be toggled with `opcache.enable` / `opcache.enable_cli`. — [lindevs](https://lindevs.com/opcache-extension-is-always-available-in-php-8-5); [Tideways: PHP 8.5](https://tideways.com/profiler/blog/whats-new-in-php-8-5-in-terms-of-performance-debugging-and-operations)
- The `opcache.jit` default is `disable`; before 8.4.0 it was `tracing`. Per the RFC, JIT is now disabled via `opcache.jit` rather than `opcache.jit_buffer_size=0`, so enabling it now requires both a buffer size and `opcache.jit=tracing` (or `1255`). — [PHP manual: OPcache config](https://www.php.net/manual/en/opcache.configuration.php); [PHP RFC: jit_config_defaults](https://wiki.php.net/rfc/jit_config_defaults)
- php.watch lists the default change under "8.6", which contradicts the manual and RFC. — [php.watch opcache.jit](https://php.watch/codex/opcache.jit) (contradicted by [PHP manual](https://www.php.net/manual/en/opcache.configuration.php))
- An anecdotal report describes tracing-JIT miscompilation in long-lived workers on PHP 8.5. — [GitHub issue (third-party project)](https://github.com/nukipratama/temari/issues/1049)

**Canonical php.ini for production** (per the [PHP manual](https://www.php.net/manual/en/opcache.configuration.php); exact values are typical recommendations, not mandates)
```ini
opcache.enable=1
opcache.memory_consumption=256
opcache.interned_strings_buffer=16
opcache.max_accelerated_files=20000
opcache.validate_timestamps=0      ; prod: requires opcache_reset()/FPM reload on deploy
; JIT (8.4+): both lines required to turn it on
; opcache.jit_buffer_size=64M
; opcache.jit=tracing
; Preloading (FPM only):
; opcache.preload=/var/www/app/preload.php
; opcache.preload_user=www-data
```

### Inferences
- **Detection:** `composer.json` `require.php` constraint; `Dockerfile` `FROM php:8.x-fpm`; `php.ini` / `conf.d/*opcache*.ini`; `opcache_get_status()` output.
- **Recommendations:**
  - Always enable OPcache.
  - Set `validate_timestamps=0` in immutable container deployments (the image is rebuilt on deploy); otherwise use `revalidate_freq`.
  - Leave JIT off unless profiling shows CPU-bound hotspots.
  - Test JIT under Octane, RoadRunner, FrankenPHP or Swoole workers given the miscompile reports.
- **Atomic deploy pitfall:** symlink-swap deploys with `validate_timestamps=0` serve old code until FPM reloads. Use `realpath`-based document roots and reload FPM, or call `opcache_reset()`.
- **JVM/.NET:** JIT warm-up isn't caching, but cold instances after deploy see slower first requests. Combined with cold in-process caches (Caffeine, IMemoryCache, HybridCache L1), this creates a "double cold start", so warm both with a readiness probe or warm-up job before taking traffic. This is synthesis, not sourced.

### Gaps
- I found no current source on PHP preloading's status or benefits in 8.4/8.5, or on JVM CDS/AOT cache (Leyden, JDK 24+ `-XX:AOTCache`) as a warm-up strategy.

---

## REST API caching: cacheable GET design, ETags/conditional requests, 304 handling, pagination, idempotency keys, rate limiting, API gateway caching (AWS API Gateway, Kong, Apigee, Azure APIM)

### Takeaway
Design APIs so reads are GETs with stable, normalized URLs, explicit `Cache-Control`, and validators (ETag/Last-Modified) for cheap 304 revalidation. Gateway caches (AWS API Gateway, Kong, APIM) add a shared layer, but their cache-key configuration decides correctness and tenant isolation. Idempotency keys are a write-safety mechanism, not a cache, and the IETF draft for them expired in April 2026.

### Cited Findings
**AWS API Gateway (REST APIs)**
- Caching is enabled per stage by provisioning a dedicated cache instance. Valid capacities run from 0.5 to 237 GB, and changing capacity deletes all cached data. — [AWS: Cache settings for REST APIs](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html); [AWS Stage API](https://docs.aws.amazon.com/apigateway/latest/api/API_Stage.html)
- The default TTL is 300 s, the maximum 3600 s, and TTL=0 disables caching. Only GET is cached by default; other methods need method-level overrides. Cache keys can include headers, paths and query strings. — [AWS: API Gateway caching](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html)
- **Client invalidation:** a client can invalidate an entry by sending `Cache-Control: max-age=0`, which requires `execute-api:InvalidateCache`. Without "Require authorization" (`requireAuthorizationForCacheControl`), any client can invalidate. `unauthorizedCacheControlHeaderStrategy` takes `FAIL_WITH_403`, `SUCCEED_WITH_RESPONSE_HEADER` or `SUCCEED_WITHOUT_RESPONSE_HEADER`. Cross-account invalidation isn't supported. — [AWS: API Gateway caching](https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-caching.html); [AWS MethodSetting](https://docs.aws.amazon.com/apigateway/latest/api/API_MethodSetting.html)

**Kong and Azure APIM**
- **Kong:**
  - The OSS Proxy Cache plugin supports only an in-memory, per-node strategy; Proxy Caching Advanced (Enterprise) adds Redis.
  - Sources conflict on the edition details.
  - `cache_control: true` honors Cache-Control.
  - `X-Cache-Status` reports Hit/Miss/Refresh/Bypass.
  - Entries can be purged via the Admin API.
  - — [Kong blog: API gateway cache](https://konghq.com/blog/engineering/api-gateway-cache); [wenhan.blog Kong 101](https://wenhan.blog/en/posts/20241206_kong_101_proxy_caching/)
- **Azure APIM:**
  - `cache-lookup` (inbound) plus `cache-store` (outbound); lookup only for GET.
  - Variation via `vary-by-developer`, `vary-by-developer-groups`, `<vary-by-header>`, `<vary-by-query-parameter>`.
  - `cache-store duration` sets the TTL in seconds, and only 200 responses are cached by default.
  - The built-in cache is volatile and shared by all units in the same region.
  - — [Azure APIM cache-lookup](https://learn.microsoft.com/en-us/azure/api-management/cache-lookup-policy); [cache-store](https://learn.microsoft.com/en-nz/azure/api-management/cache-store-policy); [Caching overview](https://learn.microsoft.com/en-us/azure/api-management/caching-overview)

**Idempotency keys and ETags**
- **Idempotency-Key draft:** draft-07 of the Idempotency-Key HTTP header (HTTPAPI WG, Standards Track) expired on 2026-04-18 and was never published as an RFC. Its stated purpose is making non-idempotent POST/PATCH fault-tolerant. — [IETF Datatracker](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/); [draft-07](https://www.ietf.org/archive/id/draft-ietf-httpapi-idempotency-key-header-07.html)
- ETag/If-None-Match yields a 304 with no body when the tags match. — [MDN: ETag](https://developer.mozilla.org/en/docs/Web/HTTP/Headers/ETag)

**Canonical patterns** (HTTP semantics per [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111) / [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110); MDN above)
```http
GET /v1/products?category=shoes&page=2&limit=20
Cache-Control: public, max-age=60, stale-while-revalidate=300
ETag: "p-c3f9-v17"
Vary: Accept, Accept-Encoding

GET /v1/products/123      (revalidation)
If-None-Match: "p-c3f9-v17"
→ 304 Not Modified (no body; client reuses cached representation)

GET /v1/me/orders
Cache-Control: private, no-cache        # browser may store, must revalidate; never shared caches
PUT /v1/products/123
If-Match: "p-c3f9-v17"                  # optimistic concurrency; 412 if changed
POST /v1/payments
Idempotency-Key: 8e03978e-40d5-43e8-bc93-6894a57f9324   # server stores result for replay; NOT a read cache
```

### Inferences
- **Cacheable-GET design rules:**
  - Normalize query parameters (sorted, defaults omitted) so cache keys collapse.
  - Avoid auth in query strings.
  - Put the API version in the path or media type.
  - Return `Vary` for content negotiation.
  - Use `private` for user-scoped data.
  - Use `no-store` for secrets and PII.
  - Use a short `max-age` plus `stale-while-revalidate` for lists.
  - Use long `max-age` + `immutable` only for versioned or content-addressed resources.
- **Pagination:**
  - Cursor-based pages are more cache-stable than offset pages, which shift when items are inserted.
  - Give the first page a short TTL and deeper pages longer TTLs.
  - Include `limit` in the key.
  - Avoid caching "total count" fields with long TTLs.
- **304 handling in clients:**
  - Browsers, URLSession, OkHttp and dio's cache interceptor handle 304s transparently when their HTTP cache is enabled.
  - Custom fetch wrappers that set `If-None-Match` manually must handle the 304 themselves (`fetch` returns status 304 with an empty body only when the app adds validators manually).
- **Rate limiting interplay:**
  - Edge and gateway cache hits typically don't reach the origin rate limiter, so caching effectively raises capacity.
  - Conversely, revalidation (304) requests still count as requests at the gateway or origin.
  - Rate-limit responses (429) must be `no-store` so they're never cached.
- **Gateway cache-key safety:** never cache authenticated responses at a gateway unless the key includes the tenant or user identity (`Authorization` header or claims). AWS's "Require authorization" for invalidation must be on, or clients can force cache misses (a DoS vector).
- **Idempotency keys:** store the request fingerprint and response for about 24 h in Redis or a DB, and return the stored response on retry. Don't confuse this with response caching: reads must not be served from the idempotency store.

### Gaps
- No current Apigee ResponseCache policy details were retrieved (known elements such as `CacheKey`, `ExpirySettings`, `SkipCacheLookup` and `SkipCachePopulation` are from knowledge only, not verified).
- Kong 3.x OSS vs Enterprise plugin capabilities weren't confirmed from official Kong docs.
- I didn't verify whether AWS API Gateway cache hits count toward usage-plan throttling.

---

## GraphQL caching: POST vs HTTP caching, persisted queries/APQ via GET, response caching (Apollo, Yoga), DataLoader, GraphQL CDNs, normalized client caches

### Takeaway
GraphQL's single-endpoint POST defeats URL-keyed HTTP caches. The fixes are:
- GET plus persisted queries or APQ (short hash URLs that CDNs can cache)
- server response caches (Apollo `responseCachePlugin` driven by `@cacheControl` hints; Yoga/Envelop `useResponseCache` with entity-based invalidation)
- gateway or edge caches (Hive Gateway, Grafbase entity caching, Stellate)

DataLoader is a per-request batching and memoization layer, not a shared cache. Apollo Server 4 reached end of life on 2026-01-26, so use Apollo Server 5 (Node 20+).

### Cited Findings
**Apollo Server**
- Apollo Server 4 has been end-of-life since 2026-01-26. Apollo Server 5 is a small upgrade, mainly Node.js v20+ and Express integration import changes, and v3 users can jump straight to v5. — [Apollo: Migrating from AS4](https://apollographql.com/docs/apollo-server/migration)
- Apollo computes the overall policy from the most restrictive field hint and emits it as `Cache-Control`: `max-age` when cacheable, `no-store` otherwise. — [Apollo: Server-side caching](https://www.apollographql.com/docs/apollo-server/performance/caching)
- `responseCachePlugin` (from `@apollo/server-plugin-response-cache`) caches whole responses when every field has a non-zero max-age; cached responses are used only for identical requests. `scope: PRIVATE` keeps a field out of shared caches. `calculateHttpHeaders: false` lets you emit custom headers such as `s-maxage` for CDNs. — [Apollo: Server-side caching](https://www.apollographql.com/docs/apollo-server/performance/caching); [GitHub caching.md](https://github.com/apollographql/apollo-server/blob/main/docs/source/performance/caching.md); [npm](https://www.npmjs.com/package/@apollo/server-plugin-response-cache)
- **APQ:** many CDNs cache only GET, and full queries are too long for comfortable GET URLs. APQ sends a SHA-256 hash, and the client's `useGETForHashedQueries` sends hashed queries as GET so CDNs can cache them. — [Apollo: APQ](https://www.apollographql.com/docs/apollo-server/performance/apq)

**GraphQL Yoga, Hive Gateway, Grafbase, Stellate**
- **Yoga `useResponseCache`:**
  - `session` partitions entries; return null for one global cache, or a user or token ID.
  - `ttl` is the default TTL and `ttlPerType` overrides it (e.g. `{ User: 500 }`).
  - A mutation returning an entity invalidates cached results containing that entity, unless `invalidateViaMutation: false`.
  - Manual invalidation goes through `createInMemoryCache()` + `cache.invalidate([{ typename, id }])` (v4 docs use `type`).
  - — [Yoga: Response caching](https://the-guild.dev/graphql/yoga-server/docs/features/response-caching); [Yoga v4](https://the-guild.dev/graphql/yoga-server/v4/features/response-caching)
- When a result touches several types, the shortest TTL wins. Yoga intentionally prefers ETags over `Cache-Control` max-age so clients revalidate and mutation-based invalidation stays effective. The trade-off is that clients still make a request per call. — [Hive Router RFC #312](https://github.com/graphql-hive/router/issues/312); [Yoga issue #4272](https://github.com/graphql-hive/graphql-yoga/issues/4272)
- Hive Gateway uses a `responseCaching` config key with `session`. Yoga subgraphs use ETags, so the gateway can invalidate on mutation; Apollo subgraphs use Cache-Control TTLs, which can't be invalidated early. — [Hive Gateway: Response caching](https://the-guild.dev/graphql/hive/docs/gateway/other-features/performance/response-caching)
- Grafbase Gateway entity caching caches subgraph requests. Its scope is computed from all headers sent to the subgraph, to prevent cross-user leaks. Storage is memory or Redis, the default TTL is 60 s, and subgraphs can override it. — [Grafbase: Entity caching](https://grafbase.com/docs/gateway/performance/entity-caching); [config](https://grafbase.com/docs/gateway/configuration/entity-cache)
- **Stellate:**
  - Purges in about 150 ms globally across 68 edge locations.
  - Invalidation via TTL, mutation-based, and the Purging API.
  - Maximum 10 MB per cacheable response.
  - The doc pages surfaced were about 1–1.5 years old, so I couldn't verify its status in 2026.
  - — [Stellate: Edge caching](https://stellate.co/graphql-edge-caching); [Limitations](https://stellate.co/docs/graphql-edge-cache/limitations); [Invalidation methods](https://stellate.co/docs/graphql-edge-cache/invalidation/methods); [Purging analytics](https://stellate.co/blog/announcing-purging-analytics)

**Canonical snippets** (per [Apollo caching docs](https://www.apollographql.com/docs/apollo-server/performance/caching), [Yoga docs](https://the-guild.dev/graphql/yoga-server/docs/features/response-caching), [DataLoader README](https://github.com/graphql/dataloader))
```graphql
enum CacheControlScope { PUBLIC PRIVATE }
directive @cacheControl(maxAge: Int, scope: CacheControlScope, inheritMaxAge: Boolean) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION
type Product @cacheControl(maxAge: 300) { id: ID!  name: String!  price: Money @cacheControl(maxAge: 30) }
type Query { me: User @cacheControl(maxAge: 0, scope: PRIVATE) }
```
```ts
// Apollo Server 5
import responseCachePlugin from '@apollo/server-plugin-response-cache';
import { KeyvAdapter } from '@apollo/utils.keyvadapter'; import Keyv from 'keyv';
const server = new ApolloServer({
  typeDefs, resolvers,
  cache: new KeyvAdapter(new Keyv(process.env.REDIS_URL)),          // shared store for APQ + response cache
  plugins: [responseCachePlugin({ sessionId: async ({ request }) => request.http?.headers.get('authorization') ?? null })],
});
// Dynamic hint in a resolver:
// (_, args, ctx, info) => { info.cacheControl.setCacheHint({ maxAge: 60, scope: 'PRIVATE' }); ... }

// Apollo Client APQ over GET
import { createPersistedQueryLink } from '@apollo/client/link/persisted-queries';
import { sha256 } from 'crypto-hash';
const link = createPersistedQueryLink({ sha256, useGETForHashedQueries: true }).concat(httpLink);
```
```ts
// GraphQL Yoga
import { createYoga } from 'graphql-yoga';
import { useResponseCache, createInMemoryCache } from '@graphql-yoga/plugin-response-cache';
const cache = createInMemoryCache();
const yoga = createYoga({ schema, plugins: [useResponseCache({
  session: (req) => req.headers.get('authorization') ?? null,
  ttl: 2_000, ttlPerType: { User: 500 }, cache,
})]});
cache.invalidate([{ typename: 'Product', id: '42' }]);
```
```ts
// DataLoader: per-request batch + memoize (create inside context factory, never global)
const context = () => ({ loaders: { user: new DataLoader(ids => db.users.findByIds(ids)) } });
```

### Inferences
- **Detection:**
  - `package.json` with `@apollo/server` (v5), `apollo-server` (legacy v2/3, upgrade), `graphql-yoga`, `@envelop/response-cache`, `@graphql-hive/gateway`, `@apollo/gateway` / Apollo Router (`router.yaml`), `mercurius` (Fastify), `dataloader`, `@grafbase/*`.
  - Persisted-query manifests (`persisted-query-manifest.json`, `@apollo/generate-persisted-query-manifest`).
  - Client caches: `@apollo/client`, `urql` + `@urql/exchange-graphcache`, `react-relay` (normalized stores keyed by `__typename` + `id`).
- **Recommendation logic:**
  1. Add `@cacheControl` hints, or Yoga TTLs, with `PRIVATE` / session for user data.
  2. Use persisted queries plus GET so the CDN can cache public operations.
  3. Add a server or gateway response cache with mutation- or entity-based invalidation.
  4. Use DataLoader for N+1.
  - Default `maxAge` should be 0. Opt fields in explicitly, because one uncached field makes the whole response uncacheable, which is the safe behavior.
- **Pitfalls:**
  - A global (non-per-request) DataLoader leaks data across users.
  - A response cache without `session`/`sessionId` on authenticated APIs leaks data.
  - Apollo `scope: PRIVATE` combined with a CDN still needs `Cache-Control: private`.
  - Errors in partial responses shouldn't be cached (both Apollo and Yoga skip results with errors by default, from knowledge).
  - Use a trusted-documents / persisted-only mode in production so the cache key space can't be blown up by arbitrary queries.

### Gaps
- I couldn't confirm Stellate's 2026 operating status or the Apollo Router (Rust) entity-caching GA status.
- Apollo Client 4 normalized-cache changes weren't researched (out of scope; referred to briefly).

---

## gRPC / tRPC caching considerations

### Takeaway
Native gRPC runs over HTTP/2 POST, so HTTP caches and CDNs don't cache it. Cache in the server (application cache) or the client, or use Connect RPC's `NO_SIDE_EFFECTS` methods over GET plus `Cache-Control`. tRPC queries can go out as GET and get `Cache-Control` via `responseMeta`, but framework layers such as Next.js App Router can override headers.

### Cited Findings
- **Connect RPC:**
  - Methods with `option idempotency_level = NO_SIDE_EFFECTS;` can be sent as HTTP GET (connect-go 1.7.0+), which makes them cacheable.
  - GET alone doesn't make proxies cache; handlers must set `Cache-Control`.
  - — [Buf blog: Cacheable RPCs in Connect](https://buf.build/blog/introducing-connect-cacheable-rpcs); [Connect Go: GET requests and caching](https://connectrpc.com/docs/go/get-requests-and-caching/); [Connect Node](https://connectrpc.com/docs/node/get-requests-and-caching/)
- **tRPC:**
  - A `responseMeta` callback can return a `cache-control` header for query requests.
  - Users report that Next.js App Router overrides headers set this way.
  - These come from community Discord threads, not official docs.
  - — [tRPC Discord Q&A](https://discord-questions.trpc.io/m/1185251842461028383); [tRPC Discord Q&A 2](https://discord-questions.trpc.io/m/1048337095195893761)

**Canonical snippets** (per [Connect docs](https://connectrpc.com/docs/go/get-requests-and-caching/) and [tRPC caching docs](https://trpc.io/docs/server/caching))
```protobuf
service ProductService {
  rpc GetProduct(GetProductRequest) returns (Product) { option idempotency_level = NO_SIDE_EFFECTS; }
}
```
```ts
// tRPC fetch adapter
responseMeta({ type, errors, ctx }) {
  const allPublic = !ctx?.user;
  if (type === 'query' && errors.length === 0 && allPublic)
    return { headers: new Headers([['cache-control', 's-maxage=60, stale-while-revalidate=300']]) };
  return {};
}
```

### Inferences
- **Detection:**
  - gRPC: `*.proto`, `grpc` / `@grpc/grpc-js` / `google.golang.org/grpc`.
  - Connect: `@connectrpc/connect`, `connectrpc.com/connect`.
  - tRPC: `@trpc/server`, `@trpc/client`.
- **Recommendations:**
  - For gRPC, use an application-level cache-aside (Redis/Caffeine/ristretto) inside handlers, with client-side memoization.
  - Expose public read endpoints via Connect GET or grpc-gateway (REST transcoding) when CDN caching matters.
  - With tRPC, batching (`httpBatchLink`) combines multiple procedures into one URL, which fragments cache keys. Use a non-batched link for cacheable public queries, and never set shared-cache headers on authenticated queries.

### Gaps
- I didn't retrieve official docs on Envoy's HTTP cache filter applied to gRPC, or tRPC v11's `httpBatchLink` GET behavior.

---

## Mobile & native: iOS URLCache/URLSession, Android OkHttp/Retrofit, image caching (SDWebImage, Kingfisher, Coil, Glide), React Native/Expo, Flutter, offline-first local DBs, app-store constraints

### Takeaway
Mobile apps have three cache layers:
1. **HTTP cache:** URLCache, OkHttp `Cache`, dio_cache_interceptor. These honor server headers, so backend `Cache-Control`/`ETag` design matters.
2. **Image caches:** Kingfisher/SDWebImage, Coil/Glide, expo-image, cached_network_image. Each has its own memory and disk tiers and expiry semantics.
3. **Data persistence:** TanStack Query persisters, or local databases such as SQLite, PowerSync, ElectricSQL and WatermelonDB acting as an offline-first cache.

Realm's Atlas Device Sync reached end of life on 2025-09-30, so Realm-sync apps must migrate. Because old app binaries live for months, cache keys and schemas must be versioned with "buster" values.

### Cited Findings
**iOS and Android HTTP caches**
- **iOS URLCache:**
  - The default policy is `.useProtocolCachePolicy` (honors HTTP headers and revalidates).
  - `.returnCacheDataElseLoad` uses cache regardless of age, which is good for offline-first UIs but can serve deleted resources.
  - `.returnCacheDataDontLoad` is strictly offline.
  - `URLCache(memoryCapacity:diskCapacity:directory:)` can be attached per `URLSessionConfiguration`, and only responses that fit the capacity limits are cached.
  - — [tanaschita: URLRequest cache policies](https://tanaschita.com/20221031-managing-cache-when-working-with-urlsession-in-ios/); [cleanor.app: URLSession cache](https://cleanor.app/reference/nsurlsession-cache); [Medium: Mastering URLCache](https://medium.com/@kost9klinov/mastering-urlcache-in-swift-a-deep-dive-into-native-ios-networking-performance-de02683266d6)
- `.reloadRevalidatingCacheData` isn't implemented before iOS 13 / macOS 10.15 / watchOS 6 / tvOS 13 (one source writes "macOS 15"), so older targets need a fallback. Apple forums report cases of URLSession returning shared-cache responses unexpectedly. — [cleanor.app](https://cleanor.app/reference/nsurlsession-cache); [Apple Developer Forums 132356](https://developer.apple.com/forums/thread/132356)
- **OkHttp + Retrofit:**
  - Attach `Cache(File(context.cacheDir, "http_cache"), 10L * 1024 * 1024)` to `OkHttpClient`.
  - Use a network interceptor to inject `Cache-Control` when the server sends none.
  - For offline use, an interceptor rewrites requests to `CacheControl.FORCE_CACHE`. One author says it must be an application interceptor (`addInterceptor`), because network interceptors don't run offline, and sources are inconsistent on this.
  - Retrofit uses whatever `OkHttpClient` it is given.
  - — [Amit Shekhar: OkHttp caching](https://medium.com/@amitshekhar/caching-with-okhttp-interceptor-and-retrofit-180faa853ff5); [outcomeschool](https://outcomeschool.com/blog/caching-with-okhttp-interceptor-and-retrofit); [i-love-coding: How OkHttp cache works](https://i-love-coding.medium.com/how-does-okhttp-cache-works-851d37dd29cd)

**Image caches**
- **Coil 3:** the default `ImageLoader` has a memory and a disk cache with platform-appropriate directories. Customize it once at startup via `SingletonImageLoader.setSafe { ... }`. Coil 2's `ImageLoaderFactory` pattern and the `respectCacheHeaders(false)` option are Coil 2 APIs. — [kmpbits: Coil 3 in CMP](https://www.kmpbits.com/posts/coil3-compose-multiplatform/); [Coil discussion #1248](https://github.com/coil-kt/coil/discussions/1248); [Coil FAQ](https://coil-kt.github.io/coil/faq/)
- **Glide 4.x:** `DiskCacheStrategy.AUTOMATIC` is the default (remote images cached as original DATA, local as transformed RESOURCE). Signatures change the disk cache key for versioning. — [Future Studio: Glide caching](https://futurestud.io/tutorials/glide-how-to-choose-the-best-caching-preference); [Glide wiki: Caching and invalidation (v3)](https://github.com/bumptech/glide/wiki/Caching-and-Cache-Invalidation)
- **Kingfisher:**
  - The default disk expiration is 7 days.
  - Expiry is "refresh when read" (access extends the lifetime); disable it with `.diskCacheAccessExtending(.none)`.
  - Per-request `.diskCacheExpiration` exists, and `cache.diskStorage.config.expiration = .never` disables expiry.
  - These sources cover v5–v7; Kingfisher 8 specifics weren't verified.
  - — [Kingfisher discussion #2087](https://github.com/onevcat/Kingfisher/discussions/2087); [New in Kingfisher 5](https://github.com/onevcat/Kingfisher/wiki/New-In-Kingfisher-5); [Kingfisher discussion #2096](https://github.com/onevcat/Kingfisher/discussions/2096)

**React Native / Expo**
- **expo-image:**
  - `cachePolicy` takes `none`, `disk`, `memory` or `memory-disk`; the official docs list `disk` as the default.
  - A 2026 PR documents that `disk` bypasses the memory cache on Android and iOS, so repeated images render faster with `memory-disk`.
  - The same PR says the default changes to `memory-disk` "in SDK 59".
  - `Image.clearDiskCache()` exists (it resolves `false` on web).
  - There is no TTL, so rotate `cacheKey` to force refresh.
  - — [Expo docs: Image](https://docs.expo.dev/versions/latest/sdk/image/); [expo/expo PR #48843](https://github.com/expo/expo/pull/48843); [expo discussion #36940](https://github.com/expo/expo/discussions/36940)
- **TanStack Query persistence:**
  - Restored caches are discarded on `maxAge` expiry, a `buster` mismatch, or a restore error.
  - The persisted shape is `{timestamp, buster, clientState}`.
  - Set `gcTime` ≥ `maxAge`, which defaults to 24 h.
  - `createAsyncStoragePersister` throttles writes to about one per second.
  - The experimental per-query `createPersister` sets `networkMode: 'offlineFirst'`.
  - — [TanStack: persistQueryClient](https://tanstack.com/query/v5/docs/framework/react/plugins/persistQueryClient); [TanStack: createPersister](https://tanstack.com/query/v5/docs/framework/react/plugins/createPersister)

**Flutter**
- **`dio_cache_interceptor` policies:**
  - `request` (default, honors headers).
  - `refresh` (always network; cache if directives present).
  - `forceCache` (cache every successful GET even without headers).
  - `refreshForceCache` (always network, force store), added in 2.1.1.
  - `noCache`.
  - — [pub.dev CachePolicy](https://pub.dev/documentation/dio_cache_interceptor/latest/dio_cache_interceptor/CachePolicy.html); [changelog](https://pub.dev/packages/dio_cache_interceptor/changelog)
- `cached_network_image` uses `flutter_cache_manager`, customized via `CacheManager(Config(key, stalePeriod: ..., maxNrOfCacheObjects: ...))`. `stalePeriod` is measured from last use and doesn't reliably force refresh; there is an open bug report. — [Qiita](https://qiita.com/sekitaka_1214/items/0d5d5e2588ec342b9b41); [Baseflow #947](https://github.com/Baseflow/flutter_cached_network_image/issues/947)

**Offline-first sync engines**
- **Realm:** Atlas Device Sync reached end of life on 2025-09-30. The on-device Realm database remains open source. MongoDB named AWS AppSync, HiveMQ, Ably and Ditto as alternatives. — [MongoDB Realm docs](https://mongodb.com/docs/realm); [MongoDB forum: EOL notice](https://mongodb.com/community/forums/t/atlas-device-sync-end-of-life-and-deprecation/296687); [realm-js discussion #6884](https://github.com/realm/realm-js/discussions/6884)
- **ElectricSQL:** Electric syncs Postgres "shapes" over a plain HTTP API that CDNs and proxies (Nginx, Caddy, Varnish, Cloudflare, Fastly) can cache. Live mode uses long-polling with a 20 s timeout. One source says Electric 1.0 reached GA in March 2025, as a read-path sync engine. — [Electric HTTP API docs](https://electric-sql.com/docs/api/http); [hysenlabs review](https://hysenlabs.com/projects/electric-sql-electric)
- **PowerSync vs Electric:** PowerSync is characterized as full-duplex with a client-side upload queue, versus Electric's read-path-only shapes. The source is low quality. — [alibaba buying guide (low quality)](https://electronics.alibaba.com/buyingguides/electricsql-guide-local-first-sync-for-developers)

**Canonical snippets** (per [Apple URLCache docs](https://developer.apple.com/documentation/foundation/urlcache), [OkHttp caching docs](https://square.github.io/okhttp/features/caching/), [Coil](https://coil-kt.github.io/coil/), [Expo Image](https://docs.expo.dev/versions/latest/sdk/image/), [TanStack persist](https://tanstack.com/query/v5/docs/framework/react/plugins/persistQueryClient), [dio_cache_interceptor](https://pub.dev/packages/dio_cache_interceptor))
```swift
// iOS
let cache = URLCache(memoryCapacity: 50 * 1024 * 1024, diskCapacity: 250 * 1024 * 1024,
                     directory: FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!.appendingPathComponent("http"))
let config = URLSessionConfiguration.default
config.urlCache = cache
config.requestCachePolicy = .useProtocolCachePolicy
let session = URLSession(configuration: config)
var req = URLRequest(url: url); req.cachePolicy = .returnCacheDataElseLoad   // offline-first screen
```
```kotlin
// Android OkHttp 4/5 + Retrofit
val client = OkHttpClient.Builder()
  .cache(Cache(File(context.cacheDir, "http_cache"), 50L * 1024 * 1024))
  .addInterceptor { chain ->                          // app interceptor: offline fallback
      val req = if (!isOnline()) chain.request().newBuilder().cacheControl(CacheControl.FORCE_CACHE).build() else chain.request()
      chain.proceed(req)
  }.build()
val retrofit = Retrofit.Builder().baseUrl(BASE).client(client).addConverterFactory(...).build()

// Coil 3
SingletonImageLoader.setSafe { ctx -> ImageLoader.Builder(ctx)
  .memoryCache { MemoryCache.Builder().maxSizePercent(ctx, 0.25).build() }
  .diskCache { DiskCache.Builder().directory(ctx.cacheDir.resolve("image_cache").toOkioPath()).maxSizeBytes(256L * 1024 * 1024).build() }
  .build() }
// Glide: Glide.with(v).load(url).signature(ObjectKey(avatarVersion)).diskCacheStrategy(DiskCacheStrategy.AUTOMATIC).into(iv)
```
```tsx
// Expo / React Native
<Image source={{ uri: url, cacheKey: `avatar-${user.id}-${user.avatarVersion}` }} cachePolicy="memory-disk" />
const persister = createAsyncStoragePersister({ storage: AsyncStorage });
const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: 1000 * 60 * 60 * 24 } } });
<PersistQueryClientProvider client={queryClient}
  persistOptions={{ persister, maxAge: 1000 * 60 * 60 * 24, buster: Application.nativeApplicationVersion ?? '' }}>
```
```dart
// Flutter
final options = CacheOptions(store: HiveCacheStore(dir), policy: CachePolicy.request,
  hitCacheOnErrorCodes: [500, 503], maxStale: const Duration(days: 7));
final dio = Dio()..interceptors.add(DioCacheInterceptor(options: options));
CachedNetworkImage(imageUrl: url, cacheKey: '$url?v=$version',
  cacheManager: CacheManager(Config('imgCache', stalePeriod: const Duration(days: 7), maxNrOfCacheObjects: 500)));
```

### Inferences
- **Detection:**
  - **iOS:** `*.xcodeproj` / `Package.swift` / `Podfile` with `Kingfisher`, `SDWebImage`, `Nuke`; `URLCache` usage.
  - **Android:** `build.gradle(.kts)` / `libs.versions.toml` with `com.squareup.okhttp3:okhttp`, `retrofit`, `io.coil-kt.coil3`, `com.github.bumptech.glide`, `androidx.room`.
  - **React Native / Expo:** `package.json` with `expo`, `expo-image`, `react-native-fast-image`, `@tanstack/react-query-persist-client`, `@react-native-async-storage/async-storage`, `react-native-mmkv`, `@nozbe/watermelondb`, `@powersync/react-native`, `@electric-sql/client`, `realm`.
  - **Flutter:** `pubspec.yaml` with `dio_cache_interceptor`, `cached_network_image`, `flutter_cache_manager`, `drift`, `sqflite`, `isar`, `powersync`.
- **Backend-to-mobile contract:** mobile HTTP caches only work if the API sends `Cache-Control` and `ETag`. Recommend that the backend skill emit validators, so mobile clients get cheap 304s on flaky networks.
- **App-store and version-skew constraints:**
  - Old binaries persist for months, so mobile caches can't be "purged" by a deploy.
  - Version cache schemas: a TanStack `buster` tied to the app version, a DB migration version, image `cacheKey`/signature with a content version.
  - Server responses must stay backward-compatible with cached shapes.
  - Use server-driven TTLs (`Cache-Control`) instead of hardcoded client TTLs, so freshness can change without an app release.
  - OTA updates (Expo Updates / EAS Update) can change JS-side cache logic but not native cache configuration.
- **Offline-first:** a local DB (SQLite/Room/Core Data/WatermelonDB/PowerSync/Electric) is the source of truth for the UI and the server is synced. It is a different paradigm from TTL caching, and conflict resolution matters on the write path.
- **Realm users:** keep Realm local-only, or migrate sync to PowerSync, Ditto, Couchbase Lite, etc. There is no official MongoDB successor; one claim that PowerSync is the "successor" came only from a LinkedIn page and is unverified.
- **Image-cache pitfalls:**
  - URL-keyed caches serve stale avatars when the URL is stable but the content changes. Fix with versioned URLs or `cacheKey`/signature.
  - Unbounded disk caches get evicted by the OS (iOS Caches directory; Android `cacheDir` under storage pressure). Don't store must-keep data in caches.

### Gaps
- I didn't verify OkHttp 5.x-specific cache API changes (5.0 stable shipped in 2025, from knowledge).
- Also unverified: Kingfisher 8 and SDWebImage 5.x default expiry (believed 1 week); the current Expo SDK number (the "SDK 59" claim in PR #48843 looks inconsistent with an Oct 2026 timeline of about SDK 55–56); WatermelonDB maintenance status; PowerSync and Electric 2026 versions; Visual Studio App Center / CodePush retirement (believed March 2025, not verified).
