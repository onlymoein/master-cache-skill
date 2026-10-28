import { revalidateTag } from 'next/cache'
export async function POST(req: Request) {
  const { id } = await req.json()
  revalidateTag(`product-${id}`)
  return Response.json({ ok: true })
}
