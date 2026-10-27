# Mobile and native apps

Last reviewed: 2026-10-27 · Applies to: iOS (URLCache/URLSession, Kingfisher, SDWebImage, Nuke), Android (OkHttp 4/5 + Retrofit, Coil 3, Glide 4), React Native/Expo (expo-image, TanStack Query persisters), Flutter (dio_cache_interceptor, cached_network_image), offline-first sync engines

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- HTTP caches
- Image caches
- Persisted query caches
- Offline-first local databases
- Version skew and app-store constraints
- Verify
- Sources

## When to read this

When the app has a mobile client, or the backend serves one (archetype `mobile-backend`). Mobile caches can't be purged by a deploy: old binaries live for months. Server headers and versioned keys are your only levers.

## How to detect

- iOS: `*.xcodeproj`, `Package.swift`, `Podfile` with `Kingfisher`, `SDWebImage`, `Nuke`; `URLCache` usage.
- Android: `build.gradle(.kts)`, `gradle/libs.versions.toml` with `com.squareup.okhttp3:okhttp`, `com.squareup.retrofit2`, `io.coil-kt.coil3`, `com.github.bumptech.glide`, `androidx.room`.
- React Native/Expo: `package.json` with `expo`, `expo-image`, `react-native-fast-image`, `@tanstack/react-query-persist-client`, `@react-native-async-storage/async-storage`, `react-native-mmkv`, `@nozbe/watermelondb`, `@powersync/react-native`, `@electric-sql/client`, `realm`.
- Flutter: `pubspec.yaml` with `dio_cache_interceptor`, `cached_network_image`, `flutter_cache_manager`, `drift`, `sqflite`, `isar`, `powersync`.

## Default recipe

1. **Backend contract:** every API response sends `Cache-Control` and an `ETag` (`references/layers/api-graphql-rpc.md`); mobile HTTP caches then give cheap 304s on flaky networks.
2. **HTTP cache on** with a sized disk cache and the protocol (header-driven) policy by default; offline fallbacks only on screens designed for it.
3. **Image cache** with bounded memory and disk; versioned image URLs or cache keys.
4. **Persisted data cache** with a `buster` tied to the app version and a `maxAge`.
5. **No secrets or tokens in caches**; clear user-scoped caches on logout.

## Rules and gotchas

1. Server-driven TTLs (`Cache-Control`) beat hardcoded client TTLs: you can change freshness without an app release.
2. Version every persisted shape: TanStack `buster`, DB migration version, image `cacheKey`/signature. Server responses must stay backward compatible with what old builds cached.
3. URL-keyed image caches show stale avatars when content changes at a stable URL; version the URL or the key.
4. The OS evicts cache directories under storage pressure (iOS Caches, Android `cacheDir`); never keep must-keep data there.
5. Clear per-user caches (HTTP, images, persisted queries, local DB) on logout or account switch; shared devices leak otherwise.
6. `Authorization` responses: shared-cache rules don't apply on device, but private user data in the HTTP cache is still on disk; use `no-store` for sensitive endpoints.
7. OTA updates (Expo Updates/EAS Update) can change JavaScript-side cache logic, not native cache configuration.

## HTTP caches

```swift
// iOS: URLCache attached to a session; header-driven by default
let cache = URLCache(memoryCapacity: 50 * 1024 * 1024, diskCapacity: 250 * 1024 * 1024,
                     directory: FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!.appendingPathComponent("http"))
let config = URLSessionConfiguration.default
config.urlCache = cache
config.requestCachePolicy = .useProtocolCachePolicy
let session = URLSession(configuration: config)

var req = URLRequest(url: url)
req.cachePolicy = .returnCacheDataElseLoad     // offline-first screen only: ignores age
```

- `.useProtocolCachePolicy` (default) honors headers and revalidates; `.returnCacheDataElseLoad` uses any cached copy regardless of age (can show deleted resources); `.returnCacheDataDontLoad` is strictly offline; `.reloadRevalidatingCacheData` isn't implemented before iOS 13.
- Only responses that fit the capacity limits are cached; size the cache for your largest cacheable response.

```kotlin
// Android: OkHttp cache + offline fallback (Retrofit uses this client)
val client = OkHttpClient.Builder()
  .cache(Cache(File(context.cacheDir, "http_cache"), 50L * 1024 * 1024))
  .addInterceptor { chain ->                       // application interceptor
      val req = if (!isOnline()) chain.request().newBuilder().cacheControl(CacheControl.FORCE_CACHE).build()
                else chain.request()
      chain.proceed(req)
  }.build()
```

- Sources disagree on application vs network interceptors for the offline rewrite; application interceptors run offline, network interceptors don't. Test airplane mode.
- Prefer fixing server headers over network interceptors that inject `Cache-Control`.

```dart
// Flutter: dio_cache_interceptor
final options = CacheOptions(store: HiveCacheStore(dir), policy: CachePolicy.request,
  hitCacheOnErrorCodes: [500, 503], maxStale: const Duration(days: 7));
final dio = Dio()..interceptors.add(DioCacheInterceptor(options: options));
```

Policies: `request` (default, honors headers), `refresh`, `forceCache` (stores every successful GET even without headers), `refreshForceCache` (2.1.1+), `noCache`.

## Image caches

| Library | Defaults and controls |
|---|---|
| Kingfisher (iOS) | Disk expiration 7 days, extended on read; `.diskCacheAccessExtending(.none)`, per-request `.diskCacheExpiration` (v5–v7 docs; Kingfisher 8 unverified) |
| SDWebImage / Nuke (iOS) | Memory + disk tiers; verify current expiry defaults |
| Coil 3 (Android/KMP) | Memory + disk by default; configure once with `SingletonImageLoader.setSafe { … }` |
| Glide 4 (Android) | `DiskCacheStrategy.AUTOMATIC` default; `.signature(ObjectKey(version))` to version |
| expo-image | `cachePolicy` `none`/`disk`/`memory`/`memory-disk` (docs: `disk` default; use `memory-disk` for repeated images); no TTL, rotate `cacheKey` |
| cached_network_image (Flutter) | `flutter_cache_manager` `Config(key, stalePeriod, maxNrOfCacheObjects)`; `stalePeriod` counts from last use and doesn't reliably force refresh (open bug) |

```kotlin
SingletonImageLoader.setSafe { ctx -> ImageLoader.Builder(ctx)
  .memoryCache { MemoryCache.Builder().maxSizePercent(ctx, 0.25).build() }
  .diskCache { DiskCache.Builder().directory(ctx.cacheDir.resolve("image_cache").toOkioPath()).maxSizeBytes(256L * 1024 * 1024).build() }
  .build() }
```

```tsx
<Image source={{ uri: url, cacheKey: `avatar-${user.id}-${user.avatarVersion}` }} cachePolicy="memory-disk" />
```

## Persisted query caches

```tsx
// React Native: TanStack Query persisted to AsyncStorage (or MMKV)
const persister = createAsyncStoragePersister({ storage: AsyncStorage })
const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: 1000 * 60 * 60 * 24 } } })

<PersistQueryClientProvider client={queryClient}
  persistOptions={{ persister, maxAge: 1000 * 60 * 60 * 24, buster: Application.nativeApplicationVersion ?? '' }}>
```

- Restored caches are discarded on `maxAge` expiry, `buster` mismatch or restore error. Keep `gcTime` ≥ `maxAge` (default 24 h). Writes are throttled (~1/s).
- Don't persist queries with secrets; use `dehydrateOptions.shouldDehydrateQuery` to exclude them.

## Offline-first local databases

A local DB (SQLite/Room/Core Data/WatermelonDB/PowerSync/Electric) as the UI's source of truth is a sync architecture, not TTL caching: plan conflict resolution on the write path and schema migrations on device.

- Realm Atlas Device Sync reached end of life on 2025-09-30; the on-device Realm database remains. Migrate sync to PowerSync, Ditto, Couchbase Lite or similar (no official successor).
- ElectricSQL syncs Postgres "shapes" over plain HTTP that CDNs and proxies can cache (live mode long-polls); it's read-path only. PowerSync adds an upload queue for writes.

## Version skew and app-store constraints

- You can't purge caches on old installs; design every cache for months-old binaries.
- Additive API changes only for cached endpoints; version breaking changes in the path.
- Minimum-version gates (force update) are the last resort for incompatible cached state.
- Background refresh and prefetch cost user battery and data; honor Low Data Mode / Data Saver.

## Verify

```bash
# Backend contract for mobile
curl -s -o /dev/null -D - https://api.example.com/v1/feed | grep -iE 'cache-control|etag|vary'
# Device: run the app with the network proxied (Charles/Proxyman/mitmproxy) and confirm 304s and cache hits on second launch;
# toggle airplane mode on offline-designed screens; log out and confirm user caches are cleared.
```

## Sources

- [Apple: URLCache](https://developer.apple.com/documentation/foundation/urlcache)
- [tanaschita: URLSession cache policies](https://tanaschita.com/20221031-managing-cache-when-working-with-urlsession-in-ios/)
- [cleanor.app: URLSession cache](https://cleanor.app/reference/nsurlsession-cache)
- [OkHttp: caching](https://square.github.io/okhttp/features/caching/)
- [Amit Shekhar: OkHttp caching with interceptors](https://medium.com/@amitshekhar/caching-with-okhttp-interceptor-and-retrofit-180faa853ff5)
- [Coil](https://coil-kt.github.io/coil/)
- [Future Studio: Glide caching](https://futurestud.io/tutorials/glide-how-to-choose-the-best-caching-preference)
- [Kingfisher discussion #2087](https://github.com/onevcat/Kingfisher/discussions/2087)
- [Expo: Image](https://docs.expo.dev/versions/latest/sdk/image/)
- [expo/expo PR #48843](https://github.com/expo/expo/pull/48843)
- [TanStack Query: persistQueryClient](https://tanstack.com/query/v5/docs/framework/react/plugins/persistQueryClient)
- [dio_cache_interceptor CachePolicy](https://pub.dev/documentation/dio_cache_interceptor/latest/dio_cache_interceptor/CachePolicy.html)
- [Baseflow/flutter_cached_network_image #947](https://github.com/Baseflow/flutter_cached_network_image/issues/947)
- [MongoDB: Atlas Device Sync end of life](https://mongodb.com/community/forums/t/atlas-device-sync-end-of-life-and-deprecation/296687)
- [Electric: HTTP API](https://electric-sql.com/docs/api/http)
