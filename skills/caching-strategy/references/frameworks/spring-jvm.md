# Spring Boot and the JVM

Last reviewed: 2026-10-27 · Applies to: Spring Boot 4.1 on Spring Framework 7.0; Caffeine, Redis, Hibernate 7 second-level cache; Quarkus/Micronaut briefly

## Contents

- When to read this
- How to detect
- Default recipe
- Rules and gotchas
- Hibernate second-level cache
- Quarkus and Micronaut
- Version notes
- Verify
- Sources

## When to read this

When the app runs on the JVM (Spring Boot, Quarkus, Micronaut) or uses Hibernate/JPA.

## How to detect

`pom.xml`/`build.gradle(.kts)` with `org.springframework.boot` and `spring-boot-starter-cache` (Boot 4 also publishes `spring-boot-cache`); `application.properties`/`.yml` with `spring.cache.*`; providers `com.github.ben-manes.caffeine:caffeine`, `spring-boot-starter-data-redis`, `org.hibernate.orm:hibernate-jcache`, `org.ehcache:ehcache`; `@Cacheable` in code. Quarkus: `io.quarkus:quarkus-cache`. Micronaut: `io.micronaut.cache`.

## Default recipe

```java
@Configuration
@EnableCaching            // on a config class, not the main application class (keeps caching optional in tests)
class CacheConfig {}

@Service
class ProductService {
  @Cacheable(cacheNames = "products", key = "#id", unless = "#result == null")
  public Product find(String id) { ... }

  @Cacheable(cacheNames = "productStats", sync = true)       // one computation per key per instance
  public Stats stats(String id) { ... }

  @CacheEvict(cacheNames = "products", key = "#product.id")  // delete on write (preferred over @CachePut)
  public Product update(Product product) { ... }
}
```

```properties
spring.cache.type=redis
spring.cache.redis.time-to-live=10m
spring.cache.redis.key-prefix=shop:prod:v3:
# Local only:
# spring.cache.type=caffeine
# spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=10m
```

```java
@GetMapping("/products/{id}")
ResponseEntity<ProductDto> product(@PathVariable String id) {
  ProductDto p = service.find(id);
  return ResponseEntity.ok()
      .cacheControl(CacheControl.noCache())                       // browsers revalidate
      .header("CDN-Cache-Control", "max-age=300, stale-while-revalidate=3600")
      .eTag(String.valueOf(p.version()))                           // 304 handled on If-None-Match
      .body(p);
}
```

## Rules and gotchas

1. Self-invocation (a method calling another `@Cacheable` method on the same bean) bypasses the proxy and the cache. So do private methods.
2. `sync = true` restrictions: no `unless`, only one cache name, no other cache operations on the method (startup error otherwise).
3. Don't combine `@CachePut` and `@Cacheable` on one method.
4. Redis caches have no TTL unless `spring.cache.redis.time-to-live` (or per-cache config) is set. Always set one.
5. Use a JSON serializer for cached values, not JDK serialization. Don't cache JPA entities with lazy associations (`LazyInitializationException` after deserialization); cache DTOs.
6. `CompositeCacheManager` returns the first manager that has the named cache; it doesn't give an L1 → L2 read path. For two tiers use a custom `Cache`/`CacheManager` or a library (`references/layers/in-process.md`).
7. Spring treats `;` as a matrix-variable delimiter: `/account;.css` can be served by `/account` and cached by an extension-based CDN rule (web cache deception). Send `private`/`no-store` on authenticated routes; restrict CDN caching to asset paths.
8. `ShallowEtagHeaderFilter` hashes the rendered body: it saves bandwidth, not server work. Prefer version-based ETags.
9. Hibernate L2 + native SQL or bulk updates leaves stale entities; other apps writing the DB make L2 stale.
10. JVM cold starts: JIT warm-up plus empty Caffeine caches make the first requests slow after deploy; warm both before taking traffic (readiness probe).

## Hibernate second-level cache

```properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.region.factory_class=org.hibernate.cache.jcache.internal.JCacheRegionFactory
```

```java
@Entity
@Cache(usage = CacheConcurrencyStrategy.READ_WRITE)
class Country { ... }
```

Off by default. Strategies: `READ_ONLY` (throws on update), `NONSTRICT_READ_WRITE`, `READ_WRITE`, `TRANSACTIONAL` (JTA). Best for reference data and rarely updated entities with a single writer app. The query cache needs the entity cache and can increase queries when expirations mismatch (`references/layers/database-orm.md`).

## Quarkus and Micronaut

Quarkus `@CacheResult`/`@CacheInvalidate` (Caffeine-backed, Redis extension available); Micronaut `@Cacheable`/`@CacheInvalidate`. Same rules: TTLs, delete on write, no shared caching of per-user data. Details weren't covered by this skill's research.

## Version notes

- Boot 4: `spring-boot-cache` module; Lettuce static master/replica auto-config; Infinispan `InfinispanCacheConfigurer` replaces the removed customizer.
- Framework 7.0.9 is the latest stable at review; 7.1 in development.

<details><summary>Old patterns</summary>

- Guava caches (use Caffeine).
- Ehcache 2 / `net.sf.ehcache` (use JCache + Ehcache 3).
- `@EnableCaching` on the `@SpringBootApplication` class.

</details>

## Verify

```bash
curl -s localhost:8080/actuator/caches | jq .
curl -s localhost:8080/actuator/metrics/cache.gets?tag=result:hit | jq .
redis-cli --scan --pattern 'shop:prod:v3:*' | head
```

## Sources

- [Spring Framework: declarative caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Boot caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring MVC HTTP caching](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-caching.html)
- [Spring Boot 4.0 release notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Release-Notes)
- [Baeldung: Hibernate second-level cache](https://www.baeldung.com/hibernate-second-level-cache)
- [PortSwigger: Gotta cache 'em all (Spring `;`)](https://portswigger.net/research/gotta-cache-em-all)
