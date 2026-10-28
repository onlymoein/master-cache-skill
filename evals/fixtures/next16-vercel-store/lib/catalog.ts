import { prisma } from './db'
// Called on every product page render; ~40 ms per query at p50, 300 ms at p95.
export async function getProduct(slug: string) {
  return prisma.product.findUnique({ where: { slug }, include: { variants: true, reviews: true } })
}
export async function getRelated(categoryId: string) {
  return prisma.product.findMany({ where: { categoryId }, take: 8 })
}
