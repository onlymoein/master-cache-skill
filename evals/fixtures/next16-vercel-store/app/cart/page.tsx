import { auth } from '@/lib/auth'
export default async function Cart() {
  const session = await auth()
  return <main>Cart for {session?.user?.email}</main>
}
