// Cache-aside with TTL jitter, single-flight, soft/hard TTL (stale-while-revalidate),
// negative caching, timeouts and a simple circuit breaker. Errors are never treated as misses
// that get cached.
//
// Works with any client exposing get/set with PX (ioredis shown). Keys follow
// {app}:{env}:v{schema}:[t:{tenant}:]{entity}:{id}.
//
// Usage:
//   const cache = new CacheAside(redis, { prefix: 'shop:prod:v3' })
//   const product = await cache.get(`product:${id}`, () => db.product.find(id), { softTtlMs: 60_000, hardTtlMs: 600_000 })
//   await cache.delete(`product:${id}`)        // after the DB commit

import type Redis from 'ioredis'

type Envelope<T> = { v: T | null; soft: number; neg?: true }

export interface GetOptions {
  softTtlMs: number          // after this, serve stale and refresh in the background
  hardTtlMs: number          // after this, the entry is gone (stored with PX = hardTtlMs)
  negativeTtlMs?: number     // cache "not found" this long (default 30 s); 0 disables
  loaderTimeoutMs?: number   // give up on the source after this (default 5 s)
}

const NOT_FOUND = Symbol('not-found')
export const notFound = <T>(): T => NOT_FOUND as unknown as T

export class CacheAside {
  private inflight = new Map<string, Promise<unknown>>()
  private failures = 0
  private openUntil = 0

  constructor(
    private redis: Redis,
    private opts: { prefix: string; cacheTimeoutMs?: number; breakerThreshold?: number; breakerOpenMs?: number },
  ) {}

  private key(k: string) {
    return `${this.opts.prefix}:${k}`
  }

  private jitter(ms: number) {
    return Math.round(ms * (0.9 + Math.random() * 0.2)) // ±10 %
  }

  private withTimeout<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const t = setTimeout(() => reject(new Error(`${what} timed out after ${ms} ms`)), ms)
      p.then((v) => { clearTimeout(t); resolve(v) }, (e) => { clearTimeout(t); reject(e) })
    })
  }

  // Cache reads fail open: a cache outage means "go to the source", guarded by the breaker.
  private async readCache<T>(k: string): Promise<Envelope<T> | undefined> {
    if (Date.now() < this.openUntil) return undefined
    try {
      const raw = await this.withTimeout(this.redis.get(k), this.opts.cacheTimeoutMs ?? 50, 'cache get')
      this.failures = 0
      return raw ? (JSON.parse(raw) as Envelope<T>) : undefined
    } catch {
      if (++this.failures >= (this.opts.breakerThreshold ?? 5)) this.openUntil = Date.now() + (this.opts.breakerOpenMs ?? 10_000)
      return undefined
    }
  }

  private async writeCache<T>(k: string, env: Envelope<T>, ttlMs: number) {
    if (Date.now() < this.openUntil) return
    try {
      await this.withTimeout(this.redis.set(k, JSON.stringify(env), 'PX', this.jitter(ttlMs)), this.opts.cacheTimeoutMs ?? 50, 'cache set')
    } catch {
      /* best effort: never fail the request because the cache write failed */
    }
  }

  // One load per key per process; other callers await the same promise (single-flight).
  private load<T>(k: string, loader: () => Promise<T>, o: GetOptions): Promise<T | null> {
    const existing = this.inflight.get(k)
    if (existing) return existing as Promise<T | null>
    const p = (async () => {
      try {
        const value = await this.withTimeout(loader(), o.loaderTimeoutMs ?? 5_000, 'loader')
        if ((value as unknown) === NOT_FOUND || value === null || value === undefined) {
          const neg = o.negativeTtlMs ?? 30_000
          if (neg > 0) await this.writeCache<T>(k, { v: null, soft: Date.now() + neg, neg: true }, neg)
          return null
        }
        await this.writeCache(k, { v: value, soft: Date.now() + o.softTtlMs }, o.hardTtlMs)
        return value
      } finally {
        this.inflight.delete(k)
      }
    })()
    this.inflight.set(k, p)
    return p
  }

  async get<T>(id: string, loader: () => Promise<T>, o: GetOptions): Promise<T | null> {
    const k = this.key(id)
    const hit = await this.readCache<T>(k)
    if (hit) {
      if (Date.now() >= hit.soft && !hit.neg) {
        // stale: serve it now, refresh once in the background (errors keep the stale value)
        void this.load(k, loader, o).catch(() => {})
      }
      return hit.v
    }
    return this.load(k, loader, o) // loader errors propagate: an error is not a miss to cache
  }

  async delete(id: string) {
    await this.redis.del(this.key(id)) // call after the DB transaction commits
  }
}
