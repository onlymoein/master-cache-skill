# Elixir and Phoenix

Last reviewed: 2026-10-27 · Applies to: Phoenix, Cachex, Nebulex 3.0, ETS

## When to read this

When the app is Elixir/Phoenix (`mix.exs`). Coverage in this skill's research was light; verify APIs against current hex docs.

## How to detect

`mix.exs` with `:phoenix`, `:cachex`, `:nebulex` (+ `:nebulex_local`, `:nebulex_redis_adapter`, `:decorator`), `:redix`; `mix.lock` for versions.

## Default recipe

```elixir
# Response headers via a plug: default no-store, routes opt in
defmodule MyAppWeb.Plugs.CacheHeaders do
  import Plug.Conn
  def init(opts), do: opts
  def call(conn, _opts) do
    register_before_send(conn, fn conn ->
      case get_resp_header(conn, "cache-control") do
        [] -> put_resp_header(conn, "cache-control", "no-store")
        _ -> conn
      end
    end)
  end
end

# Public route opting in
conn
|> put_resp_header("cache-control", "no-cache")
|> put_resp_header("cdn-cache-control", "max-age=300, stale-while-revalidate=3600")
```

```elixir
# Cachex: fetch with a fallback (one computation per key in-node)
Cachex.fetch(:app_cache, "shop:v3:product:#{id}", fn _key ->
  case Repo.get(Product, id) do
    nil -> {:ignore, nil}
    product -> {:commit, product, expire: :timer.minutes(5)}
  end
end)

Cachex.del(:app_cache, "shop:v3:product:#{id}")   # on update
```

```elixir
# Nebulex 3 decorators (needs :decorator)
use Nebulex.Caching
@decorate cacheable(cache: MyApp.Cache, key: {Product, id}, opts: [ttl: :timer.minutes(5)])
def get_product(id), do: Repo.get(Product, id)

@decorate cache_evict(cache: MyApp.Cache, key: {Product, product.id})
def update_product(product, attrs), do: ...
```

## Rules and gotchas

1. ETS/Cachex caches are per node; in a cluster, invalidate across nodes (Phoenix.PubSub broadcast, Nebulex distributed/multilevel adapters) or keep TTLs short.
2. Don't commit `nil`/error results as data; use `{:ignore, value}` or a short negative TTL.
3. Phoenix Channels/LiveView state is live data: never HTTP-cache it; only the initial static assets and bootstrap.
4. Nebulex 2.x vs 3.x decorator and adapter setup differ; check the version in `mix.lock`.
5. Set `Cache-Control` on every response (plug above), including errors.

## Verify

```bash
curl -s -o /dev/null -D - http://localhost:4000/products/1 | grep -iE 'cache-control|etag'
iex -S mix -e 'IO.inspect Cachex.stats(:app_cache)'
```

## Sources

- [Cachex](https://hexdocs.pm/cachex/)
- [Nebulex](https://hexdocs.pm/nebulex/)
- [Plug.Conn](https://hexdocs.pm/plug/Plug.Conn.html)
