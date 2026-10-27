import { cookies } from 'next/headers'
import { getProduct, getRelated } from '@/lib/catalog'

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const currency = (await cookies()).get('currency')?.value ?? 'USD'
  const product = await getProduct(slug)
  const related = await getRelated(product!.categoryId)
  return <main>{product!.name} {currency} {related.length}</main>
}
