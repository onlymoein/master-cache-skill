# Rails (7.1+/8.x): every response gets an explicit Cache-Control. Default is no-store;
# controllers/actions opt in.
#
#   class ApplicationController < ActionController::Base
#     include CacheHeaders
#   end
#
#   class ProductsController < ApplicationController
#     cache_policy :public_html, only: :show, tags: ->(c) { ["product:#{c.params[:id]}"] }
#     def show
#       @product = Product.find(params[:id])
#       fresh_when @product, public: false   # ETag/Last-Modified + 304; keep browser policy from here
#     end
#   end
#
#   class AccountsController < ApplicationController
#     cache_policy :personalized
#   end
#
# Policies match assets/policy-defaults.csv. Use the CDN's own header name if needed
# (Cloudflare-CDN-Cache-Control, Surrogate-Control for Fastly).
module CacheHeaders
  extend ActiveSupport::Concern

  POLICIES = {
    fingerprinted: { "Cache-Control" => "public, max-age=31536000, immutable" },
    public_html: {
      "Cache-Control" => "no-cache",
      "CDN-Cache-Control" => "max-age=300, stale-while-revalidate=3600, stale-if-error=86400"
    },
    public_api_volatile: { "Cache-Control" => "no-cache", "CDN-Cache-Control" => "max-age=5, stale-if-error=60" },
    personalized: { "Cache-Control" => "private, no-cache" },
    sensitive: { "Cache-Control" => "no-store" }
  }.freeze

  included do
    after_action :apply_cache_policy
    class_attribute :cache_policies, default: {}
  end

  class_methods do
    def cache_policy(name, only: nil, tags: nil)
      raise ArgumentError, "unknown cache policy #{name}" unless POLICIES.key?(name)
      actions = only ? Array(only).map(&:to_s) : [:all]
      self.cache_policies = cache_policies.merge(actions.to_h { |a| [a, { name: name, tags: tags }] })
    end
  end

  private

  def apply_cache_policy
    entry = cache_policies[action_name] || cache_policies[:all]
    if entry.nil? || !(request.get? || request.head?)
      response.headers["Cache-Control"] = "no-store" # step 0 / default
      return
    end
    headers = POLICIES.fetch(entry[:name])
    shared = headers.key?("CDN-Cache-Control")
    if shared && (request.authorization.present? || response.headers["Set-Cookie"].present? || session_in_use?)
      headers = POLICIES[:personalized] # never shared-cache logged-in or cookie-setting responses
      shared = false
    end
    headers.each { |k, v| response.headers[k] = v }
    if shared && entry[:tags]
      response.headers["Cache-Tag"] = (Array(entry[:tags].call(self)) + ["all"]).join(",")
    end
  end

  # Cookies set through `cookies[...]` are written by middleware after this callback, so they
  # aren't visible here: also keep the CDN rule "bypass when the response has Set-Cookie" on.
  def session_in_use?
    request.session.loaded? && request.session.to_hash.except("session_id", "_csrf_token").any?
  end
end
