// Express (4/5): every response gets an explicit Cache-Control. Default is no-store;
// routes opt in to a named policy. Works the same in Koa/Hono with their header APIs.
//
//   app.use(defaultCacheHeaders)
//   app.get('/products/:id', cachePolicy('publicHtml'), handler)
//   app.get('/account', cachePolicy('personalized'), handler)
//
// Policies match assets/policy-defaults.csv. CDN-targeted headers keep the shared TTL out of
// browsers; change CDN-Cache-Control to the vendor header if you need vendor-specific behavior
// (Cloudflare-CDN-Cache-Control, Vercel-CDN-Cache-Control, Netlify-CDN-Cache-Control,
// Surrogate-Control for Fastly). CloudFront has no CDN-only header: use s-maxage there.

const POLICIES = {
  // decision step 3: versioned URLs only (hash in the file name)
  fingerprinted: { 'Cache-Control': 'public, max-age=31536000, immutable' },
  // public HTML / API that changes on events: browsers revalidate, CDN holds it, purge by tag
  publicHtml: {
    'Cache-Control': 'no-cache',
    'CDN-Cache-Control': 'max-age=300, stale-while-revalidate=3600, stale-if-error=86400',
  },
  publicApiVolatile: {
    'Cache-Control': 'no-cache',
    'CDN-Cache-Control': 'max-age=5, stale-if-error=60',
  },
  // decision step 2: per-user content; browser may store, must revalidate; never shared caches
  personalized: { 'Cache-Control': 'private, no-cache' },
  // decision steps 0 and 1: writes, secrets, payment, auth
  sensitive: { 'Cache-Control': 'no-store' },
}

function defaultCacheHeaders(req, res, next) {
  // Set before the handler runs; route policies and handlers overwrite it.
  res.setHeader('Cache-Control', 'no-store')
  next()
}

function cachePolicy(name, { tags = [] } = {}) {
  const headers = POLICIES[name]
  if (!headers) throw new Error(`unknown cache policy ${name}`)
  return function applyCachePolicy(req, res, next) {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.setHeader('Cache-Control', 'no-store') // step 0: writes are never cached
      return next()
    }
    const shared = 'CDN-Cache-Control' in headers
    // Safety: a request carrying credentials never gets a shared-cache policy.
    if (shared && (req.headers.authorization || req.headers.cookie?.match(/(^|;\s*)(session|sid|auth)[^=]*=/i))) {
      res.setHeader('Cache-Control', 'private, no-cache')
      return next()
    }
    for (const [k, v] of Object.entries(headers)) res.setHeader(k, v)
    if (shared && tags.length) {
      // lowercase entity:id tags plus the constant `all`; header name depends on the CDN
      res.setHeader('Cache-Tag', [...tags, 'all'].join(','))
    }
    // A response that sets a cookie must not be shared-cached.
    const setHeader = res.setHeader.bind(res)
    res.setHeader = (k, v) => {
      if (shared && String(k).toLowerCase() === 'set-cookie') {
        setHeader('Cache-Control', 'private, no-cache')
        res.removeHeader('CDN-Cache-Control')
      }
      return setHeader(k, v)
    }
    next()
  }
}

module.exports = { defaultCacheHeaders, cachePolicy, POLICIES }
