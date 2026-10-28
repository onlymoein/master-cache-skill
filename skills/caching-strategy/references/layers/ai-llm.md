# AI and LLM caching

Last reviewed: 2026-10-27 · Applies to: Anthropic Claude API prompt caching, OpenAI prompt caching, Google Gemini implicit/explicit caching, semantic caches (Redis LangCache, RedisVL, GPTCache), embedding and RAG caches

## Contents

- When to read this
- Order of levers
- Rules and gotchas
- Provider prompt caching
- Prompt structure for cache hits
- Exact-match response cache
- Embedding, retrieval and reranker caches
- Semantic caching (last resort)
- Measuring
- Version notes
- Verify
- Sources

## When to read this

When the app calls LLM APIs (detected deps: `@anthropic-ai/sdk`, `anthropic`, `openai`, `@google/genai`, LangChain, LlamaIndex, `ai`/`@ai-sdk/*`, LiteLLM, vector DBs) and cost or latency matters. Provider prices and limits change often: re-check the provider docs before quoting numbers in a plan.

## Order of levers

1. **Provider prompt caching** (prefix KV-cache reuse): largest and safest; no correctness risk.
2. **Exact-match response cache** for deterministic or repeatable calls (templated prompts, retries, identical FAQs).
3. **Embedding cache** keyed by content + model + version: safe, content-addressed.
4. **Retrieval-result and reranker caches** keyed by query, index version, filters.
5. **Tool/API result caches** (third-party lookups the model calls).
6. **Semantic cache** only for public, non-personalized Q&A with strict thresholds and a verifier.

## Rules and gotchas

1. Prompt caching is a byte-exact prefix match. Any change anywhere in the prefix invalidates everything after it. Put stable content first, volatile content last.
2. Silent invalidators: timestamps, request IDs or user names in the system prompt; unsorted JSON (`json.dumps` without `sort_keys=True`, iterating a set); per-user tool lists; conditional system-prompt sections; switching models (caches are model-scoped). Tools render first, so changing them invalidates everything.
3. HTTP layer: LLM responses that contain user content are `private` or `no-store`; streamed responses aren't CDN-cacheable.
4. Cache keys for any response cache include model ID and version, prompt template version, tool schema version, sampling/effort settings and, for RAG, corpus/index version. Personalized answers are keyed by tenant and user, or not cached.
5. Never semantically cache answers that depend on user-specific data, real-time data, or tool side effects.
6. Provider caches are isolated per workspace or organization; traffic split across workspaces writes separate entries.
7. Parallel requests with an identical new prefix all pay full price: an entry becomes readable only once the first response starts streaming. For fan-out, send one request, await the first token, then send the rest.

## Provider prompt caching

| Provider | Mechanism | Economics (verify current pricing) | Notes |
|---|---|---|---|
| Anthropic (Claude API) | Explicit `cache_control: {"type": "ephemeral"}` breakpoints (5 min default; `"ttl": "1h"` for 1 hour), or top-level automatic caching on the request | Writes 1.25× base input (5 min) or 2× (1 h); reads ≈ 0.1× (0.05× on Claude Opus 5.5, 0.025× on Claude Fable 5.1). Break-even: 2 requests (5 min), 3 requests (1 h) | Max 4 breakpoints; each looks back at most 20 positions; minimum cacheable prefix 512–4096 tokens depending on model (shorter prefixes silently don't cache); a read refreshes the TTL; TTL counts from request start; caches per workspace (per org on Bedrock/Google Cloud) |
| OpenAI | Automatic for prompts ≥ 1,024 tokens, matched in 128-token increments | Discounts up to ~90% by model; cache writes free before the GPT-5.6 family, 1.25× from GPT-5.6 on | `prompt_cache_key` improves routing for shared prefixes; `prompt_cache_retention`: `in_memory` (default) or `24h`, same price |
| Google Gemini | Implicit caching on 2.5+ (no storage fee); explicit context caches with TTL (default 1 h) | Implicit discount 90% on 2.5+ (75% on 2.0); explicit caches bill storage per token-hour | Model minimums for explicit caches vary (1,024–4,096); `cached_content_token_count` in usage |

Choosing Anthropic's TTL by the start-to-start gap between requests sharing the prefix: under 5 min → 5-minute TTL (strictly cheaper; each read refreshes it); 5–60 min → 1-hour TTL (or, on models with very cheap reads, a `max_tokens: 0` keep-alive before expiry); over an hour → re-warm on a schedule or accept the miss.

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=16000,
    thinking={"type": "adaptive"},
    output_config={"effort": "medium"},          # pin thinking/effort per route; changing them invalidates the messages cache
    cache_control={"type": "ephemeral"},          # automatic caching for the growing conversation tail
    system=[{
        "type": "text",
        "text": STATIC_SYSTEM_PROMPT,             # frozen: no dates, IDs or user names
        "cache_control": {"type": "ephemeral"},   # guaranteed read point at the end of the shared prefix
    }],
    messages=history + [{"role": "user", "content": question}],
)
u = response.usage
log_metrics(read=u.cache_read_input_tokens, write=u.cache_creation_input_tokens, uncached=u.input_tokens)
```

If the prompt ends in unique per-request content (retrieved rows, a one-off question), skip top-level automatic caching and put one explicit marker at the end of the shared portion; otherwise every request pays the write premium on bytes never read back.

## Prompt structure for cache hits

1. Order: frozen system prompt and deterministic tool list (sorted by name) → long reference documents or few-shot examples → conversation history → the volatile user turn.
2. Inject dynamic context (date, user profile, mode) later in `messages`, not in the system prompt.
3. Don't swap tools or models mid-conversation; express modes as message content.
4. Fork operations (summaries, sub-agents) reuse the parent's exact `system`, `tools` and `model`, then append.
5. Long agent turns that add more than ~20 blocks: place an intermediate breakpoint.
6. Pre-warm (`max_tokens: 0`, same thinking/effort settings) only when first-request latency is user-visible and traffic has gaps longer than the TTL.

## Exact-match response cache

```python
import hashlib, json

def llm_cache_key(ns: str, model: str, params: dict, prompt: str) -> str:
    material = json.dumps({"model": model, "params": params, "prompt": " ".join(prompt.split())}, sort_keys=True)
    return f"llm:exact:{ns}:{hashlib.sha256(material.encode()).hexdigest()}"
# ns = tenant + prompt-template version + tool-schema version
```

Use for deterministic or idempotent calls (classification, extraction, templated summaries of the same document). TTL by content freshness; bump the namespace when prompts or models change.

## Embedding, retrieval and reranker caches

| Cache | Key | TTL |
|---|---|---|
| Chunk embeddings | `sha256(model_id + model_version + dims + normalized_text)` | Until the model changes (content-addressed) |
| Query embeddings | Same shape | Hours–days |
| Retrieval results | (query hash or normalized embedding, index version, filters, k) | Minutes–hours; bump index version on re-index |
| Reranker scores | (query hash, doc ID, reranker version) | Hours–days |

LangChain `CacheBackedEmbeddings`: set `namespace` to the embedding model name (default is empty, so models collide); prefer a SHA-256/BLAKE2 key encoder over the default SHA-1; only document embeddings are cached unless you pass a `query_embedding_store`.

## Semantic caching (last resort)

A semantic cache returns a stored answer for a *different but similar* prompt.

- Correct and incorrect hits have heavily overlapping similarity distributions (vCache), so no single global threshold is both safe and useful. Adversarial prompts can be crafted to collide with cached keys and retrieve or poison answers (arXiv 2601.23088).
- Redis LangCache defaults to a 0.85 similarity threshold (preview); RedisVL uses a *distance* threshold (strict ≈ 0.05). GPTCache no longer adds support for new APIs or models; don't adopt it for new work.
- If you use one: scope by tenant, model, system-prompt version, corpus version and locale; start strict (≥ 0.9 similarity), measure precision on labeled samples, add a verifier (cross-encoder or LLM judge) for borderline hits, log every hit with its score, set a freshness TTL, and only cache public, non-personalized, non-real-time answers.

```python
def answer(q, ctx):
    if ctx.personalized or ctx.realtime:
        return llm(q, ctx)
    exact = cache.get(llm_cache_key(ctx.ns, ctx.model, ctx.params, q))
    if exact:
        return exact
    hit = vector_index.search(embed(q), namespace=ctx.ns, k=1)
    if hit and hit.similarity >= 0.92 and verifier(q, hit.prompt):
        metrics.inc("semantic_hit")
        return hit.response
    out = llm(q, ctx)
    vector_index.upsert(embed(q), {"prompt": q, "response": out}, namespace=ctx.ns, ttl=86400)
    return out
```

## Measuring

- Anthropic: `usage.cache_read_input_tokens`, `usage.cache_creation_input_tokens`, `usage.input_tokens` (uncached remainder only; total prompt = sum of all three). Healthy multi-turn loop: reads grow each turn, writes stay small.
- OpenAI: cached tokens in the usage details. Gemini: `cached_content_token_count`.
- KPIs: cached-token share per route, cost per completed task, semantic-cache precision. Alert when the cached share drops after a deploy (usually a prompt change). Add an integration test asserting a second identical request reads from cache.

## Version notes

- Anthropic minimum cacheable prefix: 512 tokens on the newest models, up to 4,096 on some older ones (not monotonic across generations). Cache diagnostics beta (`cache-diagnosis-2026-04-07`) reports where two requests' prefixes diverged.
- OpenAI GPT-5.6+: cache writes billed at 1.25×.
- Gemini implicit discount raised to 90% on 2.5+.

<details><summary>Old patterns</summary>

- GPTCache as a default semantic cache.
- Timestamps or "current date" in system prompts.
- Re-creating tool lists per user.

</details>

## Verify

```python
r1 = call(); r2 = call()   # identical requests, under the TTL apart
assert r2.usage.cache_read_input_tokens > 0, "prompt prefix not cached: look for a silent invalidator"
```

Diff two consecutive request payloads (with `cache_control` markers stripped) to find the first divergent byte when reads drop to zero.

## Sources

- [Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Vertex AI context caching](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/context-cache/context-cache-overview)
- [Gemini API context caching](https://ai.google.dev/gemini-api/docs/caching)
- [Redis LangCache concepts](https://redis.io/docs/latest/develop/ai/context-engine/langcache/concepts/)
- [vCache: verified semantic prompt caching](https://arxiv.org/html/2502.03771v5)
- [Semantic cache collision attacks (arXiv 2601.23088)](https://arxiv.org/pdf/2601.23088)
- [GPTCache](https://github.com/zilliztech/GPTCache)
- [LangChain: caching embeddings](https://python.langchain.com/docs/how_to/caching_embeddings)
