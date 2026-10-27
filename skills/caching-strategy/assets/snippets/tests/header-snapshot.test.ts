// Header snapshot tests per route class: catch caching regressions before they ship.
// Runs with Vitest or Jest against a running server (local, preview deploy or staging):
//   BASE_URL=https://preview.example.com SESSION_COOKIE='session=...' npx vitest run header-snapshot.test.ts
//
// One row per route class from the caching plan (plan.json). Keep expectations in sync with it.

import { describe, expect, it } from 'vitest'

const BASE = process.env.BASE_URL ?? 'http://localhost:3000'
const SESSION = process.env.SESSION_COOKIE // never log its value

type Expect = {
  path: string
  cookie?: boolean
  cacheControl: RegExp // browser Cache-Control
  mustNot?: RegExp // directives that must never appear
  cdnHeader?: [name: string, value: RegExp] // e.g. ['cdn-cache-control', /max-age=\d+/]
  noSetCookie?: boolean
  validator?: boolean // ETag or Last-Modified present
}

const ROUTES: Expect[] = [
  { path: '/', cacheControl: /no-cache|max-age=0/, cdnHeader: ['cdn-cache-control', /max-age=\d+.*stale-if-error/], noSetCookie: true, validator: true },
  { path: '/products/example', cacheControl: /no-cache|max-age=0/, noSetCookie: true, validator: true },
  { path: '/account', cookie: true, cacheControl: /private|no-store/, mustNot: /public|s-maxage/ },
  { path: '/checkout', cookie: true, cacheControl: /no-store/, mustNot: /public|s-maxage|max-age=[1-9]/ },
  { path: '/sw.js', cacheControl: /no-cache|max-age=0/, mustNot: /immutable/ },
  { path: '/robots.txt', cacheControl: /./, mustNot: /immutable/ },
]

async function head(path: string, withCookie = false) {
  const res = await fetch(BASE + path, {
    redirect: 'manual',
    headers: withCookie && SESSION ? { cookie: SESSION } : {},
  })
  return res.headers
}

describe('cache headers per route class', () => {
  for (const r of ROUTES) {
    it(`${r.path}${r.cookie ? ' (logged in)' : ''}`, async () => {
      if (r.cookie && !SESSION) return // needs SESSION_COOKIE
      const h = await head(r.path, r.cookie)
      const cc = h.get('cache-control') ?? ''
      expect(cc, 'explicit Cache-Control on every response').not.toBe('')
      expect(cc).toMatch(r.cacheControl)
      if (r.mustNot) expect(cc).not.toMatch(r.mustNot)
      if (r.cdnHeader) expect(h.get(r.cdnHeader[0]) ?? '').toMatch(r.cdnHeader[1])
      if (r.noSetCookie) expect(h.get('set-cookie'), 'public cacheable page must not set cookies').toBeNull()
      if (r.validator) expect(h.get('etag') ?? h.get('last-modified')).toBeTruthy()
      expect(h.get('vary') ?? '', 'Vary on Cookie/User-Agent fragments shared caches').not.toMatch(/\b(cookie|user-agent)\b/i)
    })
  }

  it('hashed assets are immutable', async () => {
    const html = await (await fetch(BASE + '/')).text()
    const asset = html.match(/(?:src|href)="(\/[^"]+[.-][0-9a-zA-Z_-]{8,}\.(?:js|css))"/)?.[1]
    if (!asset) return // no fingerprinted asset referenced on the home page
    const cc = (await head(asset)).get('cache-control') ?? ''
    expect(cc).toMatch(/max-age=31536000/)
    expect(cc).toMatch(/immutable/)
  })
})
