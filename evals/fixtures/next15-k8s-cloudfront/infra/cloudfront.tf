resource "aws_cloudfront_distribution" "blog" {
  default_cache_behavior {
    target_origin_id = "k8s-ingress"
    cache_policy_id  = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
  }
}
