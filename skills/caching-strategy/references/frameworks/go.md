# Go

Last reviewed: 2026-10-27 · Applies to: net/http, Gin/Echo/Chi/Fiber; Otter v2, Ristretto v2, groupcache-go, golang.org/x/sync/singleflight, go-redis v9

## When to read this

When the backend is Go (`go.mod`). Go has no framework cache: set headers yourself, use an in-process cache plus `singleflight`, and Redis/Valkey for shared data.

## How to detect

`go.mod` with `github.com/maypok86/otter/v2`, `github.com/dgraph-io/ristretto/v2`, `github.com/groupcache/groupcache-go/v3`, `golang.org/x/sync`, `github.com/redis/go-redis/v9`, `github.com/redis/rueidis`, `github.com/eko/gocache`, web frameworks `gin-gonic/gin`, `labstack/echo`, `go-chi/chi`, `gofiber/fiber`.

## Default recipe

```go
// Explicit headers + conditional GET
func productHandler(w http.ResponseWriter, r *http.Request) {
    p, err := products.Get(r.Context(), r.PathValue("id"))   // L1 + singleflight + Redis
    if err != nil { http.Error(w, "unavailable", http.StatusServiceUnavailable); return }
    etag := fmt.Sprintf(`"p-%s-v%d"`, p.ID, p.Version)
    w.Header().Set("Cache-Control", "no-cache")
    w.Header().Set("CDN-Cache-Control", "max-age=300, stale-while-revalidate=3600, stale-if-error=86400")
    w.Header().Set("ETag", etag)
    if match := r.Header.Get("If-None-Match"); match == etag {
        w.WriteHeader(http.StatusNotModified)
        return
    }
    json.NewEncoder(w).Encode(p)
}
```

`http.ServeContent` handles `If-None-Match`/`If-Modified-Since`/`Range` for byte content when you set `ETag` first.

L1 + single-flight: `assets/snippets/app/singleflight.go`.

```go
var g singleflight.Group

func (s *Store) Get(ctx context.Context, id string) (*Product, error) {
    if p, ok := s.l1.GetIfPresent(id); ok { return p, nil }
    v, err, _ := g.Do("product:"+id, func() (any, error) {
        if p, ok := s.l1.GetIfPresent(id); ok { return p, nil }   // re-check inside the flight
        p, err := s.loadFromRedisOrDB(ctx, id)
        if err != nil { return nil, err }                         // never cache errors
        s.l1.Set(id, p)
        return p, nil
    })
    if err != nil { return nil, err }
    return v.(*Product), nil
}
```

## Rules and gotchas

1. Prefer Otter v2 (adaptive W-TinyLFU, loader dedupe, refresh-ahead) for in-process caching. Ristretto v2 is fine if you need cost-based admission, but a `Set` of a new item may be silently dropped (`Wait()` for read-after-set).
2. `singleflight`: one hung loader blocks all waiters. Use `DoChan` + `select` on `ctx.Done()`, and `Forget(key)` on timeout so the next caller retries.
3. groupcache-go (maintained fork, `github.com/groupcache/groupcache-go/v3`) fills each key once across a peer group; it has no versioned values or explicit invalidation, so use it for immutable or versioned keys.
4. Keep L1 TTL short across multiple instances; invalidate via Redis pub/sub or rely on TTL.
5. go-redis: one client per process (it pools); set `PoolSize` with the connection budget in mind. rueidis supports server-assisted client-side caching (RESP3); verify the API for your version.
6. Set `Cache-Control` on every handler, including errors (wrap handlers or use middleware).

## Version notes

- Otter v2 requires Go 1.24+; Ristretto v2 uses generics (Go 1.21+).
- `http.Request.PathValue` with the enhanced `ServeMux` since Go 1.22.

<details><summary>Old patterns</summary>

- `github.com/golang/groupcache` (unmaintained; use groupcache-go).
- Ristretto v0/v1 non-generic API.
- `bigcache`/`freecache` for general use (fine for byte blobs, no admission policy).

</details>

## Verify

```bash
curl -s -o /dev/null -D - http://localhost:8080/products/1 | grep -iE 'cache-control|etag'
go test -race ./...            # single-flight and cache code under the race detector
```

## Sources

- [golang.org/x/sync/singleflight](https://pkg.go.dev/golang.org/x/sync/singleflight)
- [maypok86/otter](https://github.com/maypok86/otter)
- [Ristretto](https://pkg.go.dev/github.com/dgraph-io/ristretto)
- [groupcache-go](https://github.com/groupcache/groupcache-go)
- [net/http ServeContent](https://pkg.go.dev/net/http#ServeContent)
- [go-redis](https://redis.uptrace.dev/)
