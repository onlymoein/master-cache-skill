import { Suspense } from 'react'
import { cookies } from 'next/headers'
import { notFound } from 'next/navigation'
import { getProduct, getRelated } from '@/lib/catalog'

// Prerender the top products; others render on first request and are then cached.
export async function generateStaticParams() {
  return [{ slug: 'red-shoe' }, { slug: 'blue-shoe' }]
}

export default async function ProductPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params
  const product = await getProduct(slug)
  if (!product) notFound()
  const related = await getRelated(product.categoryId)
  return (
    <main>
      <h1>{product.name}</h1>
      {/* The currency cookie is request data: read it outside the cached functions, inside Suspense. */}
      <Suspense fallback={<span>…</span>}>
        <Price usd={product.priceUsd} />
      </Suspense>
      <p>{related.length} related products</p>
    </main>
  )
}

async function Price({ usd }: { usd: number }) {
  const currency = (await cookies()).get('currency')?.value ?? 'USD'
  return <span data-currency={currency}>{new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(usd)}</span>
}
