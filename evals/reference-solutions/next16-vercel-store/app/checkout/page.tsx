import { connection } from 'next/server'

// Sensitive: no prerendered shell at all. Renders on every request (private, no-store).
export const instant = false

export default async function Checkout() {
  await connection()
  return <main>Payment form</main>
}
