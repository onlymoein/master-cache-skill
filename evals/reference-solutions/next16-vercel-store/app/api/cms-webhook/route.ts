import { createHmac, timingSafeEqual } from 'node:crypto'
import { revalidateTag } from 'next/cache'

const SECRET = process.env.CMS_WEBHOOK_SECRET ?? ''

function validSignature(body: string, signature: string | null): boolean {
  if (!SECRET || !signature) return false
  const expected = createHmac('sha256', SECRET).update(body).digest('hex')
  const given = signature.replace(/^sha256=/, '')
  return given.length === expected.length && timingSafeEqual(Buffer.from(given), Buffer.from(expected))
}

export async function POST(req: Request) {
  const body = await req.text()
  if (!validSignature(body, req.headers.get('x-signature'))) {
    return Response.json({ ok: false }, { status: 401, headers: { 'Cache-Control': 'no-store' } })
  }
  const { id, slug } = JSON.parse(body) as { id: string; slug?: string }
  revalidateTag(`product:${id}`, 'max') // stale-while-revalidate; Vercel follows the tag at the edge
  if (slug) revalidateTag(`product-slug:${slug}`, 'max') // clears a cached "not found" for new products
  return Response.json({ ok: true }, { headers: { 'Cache-Control': 'no-store' } })
}
