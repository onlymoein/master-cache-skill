# Magento / Adobe Commerce

Last reviewed: 2026-10-27 · Applies to: Magento Open Source / Adobe Commerce 2.4.x; Varnish (on-prem), Fastly (Adobe Commerce Cloud), Valkey/Redis

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Cache types
- Version notes
- Verify
- Sources

## When to read this

When the store is Magento or Adobe Commerce. Magento has full-page cache with tag-based purge built in; production must use Varnish or Fastly for the FPC and Valkey/Redis for the backend cache and sessions.

## How to detect

`composer.json` with `magento/product-community-edition` or `magento/product-enterprise-edition`; `bin/magento`; `app/etc/env.php` (cache backends, `http_cache_hosts`), `app/etc/config.php`; `.magento.app.yaml`/`.magento/services.yaml` (Adobe Commerce Cloud). Response headers `X-Magento-Cache-Debug`, `X-Magento-Tags` (developer mode), `X-Cache` (Fastly), `Fastly-Debug`.

## Default recipe

1. **Full-page cache:** Varnish on-prem (Stores → Configuration → Advanced → System → Full Page Cache → Varnish), or Fastly on Adobe Commerce Cloud. Generate the VCL from Magento, don't hand-write it.
2. **Backend cache + sessions:** Valkey (2.4.9 and later security patches of 2.4.5–2.4.8 support it) or Redis; separate databases/instances for cache, page cache (if not Varnish) and sessions.
3. **Purge:** Magento sends `PURGE` with `X-Magento-Tags-Pattern` to `http_cache_hosts` on entity save; keep that path working and authenticated.
4. **Private content** (cart, customer name, wishlist) loads via customer-data sections (`customer/section/load`), never via FPC.

```bash
bin/magento config:set system/full_page_cache/caching_application 2      # 2 = Varnish
bin/magento varnish:vcl:generate --export-version=7 --output-file=default.vcl
bin/magento setup:config:set --http-cache-hosts=varnish:6081
bin/magento setup:config:set --cache-backend=redis --cache-backend-redis-server=valkey --cache-backend-redis-db=0
bin/magento setup:config:set --page-cache=redis --page-cache-redis-server=valkey --page-cache-redis-db=1   # only if not Varnish
bin/magento setup:config:set --session-save=redis --session-save-redis-host=valkey --session-save-redis-db=2
bin/magento cache:status
bin/magento cache:clean full_page      # by type; prefer clean over flush
```

## Rules and gotchas

1. The built-in (file/Redis) FPC is for development; production uses Varnish or Fastly.
2. Check the supported Varnish version for your Magento patch release (sources disagree between 7.6 and 8); generate VCL for that version.
3. `cache:flush` empties the whole storage (including other apps' keys on shared Redis); `cache:clean` removes only Magento-tagged entries. Prefer `clean` or tag purges.
4. Blocks marked `cacheable="false"` in layout XML make the whole page uncacheable; use private content sections instead.
5. Separate Redis/Valkey databases for cache vs sessions; cache eviction policies must not evict sessions.
6. Varnish purge requests must be restricted to the Magento hosts (ACL in VCL).
7. Reindex and cache warming after large catalog imports; the FPC is cold after a full purge.

## Cache types

| Type | Purpose |
|---|---|
| `config`, `layout`, `block_html`, `collections`, `reflection`, `db_ddl`, `eav`, `customer_notification`, `config_integration`, `config_webservice`, `translate`, `compiled_config`, `graphql_query_resolver_result` | Backend caches (Valkey/Redis) |
| `full_page` | Page cache (Varnish/Fastly in production) |

## Version notes

- Valkey replaces Redis in 2.4.9 and later patches of 2.4.5–2.4.8.

<details><summary>Old patterns</summary>

- Varnish 4/6 VCL exports for older 2.x releases.
- File-system cache backend in production.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://store.example.com/ | grep -iE 'x-magento-cache-debug|x-cache|age|cache-control'
bin/magento cache:status
```

## Sources

- [Commerce caching overview](https://experienceleague.adobe.com/en/docs/commerce-operations/configuration-guide/cache/caching-overview)
- [Commerce cache options](https://experienceleague.adobe.com/en/docs/commerce-operations/configuration-guide/cache/cache-options)
- [Redis/Valkey service configuration best practices](https://experienceleague.adobe.com/en/docs/commerce-operations/implementation-playbook/best-practices/planning/redis-valkey-service-configuration)
- [Adobe Commerce 2.4.8 release notes](https://experienceleague.adobe.com/en/docs/commerce-operations/release/notes/adobe-commerce/2-4-8?lang=en)
- [magento.watch: 2.4.8-p5](https://magento.watch/versions/magento-commerce/2.4.8-p5)
