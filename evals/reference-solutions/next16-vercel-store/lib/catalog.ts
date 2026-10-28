import { cacheLife, cacheTag } from 'next/cache'
import { prisma } from './db'

// Cached across requests and users: the data doesn't depend on the requester.
export async function getProduct(slug: string) {
  'use cache'
  cacheLife('hours')
  const product = await prisma.product.findUnique({ where: { slug }, include: { variants: true, reviews: true } })
  cacheTag(`product-slug:${slug}`, ...(product ? [`product:${product.id}`, `category:${product.categoryId}`] : []))
  return product
}

export async function getRelated(categoryId: string) {
  'use cache'
  cacheLife('hours')
  cacheTag(`category:${categoryId}`)
  return prisma.product.findMany({ where: { categoryId }, take: 8 })
}
