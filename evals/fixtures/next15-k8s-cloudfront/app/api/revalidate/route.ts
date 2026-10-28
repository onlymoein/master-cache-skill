import { revalidateTag } from 'next/cache'
export async function POST() {
  revalidateTag('posts')
  return Response.json({ revalidated: true })
}
