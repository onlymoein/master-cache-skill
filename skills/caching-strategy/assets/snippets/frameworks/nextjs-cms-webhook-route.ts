// CMS publish webhook → Next.js tag revalidation (+ optional CDN purge).
// app/api/revalidate/route.ts  (Next.js 16; Route Handlers use revalidateTag, never updateTag)
//
// - Verifies an HMAC signature (or a shared secret header) before doing anything.
// - Idempotent: the same event can arrive twice or out of order.
// - Maps CMS document ids/types to tags: `post:{id}`, `type:post`, plus referencing documents.
// - revalidateTag(tag, 'max') = stale-while-revalidate (recommended for content);
//   use { expire: 0 } only when the next request must block on fresh data.
// - Debounce bursts (bulk publishes) upstream, or batch tags here: CDN purge APIs are rate limited.

import { createHmac, timingSafeEqual } from 'node:crypto'
import { revalidateTag } from 'next/cache'
import { NextResponse, type NextRequest } from 'next/server'

const SECRET = process.env.CMS_WEBHOOK_SECRET ?? ''

function validSignature(body: string, signature: string | null): boolean {
  if (!SECRET || !signature) return false
  const expected = createHmac('sha256', SECRET).update(body).digest('hex')
  const given = signature.replace(/^sha256=/, '')
  return given.length === expected.length && timingSafeEqual(Buffer.from(given), Buffer.from(expected))
}

type CmsEvent = { id: string; type: string; references?: string[] }

function tagsFor(evt: CmsEvent): string[] {
  const tags = new Set<string>([`${evt.type}:${evt.id}`.toLowerCase(), `type:${evt.type}`.toLowerCase()])
  for (const ref of evt.references ?? []) tags.add(ref.toLowerCase()) // e.g. author:42 used by many posts
  return [...tags].slice(0, 50)
}

async function purgeCdn(tags: string[]) {
  // Only needed when a CDN you run caches these pages (Vercel's own CDN follows revalidateTag).
  // Cloudflare soft purge example:
  if (!process.env.CF_ZONE_ID || !process.env.CF_API_TOKEN) return
  await fetch(`https://api.cloudflare.com/client/v4/zones/${process.env.CF_ZONE_ID}/invalidate_cache`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${process.env.CF_API_TOKEN}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ tags }),
  })
}

export async function POST(req: NextRequest) {
  const body = await req.text()
  if (!validSignature(body, req.headers.get('x-signature'))) {
    return NextResponse.json({ ok: false }, { status: 401, headers: { 'Cache-Control': 'no-store' } })
  }
  let evt: CmsEvent
  try {
    evt = JSON.parse(body)
  } catch {
    return NextResponse.json({ ok: false, error: 'bad json' }, { status: 400, headers: { 'Cache-Control': 'no-store' } })
  }
  const tags = tagsFor(evt)
  for (const tag of tags) revalidateTag(tag, 'max')
  await purgeCdn(tags).catch((err) => console.error('CDN purge failed; TTL backstop applies', err))
  return NextResponse.json({ ok: true, tags }, { headers: { 'Cache-Control': 'no-store' } })
}
