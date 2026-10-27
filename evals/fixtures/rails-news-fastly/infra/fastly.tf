resource "fastly_service_vcl" "news" {
  name = "news"
  domain { name = "news.example.com" }
  backend { address = "origin.news.example.com" name = "origin" }
}
