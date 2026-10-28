# CloudFront: one behavior per path class, query strings allow-listed, no cookies in the key.
# AWS provider 5.x/6.x. Check argument names against the provider docs for your version.
#
# Origin headers:
#   public HTML  -> Cache-Control: max-age=0, s-maxage=300, stale-while-revalidate=3600, stale-if-error=86400
#   personalized -> Cache-Control: private, no-cache        (served by the CachingDisabled behavior)
#   hashed asset -> Cache-Control: public, max-age=31536000, immutable
# Keep min_ttl = 0 wherever personalized responses could appear: min_ttl > 0 overrides origin
# no-cache/no-store/private.

resource "aws_cloudfront_cache_policy" "html_anon" {
  name        = "html-anon"
  min_ttl     = 0
  default_ttl = 0     # no Cache-Control from origin => don't cache (explicit headers only)
  max_ttl     = 86400

  parameters_in_cache_key_and_forwarded_to_origin {
    enable_accept_encoding_gzip   = true
    enable_accept_encoding_brotli = true

    cookies_config {
      cookie_behavior = "none"
    }
    headers_config {
      header_behavior = "none"
    }
    query_strings_config {
      query_string_behavior = "whitelist"
      query_strings {
        items = ["page", "q", "sort"]
      }
    }
  }
}

# Forward what the origin needs without adding it to the cache key.
resource "aws_cloudfront_origin_request_policy" "html_anon" {
  name = "html-anon-origin"
  cookies_config {
    cookie_behavior = "none"
  }
  headers_config {
    header_behavior = "whitelist"
    headers {
      items = ["Accept-Language"]
    }
  }
  query_strings_config {
    query_string_behavior = "all"
  }
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "site" {
  enabled = true
  aliases = ["www.example.com"]

  origin {
    domain_name = var.origin_domain
    origin_id   = "app"
    origin_shield {
      enabled              = true
      origin_shield_region = var.origin_region
    }
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  # Hashed assets
  ordered_cache_behavior {
    path_pattern           = "/assets/*"
    target_origin_id       = "app"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
  }

  # Private paths: never cached, everything forwarded
  ordered_cache_behavior {
    path_pattern             = "/account*"
    target_origin_id         = "app"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "app"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  # Public HTML (default)
  default_cache_behavior {
    target_origin_id         = "app"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = aws_cloudfront_cache_policy.html_anon.id
    origin_request_policy_id = aws_cloudfront_origin_request_policy.html_anon.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn = var.acm_certificate_arn
    ssl_support_method  = "sni-only"
  }
}

variable "origin_domain" { type = string }
variable "origin_region" { type = string }
variable "acm_certificate_arn" { type = string }

# Invalidate after deploys or content changes (path-based; tag invalidation exists since 2026-04,
# check the API before relying on it):
#   aws cloudfront create-invalidation --distribution-id $DIST_ID --paths "/products/123" "/"
