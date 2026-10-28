import { Suspense } from 'react'
import { auth } from '@/lib/auth'

// Personalized: static shell + per-request content streamed into the Suspense hole.
export default function CartPage() {
  return (
    <main>
      <h1>Your cart</h1>
      <Suspense fallback={<p>Loading cart…</p>}>
        <Cart />
      </Suspense>
    </main>
  )
}

async function Cart() {
  const session = await auth()
  return <p>Cart for {session?.user?.email ?? 'guest'}</p>
}
