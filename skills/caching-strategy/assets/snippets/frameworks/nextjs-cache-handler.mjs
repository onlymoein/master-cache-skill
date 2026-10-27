// @ts-check
// Shared Redis-backed cache handler for `'use cache'` / `'use cache: remote'` (Next.js 16,
// Cache Components) when several instances serve one app (Kubernetes, autoscaling, ephemeral disks).
// Interface and tag semantics follow the cacheHandlers docs bundled with next@16.4
// (node_modules/next/dist/docs/01-app/03-api-reference/05-config/01-next-config-js/cacheHandlers.md)
// and the built-in handler's tag manifest. Re-check those docs when upgrading Next.
//
// next.config.js
//   module.exports = {
//     cacheComponents: true,
//     cacheHandlers: {
//       default: require.resolve('./cache-handlers/redis.mjs'),
//       remote: require.resolve('./cache-handlers/redis.mjs'),
//     },
//     // ISR, Route Handlers, fetch/unstable_cache and image optimization use the singular
//     // `cacheHandler` (different interface); multi-instance apps need both.
//   }
//
// Rules this handler follows:
//   - get() never throws (an exception becomes a render error); it returns undefined instead
//   - the entry value is a single-read stream: consumed once in set(), re-wrapped on every get()
//   - eviction is ours: Redis TTL = entry.expire (Next never deletes from the store)
//   - tags: `expired` (immediate: updateTag, revalidateTag(tag, { expire: 0 })) makes older
//     entries a miss; `stale` (revalidateTag(tag, 'max')) serves them with revalidate: -1 so
//     Next refreshes in the background
//   - all instances must share one build ID / deploymentId

import { createClient } from 'redis'

/** @typedef {import('next/cache').CacheHandler} CacheHandler */
/** @typedef {{ stale?: number, expired?: number }} TagState */

const PREFIX = process.env.NEXT_CACHE_PREFIX ?? 'next:prod:v1'
const client = createClient({ url: process.env.REDIS_URL })
client.on('error', (/** @type {Error} */ err) => console.error('[cache-handler] redis error:', err.message))
const ready = client.connect().catch(() => undefined)

/** @param {string} k */
const entryKey = (k) => `${PREFIX}:entry:${k}`
/** @param {string} t */
const tagKey = (t) => `${PREFIX}:tag:${t}`

/** @param {string[]} tags @returns {Promise<TagState[]>} */
async function readTags(tags) {
  if (tags.length === 0) return []
  const rows = await Promise.all(tags.map((t) => client.hGetAll(tagKey(t))))
  return rows.map((row) => ({
    stale: row.stale ? Number(row.stale) : undefined,
    expired: row.expired ? Number(row.expired) : undefined,
  }))
}

/** @type {CacheHandler} */
const handler = {
  async get(cacheKey, softTags) {
    try {
      await ready
      const raw = await client.get(entryKey(cacheKey))
      if (!raw) return undefined
      const stored = JSON.parse(raw)
      const now = Date.now()
      let stale = false
      for (const state of await readTags([...stored.tags, ...softTags])) {
        if (state.expired !== undefined && state.expired <= now && state.expired > stored.timestamp) return undefined
        if (state.stale !== undefined && state.stale > stored.timestamp) stale = true
      }
      const bytes = Buffer.from(stored.value, 'base64')
      return {
        ...stored,
        revalidate: stale ? -1 : stored.revalidate,
        value: new ReadableStream({
          start(controller) {
            controller.enqueue(new Uint8Array(bytes))
            controller.close()
          },
        }),
      }
    } catch {
      return undefined
    }
  },

  async set(cacheKey, pendingEntry) {
    try {
      await ready
      const entry = await pendingEntry
      const bytes = Buffer.from(await new Response(entry.value).arrayBuffer()) // consume once
      const ttl = Math.max(1, Math.ceil(entry.expire)) // seconds; Redis evicts at hard expiry
      await client.set(entryKey(cacheKey), JSON.stringify({ ...entry, value: bytes.toString('base64') }), { EX: ttl })
    } catch {
      // best effort: a failed write is a future miss, never an error for the user
    }
  },

  // get() reads tag state from Redis directly, so there is nothing to sync per request.
  async refreshTags() {},

  async getExpiration(tags) {
    try {
      await ready
      const states = await readTags(tags)
      return Math.max(0, ...states.map((s) => Math.max(s.expired ?? 0, s.stale ?? 0)))
    } catch {
      return 0
    }
  },

  async updateTags(tags, durations) {
    try {
      await ready
      const now = Date.now()
      const multi = client.multi()
      for (const tag of tags) {
        if (durations) {
          multi.hSet(tagKey(tag), 'stale', String(now)) // serve while refreshing
          if (durations.expire !== undefined) multi.hSet(tagKey(tag), 'expired', String(now + durations.expire * 1000))
        } else {
          multi.hSet(tagKey(tag), 'expired', String(now)) // immediate
        }
      }
      await multi.exec()
      // If a CDN you run caches these pages, purge it here or in the webhook that called revalidateTag.
    } catch {
      // the TTL backstop still applies
    }
  },
}

export default handler
