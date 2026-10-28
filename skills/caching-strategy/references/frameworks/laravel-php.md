# Laravel and PHP

Last reviewed: 2026-10-27 · Applies to: Laravel 13 (PHP 8.3+), Laravel 11–12 notes; PHP 8.4/8.5 OPcache; Symfony briefly

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- PHP runtime (OPcache, JIT)
- Symfony
- Version notes
- Verify
- Sources

## When to read this

When the app is Laravel, Symfony or other PHP (`composer.json`). For WordPress, Drupal and Magento see `references/cms/*.md`.

## How to detect

`composer.json` with `laravel/framework`; `artisan` at the root; `config/cache.php`; `CACHE_STORE` env (renamed from `CACHE_DRIVER` in 11). Octane: `laravel/octane` + `config/octane.php`. Response cache package: `spatie/laravel-responsecache`. Symfony: `symfony/framework-bundle`, `config/packages/cache.yaml`. PHP version: `composer.json` `require.php`, Dockerfile `FROM php:8.x-fpm`.

## Default recipe

```php
use Illuminate\Support\Facades\Cache;

$users = Cache::remember('v3:users', 600, fn () => DB::table('users')->get());          // cache-aside
$stats = Cache::flexible('v3:dashboard', [300, 900], fn () => Stats::compute());       // fresh 5 min, stale-while-revalidate to 15 min
Cache::tags(['products', "product:{$id}"])->put("v3:product:{$id}", $product, 3600);   // Redis/Memcached only
Cache::tags(["product:{$id}"])->flush();                                               // on update

$lock = Cache::lock('v3:report:build', 10);                                            // stampede/critical section
if ($lock->get()) { try { /* build */ } finally { $lock->release(); } }

$settings = Cache::memo()->get('settings');   // request-scoped memo over the default store (12.9+)
Cache::touch('session:abc', 3600);            // extend TTL without rewriting (13)
```

```php
// config/cache.php
'default' => env('CACHE_STORE', 'redis'),
'stores' => [
    'redis'    => ['driver' => 'redis', 'connection' => 'cache', 'lock_connection' => 'default'],
    'failover' => ['driver' => 'failover', 'stores' => ['redis', 'database']],   // 12.35+
],
```

```bash
php artisan optimize          # caches config, routes, views, events at deploy
```

## Rules and gotchas

1. The Laravel 11+ skeleton defaults to the `database` store: no extra infrastructure, but it adds DB load and doesn't support tags. Use Redis/Valkey for tags and locks.
2. Tags aren't supported on `file`, `dynamodb` or `database` drivers.
3. `php artisan optimize:clear` (and `cache:clear`) flush the application cache store. Never run them in deploy scripts if that store also holds sessions, locks or rate-limiter counters; use a separate store or prefix-bump.
4. Once config is cached, `env()` outside config files returns null.
5. `Cache::flexible` reportedly stores extra keys per entry; invalidate with `Cache::forget` on the main key and verify it clears metadata, or let it expire.
6. `failover` takes effect only when the default store points at it.
7. Under Octane, singletons and static state persist across requests: accidental in-process caching becomes a cross-request (and cross-user) leak risk. The Octane cache driver (Swoole tables) is per server (details unverified; check Octane docs).
8. Response-cache packages (spatie/laravel-responsecache) must never cache authenticated pages without a per-user cache profile; their current features weren't verified.
9. Set explicit `Cache-Control` per route with middleware (`->middleware('cache.headers:public;max_age=60;etag')` for public routes; `private`/`no-store` for authenticated).

## PHP runtime (OPcache, JIT)

```ini
opcache.enable=1
opcache.memory_consumption=256
opcache.interned_strings_buffer=16
opcache.max_accelerated_files=20000
opcache.validate_timestamps=0     ; immutable containers; reload FPM or opcache_reset() on deploy
; JIT (8.4+ needs both lines to turn it on)
; opcache.jit_buffer_size=64M
; opcache.jit=tracing
```

- OPcache is mandatory in production; from PHP 8.5 it is always compiled in (still toggled by `opcache.enable`).
- JIT defaults to `disable` since 8.4 (one source says 8.6; the PHP manual and RFC say 8.4). Leave it off unless profiling shows CPU-bound hotspots; there are anecdotal miscompile reports in long-lived workers (Octane, RoadRunner, FrankenPHP, Swoole).
- Symlink-swap deploys with `validate_timestamps=0` serve old code until FPM reloads.

## Symfony

Symfony Cache (`cache.app`, PSR-6/16, tag-aware pools) and `HttpCache` reverse proxy with ESI exist; apply the same rules (Redis adapter in production, explicit headers, no shared caching of authenticated responses). Details weren't covered by this skill's research.

## Version notes

- Laravel 11: `CACHE_STORE`, database default store, `Cache::flexible`. 12.9: `Cache::memo()`. 12.35: `failover` driver. 13: `Cache::touch()`; 13.33: tags on the memo store.

<details><summary>Old patterns</summary>

- `CACHE_DRIVER` env name.
- `Cache::rememberForever` for data that changes (use TTL + tags).
- Enabling PHP JIT by setting only `opcache.jit_buffer_size` (8.4+ also needs `opcache.jit`).

</details>

## Verify

```bash
php artisan about | grep -i -E 'cache|config|routes'
php -i | grep -E 'opcache.enable|opcache.jit '
curl -s -o /dev/null -D - https://example.com/ | grep -iE 'cache-control|etag|set-cookie'
```

## Sources

- [Laravel cache](https://laravel.com/docs/12.x/cache)
- [Laravel 13 release (Laravel News)](https://laravel-news.com/laravel-13)
- [Laravel 12.35 failover driver](https://laravel-news.com/laravel-12-35-0)
- [Laravel 12.9 memo cache](https://laravel-news.com/laravel-12-9-0)
- [PHP manual: OPcache configuration](https://www.php.net/manual/en/opcache.configuration.php)
- [PHP RFC: JIT config defaults](https://wiki.php.net/rfc/jit_config_defaults)
- [Symfony Cache component](https://symfony.com/doc/current/components/cache.html)
