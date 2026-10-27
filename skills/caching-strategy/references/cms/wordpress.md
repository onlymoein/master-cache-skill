# WordPress and WooCommerce

Last reviewed: 2026-10-27 · Applies to: WordPress 6.x, WooCommerce; Redis Object Cache 3.0, Cloudflare APO, LiteSpeed Cache, WP Rocket, host page caches

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Layers in a WordPress stack
- WooCommerce
- Version notes
- Verify
- Sources

## When to read this

When the site is WordPress (with or without WooCommerce). The main decisions: one page-cache layer, a persistent object cache, and correct bypass rules for logged-in users, commenters and carts.

## How to detect

`wp-config.php`, `wp-content/`, `wp-includes/`; drop-ins `wp-content/object-cache.php` (persistent object cache) and `wp-content/advanced-cache.php` (page cache, enabled by `define('WP_CACHE', true)`); plugins in `wp-content/plugins/` (`redis-cache`, `litespeed-cache`, `wp-rocket`, `w3-total-cache`, `wp-super-cache`, `cloudflare`, `woocommerce`); `composer.json` with `roots/wordpress` (Bedrock). Response headers: `cf-apo-via`, `x-litespeed-cache`, host headers (`x-kinsta-cache`, `x-wpe-*`, `x-cache`).

## Default recipe

1. **One page cache.** Prefer the host's page cache or an edge cache (Cloudflare APO, Fastly, Varnish) over a plugin page cache; never stack two (APO + LiteSpeed Cache page caching conflict, for example).
2. **Persistent object cache** with Redis/Valkey (Redis Object Cache plugin or the host's drop-in).
3. **Bypass rules:** never cache for `wordpress_logged_in_*`, `wp-postpass_*`, `comment_author_*`, `woocommerce_items_in_cart`, `woocommerce_cart_hash`, `wp_woocommerce_session_*`; never cache `/wp-admin/`, `/wp-login.php`, `/cart/`, `/checkout/`, `/my-account/`, `?add-to-cart=`, `/wp-json/` routes that are authenticated, `xmlrpc.php`.
4. **Purge on publish** via the page-cache plugin or host integration (post, term and home/feeds pages).
5. **Static assets:** versioned (`?ver=`) assets get long TTLs; WordPress core appends `ver` to enqueued scripts/styles.

```php
// wp-config.php
define('WP_CACHE', true);                       // enables advanced-cache.php (page-cache plugin)
define('WP_REDIS_HOST', getenv('REDIS_HOST'));
define('WP_REDIS_PREFIX', 'site1:prod:');       // unique per site on shared Redis
define('WP_REDIS_MAXTTL', 86400);               // cap TTLs; transients without expiry otherwise live forever
```

```bash
wp plugin install redis-cache --activate
wp redis enable          # installs the object-cache.php drop-in
wp redis status
wp cache flush           # object cache only
```

## Rules and gotchas

1. Without a persistent object cache, `wp_cache_*` lasts one request; transients fall back to the `wp_options` table (autoloaded rows bloat every request).
2. With a persistent object cache, transients live in Redis and can be evicted any time: code must handle `get_transient()` returning false.
3. Use a unique `WP_REDIS_PREFIX` per site and environment on shared Redis; a flush or key clash otherwise crosses sites.
4. Cloudflare APO bypasses on WordPress/WooCommerce cookies; custom membership plugins with their own cookies need extra bypass rules or they leak logged-in pages.
5. Page caches serve the same HTML to everyone: nonces embedded in cached pages expire (12–24 h); fetch nonce-bearing fragments over AJAX/REST or keep page TTL below the nonce lifetime.
6. Plugins that set cookies for all visitors (A/B testing, GDPR banners, analytics) silently turn page caching off at some layers; audit `Set-Cookie` on anonymous responses.
7. Disable WP-Cron on every page load (`DISABLE_WP_CRON` + system cron) for busy cached sites so scheduled work isn't tied to cache misses.
8. Logged-in admin traffic is never page-cached; the object cache is what speeds up wp-admin.

## Layers in a WordPress stack

| Layer | Typical tool | Notes |
|---|---|---|
| Edge/page | Host page cache, Cloudflare APO, Fastly/Varnish | Pick one; purge on publish |
| Plugin page cache | LiteSpeed Cache (on LiteSpeed servers), WP Rocket, WP Super Cache | Only if no host/edge page cache |
| Object cache | Redis Object Cache, Memcached drop-ins | Persistent `wp_cache_*` + transients |
| Opcode | PHP OPcache | `references/frameworks/laravel-php.md` (PHP runtime section) |
| Browser | `Cache-Control` on assets | Versioned assets long TTL |

## WooCommerce

- Cart, checkout and account pages are personalized: bypass page caches; fetch cart fragments over AJAX (cart fragments script) or the Store API.
- Product and category pages can be page-cached for anonymous visitors when price/stock changes purge them; dynamic pricing by user/role/geo needs bypass or edge personalization.
- Stock and price updates must trigger purges for product, category and shop pages.

## Version notes

- Redis Object Cache 3.0 (2026). WordPress core has no built-in persistent object cache; hosts often ship their own drop-in.

<details><summary>Old patterns</summary>

- W3 Total Cache with database/object caching to disk.
- Multiple page-cache plugins stacked with a CDN page cache.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://example.com/ | grep -iE 'cache-control|age|cf-cache-status|cf-apo-via|x-litespeed-cache|set-cookie'
curl -s -o /dev/null -D - -H 'Cookie: wordpress_logged_in_x=1' https://example.com/ | grep -iE 'cf-cache-status|x-litespeed-cache|age'   # expect BYPASS/MISS
wp redis status
```

## Sources

- [WordPress object cache](https://developer.wordpress.org/reference/classes/wp_object_cache/)
- [Transients API](https://developer.wordpress.org/apis/transients/)
- [Redis Object Cache plugin](https://wordpress.org/plugins/redis-cache/)
- [rhubarbgroup/redis-cache](https://github.com/rhubarbgroup/redis-cache)
- [WP Rocket: using Cloudflare APO with WP Rocket](https://docs.wp-rocket.me/article/1444-using-cloudflare-apo-with-wp-rocket)
- [StackHarbor: Cloudflare APO deep configuration](https://stackharbor.com/en/knowledge-base/wp-cdn-cloudflare-apo-deep-config/)
- [StackHarbor: cookies and cache bypass](https://stackharbor.com/en/knowledge-base/cfops-cookies-cache-bypass/)
