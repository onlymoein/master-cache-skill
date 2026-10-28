import { cacheLife, cacheTag, revalidateTag } from 'next/cache'
export async function getProduct(id: string) {
  'use cache'
  cacheLife('hours')
  cacheTag(`product:${id}`)
  return { id }
}
export async function onUpdate(id: string) {
  revalidateTag(`product:${id}`)
}
