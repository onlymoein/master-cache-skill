# Drupal

Last reviewed: 2026-10-27 · Applies to: Drupal 10/11; Internal Page Cache, Dynamic Page Cache, BigPipe; Varnish/Fastly/Cloudflare with Purge modules

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Cacheability metadata
- Version notes
- Verify
- Sources

## When to read this

When the site is Drupal. Drupal has the most complete built-in cache model of any CMS: render arrays carry tags, contexts and max-age that bubble up to the response; keep it intact and propagate tags to the CDN.

## How to detect

`composer.json` with `drupal/core` or `drupal/core-recommended`; `web/core/`, `web/sites/default/settings.php`; modules `page_cache`, `dynamic_page_cache`, `big_pipe`, `purge`, `varnish_purger`, `fastly`, `cloudflare`, `redis`, `memcache`. Response headers `X-Drupal-Cache`, `X-Drupal-Dynamic-Cache`, `X-Drupal-Cache-Tags`, `X-Drupal-Cache-Contexts`, `X-Drupal-Cache-Max-Age` (debug).

## Default recipe

1. Keep Dynamic Page Cache and BigPipe enabled (both default). Enable Internal Page Cache only for anonymous-heavy sites without a reverse proxy/CDN.
2. Put Varnish/Fastly/Cloudflare in front, send cache tags as surrogate keys (Purge + purger module, Fastly module), and purge by tag on entity save.
3. Back the cache bins with Redis/Valkey or Memcached (`redis` module) instead of the database.
4. Set page max-age for proxies in Basic site settings → Performance (`system.performance:cache.page.max_age`); rely on tag purges for freshness.
5. Personalize with lazy builders/placeholders (BigPipe) instead of disabling caching.

```php
// Render array with cacheability metadata
$build['teaser'] = [
  '#theme' => 'node_teaser',
  '#node' => $node,
  '#cache' => [
    'tags' => $node->getCacheTags(),            // ['node:42']
    'contexts' => ['languages:language_interface', 'user.roles'],
    'max-age' => Cache::PERMANENT,
  ],
];

// Per-user bit as a placeholder (doesn't break page caching)
$build['cart'] = [
  '#lazy_builder' => ['my_module.cart_builder:build', []],
  '#create_placeholder' => TRUE,
];

\Drupal\Core\Cache\Cache::invalidateTags(['node:42', 'node_list']);   // custom invalidation
```

```php
// settings.php: Redis cache backend (redis module)
$settings['redis.connection']['host'] = getenv('REDIS_HOST');
$settings['cache']['default'] = 'cache.backend.redis';
$settings['cache_prefix'] = 'site1_prod_';
```

## Rules and gotchas

1. Internal Page Cache (anonymous only) uses a single max-age for all pages and ignores bubbled `max-age`; a block with `max-age: 0` doesn't stop the anonymous page from being cached there. Use Dynamic Page Cache + a proxy for mixed content, or the Page Cache Kill Switch service for pages that must not be cached.
2. Missing cacheability metadata is the top source of stale content: when custom code renders entity data, add its cache tags (`addCacheableDependency()`).
3. Contexts like `user` fragment caches per user; prefer `user.roles` or `user.permissions` where the output allows.
4. `X-Drupal-Cache-Tags` headers can exceed CDN header limits on large pages; purger modules hash or shorten tags; check vendor limits (`references/platforms/*.md`).
5. Disable debug cacheability headers (`http.response.debug_cacheability_headers`) in production.
6. Don't run `drush cr` (rebuild all) as routine invalidation: it empties every bin; invalidate tags instead.

## Cacheability metadata

| Property | Meaning | Examples |
|---|---|---|
| tags | What data the output depends on | `node:42`, `node_list`, `config:system.site`, `user:7` |
| contexts | What request variation it depends on | `url.path`, `url.query_args:page`, `languages`, `user.roles`, `theme` |
| max-age | How long it's valid | `Cache::PERMANENT` (-1), `0` (uncacheable), seconds |

Metadata bubbles from render elements to the page. Dynamic Page Cache caches the page minus highly dynamic parts (auto-placeholdered), and BigPipe streams those placeholders after the cached shell.

## Version notes

- Drupal 10/11 share this model. Drupal 11 requires PHP 8.3+.

<details><summary>Old patterns</summary>

- Drupal 7 `cache_set`/`cache_get` with `CACHE_TEMPORARY` and manual bin clears (no tags).
- Boost module static page caching.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/node/42 | grep -iE 'x-drupal-cache|x-drupal-dynamic-cache|cache-control|age|x-cache'
drush php:eval "\Drupal\Core\Cache\Cache::invalidateTags(['node:42']);" && curl -sI https://example.com/node/42 | grep -i x-drupal
```

## Sources

- [Drupal cache API](https://www.drupal.org/docs/drupal-apis/cache-api)
- [Cacheability of render arrays](https://www.drupal.org/docs/drupal-apis/render-api/cacheability-of-render-arrays)
- [Lullabot: common max-age pitfalls with Drupal cache](https://www.lullabot.com/articles/common-max-age-pitfalls-with-drupal-cache)
- [Weekly Drupal: Dynamic Page Cache](https://weeklydrupal.com/blog/caching-system-dynamic-page-cache)
- [Droptica: BigPipe and lazy builders](https://droptica.com/blog/drupal-bigpipe-using-lazy-builders-2023)
- [QED42: page and block caching in Drupal](https://www.qed42.com/insights/mastering-page-and-block-caching-in-drupal)
- [Purge module](https://www.drupal.org/project/purge)
- [Redis module](https://www.drupal.org/project/redis)
