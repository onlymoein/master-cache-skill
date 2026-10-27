// Next.js 15/16 App Router: browser vs CDN headers from a Route Handler.
// Pages and layouts get their headers from the caching model (see references/frameworks/nextjs.md);
// Route Handlers and proxy.ts set them explicitly.
//
// app/api/products/[id]/route.ts

import { NextResponse, type NextRequest } from 'next/server'

const PUBLIC_CDN = 'max-age=300, stale-while-revalidate=3600, stale-if-error=86400'

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  const product = await getProduct(id) // your data layer ('use cache' + cacheTag(`product:${id}`) under Cache Components)
  if (!product) {
    return NextResponse.json({ error: 'not found' }, {
      status: 404,
      headers: { 'Cache-Control': 'public, max-age=60' }, // short negative caching
    })
  }
  const etag = `"p-${product.id}-v${product.version}"`
  const headers = new Headers({
    'Cache-Control': 'no-cache', // browsers revalidate (cheap 304s)
    // Vercel: Vercel-CDN-Cache-Control; Netlify: Netlify-CDN-Cache-Control;
    // Cloudflare: Cloudflare-CDN-Cache-Control; generic CDNs: CDN-Cache-Control;
    // CloudFront (no CDN-only header): 'Cache-Control: max-age=0, s-maxage=300, ...'
    'CDN-Cache-Control': PUBLIC_CDN,
    'Cache-Tag': `product:${id},all`, // Vercel-Cache-Tag / Netlify-Cache-Tag / Surrogate-Key (Fastly, space-separated)
    ETag: etag,
  })
  if (req.headers.get('if-none-match') === etag) {
    return new NextResponse(null, { status: 304, headers })
  }
  return NextResponse.json(product, { headers })
}

// Personalized handlers (app/api/me/route.ts) never get CDN headers:
//   return NextResponse.json(data, { headers: { 'Cache-Control': 'private, no-cache' } })
// Route files may only export HTTP method handlers and segment config.

// proxy.ts (Next 16; `middleware.ts` before 16): enforce the default for paths that must never
// be shared-cached, whatever the handler set.
//
// import { NextResponse, type NextRequest } from 'next/server'
// export function proxy(req: NextRequest) {
//   const res = NextResponse.next()
//   if (req.nextUrl.pathname.startsWith('/account') || req.nextUrl.pathname.startsWith('/api/me')) {
//     res.headers.set('Cache-Control', 'private, no-store')
//   }
//   return res
// }
// export const config = { matcher: ['/account/:path*', '/api/me/:path*'] }

declare function getProduct(id: string): Promise<{ id: string; version: number } | null>
