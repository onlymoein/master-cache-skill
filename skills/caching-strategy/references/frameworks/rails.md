# Ruby on Rails

Last reviewed: 2026-10-27 · Applies to: Rails 8.1.x (8.0 security-only since May 2026); Solid Cache, Redis, Memcached (dalli)

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- HTTP caching helpers
- CDN purge on change
- Version notes
- Verify
- Sources

## When to read this

When the app is Rails. Rails caching is key-based expiry: keys embed `cache_key_with_version`, so you rarely delete keys; changed records get new keys and old ones age out.

## How to detect

`Gemfile`/`Gemfile.lock` with `rails`; `config/application.rb`, `bin/rails`. Store: `config.cache_store` in `config/environments/production.rb`. Solid Cache: `solid_cache` gem, `config/cache.yml`, a `cache:` database in `config/database.yml`, `db/cache_schema.rb`. Redis: `redis`/`hiredis-client`; Memcached: `dalli`.

## Default recipe

```ruby
# config/environments/production.rb (Rails 8 default)
config.cache_store = :solid_cache_store
# config.cache_store = :redis_cache_store, { url: ENV["REDIS_URL"] }   # when sub-ms latency matters
```

```yaml
# config/cache.yml
default: &default
  store_options:
    max_age: <%= 60.days.to_i %>
    max_size: <%= 256.megabytes %>
    namespace: <%= Rails.env %>
production:
  database: cache
  <<: *default
```

```erb
<% cache @product do %>                      <%# key = cache_key_with_version + template digest %>
  <%= render @product.variants %>            <%# inner fragments (Russian doll) %>
<% end %>
<%= render partial: "products/product", collection: @products, cached: true %>   <%# multi-read %>
```

```ruby
class Variant < ApplicationRecord
  belongs_to :product, touch: true          # child update bumps parent updated_at → new outer key
end

Rails.cache.fetch([product, "competing_price"], expires_in: 12.hours, race_condition_ttl: 10.seconds) do
  Competitor::API.find_price(product.id)
end

class ArticlesController < ApplicationController
  def show
    @article = Article.find(params[:id])
    fresh_when @article                      # ETag + Last-Modified, 304 when fresh; private by default
  end
end
```

Default headers for every response: `assets/snippets/headers/rails_cache_headers.rb`.

## Rules and gotchas

1. Russian-doll invalidation fails silently without `touch: true` on the child association.
2. Fragment keys must include every variant dimension the fragment shows (locale, currency, role): `cache [@product, I18n.locale, current_user.role]`.
3. `fresh_when`/`expires_in` with `public: true` on personalized pages leaks through CDNs. Use `public: true` only for anonymous, public responses.
4. `race_condition_ttl` serves the stale value briefly while one process regenerates, but doesn't stop cold-cache stampedes (no lock before the first write). Add a lock or single-flight for hot cold keys.
5. Rails treats `.` as a format delimiter: `/account.css` routes to `/account`. A CDN that caches by extension will cache the private page (web cache deception). Origin must send `private`/`no-store` on authenticated routes; restrict CDN caching to asset paths; consider constraining formats on sensitive routes.
6. Rails merges body and query params on GET ("fat GET" poisoning): reject bodies on GET at the edge for cacheable routes.
7. `MemoryStore` is per process (each Puma worker has its own). Use Solid Cache or Redis in production.
8. If Redis backs both the cache and Sidekiq, use separate instances/databases: a cache eviction policy (`allkeys-lru`) must not evict queue data.
9. Solid Cache eviction is FIFO or LRU depending on source (unverified); size `max_size`/`max_age` with headroom. 37signals' Solid Cache grew past 10 TB on disk: the right fit when the working set exceeds affordable RAM.
10. `config.action_dispatch.strict_freshness = true` makes `If-None-Match` win over `If-Modified-Since` (RFC behavior); check whether the app's `load_defaults` enables it.

## HTTP caching helpers

| Helper | Effect |
|---|---|
| `fresh_when(record_or_collection, public: false)` | ETag (`cache_key_with_version`) + Last-Modified (`updated_at`); renders 304 when fresh |
| `stale?(obj)` | Same, as a conditional around rendering |
| `expires_in 5.minutes, public: true` | `Cache-Control: max-age=300, public` (public pages only) |
| `http_cache_forever(public: true)` | For immutable responses |
| `expires_now` | `no-cache` |

Set CDN TTLs separately with `response.headers["CDN-Cache-Control"] = "max-age=300, stale-while-revalidate=3600"` (or the vendor header) on public routes.

## CDN purge on change

A long shared TTL is only safe with event-driven purges. Purge after the transaction commits, from a background job, by surrogate key/tag (Fastly shown; same shape for Cloudflare tags, `references/platforms/*.md`):

```ruby
class ArticlesController < ApplicationController
  def show
    @article = Article.find(params[:id])
    expires_now                                                     # browsers: Cache-Control: no-cache
    response.headers["Surrogate-Control"] = "max-age=86400, stale-while-revalidate=60, stale-if-error=86400"
    response.headers["Surrogate-Key"] = "article-#{@article.id} section-#{@article.section_id} all"
    fresh_when @article                                             # ETag/Last-Modified → 304s
  end
end

class Article < ApplicationRecord
  has_many :comments
  after_commit -> { CdnPurgeJob.perform_later(["article-#{id}", "section-#{section_id}"]) }
end

class Comment < ApplicationRecord
  belongs_to :article, touch: true   # touch runs the article's commit callbacks → purge
end

class CdnPurgeJob < ApplicationJob
  retry_on StandardError, wait: :polynomially_longer, attempts: 5
  def perform(keys)
    uri = URI("https://api.fastly.com/service/#{ENV.fetch('FASTLY_SERVICE_ID')}/purge")
    res = Net::HTTP.post(uri, { surrogate_keys: keys }.to_json,
                         "Fastly-Key" => ENV.fetch("FASTLY_API_TOKEN"), "Fastly-Soft-Purge" => "1",
                         "Content-Type" => "application/json")
    raise "purge failed: #{res.code}" unless res.is_a?(Net::HTTPSuccess)
  end
end
```

- Purge in `after_commit`, never `after_save`: a purge before commit lets the CDN refetch the old row.
- Soft purge keeps serving stale (with `stale-if-error`) if the origin is down; hard purge only for takedowns.
- Measure publish-to-visible time after each change (see Verify).

## Version notes

- Rails 8: Solid Cache default. 8.1: cache store namespace getter/setter. 8.1.2: LocalCache strategy on `MemoryStore`.
- `bin/rails dev:cache` toggles caching in development.

<details><summary>Old patterns</summary>

- `caches_action` / `caches_page` (removed from core; gems only).
- Manual `expire_fragment` sweepers (use key-based expiration).

</details>

## Verify

```bash
bin/rails runner 'p Rails.cache.class; p Rails.cache.fetch("probe", expires_in: 5) { 42 }'
curl -s -o /dev/null -D - https://example.com/articles/1 | grep -iE 'cache-control|etag|last-modified'
curl -s -o /dev/null -D - -H 'Cookie: _app_session=x' https://example.com/account.css | grep -iE 'cache-control|age|x-cache'
# publish-to-visible: update a record, then poll until the CDN serves it
start=$(date +%s); until curl -s https://example.com/articles/1 | grep -q 'NEW TITLE'; do sleep 2; done; echo "$(( $(date +%s) - start )) s"
```

## Sources

- [Rails Guides: Caching with Rails](https://guides.rubyonrails.org/caching_with_rails.html)
- [ActiveSupport::Cache::Store](https://api.rubyonrails.org/classes/ActiveSupport/Cache/Store.html)
- [ActionController::ConditionalGet](https://api.rubyonrails.org/classes/ActionController/ConditionalGet.html)
- [rails/rails#52274 (strict_freshness)](https://github.com/rails/rails/pull/52274)
- [Honeybadger: Rails 8 and Solid Cache](https://www.honeybadger.io/blog/rails-8/)
- [PortSwigger: Gotta cache 'em all (Rails `.` delimiter)](https://portswigger.net/research/gotta-cache-em-all)
- [Kit Engineering: cache stampede and race_condition_ttl](https://engineering.kit.com/2019/10/29/we-built-our-own-cache/)
