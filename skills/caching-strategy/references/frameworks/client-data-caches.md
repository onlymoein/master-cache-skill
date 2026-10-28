# Client-side data caches

Last reviewed: 2026-10-27 · Applies to: TanStack Query 5.105, SWR 2.5, Apollo Client 4.3, Relay 21, urql 5 / Graphcache 9, RTK Query (RTK 2.13), React 19 `cache()`

## Contents

- When to read this
- Rules and gotchas
- Recommended defaults
- TanStack Query
- SWR
- Apollo Client
- Relay
- urql
- RTK Query
- React cache()
- Version notes
- Verify
- Sources

## When to read this

When the app uses a client data library (detected deps: `@tanstack/*-query`, `swr`, `@apollo/client`, `relay-runtime`/`react-relay`, `urql`/`@urql/*`, `@reduxjs/toolkit` with `createApi`). These caches live in the browser (or app) per user; they don't replace HTTP or server caching.

## Rules and gotchas

1. Every client cache has a key, a freshness window, a retention window and invalidation. Set all four deliberately.
2. When the framework already delivered fresh data during SSR (Next.js, Nuxt payload, SvelteKit inlined fetch), set an initial `staleTime` above 0, or the client refetches immediately after hydration.
3. Clear client caches on logout and on tenant/account switch (`queryClient.clear()`, `cache.reset()`, SWR `mutate(() => true, undefined, { revalidate: false })`). Persisted caches must be scoped per user (user ID in the storage key) or cleared, or a shared device leaks data.
4. Persisted caches need a version buster tied to the build or API version.
5. On the server, create a new client cache per request (TanStack `QueryClient`, Apollo client, SWR provider); a module-level singleton leaks data between users.
6. Client caches can't fix a missing `private`: HTTP and CDN headers still decide what shared caches store.

## Recommended defaults

| Library | Lists / feeds | Entities | Reference data | Notes |
|---|---|---|---|---|
| TanStack Query | `staleTime` 30–60 s | 30–60 s | `Infinity` (or `'static'` for boot-time flags/permissions) | `gcTime` ≥ persister `maxAge`; `buster` = build ID |
| SWR | defaults | defaults | `revalidateIfStale: false` | Raise `dedupingInterval` for expensive endpoints; `revalidateOnFocus: false` for heavy dashboards |
| Apollo | `cache-and-network` | `cache-first` | `cache-first` | `keyFields` for types without `id` |
| RTK Query | `keepUnusedDataFor` 60 s (default) | 300 for tab-switching UIs | long | Tags per entity + `LIST` |

## TanStack Query

Defaults: `staleTime` 0 (stale immediately); refetch on mount, window focus and reconnect when stale; inactive queries garbage-collected after 5 min (`gcTime`); 3 retries with backoff; structural sharing.

```ts
const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } })

useMutation({
  mutationFn: addTodo,
  onMutate: async (newTodo, context) => {
    await context.client.cancelQueries({ queryKey: ['todos'] })
    const previous = context.client.getQueryData(['todos'])
    context.client.setQueryData(['todos'], (old: Todo[] = []) => [...old, newTodo])
    return { previous }
  },
  onError: (_err, _newTodo, onMutateResult, context) =>
    context.client.setQueryData(['todos'], onMutateResult?.previous),
  onSettled: () => queryClient.invalidateQueries({ queryKey: ['todos'] }),
})
```

- `invalidateQueries({ queryKey: ['todos'] })` matches by prefix; `exact: true` for one key.
- `staleTime: Infinity` still allows manual invalidation; `staleTime: 'static'` blocks even `invalidateQueries` and `refetch*: 'always'`.
- SSR: new `QueryClient` per request on the server, singleton in the browser; `dehydrate` + `<HydrationBoundary>`; to stream, include pending queries in `shouldDehydrateQuery`.
- Persistence: `persistQueryClient` with `createSyncStoragePersister`/`createAsyncStoragePersister`; default `maxAge` 24 h; `gcTime` must be ≥ `maxAge`; always pass `buster`. Max `gcTime` ≈ 24 days (setTimeout limit).

## SWR

Defaults: `revalidateIfStale`, `revalidateOnFocus`, `revalidateOnReconnect` all true; `refreshInterval` 0; `dedupingInterval` 2000 ms; `focusThrottleInterval` 5000 ms; `keepPreviousData` false.

- Cache provider: a global `Map` by default; `<SWRConfig value={{ provider: () => new Map() }}>` defined high in the tree (one per user session).
- `mutate(key)` revalidates; `mutate(key, data, { optimisticData, revalidate, populateCache, rollbackOnError })` for optimistic writes; a function key filters many keys. `useSWRMutation` for remote mutations.
- RSC: `const cacheData = { ...preload('/api/user', fetchUser) }` in a Server Component layout, then `<SWRConfig value={{ cacheData }}>`.

## Apollo Client

- Fetch policies: `cache-first` (default), `cache-only`, `cache-and-network`, `network-only`, `no-cache`, `standby`; `nextFetchPolicy` for later executions.
- Normalized `InMemoryCache` with `typePolicies` (`keyFields`, field `merge`), `possibleTypes`. Types without an `id` field need `keyFields` or they're cached by path and duplicate.
- Eviction: `cache.evict({ id })` or `{ id, fieldName }` then `cache.gc()`; `cache.modify` in mutation `update`. `client.resetStore()`/`clearStore()` on logout.
- Apollo Client 4: `notifyOnNetworkStatusChange` defaults to `true` (more loading states); `canonizeResults` removed.

## Relay

Fetch policies: `store-or-network` (default), `store-and-network`, `network-only`, `store-only`. GC removes data not referenced by mounted components; `retain()` keeps it; tune with `gcReleaseBufferSize`.

## urql

- Default document cache (`cache-first`) invalidates by `__typename` seen in mutation results; empty lists hide their typename (use `additionalTypenames` or switch to Graphcache).
- Graphcache: `cacheExchange({ keys, resolvers, updates, optimistic })` for normalized caching.

## RTK Query

```ts
const api = createApi({
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['Post'],
  keepUnusedDataFor: 60,
  endpoints: (b) => ({
    getPosts: b.query<Post[], void>({
      query: () => 'posts',
      providesTags: (r = []) => [...r.map(({ id }) => ({ type: 'Post' as const, id })), { type: 'Post', id: 'LIST' }],
    }),
    addPost: b.mutation<Post, Partial<Post>>({
      query: (body) => ({ url: 'posts', method: 'POST', body }),
      invalidatesTags: [{ type: 'Post', id: 'LIST' }],
    }),
  }),
})
```

Subscriptions are ref-counted; unused data is removed after `keepUnusedDataFor` (60 s default). `refetchOnFocus`/`refetchOnReconnect` need `setupListeners(store.dispatch)`.

## React cache()

`cache(fn)` memoizes per server request in Server Components only; React invalidates it for every request. Define memoized functions at module scope (each `cache()` call creates a separate cache). `cacheSignal()` can abort work. Use it to dedupe DB/ORM calls within a render, not as a cross-request cache.

## Version notes

- TanStack Query v5: `gcTime` (renamed from `cacheTime`), `staleTime: 'static'`, mutation callbacks receive `context.client`.
- Apollo Client 4: `notifyOnNetworkStatusChange` default true.
- SWR 2.5: RSC `preload` + `cacheData`.

<details><summary>Old patterns</summary>

- TanStack Query v4 `cacheTime` and `onSuccess` on queries.
- Apollo `canonizeResults`.
- A module-level `QueryClient` shared by every SSR request.

</details>

## Verify

- React Query Devtools / Apollo DevTools / Redux DevTools show cache entries, staleness and GC.
- Log out and back in as another user: no previous user's data appears before refetch.
- Reload after a deploy: the persisted cache is discarded when the buster changes.

## Sources

- [TanStack Query important defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults)
- [TanStack Query advanced SSR](https://tanstack.com/query/latest/docs/framework/react/guides/advanced-ssr)
- [TanStack persistQueryClient](https://tanstack.com/query/latest/docs/framework/react/plugins/persistQueryClient)
- [SWR API](https://swr.vercel.app/docs/api)
- [Apollo Client caching](https://www.apollographql.com/docs/react/caching/overview)
- [Apollo Client 4 migration](https://www.apollographql.com/docs/react/migrating/apollo-client-4-migration)
- [Relay fetch policies](https://relay.dev/docs/guided-tour/reusing-cached-data/fetch-policies/)
- [urql document caching](https://nearform.com/open-source/urql/docs/basics/document-caching/)
- [RTK Query cache behavior](https://redux-toolkit.js.org/rtk-query/usage/cache-behavior)
- [React cache](https://react.dev/reference/react/cache)
