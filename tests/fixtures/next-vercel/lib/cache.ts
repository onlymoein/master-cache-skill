import Redis from 'ioredis'
import DataLoader from 'dataloader'
import { LRUCache } from 'lru-cache'

const redis = new Redis(process.env.REDIS_URL!)
export const userLoader = new DataLoader(async (ids: readonly string[]) => ids.map((id) => ({ id })))
const local = new LRUCache({})

export async function clearProducts() {
  const keys = await redis.keys('shop:prod:v1:product:*')
  if (keys.length) await redis.del(...keys)
}

export async function put(key: string, value: string) {
  await redis.set(key, value)
}
