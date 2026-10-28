# ASP.NET Core

Last reviewed: 2026-10-27 · Applies to: .NET 10 (LTS); Output Caching (.NET 7+), HybridCache (`Microsoft.Extensions.Caching.Hybrid`), IMemoryCache, IDistributedCache

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- FusionCache
- Version notes
- Verify
- Sources

## When to read this

When the app is ASP.NET Core. Use Output Caching for whole responses and HybridCache for data.

## How to detect

`*.csproj` with `Sdk="Microsoft.NET.Sdk.Web"` and `<TargetFramework>net10.0</TargetFramework>`; `Program.cs` with `WebApplication.CreateBuilder`; packages `Microsoft.Extensions.Caching.Hybrid`, `Microsoft.Extensions.Caching.StackExchangeRedis`, `Microsoft.AspNetCore.OutputCaching.StackExchangeRedis`, `ZiggyCreatures.FusionCache`, `EasyCaching`.

## Default recipe

```csharp
// Output caching (server-side responses) with a shared Redis store and tag eviction
builder.Services.AddOutputCache(o =>
{
    o.AddBasePolicy(b => b.Expire(TimeSpan.FromSeconds(30)));
    o.AddPolicy("Products", b => b.Expire(TimeSpan.FromMinutes(5))
                                  .SetVaryByQuery("page", "sort")
                                  .Tag("products"));
});
builder.Services.AddStackExchangeRedisOutputCache(o => o.Configuration = redisConn);

var app = builder.Build();
app.UseCors();
app.UseRouting();
app.UseOutputCache();                                  // after CORS/routing

app.MapGet("/products", GetProducts).CacheOutput("Products");
app.MapPost("/products", async (Product p, IOutputCacheStore store, CancellationToken ct) =>
{
    await Save(p);
    await store.EvictByTagAsync("products", ct);
    return Results.Created();
});
```

```csharp
// HybridCache (data): L1 memory + L2 Redis, stampede protection, tags
builder.Services.AddStackExchangeRedisCache(o => o.Configuration = redisConn);   // becomes L2
builder.Services.AddHybridCache(o =>
{
    o.MaximumPayloadBytes = 1024 * 1024;
    o.DefaultEntryOptions = new HybridCacheEntryOptions
    {
        Expiration = TimeSpan.FromMinutes(10),          // L2
        LocalCacheExpiration = TimeSpan.FromMinutes(1)  // L1: keep shorter
    };
});

public Task<Product?> Get(int id, HybridCache cache, CancellationToken ct) =>
    cache.GetOrCreateAsync($"shop:v3:product:{id}",
        async token => await db.Products.FindAsync([id], token),
        tags: ["products", $"product:{id}"], cancellationToken: ct).AsTask();

await cache.RemoveByTagAsync($"product:{id}");
```

## Rules and gotchas

1. Output Caching defaults: only 200, only GET/HEAD, never responses that set cookies, never authenticated requests. To cache per user, write a custom policy that varies by user ID (`SetVaryByValue` from the `ClaimsPrincipal`) and never shares across users. Don't just drop the defaults.
2. The in-memory output-cache store is per instance: multi-instance deployments need the Redis store (since .NET 8) or eviction is inconsistent. A custom `IOutputCacheStore` must implement tagging atomically.
3. `EvictByTagAsync` is output-cache only; `RemoveByTagAsync` is HybridCache.
4. Output Caching ignores client `Cache-Control` and controls only the server store; it doesn't set browser/CDN headers for you. Set `Cache-Control`/`CDN-Cache-Control` explicitly (or `[ResponseCache]`) per endpoint.
5. Response Caching middleware is the older header-driven cache that honors client hints; prefer Output Caching for server-side response caching.
6. HybridCache L1 is per node: after an update elsewhere, other nodes serve L1 until `LocalCacheExpiration`. Keep L1 short, or use FusionCache's backplane for cross-node eviction (built-in HybridCache cross-node invalidation wasn't confirmed).
7. Raw `IDistributedCache` stores byte arrays with no stampede protection; `IMemoryCache` is single node without stampede protection. Prefer HybridCache for new code.
8. Don't cache EF entities with change tracking or lazy-loading proxies; cache DTOs.
9. HybridCache rejects payloads above `MaximumPayloadBytes` (1 MB in the docs sample); cache projections instead of large graphs.

## FusionCache

Alternative/implementation of the HybridCache abstraction with fail-safe (serve expired on factory errors), soft/hard timeouts, eager refresh, a backplane for multi-node L1 eviction, and tagging. Pick it when you need fail-safe or cross-node L1 invalidation.

## Version notes

- .NET 7: Output Caching. .NET 8: Redis output-cache store. .NET 9: HybridCache (preview → GA package). .NET 10 LTS current; .NET 11 previews not checked.

<details><summary>Old patterns</summary>

- `[OutputCache]` from classic ASP.NET MVC.
- Response Caching middleware for server-side caching.
- Hand-rolled `IDistributedCache` + JSON helpers with no stampede protection.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://localhost:5001/products | grep -iE 'cache-control|age|etag'
redis-cli --scan --pattern '*products*' | head
```

## Sources

- [Output caching middleware (.NET 10)](https://learn.microsoft.com/en-us/aspnet/core/performance/caching/output?view=aspnetcore-10.0)
- [HybridCache library](https://learn.microsoft.com/aspnet/core/performance/caching/hybrid)
- [Caching in .NET](https://learn.microsoft.com/en-us/dotnet/core/extensions/caching)
- [FusionCache](https://github.com/ZiggyCreatures/FusionCache)
