# Headless CMS (Sanity, Contentful, Strapi, Payload, others)

Last reviewed: 2026-10-27 · Applies to: Sanity (API CDN, Live Content API), Contentful (CDA/CPA, webhooks), Strapi, Payload, Storyblok, Prismic, Hygraph

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Sanity
- Contentful
- Strapi and Payload
- Verify
- Sources

## When to read this

When content comes from a headless CMS and is rendered by a framework (Next.js, Nuxt, Astro, SvelteKit, Remix). The CMS has its own CDN; your framework and CDN add more layers. The plan must say which layer owns freshness and how publish events reach each one.

## How to detect

`package.json` with `@sanity/client`/`next-sanity`/`sanity`, `contentful`/`contentful-management`, `@strapi/strapi` or a Strapi URL env, `payload`/`@payloadcms/*`, `@storyblok/*`, `@prismicio/client`, `graphql-request` pointing at `hygraph.com`; env vars like `SANITY_PROJECT_ID`, `CONTENTFUL_SPACE_ID`, `CONTENTFUL_PREVIEW_TOKEN`.

## Default recipe

1. **Tag each fetch** by entity (`post:{id}`, `type:post`) in the framework cache, with a long TTL backstop.
2. **Publish webhook → route handler** that verifies a secret/signature, maps the payload to tags, and calls the framework invalidation (`revalidateTag`, Nuxt storage removal, CDN purge by tag). Example: `assets/snippets/frameworks/nextjs-cms-webhook-route.ts`.
3. **Drafts/preview bypass every cache** (CMS CDN off, framework cache off, `private, no-store`).
4. **CDN layer** in front of the site purges by the same tags (`references/layers/cdn-concepts.md`).

## Rules and gotchas

1. Count the layers: CMS CDN → framework data cache → full-route cache → CDN → browser. A publish must clear each one or wait out its TTL; the slowest layer sets real freshness.
2. Framework revalidation doesn't clear the CMS's own CDN: Next.js `revalidate` doesn't control Sanity's API CDN, so stale content can be re-fetched right after revalidation. Use the CMS's sync/live features or bypass its CDN for revalidation fetches.
3. Webhook endpoints must verify a secret or signature and be idempotent; retries and reorderings happen. Rate-limit and log them.
4. Map references: when a referenced document changes (author, category), invalidate the documents that embed it (tag by referenced IDs or use the CMS's dependency info).
5. Preview tokens must never reach a cached response or the client bundle.
6. Scheduled publishing needs the same webhook path (publish events at the scheduled time).

## Sanity

- `useCdn: true` serves from the API CDN (cached; about 600 s stale-while-revalidate behavior per Sanity docs); `useCdn: false` for drafts, preview and fetches right after a webhook.
- Live Content API / Sync Tags: responses carry sync tags you can map to framework cache tags; `next-sanity` integrates this with `defineLive`/`sanityFetch`. Prefer it over hand-rolled webhooks on Next.js.
- Perspectives: `published` for production, `previewDrafts`/`drafts` for preview (never cached).

## Contentful

- Content Delivery API (cached CDN) for published content; Content Preview API for drafts (never cached).
- Webhooks on Entry/Asset publish/unpublish; protect with a secret header; map `sys.id` and content type to tags.
- Next.js: tag fetches with `sys.id`, then `revalidateTag(tag, 'max')` in the webhook handler (Next 16 two-argument form; `references/frameworks/nextjs.md`).

## Strapi and Payload

Self-hosted: you own their response caching. Use lifecycle hooks/webhooks (Strapi webhooks, Payload `afterChange` hooks) to purge framework and CDN caches by tag. Their REST/GraphQL APIs aren't CDN-cached by default; add a CDN or app cache only for published, public content. Plugin specifics weren't verified in this skill's research.

## Verify

```bash
# Publish a change, then within the expected propagation time:
curl -s -o /dev/null -D - https://example.com/blog/post-slug | grep -iE 'age|x-cache|cf-cache-status|x-vercel-cache|x-nextjs-cache'
curl -s -X POST https://example.com/api/revalidate -H 'x-webhook-secret: wrong' -o /dev/null -w '%{http_code}\n'   # expect 401
```

## Sources

- [Sanity: API requests vs CDN requests](https://www.sanity.io/answers/difference-between-api-requests-and-cdn-requests-in-sanity-io-)
- [Sanity: Live CDN](https://www.sanity.io/live-cdn)
- [Content Architecture: stale Sanity content with Next.js caching](https://www.contentarchitecture.dev/blog/stale-sanity-content-nextjs-caching-revalidation)
- [Contentful: Next.js Cache Components](https://www.contentful.com/blog/nextjs-cache-components/)
- [Next.js: revalidating](https://nextjs.org/docs/app/getting-started/revalidating)
- [Strapi webhooks](https://docs.strapi.io/cms/backend-customization/webhooks)
- [Payload hooks](https://payloadcms.com/docs/hooks/overview)
