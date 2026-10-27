import { updateTag } from 'next/cache'
export async function POST() {
  updateTag('user:1')
  return new Response(null, { headers: { 'Cache-Control': 'public, s-maxage=600' } })
}
