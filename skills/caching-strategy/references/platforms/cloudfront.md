# Amazon CloudFront

Last reviewed: 2026-10-27 · Applies to: CloudFront cache policies, origin request policies, Origin Shield, invalidations (path and tag), OpenNext on AWS

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Cache key and TTLs
- Invalidation
- Signed URLs and private content
- OpenNext / SST
- Status headers
- Version notes
- Verify
- Sources

## When to read this

When the app is served through CloudFront (directly, via Amplify, SST/OpenNext, Serverless, or IaC). Vendor-neutral concepts: `references/layers/cdn-concepts.md`.

## How to detect

Terraform `aws_cloudfront_distribution`/`aws_cloudfront_cache_policy`/`aws_cloudfront_origin_request_policy`, CDK `aws-cloudfront`, `serverless.yml`, `sst.config.ts`, `open-next.config.ts`, `amplify.yml`; response headers `x-cache: … from cloudfront`, `x-amz-cf-pop`, `x-amz-cf-id`, `via: … cloudfront`.

## Default recipe

Full Terraform: `assets/snippets/cdn/cloudfront-cache-policy.tf`.

```json
{
  "Name": "html-anon",
  "MinTTL": 0, "DefaultTTL": 300, "MaxTTL": 86400,
  "ParametersInCacheKeyAndForwardedToOrigin": {
    "EnableAcceptEncodingGzip": true, "EnableAcceptEncodingBrotli": true,
    "HeadersConfig":      { "HeaderBehavior": "none" },
    "CookiesConfig":      { "CookieBehavior": "none" },
    "QueryStringsConfig": { "QueryStringBehavior": "whitelist",
                            "QueryStrings": { "Quantity": 2, "Items": ["page", "q"] } }
  }
}
```

- One cache behavior per path class: hashed assets (`CachingOptimized` managed policy is fine), public HTML (policy above, origin sends `s-maxage`), private/API paths (`CachingDisabled` managed policy).
- Origin sends `Cache-Control: no-cache` plus `s-maxage=…, stale-while-revalidate=…, stale-if-error=…` for public HTML (CloudFront reads `s-maxage` within the policy's min/max).
- Enable Origin Shield in the region nearest the origin.

## Rules and gotchas

1. A cache policy with `MinTTL > 0` can override origin `no-cache`, `no-store` and `private`. Use `MinTTL: 0` on any behavior that may serve personalized responses, or route those paths to `CachingDisabled`.
2. Cache policy = what's in the key (and forwarded). Origin request policy = what's forwarded without entering the key. Use the origin request policy for cookies/headers the origin needs but that must not split the cache.
3. Never put session cookies or `Authorization` in the key "to be safe"; route authenticated paths to a non-caching behavior instead.
4. With compression enabled in the cache policy, don't also list `Accept-Encoding` in the origin request policy.
5. Forwarding or keying on all query strings increases misses and origin load; allow-list.
6. Invalidations are billed beyond 1,000 paths/month per account; a wildcard path or a tag counts as one path. Prefer tags or wildcards over long URL lists.
7. Self-hosted frameworks on AWS (OpenNext) still need a CloudFront invalidation after on-demand revalidation; the framework's own cache doesn't purge CloudFront.

## Cache key and TTLs

- Managed `CachingOptimized` (ID `658327ea-f89d-4fab-a63d-7e88639e58f6`): min 1 s, default 86,400 s, max 31,536,000 s; no query strings or cookies in the key; normalized `Accept-Encoding` only. Good for hashed assets, wrong for HTML that might be personalized (min TTL 1 s).
- Headers listed in an origin request policy are forwarded even when the cache policy's `HeaderBehavior` is `none`.
- Legacy `ForwardedValues`/`QueryStringCacheKeys` on behaviors are deprecated in favor of policies.

## Invalidation

```bash
# Path invalidation (wildcard counts as one path)
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/products/*"

# Tag invalidation (April 2026): opt in with CacheTagConfig naming the origin header that carries tags
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "#product:123"
```

- Tag invalidation: distributions without `CacheTagConfig` ignore tag headers; the origin sends comma-separated tags in the configured header; at most 50 tags are stored per object; each tag is billed as one path (shares the 1,000 free paths); not in China regions; distribution tenants use `CreateInvalidationForDistributionTenant`.
- Overage price per path: commonly cited as $0.005 (third-party); check the AWS pricing page.
- Concurrency limits are reported inconsistently; batch and queue invalidations from webhooks.

## Signed URLs and private content

- Signed URLs for individual files or cookie-less clients; signed cookies for many files (HLS segments) or to keep URLs unchanged. Use trusted key groups.
- URLs containing `Expires`, `Policy`, `Signature` or `Key-Pair-Id` are treated as signed. Whether signature params enter the key wasn't verified; keep them out of the cache policy's query allow-list.

## OpenNext / SST

- OpenNext on AWS: S3 incremental cache, DynamoDB tag cache, SQS revalidation queue, plus CloudFront in front. After `revalidateTag`/`revalidatePath`, CloudFront still serves its copy until its TTL or an invalidation: wire an invalidation (or use short `s-maxage` with SWR).
- OpenNext AWS docs state support for "all Next.js 15 features"; confirm Next 16 Cache Components support before relying on it.
- See `references/frameworks/nextjs.md` for the framework side.

## Status headers

`X-Cache: Hit from cloudfront` | `Miss from cloudfront` | `RefreshHit from cloudfront` (revalidated with origin) | `Error from cloudfront` | `LimitExceeded from cloudfront`. `Age` on hits; `X-Amz-Cf-Pop` names the edge. Logs carry `OriginShieldHit`.

## Version notes

- April 2026: tag-based invalidation (`CacheTagConfig`).
- Cache and origin request policies replaced `ForwardedValues`.

<details><summary>Old patterns</summary>

- `ForwardedValues` with `Cookies: all` / `QueryString: true` on every behavior.
- Invalidating `/*` on every deploy instead of hashing assets.

</details>

## Verify

```bash
curl -s -o /dev/null -D - https://d123.cloudfront.net/page | grep -iE 'x-cache|age|cache-control|x-amz-cf-pop'
aws cloudfront get-cache-policy --id "$POLICY_ID" --query 'CachePolicy.CachePolicyConfig.[MinTTL,DefaultTTL,MaxTTL]'
aws cloudfront list-invalidations --distribution-id "$DIST_ID" --max-items 5
```

## Sources

- [CloudFront managed cache policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-managed-cache-policies.html)
- [CloudFront create_cache_policy (boto3)](https://boto3.readthedocs.io/reference/services/cloudfront/client/create_cache_policy.html)
- [CloudFront ForwardedValues (deprecated)](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_ForwardedValues.html)
- [CloudFront invalidation by tags](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/invalidation-by-tags.md)
- [CloudFront paying for invalidation](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/PayingForInvalidation.md)
- [CloudFront signed URLs vs cookies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-choosing-signed-urls-cookies.html)
- [OpenNext AWS caching internals](https://github.com/opennextjs/docs/blob/main/pages/aws/inner_workings/caching.mdx)
