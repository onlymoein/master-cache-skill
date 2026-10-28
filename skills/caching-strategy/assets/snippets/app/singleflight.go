// L1 (in-process, Otter v2) + single-flight + L2 (Redis) read path.
//
//	go get github.com/maypok86/otter/v2 golang.org/x/sync github.com/redis/go-redis/v9
//
// Builds and passes `go vet` with otter v2.4.0, go-redis v9.23.0 and x/sync v0.24.0 (October 2026).
package cache

import (
	"context"
	"encoding/json"
	"math/rand"
	"time"

	"github.com/maypok86/otter/v2"
	"github.com/redis/go-redis/v9"
	"golang.org/x/sync/singleflight"
)

type Product struct {
	ID      string `json:"id"`
	Version int64  `json:"version"`
	Name    string `json:"name"`
}

type Store struct {
	l1     *otter.Cache[string, *Product]
	rdb    *redis.Client
	group  singleflight.Group
	prefix string // {app}:{env}:v{schema}
	load   func(ctx context.Context, id string) (*Product, error)
}

func NewStore(rdb *redis.Client, prefix string, load func(context.Context, string) (*Product, error)) *Store {
	l1 := otter.Must(&otter.Options[string, *Product]{
		MaximumSize:      10_000,
		ExpiryCalculator: otter.ExpiryWriting[string, *Product](30 * time.Second), // keep L1 short: it drifts per instance
	})
	return &Store{l1: l1, rdb: rdb, prefix: prefix, load: load}
}

func jitter(d time.Duration) time.Duration {
	return time.Duration(float64(d) * (0.9 + 0.2*rand.Float64())) // ±10 %
}

// Get never blocks longer than ctx: waiters leave on ctx.Done(), and a timed-out flight is
// forgotten so the next caller starts a fresh load instead of joining a hung one.
func (s *Store) Get(ctx context.Context, id string) (*Product, error) {
	if p, ok := s.l1.GetIfPresent(id); ok {
		return p, nil
	}
	key := s.prefix + ":product:" + id
	ch := s.group.DoChan(key, func() (any, error) {
		if p, ok := s.l1.GetIfPresent(id); ok { // re-check inside the flight
			return p, nil
		}
		// Use a detached context so one caller's cancellation doesn't fail everyone's load.
		lctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
		defer cancel()
		// redis.Nil is a miss; any other Redis error fails open to the source (and is never cached)
		if raw, err := s.rdb.Get(lctx, key).Bytes(); err == nil {
			var p Product
			if json.Unmarshal(raw, &p) == nil {
				s.l1.Set(id, &p)
				return &p, nil
			}
		}
		p, err := s.load(lctx, id)
		if err != nil {
			return nil, err // never cache errors
		}
		if raw, err := json.Marshal(p); err == nil {
			_ = s.rdb.Set(lctx, key, raw, jitter(10*time.Minute)).Err()
		}
		s.l1.Set(id, p)
		return p, nil
	})
	select {
	case res := <-ch:
		if res.Err != nil {
			return nil, res.Err
		}
		return res.Val.(*Product), nil
	case <-ctx.Done():
		s.group.Forget(key)
		return nil, ctx.Err()
	}
}

// Invalidate after the DB commit. Other instances keep their L1 copy until it expires
// (or broadcast the id over Redis pub/sub and call s.l1.Invalidate on receipt).
func (s *Store) Invalidate(ctx context.Context, id string) error {
	s.l1.Invalidate(id)
	return s.rdb.Del(ctx, s.prefix+":product:"+id).Err()
}
