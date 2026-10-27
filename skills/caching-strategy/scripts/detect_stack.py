#!/usr/bin/env python3
"""Fingerprint a repository's stack and say which caching references to read.

Usage:
    python scripts/detect_stack.py <repo_dir>
    python scripts/detect_stack.py --list-references

Reads manifests, lockfiles and config files only (no code execution, no network).
Prints one JSON object on stdout:

    frameworks          [{name, version, kind, source, config}]
    client_caches, hosting, cdn, proxies, data_stores, orm, cms, api,
    mobile, ai, ci, service_worker      [{name, version?, source}]
    archetype_candidates [{id, confidence, evidence}]
    read                 reference paths to read now (relative to the skill dir)
    read_when            [{path, when}] references to read if a condition holds
    notes                things the agent should confirm or know
    limits               what the scan skipped or truncated

Exit codes: 0 success, 2 bad usage. Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REFERENCES = [
    "references/core/decision-framework.md",
    "references/core/archetypes.md",
    "references/core/http-semantics.md",
    "references/core/invalidation-consistency.md",
    "references/core/stampede-failure.md",
    "references/core/security.md",
    "references/core/observability-testing.md",
    "references/layers/browser-platform.md",
    "references/layers/service-workers.md",
    "references/layers/cdn-concepts.md",
    "references/layers/reverse-proxies.md",
    "references/layers/in-process.md",
    "references/layers/distributed-cache.md",
    "references/layers/database-orm.md",
    "references/layers/serverless-edge-data.md",
    "references/layers/api-graphql-rpc.md",
    "references/layers/mobile-native.md",
    "references/layers/ai-llm.md",
    "references/layers/build-ci-network.md",
    "references/frameworks/nextjs.md",
    "references/frameworks/nuxt-nitro.md",
    "references/frameworks/sveltekit.md",
    "references/frameworks/react-router-remix.md",
    "references/frameworks/astro.md",
    "references/frameworks/other-frontend.md",
    "references/frameworks/client-data-caches.md",
    "references/frameworks/rails.md",
    "references/frameworks/django.md",
    "references/frameworks/laravel-php.md",
    "references/frameworks/spring-jvm.md",
    "references/frameworks/aspnet.md",
    "references/frameworks/node-backends.md",
    "references/frameworks/python-web.md",
    "references/frameworks/go.md",
    "references/frameworks/elixir.md",
    "references/cms/wordpress.md",
    "references/cms/drupal.md",
    "references/cms/shopify-hydrogen.md",
    "references/cms/magento.md",
    "references/cms/headless-cms.md",
    "references/platforms/cloudflare.md",
    "references/platforms/vercel.md",
    "references/platforms/netlify.md",
    "references/platforms/fastly.md",
    "references/platforms/cloudfront.md",
    "references/platforms/akamai.md",
    "references/platforms/gcp-azure-cdn.md",
    "references/platforms/other-hosts.md",
]

ALWAYS_READ = [
    "references/core/decision-framework.md",
    "references/core/http-semantics.md",
    "references/core/security.md",
]

SKIP_DIRS = {
    "node_modules", ".git", ".hg", ".svn", "vendor", "dist", "build", "out", ".next", ".nuxt",
    ".output", ".svelte-kit", ".astro", ".vercel/output", ".netlify", ".turbo", ".cache",
    "coverage", "target", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", "Pods", ".gradle", ".idea", ".terraform", "bower_components", "tmp",
    "storage", "obj", "_build", "deps", ".dart_tool", "DerivedData", ".expo",
    "public/build", "wp-includes", "wp-admin",
}
MAX_FILES = 20000
MAX_DEPTH = 8
MAX_READ_BYTES = 512 * 1024

# --------------------------------------------------------------------------- dependency signals
# name -> (category, label, kind or None)
NPM_SIGNALS = {
    # frameworks
    "next": ("framework", "nextjs", "fullstack"),
    "nuxt": ("framework", "nuxt", "fullstack"),
    "nitropack": ("framework", "nitro", "backend"),
    "nitro": ("framework", "nitro", "backend"),
    "@sveltejs/kit": ("framework", "sveltekit", "fullstack"),
    "@react-router/dev": ("framework", "react-router", "fullstack"),
    "@remix-run/react": ("framework", "remix", "fullstack"),
    "@remix-run/node": ("framework", "remix", "fullstack"),
    "astro": ("framework", "astro", "fullstack"),
    "@angular/core": ("framework", "angular", "frontend"),
    "gatsby": ("framework", "gatsby", "static"),
    "@builder.io/qwik": ("framework", "qwik", "fullstack"),
    "@qwik.dev/core": ("framework", "qwik", "fullstack"),
    "@solidjs/start": ("framework", "solidstart", "fullstack"),
    "@tanstack/react-start": ("framework", "tanstack-start", "fullstack"),
    "@tanstack/start": ("framework", "tanstack-start", "fullstack"),
    "@docusaurus/core": ("framework", "docusaurus", "static"),
    "vitepress": ("framework", "vitepress", "static"),
    "@11ty/eleventy": ("framework", "eleventy", "static"),
    "express": ("framework", "express", "backend"),
    "fastify": ("framework", "fastify", "backend"),
    "@nestjs/core": ("framework", "nestjs", "backend"),
    "koa": ("framework", "koa", "backend"),
    "hono": ("framework", "hono", "backend"),
    # client data caches
    "@tanstack/react-query": ("client_cache", "tanstack-query", None),
    "@tanstack/vue-query": ("client_cache", "tanstack-query", None),
    "@tanstack/svelte-query": ("client_cache", "tanstack-query", None),
    "@tanstack/solid-query": ("client_cache", "tanstack-query", None),
    "@tanstack/angular-query-experimental": ("client_cache", "tanstack-query", None),
    "swr": ("client_cache", "swr", None),
    "@apollo/client": ("client_cache", "apollo-client", None),
    "relay-runtime": ("client_cache", "relay", None),
    "react-relay": ("client_cache", "relay", None),
    "urql": ("client_cache", "urql", None),
    "@urql/core": ("client_cache", "urql", None),
    "@reduxjs/toolkit": ("client_cache", "rtk-query", None),
    "@tanstack/query-persist-client-core": ("client_cache", "tanstack-query-persist", None),
    "@tanstack/react-query-persist-client": ("client_cache", "tanstack-query-persist", None),
    # hosting / cdn
    "vercel": ("hosting", "vercel", None),
    "@vercel/functions": ("hosting", "vercel", None),
    "@vercel/kv": ("data_store", "vercel-kv", None),
    "@vercel/edge-config": ("data_store", "vercel-edge-config", None),
    "@netlify/functions": ("hosting", "netlify", None),
    "@netlify/plugin-nextjs": ("hosting", "netlify", None),
    "@netlify/blobs": ("data_store", "netlify-blobs", None),
    "@netlify/cache": ("hosting", "netlify", None),
    "wrangler": ("hosting", "cloudflare", None),
    "@cloudflare/workers-types": ("hosting", "cloudflare", None),
    "@opennextjs/cloudflare": ("hosting", "cloudflare", None),
    "@opennextjs/aws": ("hosting", "aws", None),
    "@sveltejs/adapter-vercel": ("hosting", "vercel", None),
    "@sveltejs/adapter-netlify": ("hosting", "netlify", None),
    "@sveltejs/adapter-cloudflare": ("hosting", "cloudflare", None),
    "@astrojs/vercel": ("hosting", "vercel", None),
    "@astrojs/netlify": ("hosting", "netlify", None),
    "@astrojs/cloudflare": ("hosting", "cloudflare", None),
    "@fastly/js-compute": ("hosting", "fastly", None),
    "sst": ("hosting", "aws", None),
    "serverless": ("hosting", "aws", None),
    "aws-cdk-lib": ("hosting", "aws", None),
    "firebase-tools": ("hosting", "firebase", None),
    # data stores
    "ioredis": ("data_store", "redis", None),
    "redis": ("data_store", "redis", None),
    "@redis/client": ("data_store", "redis", None),
    "iovalkey": ("data_store", "valkey", None),
    "@valkey/valkey-glide": ("data_store", "valkey", None),
    "@upstash/redis": ("data_store", "upstash-redis", None),
    "memjs": ("data_store", "memcached", None),
    "memcached": ("data_store", "memcached", None),
    "@keyv/redis": ("data_store", "redis", None),
    "pg": ("data_store", "postgres", None),
    "postgres": ("data_store", "postgres", None),
    "@neondatabase/serverless": ("data_store", "postgres", None),
    "mysql2": ("data_store", "mysql", None),
    "mongodb": ("data_store", "mongodb", None),
    "@libsql/client": ("data_store", "libsql", None),
    "@planetscale/database": ("data_store", "mysql", None),
    "@supabase/supabase-js": ("data_store", "supabase", None),
    # in-process
    "lru-cache": ("in_process", "lru-cache", None),
    "node-cache": ("in_process", "node-cache", None),
    "quick-lru": ("in_process", "quick-lru", None),
    "@isaacs/ttlcache": ("in_process", "ttlcache", None),
    "cache-manager": ("in_process", "cache-manager", None),
    "keyv": ("in_process", "keyv", None),
    "@nestjs/cache-manager": ("in_process", "nestjs-cache-manager", None),
    "apicache": ("in_process", "apicache", None),
    "dataloader": ("api", "dataloader", None),
    # orm
    "prisma": ("orm", "prisma", None),
    "@prisma/client": ("orm", "prisma", None),
    "drizzle-orm": ("orm", "drizzle", None),
    "typeorm": ("orm", "typeorm", None),
    "sequelize": ("orm", "sequelize", None),
    "mongoose": ("orm", "mongoose", None),
    "kysely": ("orm", "kysely", None),
    "@mikro-orm/core": ("orm", "mikro-orm", None),
    # cms / commerce
    "@shopify/hydrogen": ("cms", "shopify-hydrogen", None),
    "contentful": ("cms", "contentful", None),
    "@sanity/client": ("cms", "sanity", None),
    "next-sanity": ("cms", "sanity", None),
    "sanity": ("cms", "sanity", None),
    "@strapi/strapi": ("cms", "strapi", None),
    "payload": ("cms", "payload", None),
    "@storyblok/js": ("cms", "storyblok", None),
    "@storyblok/react": ("cms", "storyblok", None),
    "@prismicio/client": ("cms", "prismic", None),
    "@directus/sdk": ("cms", "directus", None),
    "@tryghost/content-api": ("cms", "ghost", None),
    "@medusajs/medusa": ("commerce", "medusa", None),
    "@medusajs/framework": ("commerce", "medusa", None),
    "@commercetools/platform-sdk": ("commerce", "commercetools", None),
    "@bigcommerce/catalyst-core": ("commerce", "bigcommerce", None),
    "@vendure/core": ("commerce", "vendure", None),
    "@saleor/app-sdk": ("commerce", "saleor", None),
    # api
    "@apollo/server": ("api", "apollo-server", None),
    "apollo-server": ("api", "apollo-server-legacy", None),
    "apollo-server-express": ("api", "apollo-server-legacy", None),
    "graphql-yoga": ("api", "graphql-yoga", None),
    "@envelop/response-cache": ("api", "envelop-response-cache", None),
    "@graphql-hive/gateway": ("api", "hive-gateway", None),
    "@apollo/gateway": ("api", "apollo-gateway", None),
    "mercurius": ("api", "mercurius", None),
    "@grafbase/sdk": ("api", "grafbase", None),
    "@trpc/server": ("api", "trpc", None),
    "@connectrpc/connect": ("api", "connect-rpc", None),
    "@grpc/grpc-js": ("api", "grpc", None),
    # mobile
    "expo": ("mobile", "expo", None),
    "react-native": ("mobile", "react-native", None),
    "expo-image": ("mobile", "expo-image", None),
    "react-native-fast-image": ("mobile", "react-native-fast-image", None),
    "@react-native-async-storage/async-storage": ("mobile", "async-storage", None),
    "react-native-mmkv": ("mobile", "mmkv", None),
    "@nozbe/watermelondb": ("mobile", "watermelondb", None),
    "@powersync/react-native": ("mobile", "powersync", None),
    "@electric-sql/client": ("data_store", "electric-sql", None),
    "realm": ("mobile", "realm", None),
    # ai
    "@anthropic-ai/sdk": ("ai", "anthropic", None),
    "openai": ("ai", "openai", None),
    "@google/genai": ("ai", "google-genai", None),
    "@google/generative-ai": ("ai", "google-generative-ai", None),
    "langchain": ("ai", "langchain", None),
    "@langchain/core": ("ai", "langchain", None),
    "llamaindex": ("ai", "llamaindex", None),
    "ai": ("ai", "vercel-ai-sdk", None),
    "@pinecone-database/pinecone": ("ai", "pinecone", None),
    "@qdrant/js-client-rest": ("ai", "qdrant", None),
    "weaviate-client": ("ai", "weaviate", None),
    "chromadb": ("ai", "chroma", None),
    "@upstash/vector": ("ai", "upstash-vector", None),
    # service workers
    "workbox-build": ("service_worker", "workbox", None),
    "workbox-webpack-plugin": ("service_worker", "workbox", None),
    "workbox-window": ("service_worker", "workbox", None),
    "workbox-routing": ("service_worker", "workbox", None),
    "@serwist/next": ("service_worker", "serwist", None),
    "serwist": ("service_worker", "serwist", None),
    "@serwist/vite": ("service_worker", "serwist", None),
    "vite-plugin-pwa": ("service_worker", "vite-plugin-pwa", None),
    "next-pwa": ("service_worker", "next-pwa", None),
    "@ducanh2912/next-pwa": ("service_worker", "next-pwa", None),
    "@angular/service-worker": ("service_worker", "angular-sw", None),
    # realtime / media (archetype hints)
    "socket.io": ("realtime", "socket.io", None),
    "ws": ("realtime", "ws", None),
    "yjs": ("realtime", "yjs", None),
    "@liveblocks/client": ("realtime", "liveblocks", None),
    "pusher": ("realtime", "pusher", None),
    "ably": ("realtime", "ably", None),
    "convex": ("realtime", "convex", None),
    "hls.js": ("media", "hls.js", None),
    "video.js": ("media", "video.js", None),
    "shaka-player": ("media", "shaka-player", None),
    "@mux/mux-node": ("media", "mux", None),
    "@mux/mux-player-react": ("media", "mux", None),
    "fluent-ffmpeg": ("media", "ffmpeg", None),
    "react-admin": ("internal", "react-admin", None),
    "@refinedev/core": ("internal", "refine", None),
    "next-auth": ("auth", "next-auth", None),
    "@auth/core": ("auth", "authjs", None),
    "@clerk/nextjs": ("auth", "clerk", None),
    "@clerk/clerk-react": ("auth", "clerk", None),
    "better-auth": ("auth", "better-auth", None),
    "@supabase/ssr": ("auth", "supabase-auth", None),
    "stripe": ("payments", "stripe", None),
    "@stripe/stripe-js": ("payments", "stripe", None),
}

PY_SIGNALS = {
    "django": ("framework", "django", "backend"),
    "fastapi": ("framework", "fastapi", "backend"),
    "flask": ("framework", "flask", "backend"),
    "starlette": ("framework", "starlette", "backend"),
    "litestar": ("framework", "litestar", "backend"),
    "mkdocs": ("framework", "mkdocs", "static"),
    "mkdocs-material": ("framework", "mkdocs", "static"),
    "redis": ("data_store", "redis", None),
    "valkey": ("data_store", "valkey", None),
    "django-redis": ("data_store", "redis", None),
    "pymemcache": ("data_store", "memcached", None),
    "pylibmc": ("data_store", "memcached", None),
    "psycopg": ("data_store", "postgres", None),
    "psycopg2": ("data_store", "postgres", None),
    "psycopg2-binary": ("data_store", "postgres", None),
    "asyncpg": ("data_store", "postgres", None),
    "pymysql": ("data_store", "mysql", None),
    "mysqlclient": ("data_store", "mysql", None),
    "pymongo": ("data_store", "mongodb", None),
    "cachetools": ("in_process", "cachetools", None),
    "flask-caching": ("in_process", "flask-caching", None),
    "cashews": ("in_process", "cashews", None),
    "aiocache": ("in_process", "aiocache", None),
    "fastapi-cache2": ("in_process", "fastapi-cache2", None),
    "diskcache": ("in_process", "diskcache", None),
    "sqlalchemy": ("orm", "sqlalchemy", None),
    "sqlmodel": ("orm", "sqlmodel", None),
    "tortoise-orm": ("orm", "tortoise", None),
    "peewee": ("orm", "peewee", None),
    "graphene": ("api", "graphene", None),
    "graphene-django": ("api", "graphene", None),
    "strawberry-graphql": ("api", "strawberry", None),
    "ariadne": ("api", "ariadne", None),
    "grpcio": ("api", "grpc", None),
    "djangorestframework": ("api", "django-rest-framework", None),
    "anthropic": ("ai", "anthropic", None),
    "openai": ("ai", "openai", None),
    "google-genai": ("ai", "google-genai", None),
    "langchain": ("ai", "langchain", None),
    "langchain-core": ("ai", "langchain", None),
    "llama-index": ("ai", "llamaindex", None),
    "llama-index-core": ("ai", "llamaindex", None),
    "litellm": ("ai", "litellm", None),
    "pinecone": ("ai", "pinecone", None),
    "pinecone-client": ("ai", "pinecone", None),
    "qdrant-client": ("ai", "qdrant", None),
    "weaviate-client": ("ai", "weaviate", None),
    "chromadb": ("ai", "chroma", None),
    "pgvector": ("ai", "pgvector", None),
    "channels": ("realtime", "django-channels", None),
    "python-socketio": ("realtime", "socket.io", None),
    "stripe": ("payments", "stripe", None),
    "django-allauth": ("auth", "django-allauth", None),
    "django-tenants": ("tenancy", "django-tenants", None),
    "saleor": ("commerce", "saleor", None),
}

RUBY_SIGNALS = {
    "rails": ("framework", "rails", "backend"),
    "jekyll": ("framework", "jekyll", "static"),
    "solid_cache": ("data_store", "solid_cache", None),
    "redis": ("data_store", "redis", None),
    "hiredis-client": ("data_store", "redis", None),
    "dalli": ("data_store", "memcached", None),
    "pg": ("data_store", "postgres", None),
    "mysql2": ("data_store", "mysql", None),
    "sidekiq": ("data_store", "redis", None),
    "graphql": ("api", "graphql-ruby", None),
    "anthropic": ("ai", "anthropic", None),
    "ruby-openai": ("ai", "openai", None),
    "spree": ("commerce", "spree", None),
    "solidus": ("commerce", "solidus", None),
    "devise": ("auth", "devise", None),
    "acts_as_tenant": ("tenancy", "acts_as_tenant", None),
    "apartment": ("tenancy", "apartment", None),
    "ros-apartment": ("tenancy", "apartment", None),
    "stripe": ("payments", "stripe", None),
}

PHP_SIGNALS = {
    "laravel/framework": ("framework", "laravel", "backend"),
    "symfony/framework-bundle": ("framework", "symfony", "backend"),
    "laravel/octane": ("framework", "laravel-octane", None),
    "drupal/core": ("cms", "drupal", None),
    "drupal/core-recommended": ("cms", "drupal", None),
    "roots/wordpress": ("cms", "wordpress", None),
    "johnpbloch/wordpress": ("cms", "wordpress", None),
    "magento/product-community-edition": ("cms", "magento", None),
    "magento/product-enterprise-edition": ("cms", "magento", None),
    "magento/magento2-base": ("cms", "magento", None),
    "predis/predis": ("data_store", "redis", None),
    "spatie/laravel-responsecache": ("in_process", "laravel-responsecache", None),
    "doctrine/orm": ("orm", "doctrine", None),
    "nuwave/lighthouse": ("api", "lighthouse-graphql", None),
    "sylius/sylius": ("commerce", "sylius", None),
    "stancl/tenancy": ("tenancy", "stancl-tenancy", None),
    "openai-php/client": ("ai", "openai", None),
    "anthropic-ai/sdk": ("ai", "anthropic", None),
}

# substring of group:artifact -> signal
JVM_SIGNALS = [
    ("org.springframework.boot", ("framework", "spring-boot", "backend")),
    ("io.quarkus", ("framework", "quarkus", "backend")),
    ("io.micronaut", ("framework", "micronaut", "backend")),
    ("hibernate-core", ("orm", "hibernate", None)),
    ("org.hibernate", ("orm", "hibernate", None)),
    ("hibernate-jcache", ("orm", "hibernate-l2", None)),
    ("com.github.ben-manes.caffeine", ("in_process", "caffeine", None)),
    ("org.ehcache", ("in_process", "ehcache", None)),
    ("spring-boot-starter-data-redis", ("data_store", "redis", None)),
    ("io.lettuce", ("data_store", "redis", None)),
    ("redis.clients:jedis", ("data_store", "redis", None)),
    ("org.redisson", ("data_store", "redis", None)),
    ("org.postgresql", ("data_store", "postgres", None)),
    ("com.mysql", ("data_store", "mysql", None)),
    ("com.graphql-java", ("api", "graphql-java", None)),
    ("spring-boot-starter-graphql", ("api", "spring-graphql", None)),
    ("io.grpc", ("api", "grpc", None)),
    ("com.squareup.okhttp3", ("mobile", "okhttp", None)),
    ("com.squareup.retrofit2", ("mobile", "retrofit", None)),
    ("io.coil-kt", ("mobile", "coil", None)),
    ("com.github.bumptech.glide", ("mobile", "glide", None)),
    ("androidx.room", ("mobile", "room", None)),
    ("com.anthropic", ("ai", "anthropic", None)),
    ("dev.langchain4j", ("ai", "langchain4j", None)),
    ("org.springframework.ai", ("ai", "spring-ai", None)),
]

NUGET_SIGNALS = [
    ("Microsoft.Extensions.Caching.Hybrid", ("in_process", "hybridcache", None)),
    ("Microsoft.Extensions.Caching.Memory", ("in_process", "imemorycache", None)),
    ("Microsoft.Extensions.Caching.StackExchangeRedis", ("data_store", "redis", None)),
    ("Microsoft.AspNetCore.OutputCaching.StackExchangeRedis", ("data_store", "redis", None)),
    ("StackExchange.Redis", ("data_store", "redis", None)),
    ("ZiggyCreatures.FusionCache", ("in_process", "fusioncache", None)),
    ("EasyCaching", ("in_process", "easycaching", None)),
    ("Microsoft.EntityFrameworkCore", ("orm", "ef-core", None)),
    ("Npgsql", ("data_store", "postgres", None)),
    ("HotChocolate", ("api", "hotchocolate", None)),
    ("Grpc.AspNetCore", ("api", "grpc", None)),
    ("Anthropic", ("ai", "anthropic", None)),
    ("OpenAI", ("ai", "openai", None)),
    ("Microsoft.SemanticKernel", ("ai", "semantic-kernel", None)),
]

GO_SIGNALS = [
    ("github.com/maypok86/otter", ("in_process", "otter", None)),
    ("github.com/dgraph-io/ristretto", ("in_process", "ristretto", None)),
    ("github.com/groupcache/groupcache-go", ("in_process", "groupcache-go", None)),
    ("github.com/golang/groupcache", ("in_process", "groupcache-legacy", None)),
    ("github.com/allegro/bigcache", ("in_process", "bigcache", None)),
    ("github.com/coocood/freecache", ("in_process", "freecache", None)),
    ("github.com/eko/gocache", ("in_process", "gocache", None)),
    ("golang.org/x/sync", ("in_process", "singleflight", None)),
    ("github.com/redis/go-redis", ("data_store", "redis", None)),
    ("github.com/go-redis/redis", ("data_store", "redis", None)),
    ("github.com/redis/rueidis", ("data_store", "redis", None)),
    ("github.com/valkey-io/valkey-go", ("data_store", "valkey", None)),
    ("github.com/bradfitz/gomemcache", ("data_store", "memcached", None)),
    ("github.com/jackc/pgx", ("data_store", "postgres", None)),
    ("github.com/lib/pq", ("data_store", "postgres", None)),
    ("gorm.io/gorm", ("orm", "gorm", None)),
    ("entgo.io/ent", ("orm", "ent", None)),
    ("github.com/99designs/gqlgen", ("api", "gqlgen", None)),
    ("google.golang.org/grpc", ("api", "grpc", None)),
    ("connectrpc.com/connect", ("api", "connect-rpc", None)),
    ("github.com/gin-gonic/gin", ("framework", "gin", "backend")),
    ("github.com/labstack/echo", ("framework", "echo", "backend")),
    ("github.com/go-chi/chi", ("framework", "chi", "backend")),
    ("github.com/gofiber/fiber", ("framework", "fiber", "backend")),
    ("github.com/anthropics/anthropic-sdk-go", ("ai", "anthropic", None)),
    ("github.com/openai/openai-go", ("ai", "openai", None)),
    ("github.com/gohugoio/hugo", ("framework", "hugo", "static")),
]

HEX_SIGNALS = {
    "phoenix": ("framework", "phoenix", "backend"),
    "phoenix_live_view": ("realtime", "liveview", None),
    "cachex": ("in_process", "cachex", None),
    "nebulex": ("in_process", "nebulex", None),
    "redix": ("data_store", "redis", None),
    "ecto": ("orm", "ecto", None),
    "ecto_sql": ("orm", "ecto", None),
    "postgrex": ("data_store", "postgres", None),
    "absinthe": ("api", "absinthe", None),
}

DART_SIGNALS = {
    "flutter": ("mobile", "flutter", None),
    "dio_cache_interceptor": ("mobile", "dio_cache_interceptor", None),
    "cached_network_image": ("mobile", "cached_network_image", None),
    "flutter_cache_manager": ("mobile", "flutter_cache_manager", None),
    "drift": ("mobile", "drift", None),
    "sqflite": ("mobile", "sqflite", None),
    "isar": ("mobile", "isar", None),
    "powersync": ("mobile", "powersync", None),
}

COMPOSE_IMAGES = {
    "nginx": ("proxy", "nginx"),
    "openresty": ("proxy", "nginx"),
    "varnish": ("proxy", "varnish"),
    "haproxy": ("proxy", "haproxy"),
    "caddy": ("proxy", "caddy"),
    "traefik": ("proxy", "traefik"),
    "envoy": ("proxy", "envoy"),
    "redis": ("data_store", "redis"),
    "valkey": ("data_store", "valkey"),
    "keydb": ("data_store", "keydb"),
    "dragonfly": ("data_store", "dragonfly"),
    "memcached": ("data_store", "memcached"),
    "postgres": ("data_store", "postgres"),
    "postgis": ("data_store", "postgres"),
    "mysql": ("data_store", "mysql"),
    "mariadb": ("data_store", "mysql"),
    "mongo": ("data_store", "mongodb"),
    "pgbouncer": ("data_store", "pgbouncer"),
    "elasticsearch": ("data_store", "elasticsearch"),
    "opensearch": ("data_store", "opensearch"),
    "wordpress": ("cms", "wordpress"),
    "drupal": ("cms", "drupal"),
    "ghost": ("cms", "ghost"),
}

TERRAFORM_SIGNALS = [
    (r'"aws_cloudfront_(distribution|cache_policy|origin_request_policy|function)"', ("cdn", "cloudfront")),
    (r'"aws_api_gateway_(stage|method_settings|rest_api)"', ("api", "aws-api-gateway")),
    (r'"aws_apigatewayv2_', ("api", "aws-http-api")),
    (r'"aws_elasticache_', ("data_store", "elasticache")),
    (r'"aws_lambda_function"', ("hosting", "aws-lambda")),
    (r'"fastly_service_(vcl|compute)"', ("cdn", "fastly")),
    (r'"akamai_property', ("cdn", "akamai")),
    (r'"google_compute_backend_(service|bucket)"[\s\S]{0,2000}?enable_cdn\s*=\s*true', ("cdn", "google-cloud-cdn")),
    (r'"google_network_services_edge_cache_', ("cdn", "google-media-cdn")),
    (r'"google_redis_instance"', ("data_store", "memorystore")),
    (r'"azurerm_cdn_frontdoor_', ("cdn", "azure-front-door")),
    (r'"azurerm_cdn_(profile|endpoint)"', ("cdn", "azure-cdn")),
    (r'"azurerm_redis_cache"', ("data_store", "azure-cache-redis")),
    (r'"azurerm_api_management', ("api", "azure-apim")),
    (r'"cloudflare_(ruleset|zone|worker|workers_script|page_rule)', ("cdn", "cloudflare")),
    (r'"kong_', ("api", "kong")),
    (r'"bunnynet_', ("cdn", "bunny")),
]

CATEGORY_KEYS = {
    "client_cache": "client_caches",
    "hosting": "hosting",
    "cdn": "cdn",
    "proxy": "proxies",
    "data_store": "data_stores",
    "orm": "orm",
    "cms": "cms",
    "commerce": "cms",
    "api": "api",
    "mobile": "mobile",
    "ai": "ai",
    "ci": "ci",
    "service_worker": "service_worker",
    "in_process": "data_stores",
}

# --------------------------------------------------------------------------- helpers


def read_text(path: Path, limit: int = MAX_READ_BYTES) -> str:
    try:
        with open(path, "rb") as fh:
            data = fh.read(limit)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def load_json(path: Path):
    text = read_text(path, 8 * MAX_READ_BYTES)
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        # tolerate JSONC (comments, trailing commas) for wrangler.jsonc, tsconfig-like files
        stripped = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", "", text)
        stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
        try:
            return json.loads(stripped)
        except ValueError:
            return None


class Scan:
    def __init__(self, root: Path):
        self.root = root
        self.files: list[Path] = []
        self.dirs: set[str] = set()
        self.truncated = False
        self.skipped: set[str] = set()

    def walk(self) -> None:
        root_depth = len(self.root.parts)
        for dirpath, dirnames, filenames in os.walk(self.root):
            here = Path(dirpath)
            depth = len(here.parts) - root_depth
            rel_dir = here.relative_to(self.root).as_posix()
            keep = []
            for d in dirnames:
                rel = f"{rel_dir}/{d}" if rel_dir != "." else d
                if d in SKIP_DIRS or rel in SKIP_DIRS or (d.startswith(".") and d not in {".github", ".vercel", ".circleci", ".gitlab", ".claude-plugin", ".magento", ".platform", ".do"}):
                    self.skipped.add(d)
                    continue
                if depth >= MAX_DEPTH:
                    self.truncated = True
                    continue
                keep.append(d)
                self.dirs.add(rel)
            dirnames[:] = keep
            for f in filenames:
                if len(self.files) >= MAX_FILES:
                    self.truncated = True
                    dirnames[:] = []
                    break
                self.files.append(here / f)

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()

    def named(self, *names: str) -> list[Path]:
        wanted = set(names)
        return [p for p in self.files if p.name in wanted]

    def matching(self, pattern: str) -> list[Path]:
        rx = re.compile(pattern)
        return [p for p in self.files if rx.search(self.rel(p))]


class Findings:
    def __init__(self):
        self.items: dict[str, dict[str, dict]] = {}
        self.frameworks: dict[str, dict] = {}
        self.hints: dict[str, set] = {}

    def add(self, category: str, name: str, source: str, version: str | None = None, kind: str | None = None,
            via: str | None = None) -> None:
        if category == "framework":
            entry = self.frameworks.setdefault(name, {"name": name, "version": None, "kind": kind, "source": source, "config": {}})
            if version and not entry["version"]:
                entry["version"] = version
                entry["source"] = source
            return
        if category in ("realtime", "media", "internal", "auth", "payments", "tenancy", "commerce_hint"):
            self.hints.setdefault(category, set()).add(name)
            return
        key = CATEGORY_KEYS.get(category, category)
        bucket = self.items.setdefault(key, {})
        entry = bucket.setdefault(name, {"name": name, "version": None, "source": source})
        if category == "in_process":
            entry["layer"] = "in-process"
        if category == "commerce":
            self.hints.setdefault("commerce", set()).add(name)
        if key in ("hosting", "cdn"):
            version = None  # an adapter or CLI version says nothing about the platform
        if version and not entry.get("version"):
            entry["version"] = version
            if via and via != name:
                entry["via"] = via  # the version is this package's version (client library, adapter)

    def has(self, key: str, *names: str) -> bool:
        bucket = self.items.get(key, {})
        return any(n in bucket for n in names) if names else bool(bucket)

    def fw(self, *names: str) -> bool:
        return any(n in self.frameworks for n in names)


# --------------------------------------------------------------------------- lockfile versions


def npm_versions(scan: Scan) -> tuple[dict[str, str], str]:
    versions: dict[str, str] = {}
    source = ""
    for lock in scan.named("package-lock.json", "npm-shrinkwrap.json"):
        data = load_json(lock)
        if not isinstance(data, dict):
            continue
        source = scan.rel(lock)
        for key, meta in (data.get("packages") or {}).items():
            if key.startswith("node_modules/") and isinstance(meta, dict) and meta.get("version"):
                name = key.split("node_modules/")[-1]
                versions.setdefault(name, meta["version"])
        for name, meta in (data.get("dependencies") or {}).items():
            if isinstance(meta, dict) and meta.get("version"):
                versions.setdefault(name, meta["version"])
    for lock in scan.named("pnpm-lock.yaml"):
        text = read_text(lock, 16 * MAX_READ_BYTES)
        source = source or scan.rel(lock)
        for m in re.finditer(r"(?m)^\s+'?/?((?:@[^/@\s']+/)?[^/@\s':]+)[@/](\d[\w.+-]*)", text):
            versions.setdefault(m.group(1), m.group(2))
        for m in re.finditer(r"(?m)^\s+'?((?:@[^/@\s']+/)?[^/@\s':]+)'?:\n\s+specifier:[^\n]*\n\s+version:\s*'?(\d[\w.+-]*)", text):
            versions[m.group(1)] = m.group(2)
    for lock in scan.named("yarn.lock"):
        text = read_text(lock, 16 * MAX_READ_BYTES)
        source = source or scan.rel(lock)
        for m in re.finditer(r'(?m)^"?((?:@[^/@\s"]+/)?[^@\s",]+)@[^\n]*:\n(?:\s+[^\n]*\n)*?\s+version:?\s+"?(\d[\w.+-]*)', text):
            versions.setdefault(m.group(1), m.group(2))
    for lock in scan.named("bun.lock"):
        text = read_text(lock, 16 * MAX_READ_BYTES)
        source = source or scan.rel(lock)
        for m in re.finditer(r'"((?:@[^/"]+/)?[^@"/]+)":\s*\["(?:@[^/"]+/)?[^@"]+@(\d[\w.+-]*)"', text):
            versions.setdefault(m.group(1), m.group(2))
    return versions, source


def spec_version(spec: str) -> str | None:
    m = re.search(r"(\d+(?:\.\d+){0,2}[\w.+-]*)", spec or "")
    return m.group(1) if m else None


def major(version: str | None) -> int | None:
    if not version:
        return None
    m = re.match(r"\D*(\d+)", version)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- ecosystem readers


def scan_node(scan: Scan, found: Findings, notes: list[str]) -> dict[str, str]:
    lock_versions, lock_source = npm_versions(scan)
    manifests = [p for p in scan.named("package.json")]
    declared: dict[str, str] = {}
    for manifest in manifests:
        data = load_json(manifest)
        if not isinstance(data, dict):
            continue
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for name, spec in (data.get(field) or {}).items():
                declared.setdefault(name, str(spec))
    for name, spec in declared.items():
        sig = NPM_SIGNALS.get(name)
        if not sig:
            if name.startswith("@ai-sdk/"):
                sig = ("ai", "vercel-ai-sdk", None)
            elif name.startswith("@langchain/"):
                sig = ("ai", "langchain", None)
            elif name in ("@remix-run/serve", "@remix-run/dev", "@remix-run/cloudflare", "@remix-run/express"):
                sig = ("framework", "remix", "fullstack")
            elif name.startswith("@storyblok/"):
                sig = ("cms", "storyblok", None)
            elif name.startswith("workbox-"):
                sig = ("service_worker", "workbox", None)
            elif name.startswith("@upstash/") and name != "@upstash/vector":
                sig = ("data_store", "upstash", None)
            else:
                continue
        category, label, kind = sig
        version = lock_versions.get(name)
        source = lock_source if version else "package.json"
        if not version:
            version = spec_version(spec)
        found.add(category, label, source, version, kind, via=name)
    # plain Vite SPA when nothing else claims the frontend
    if "vite" in declared and not found.fw(
        "nextjs", "nuxt", "sveltekit", "react-router", "remix", "astro", "angular", "qwik",
        "solidstart", "tanstack-start", "vitepress", "gatsby", "docusaurus",
    ):
        found.add("framework", "vite-spa", "package.json", lock_versions.get("vite") or spec_version(declared["vite"]), "frontend")
    if "react-router" in declared and "@react-router/dev" not in declared:
        notes.append("react-router without @react-router/dev: library (data/declarative) mode, not framework mode; client-side caching only.")
    lockfiles = [p.name for p in scan.named("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")]
    if len(set(lockfiles)) > 1:
        notes.append(f"Multiple JS lockfiles found ({', '.join(sorted(set(lockfiles)))}); versions come from the first readable one.")
    if declared and not lock_source:
        notes.append("No readable JS lockfile: versions are declared ranges from package.json, not resolved versions.")
    return declared


REQ_STRING = re.compile(r"""["']([A-Za-z0-9][A-Za-z0-9_.\-]*)(?:\[[^\]]*\])?\s*(?:(?:==|~=|>=|<=|>|<|\^|!=)\s*v?(\d[\w.+-]*))?[^"']*["']""")
TOML_KEY = re.compile(r"""(?m)^\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*=\s*(?:["']\D*(\d[\w.+-]*)?|\{[^}\n]*?version\s*=\s*["']\D*(\d[\w.+-]*)?)""")


def python_requirements(text: str) -> dict[str, str | None]:
    """Dependency names (lowercased) and versions from pyproject.toml, Pipfile, setup.cfg or setup.py.

    Only dependency regions are read, so words in descriptions don't count as packages.
    """
    reqs: dict[str, str | None] = {}
    # TOML tables whose header names dependencies: [tool.poetry.dependencies], [packages], [dev-packages] ...
    for m in re.finditer(r"(?ms)^\[([^\]\n]*(?:dependencies|packages)[^\]\n]*)\]\s*\n(.*?)(?=^\[|\Z)", text):
        header, body = m.group(1), m.group(2)
        if header.endswith("optional-dependencies") or header == "dependency-groups":
            for s in REQ_STRING.finditer(body):
                reqs.setdefault(s.group(1).lower(), s.group(2))
            continue
        for k in TOML_KEY.finditer(body):
            reqs.setdefault(k.group(1).lower(), k.group(2) or k.group(3))
    # PEP 621 arrays, setup.py install_requires, setup.cfg install_requires
    for m in re.finditer(r"""(?ms)(?:^|\s)(?:dependencies|install_requires|requires)\s*=\s*\[((?:[^\[\]"']|"[^"]*"|'[^']*')*)\]""", text):
        for s in REQ_STRING.finditer(m.group(1)):
            reqs.setdefault(s.group(1).lower(), s.group(2))
    for m in re.finditer(r"(?ms)^install_requires\s*=\s*\n((?:[ \t]+[^\n]+\n?)+)", text):
        for line in m.group(1).splitlines():
            r = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.\-]*)(?:\[[^\]]*\])?\s*(?:[=~<>!]=?\s*(\d[\w.+-]*))?", line)
            if r:
                reqs.setdefault(r.group(1).lower(), r.group(2))
    reqs.pop("python", None)
    return reqs


def scan_python(scan: Scan, found: Findings) -> None:
    names: dict[str, tuple[str | None, str]] = {}
    for req in scan.matching(r"(^|/)requirements[^/]*\.(txt|in)$"):
        for line in read_text(req).splitlines():
            m = re.match(r"\s*([A-Za-z0-9_.\-\[\]]+)\s*(?:[=~<>!]=?\s*([\w.+-]+))?", line)
            if m and not line.strip().startswith(("#", "-")):
                name = re.sub(r"\[.*\]", "", m.group(1)).lower()
                names.setdefault(name, (m.group(2), scan.rel(req)))
    for pp in scan.named("pyproject.toml", "Pipfile", "setup.py", "setup.cfg"):
        for name, version in python_requirements(read_text(pp)).items():
            names.setdefault(name, (version, scan.rel(pp)))
    for lock in scan.named("poetry.lock", "uv.lock", "pdm.lock"):
        text = read_text(lock, 16 * MAX_READ_BYTES)
        for m in re.finditer(r'(?m)^name\s*=\s*"([^"]+)"\s*\nversion\s*=\s*"([^"]+)"', text):
            name = m.group(1).lower()
            if name in PY_SIGNALS:
                names[name] = (m.group(2), scan.rel(lock))
    for name, (version, source) in names.items():
        sig = PY_SIGNALS.get(name)
        if sig:
            category, label, kind = sig
            found.add(category, label, source, version, kind, via=name)
    if scan.named("manage.py") and not found.fw("django"):
        found.add("framework", "django", "manage.py", None, "backend")
    if scan.named("mkdocs.yml") and not found.fw("mkdocs"):
        found.add("framework", "mkdocs", "mkdocs.yml", None, "static")


def scan_ruby(scan: Scan, found: Findings) -> None:
    lock_versions: dict[str, str] = {}
    for lock in scan.named("Gemfile.lock"):
        for m in re.finditer(r"(?m)^    ([a-z0-9_\-]+) \((\d[^)]*)\)", read_text(lock, 8 * MAX_READ_BYTES)):
            lock_versions.setdefault(m.group(1), m.group(2))
    for gemfile in scan.named("Gemfile"):
        text = read_text(gemfile)
        for name, (category, label, kind) in RUBY_SIGNALS.items():
            if re.search(r"""(?m)^\s*gem\s+['"]""" + re.escape(name) + r"""['"]""", text):
                version = lock_versions.get(name)
                found.add(category, label, "Gemfile.lock" if version else scan.rel(gemfile), version, kind, via=name)
    if scan.named("_config.yml") and lock_versions.get("jekyll"):
        found.add("framework", "jekyll", "Gemfile.lock", lock_versions["jekyll"], "static")


def scan_php(scan: Scan, found: Findings) -> None:
    lock_versions: dict[str, str] = {}
    for lock in scan.named("composer.lock"):
        data = load_json(lock)
        if isinstance(data, dict):
            for pkg in (data.get("packages") or []) + (data.get("packages-dev") or []):
                if isinstance(pkg, dict) and pkg.get("name"):
                    lock_versions[pkg["name"]] = str(pkg.get("version", "")).lstrip("v")
    composer_found = False
    for manifest in scan.named("composer.json"):
        data = load_json(manifest)
        if not isinstance(data, dict):
            continue
        composer_found = True
        reqs = {**(data.get("require") or {}), **(data.get("require-dev") or {})}
        for name, spec in reqs.items():
            sig = PHP_SIGNALS.get(name)
            if not sig and name.startswith("magento/"):
                sig = ("cms", "magento", None)
            if not sig:
                continue
            category, label, kind = sig
            version = lock_versions.get(name) or spec_version(str(spec))
            found.add(category, label, "composer.lock" if name in lock_versions else scan.rel(manifest), version, kind, via=name)
        php = reqs.get("php")
        if php:
            found.add("framework", "php", scan.rel(manifest), spec_version(str(php)), "backend")
    if composer_found and not found.fw("php", "laravel", "symfony"):
        found.add("framework", "php", "composer.json", None, "backend")


def scan_jvm(scan: Scan, found: Findings) -> None:
    for build in scan.named("pom.xml", "build.gradle", "build.gradle.kts", "libs.versions.toml"):
        text = read_text(build)
        for needle, (category, label, kind) in JVM_SIGNALS:
            if needle in text:
                version = None
                if label == "spring-boot":
                    m = re.search(r'org\.springframework\.boot["\')]*\s*(?:version\s*["\']|[^\n]*<version>)(\d[\w.\-]*)', text) or \
                        re.search(r"<parent>[\s\S]*?spring-boot-starter-parent[\s\S]*?<version>(\d[\w.\-]*)</version>", text) or \
                        re.search(r'spring-?boot\s*=\s*"(\d[\w.\-]*)"', text)
                    version = m.group(1) if m else None
                found.add(category, label, scan.rel(build), version, kind)
        if re.search(r"com\.android\.(application|library)", text):
            found.add("mobile", "android", scan.rel(build))


def scan_dotnet(scan: Scan, found: Findings) -> None:
    for proj in scan.matching(r"\.(csproj|fsproj)$"):
        text = read_text(proj)
        tfm = re.search(r"<TargetFrameworks?>([^<]+)</TargetFrameworks?>", text)
        version = None
        if tfm:
            m = re.search(r"net(\d+\.\d+)", tfm.group(1))
            version = m.group(1) if m else tfm.group(1)
        if 'Sdk="Microsoft.NET.Sdk.Web"' in text or "Microsoft.AspNetCore" in text:
            found.add("framework", "aspnet-core", scan.rel(proj), version, "backend")
        for needle, (category, label, kind) in NUGET_SIGNALS:
            if re.search(r'Include="' + re.escape(needle), text):
                found.add(category, label, scan.rel(proj), None, kind)
        if "Microsoft.NET.Sdk.Razor" in text or "Microsoft.Maui" in text:
            found.add("mobile", "maui", scan.rel(proj))


def scan_go(scan: Scan, found: Findings) -> None:
    for mod in scan.named("go.mod"):
        text = read_text(mod)
        goline = re.search(r"(?m)^go\s+(\d[\w.]*)", text)
        found.add("framework", "go", scan.rel(mod), goline.group(1) if goline else None, "backend")
        for needle, (category, label, kind) in GO_SIGNALS:
            m = re.search(re.escape(needle) + r"(?:/v\d+)?\s+v(\d[\w.\-+]*)", text)
            if m or needle in text:
                found.add(category, label, scan.rel(mod), m.group(1) if m else None, kind, via=needle)


def scan_elixir(scan: Scan, found: Findings) -> None:
    lock_versions: dict[str, str] = {}
    for lock in scan.named("mix.lock"):
        for m in re.finditer(r'"([a-z0-9_]+)":\s*\{:hex,\s*:[a-z0-9_]+,\s*"([^"]+)"', read_text(lock, 4 * MAX_READ_BYTES)):
            lock_versions[m.group(1)] = m.group(2)
    for mix in scan.named("mix.exs"):
        text = read_text(mix)
        found.add("framework", "elixir", scan.rel(mix), None, "backend")
        for name, (category, label, kind) in HEX_SIGNALS.items():
            if re.search(r"\{:" + re.escape(name) + r"\b", text):
                found.add(category, label, "mix.lock" if name in lock_versions else scan.rel(mix), lock_versions.get(name), kind, via=name)


def scan_mobile(scan: Scan, found: Findings) -> None:
    for pub in scan.named("pubspec.yaml"):
        text = read_text(pub)
        for name, (category, label, kind) in DART_SIGNALS.items():
            if re.search(r"(?m)^\s+" + re.escape(name) + r"\s*:", text) or (name == "flutter" and "sdk: flutter" in text):
                found.add(category, label, scan.rel(pub), None, kind)
    for pod in scan.named("Podfile", "Package.swift", "Cartfile"):
        text = read_text(pod)
        found.add("mobile", "ios", scan.rel(pod))
        for lib in ("Kingfisher", "SDWebImage", "Nuke", "Alamofire"):
            if lib in text:
                found.add("mobile", lib.lower(), scan.rel(pod))
    if any(d.endswith(".xcodeproj") or d.endswith(".xcworkspace") for d in scan.dirs):
        found.add("mobile", "ios", "*.xcodeproj")
    if scan.named("AndroidManifest.xml"):
        found.add("mobile", "android", "AndroidManifest.xml")


def scan_hosting_and_infra(scan: Scan, found: Findings, notes: list[str]) -> None:
    file_signals = {
        "vercel.json": ("hosting", "vercel"),
        "netlify.toml": ("hosting", "netlify"),
        "wrangler.toml": ("hosting", "cloudflare"),
        "wrangler.json": ("hosting", "cloudflare"),
        "wrangler.jsonc": ("hosting", "cloudflare"),
        "fastly.toml": ("hosting", "fastly"),
        "fly.toml": ("hosting", "fly"),
        "render.yaml": ("hosting", "render"),
        "railway.json": ("hosting", "railway"),
        "railway.toml": ("hosting", "railway"),
        "Procfile": ("hosting", "heroku"),
        "app.json": ("hosting", "heroku-or-expo"),
        "firebase.json": ("hosting", "firebase"),
        "amplify.yml": ("hosting", "aws-amplify"),
        "open-next.config.ts": ("hosting", "aws-opennext"),
        "serverless.yml": ("hosting", "aws-lambda"),
        "serverless.yaml": ("hosting", "aws-lambda"),
        "sst.config.ts": ("hosting", "aws-sst"),
        "cdk.json": ("hosting", "aws-cdk"),
        "template.yaml": ("hosting", "aws-sam?"),
        "app.yaml": ("hosting", "google-app-engine?"),
        ".edgerc": ("cdn", "akamai"),
        "staticwebapp.config.json": ("hosting", "azure-static-web-apps"),
    }
    for path in scan.files:
        sig = file_signals.get(path.name)
        if sig:
            category, label = sig
            if label == "heroku-or-expo":
                text = read_text(path)
                if '"expo"' in text:
                    continue
                label = "heroku"
            if label.endswith("?"):
                text = read_text(path)
                if label == "aws-sam?" and "AWS::Serverless" not in text:
                    continue
                if label == "google-app-engine?" and not re.search(r"(?m)^runtime:", text):
                    continue
                label = label[:-1]
            found.add(category, label, scan.rel(path))
    if ".vercel" in scan.dirs:
        found.add("hosting", "vercel", ".vercel/")
    # CDN implied by hosting platforms
    for host, cdn in (("vercel", "vercel"), ("netlify", "netlify"), ("cloudflare", "cloudflare"), ("fastly", "fastly"),
                      ("firebase", "firebase-hosting"), ("aws-amplify", "cloudfront"), ("aws-opennext", "cloudfront"), ("aws-sst", "cloudfront?")):
        if found.has("hosting", host):
            if cdn.endswith("?"):
                notes.append("SST/serverless deployments often front functions with CloudFront; confirm the CDN in the stack config.")
                continue
            found.add("cdn", cdn, f"hosting:{host}")
    for path in scan.matching(r"\.tf$|\.tf\.json$"):
        text = read_text(path)
        for pattern, (category, label) in TERRAFORM_SIGNALS:
            if re.search(pattern, text):
                found.add(category, label, scan.rel(path))
    for path in scan.matching(r"\.(bicep)$|azuredeploy\.json$"):
        text = read_text(path)
        if "Microsoft.Cdn/profiles" in text:
            found.add("cdn", "azure-front-door", scan.rel(path))
    for path in scan.matching(r"(^|/)(cdk|infra|lib|stacks?)/.*\.(ts|py)$"):
        text = read_text(path, 128 * 1024)
        if re.search(r"aws-cloudfront|aws_cloudfront|cloudfront\.Distribution", text):
            found.add("cdn", "cloudfront", scan.rel(path))
    for path in scan.named("sst.config.ts", "serverless.yml", "serverless.yaml"):
        text = read_text(path)
        if re.search(r"(?i)cloudfront|sst\.aws\.(Nextjs|Router|StaticSite|Astro|Remix|SvelteKit|Nuxt)", text):
            found.add("cdn", "cloudfront", scan.rel(path))
    # docker compose / k8s images
    for path in scan.matching(r"(^|/)(docker-)?compose[^/]*\.ya?ml$|(^|/)k8s/.*\.ya?ml$|(^|/)(helm|charts|deploy|manifests)/.*\.ya?ml$"):
        text = read_text(path)
        for m in re.finditer(r"(?m)^\s*image:\s*['\"]?(?:[\w.\-]+/)*([\w.\-]+)", text):
            image = m.group(1).lower()
            for key, (category, label) in COMPOSE_IMAGES.items():
                if image == key or image.startswith(key + "-") or image.startswith(key + ":") or image.split(":")[0] == key:
                    found.add(category, label, scan.rel(path))
    for path in scan.matching(r"(^|/)Dockerfile[^/]*$"):
        text = read_text(path)
        for m in re.finditer(r"(?mi)^FROM\s+(?:[\w.\-]+/)*([\w.\-]+)", text):
            image = m.group(1).lower()
            if image in ("nginx", "openresty", "varnish", "haproxy", "caddy", "traefik"):
                found.add("proxy", COMPOSE_IMAGES.get(image, ("proxy", image))[1], scan.rel(path))
    # proxy configs
    for path in scan.files:
        name = path.name
        rel = scan.rel(path)
        if name == "nginx.conf" or (name.endswith(".conf") and ("nginx" in rel or "sites-" in rel or "conf.d" in rel)):
            found.add("proxy", "nginx", rel)
        elif name.endswith(".vcl"):
            text = read_text(path, 64 * 1024)
            label = "fastly" if re.search(r"(?i)fastly|surrogate", text) and "vcl 4" not in text else "varnish"
            found.add("cdn" if label == "fastly" else "proxy", label, rel)
        elif name in ("haproxy.cfg",):
            found.add("proxy", "haproxy", rel)
        elif name == "Caddyfile":
            found.add("proxy", "caddy", rel)
        elif name in ("traefik.yml", "traefik.yaml", "traefik.toml"):
            found.add("proxy", "traefik", rel)
        elif name in ("envoy.yaml", "envoy.yml"):
            found.add("proxy", "envoy", rel)
        elif name in ("kong.yml", "kong.yaml") or rel.endswith("deck/kong.yaml"):
            found.add("api", "kong", rel)
    # api specs and protos
    for path in scan.files:
        n = path.name.lower()
        if n in ("openapi.yaml", "openapi.yml", "openapi.json", "swagger.json", "swagger.yaml"):
            found.add("api", "openapi", scan.rel(path))
        elif n.endswith(".proto"):
            found.add("api", "protobuf", scan.rel(path))
        elif n in ("router.yaml", "supergraph.yaml"):
            found.add("api", "apollo-router", scan.rel(path))
        elif n in ("persisted-query-manifest.json",):
            found.add("api", "persisted-queries", scan.rel(path))


def scan_cms_files(scan: Scan, found: Findings) -> None:
    if scan.named("wp-config.php", "wp-config-sample.php") or "wp-content" in {d.split("/")[-1] for d in scan.dirs}:
        found.add("cms", "wordpress", "wp-config.php / wp-content")
        plugins = {d.split("/")[-1] for d in scan.dirs if "/plugins/" in f"/{d}/" and d.count("/") >= 2}
        for plugin in ("woocommerce", "redis-cache", "litespeed-cache", "wp-rocket", "w3-total-cache", "wp-super-cache", "cloudflare"):
            if plugin in plugins:
                if plugin == "woocommerce":
                    found.hints.setdefault("commerce", set()).add("woocommerce")
                found.add("cms", f"wp-plugin:{plugin}", "wp-content/plugins")
        for dropin in ("object-cache.php", "advanced-cache.php"):
            if any(p.name == dropin and "wp-content" in scan.rel(p) for p in scan.files):
                found.add("cms", f"wp-dropin:{dropin}", "wp-content")
    if any(scan.rel(p).endswith("bin/magento") for p in scan.files):
        found.add("cms", "magento", "bin/magento")
    if any(scan.rel(p).endswith("layout/theme.liquid") for p in scan.files):
        found.add("cms", "shopify-liquid", "layout/theme.liquid")
    if any(scan.rel(p).endswith("core/lib/Drupal.php") for p in scan.files):
        found.add("cms", "drupal", "core/lib/Drupal.php")
    for path in scan.named("hugo.toml", "hugo.yaml", "hugo.json", "config.toml"):
        text = read_text(path, 64 * 1024)
        if path.name.startswith("hugo.") or re.search(r"(?m)^baseURL\s*=", text):
            found.add("framework", "hugo", scan.rel(path), None, "static")
    if scan.named(".eleventy.js", "eleventy.config.js", "eleventy.config.mjs") and not found.fw("eleventy"):
        found.add("framework", "eleventy", "eleventy config", None, "static")


def scan_service_workers(scan: Scan, found: Findings) -> None:
    for path in scan.files:
        n = path.name
        if n in ("sw.js", "service-worker.js", "serviceworker.js", "sw.ts", "service-worker.ts", "ngsw-config.json"):
            found.add("service_worker", "custom-sw" if n != "ngsw-config.json" else "angular-sw", scan.rel(path))
        elif n in ("manifest.webmanifest", "site.webmanifest"):
            found.add("service_worker", "web-manifest", scan.rel(path))


def scan_ci(scan: Scan, found: Findings) -> None:
    for path in scan.files:
        rel = scan.rel(path)
        if rel.startswith(".github/workflows/") and path.suffix in (".yml", ".yaml"):
            found.add("ci", "github-actions", ".github/workflows")
        elif path.name == ".gitlab-ci.yml":
            found.add("ci", "gitlab-ci", rel)
        elif rel == ".circleci/config.yml":
            found.add("ci", "circleci", rel)
        elif path.name in ("azure-pipelines.yml", "bitbucket-pipelines.yml", "Jenkinsfile"):
            found.add("ci", path.name.split(".")[0].lower(), rel)
        elif path.name in ("turbo.json", "nx.json"):
            found.add("ci", path.name.split(".")[0], rel)
        elif path.name.startswith("Dockerfile"):
            found.add("ci", "docker", rel)


# --------------------------------------------------------------------------- framework config


def inspect_framework_configs(scan: Scan, found: Findings, notes: list[str]) -> None:
    nxt = found.frameworks.get("nextjs")
    if nxt:
        for cfg in scan.matching(r"(^|/)next\.config\.(js|mjs|cjs|ts|mts)$"):
            text = read_text(cfg)
            conf = nxt["config"]
            conf["file"] = scan.rel(cfg)
            conf["cacheComponents"] = bool(re.search(r"cacheComponents\s*:\s*true", text))
            conf["cacheHandler"] = bool(re.search(r"\bcacheHandler\s*:", text))
            conf["cacheHandlers"] = bool(re.search(r"\bcacheHandlers\s*:", text))
            m = re.search(r"\boutput\s*:\s*['\"](export|standalone)['\"]", text)
            conf["output"] = m.group(1) if m else None
            conf["legacy_flags"] = sorted(set(re.findall(r"\b(dynamicIO|useCache|ppr)\s*:", text)))
            conf["cacheMaxMemorySize"] = bool(re.search(r"cacheMaxMemorySize", text))
            break
        mj = major(nxt.get("version"))
        model = "cache-components" if nxt["config"].get("cacheComponents") else "previous"
        nxt["config"]["model"] = model
        if nxt["config"].get("legacy_flags"):
            notes.append("next.config uses removed experimental flags " + ", ".join(nxt["config"]["legacy_flags"]) + " (replaced by cacheComponents in Next 16).")
        if mj and mj >= 16:
            notes.append("Next.js 16: one-argument revalidateTag(tag) is deprecated; run find_cache_primitives.py to list calls.")
        if nxt["config"].get("output") == "standalone" and not nxt["config"].get("cacheHandler"):
            notes.append("Next.js standalone output without a cacheHandler: fine for one instance; multi-instance needs a shared cacheHandler/cacheHandlers.")
    kit = found.frameworks.get("sveltekit")
    if kit:
        mj = major(kit.get("version"))
        kit["config"]["config_location"] = "vite.config (sveltekit plugin)" if (mj or 0) >= 3 else "svelte.config.js"
        for cfg in scan.matching(r"(^|/)(vite\.config\.(js|ts|mjs)|svelte\.config\.(js|mjs))$"):
            text = read_text(cfg)
            m = re.search(r"adapter-(vercel|netlify|cloudflare|node|static|auto)", text)
            if m:
                kit["config"]["adapter"] = m.group(1)
    for name in ("nuxt", "nitro"):
        fw = found.frameworks.get(name)
        if fw:
            for cfg in scan.matching(r"(^|/)(nuxt|nitro)\.config\.(ts|js|mjs)$"):
                text = read_text(cfg)
                fw["config"]["routeRules"] = "routeRules" in text
                m = re.search(r"preset\s*:\s*['\"]([\w-]+)['\"]", text)
                if m:
                    fw["config"]["preset"] = m.group(1)
                fw["config"]["storage"] = bool(re.search(r"\bstorage\s*:", text))
    astro = found.frameworks.get("astro")
    if astro:
        for cfg in scan.matching(r"(^|/)astro\.config\.(mjs|js|ts)$"):
            text = read_text(cfg)
            m = re.search(r"\boutput\s*:\s*['\"](server|static|hybrid)['\"]", text)
            astro["config"]["output"] = m.group(1) if m else "static (default)"
            astro["config"]["route_cache"] = bool(re.search(r"\bcache\s*:\s*\{", text))
            astro["config"]["routeRules"] = "routeRules" in text
    rr = found.frameworks.get("react-router")
    if rr:
        rr["config"]["mode"] = "framework"
        if scan.matching(r"(^|/)react-router\.config\.(ts|js)$"):
            text = read_text(scan.matching(r"(^|/)react-router\.config\.(ts|js)$")[0])
            rr["config"]["ssr"] = not bool(re.search(r"ssr\s*:\s*false", text))


# --------------------------------------------------------------------------- archetypes and routing


def archetypes(found: Findings, declared_npm: dict[str, str]) -> list[dict]:
    cands: list[dict] = []

    def add(aid: str, conf: float, evidence: list[str]) -> None:
        cands.append({"id": aid, "confidence": round(conf, 2), "evidence": evidence})

    hints = found.hints
    cms = set(found.items.get("cms", {}))
    if found.items.get("ai"):
        add("ai-llm-app", 0.7, ["LLM/vector SDKs: " + ", ".join(sorted(found.items["ai"]))])
    commerce = set(hints.get("commerce", set())) | ({"shopify"} if cms & {"shopify-hydrogen", "shopify-liquid"} else set()) | ({"magento"} if "magento" in cms else set())
    if commerce:
        add("ecommerce", 0.8, ["commerce platform: " + ", ".join(sorted(commerce))])
    elif hints.get("payments") and (found.fw("nextjs", "nuxt", "sveltekit", "remix", "react-router", "rails", "django", "laravel")):
        add("ecommerce", 0.3, ["payments SDK with a web framework (could also be SaaS billing)"])
    static_fw = [f for f, e in found.frameworks.items() if e.get("kind") == "static"]
    nxt = found.frameworks.get("nextjs", {})
    if nxt.get("config", {}).get("output") == "export":
        static_fw.append("nextjs (output: export)")
    astro = found.frameworks.get("astro", {})
    if astro and astro.get("config", {}).get("output", "static (default)").startswith("static"):
        static_fw.append("astro (static output)")
    if static_fw:
        add("static-docs-marketing", 0.75, ["static/SSG frameworks: " + ", ".join(sorted(static_fw))])
    content_cms = cms & {"wordpress", "drupal", "contentful", "sanity", "strapi", "payload", "storyblok", "prismic", "directus", "ghost"}
    if content_cms and not commerce:
        add("news-media", 0.4, ["content CMS: " + ", ".join(sorted(content_cms)) + " (or static-docs-marketing; confirm publish frequency)"])
    if hints.get("tenancy"):
        add("saas-multitenant", 0.75, ["tenancy library: " + ", ".join(sorted(hints["tenancy"]))])
    elif hints.get("auth") and not commerce:
        add("saas-multitenant", 0.35, ["auth library: " + ", ".join(sorted(hints["auth"])) + "; confirm tenancy model"])
    if hints.get("realtime"):
        add("realtime-collab", 0.5, ["realtime libraries: " + ", ".join(sorted(hints["realtime"]))])
    if hints.get("media"):
        add("video-media", 0.6, ["media/video libraries: " + ", ".join(sorted(hints["media"]))])
    if hints.get("internal"):
        add("internal-tool", 0.6, ["admin frameworks: " + ", ".join(sorted(hints["internal"]))])
    frontend = [f for f, e in found.frameworks.items() if e.get("kind") in ("frontend", "fullstack", "static")]
    backend = [f for f, e in found.frameworks.items() if e.get("kind") == "backend"]
    api = set(found.items.get("api", {}))
    if found.items.get("mobile"):
        add("mobile-backend", 0.6 if backend else 0.45, ["mobile client: " + ", ".join(sorted(found.items["mobile"]))])
    api_first = {"fastapi", "starlette", "litestar", "express", "fastify", "nestjs", "koa", "hono",
                 "go", "gin", "echo", "chi", "fiber", "aspnet-core", "spring-boot", "quarkus", "micronaut"}
    strong_api = api & {"openapi", "aws-api-gateway", "aws-http-api", "kong", "azure-apim", "apollo-server",
                        "graphql-yoga", "hive-gateway", "protobuf", "connect-rpc", "grpc"}
    if strong_api and not frontend and not cms:
        add("public-api", 0.55, ["API surface without a frontend framework: " + ", ".join(sorted(strong_api))])
    elif "django-rest-framework" in api and not frontend:
        add("public-api", 0.35, ["Django REST framework (the app may also render HTML)"])
    elif set(backend) & api_first and not frontend and not cms and not found.items.get("mobile"):
        add("public-api", 0.3, ["API-first backend framework only: " + ", ".join(sorted(set(backend) & api_first))])
    cands.sort(key=lambda c: -c["confidence"])
    return cands


ROUTING_FRAMEWORKS = {
    "nextjs": "references/frameworks/nextjs.md",
    "nuxt": "references/frameworks/nuxt-nitro.md",
    "nitro": "references/frameworks/nuxt-nitro.md",
    "sveltekit": "references/frameworks/sveltekit.md",
    "react-router": "references/frameworks/react-router-remix.md",
    "remix": "references/frameworks/react-router-remix.md",
    "astro": "references/frameworks/astro.md",
    "angular": "references/frameworks/other-frontend.md",
    "gatsby": "references/frameworks/other-frontend.md",
    "qwik": "references/frameworks/other-frontend.md",
    "solidstart": "references/frameworks/other-frontend.md",
    "tanstack-start": "references/frameworks/other-frontend.md",
    "vite-spa": "references/frameworks/other-frontend.md",
    "docusaurus": "references/frameworks/other-frontend.md",
    "vitepress": "references/frameworks/other-frontend.md",
    "eleventy": "references/frameworks/other-frontend.md",
    "hugo": "references/frameworks/other-frontend.md",
    "jekyll": "references/frameworks/other-frontend.md",
    "mkdocs": "references/frameworks/other-frontend.md",
    "rails": "references/frameworks/rails.md",
    "django": "references/frameworks/django.md",
    "laravel": "references/frameworks/laravel-php.md",
    "laravel-octane": "references/frameworks/laravel-php.md",
    "symfony": "references/frameworks/laravel-php.md",
    "php": "references/frameworks/laravel-php.md",
    "spring-boot": "references/frameworks/spring-jvm.md",
    "quarkus": "references/frameworks/spring-jvm.md",
    "micronaut": "references/frameworks/spring-jvm.md",
    "aspnet-core": "references/frameworks/aspnet.md",
    "express": "references/frameworks/node-backends.md",
    "fastify": "references/frameworks/node-backends.md",
    "nestjs": "references/frameworks/node-backends.md",
    "koa": "references/frameworks/node-backends.md",
    "hono": "references/frameworks/node-backends.md",
    "fastapi": "references/frameworks/python-web.md",
    "flask": "references/frameworks/python-web.md",
    "starlette": "references/frameworks/python-web.md",
    "litestar": "references/frameworks/python-web.md",
    "go": "references/frameworks/go.md",
    "gin": "references/frameworks/go.md",
    "echo": "references/frameworks/go.md",
    "chi": "references/frameworks/go.md",
    "fiber": "references/frameworks/go.md",
    "elixir": "references/frameworks/elixir.md",
    "phoenix": "references/frameworks/elixir.md",
}

ROUTING_CMS = {
    "wordpress": "references/cms/wordpress.md",
    "drupal": "references/cms/drupal.md",
    "shopify-hydrogen": "references/cms/shopify-hydrogen.md",
    "shopify-liquid": "references/cms/shopify-hydrogen.md",
    "magento": "references/cms/magento.md",
}
HEADLESS = {"contentful", "sanity", "strapi", "payload", "storyblok", "prismic", "directus", "ghost"}

ROUTING_PLATFORMS = {
    "vercel": "references/platforms/vercel.md",
    "netlify": "references/platforms/netlify.md",
    "cloudflare": "references/platforms/cloudflare.md",
    "fastly": "references/platforms/fastly.md",
    "cloudfront": "references/platforms/cloudfront.md",
    "aws-opennext": "references/platforms/cloudfront.md",
    "aws-amplify": "references/platforms/cloudfront.md",
    "akamai": "references/platforms/akamai.md",
    "google-cloud-cdn": "references/platforms/gcp-azure-cdn.md",
    "google-media-cdn": "references/platforms/gcp-azure-cdn.md",
    "azure-front-door": "references/platforms/gcp-azure-cdn.md",
    "azure-cdn": "references/platforms/gcp-azure-cdn.md",
    "fly": "references/platforms/other-hosts.md",
    "render": "references/platforms/other-hosts.md",
    "railway": "references/platforms/other-hosts.md",
    "heroku": "references/platforms/other-hosts.md",
    "firebase": "references/platforms/other-hosts.md",
    "firebase-hosting": "references/platforms/other-hosts.md",
    "bunny": "references/platforms/other-hosts.md",
    "azure-static-web-apps": "references/platforms/gcp-azure-cdn.md",
}

SERVERLESS_HOSTS = {"vercel", "netlify", "cloudflare", "aws-lambda", "aws-sst", "aws-opennext", "aws-amplify", "fastly", "firebase"}
SERVERLESS_STORES = {"upstash", "upstash-redis", "vercel-kv", "vercel-edge-config", "netlify-blobs", "libsql"}
DISTRIBUTED = {"redis", "valkey", "memcached", "keydb", "dragonfly", "solid_cache", "elasticache", "memorystore", "azure-cache-redis", "upstash", "upstash-redis", "vercel-kv"}
DATABASES = {"postgres", "mysql", "mongodb", "pgbouncer", "supabase", "libsql"}


def route(found: Findings) -> tuple[list[str], list[dict]]:
    read: list[str] = list(ALWAYS_READ)

    def want(path: str) -> None:
        if path not in read:
            read.append(path)

    web = bool(found.frameworks) or bool(found.items.get("cms"))
    if web:
        want("references/layers/browser-platform.md")
        want("references/layers/cdn-concepts.md")
    for name in found.frameworks:
        if name in ROUTING_FRAMEWORKS:
            want(ROUTING_FRAMEWORKS[name])
    if found.items.get("client_caches"):
        want("references/frameworks/client-data-caches.md")
    for name in found.items.get("cms", {}):
        if name in ROUTING_CMS:
            want(ROUTING_CMS[name])
        if name in HEADLESS:
            want("references/cms/headless-cms.md")
    for key in ("hosting", "cdn"):
        for name in found.items.get(key, {}):
            if name in ROUTING_PLATFORMS:
                want(ROUTING_PLATFORMS[name])
    if found.items.get("proxies"):
        want("references/layers/reverse-proxies.md")
    if found.items.get("service_worker"):
        want("references/layers/service-workers.md")
    stores = found.items.get("data_stores", {})
    if any(e.get("layer") == "in-process" for e in stores.values()):
        want("references/layers/in-process.md")
    if set(stores) & DISTRIBUTED:
        want("references/layers/distributed-cache.md")
    if found.items.get("orm") or set(stores) & DATABASES:
        want("references/layers/database-orm.md")
    hosts = set(found.items.get("hosting", {}))
    if hosts & SERVERLESS_HOSTS or set(stores) & SERVERLESS_STORES:
        want("references/layers/serverless-edge-data.md")
    if found.items.get("api"):
        want("references/layers/api-graphql-rpc.md")
    if found.items.get("mobile"):
        want("references/layers/mobile-native.md")
    if found.items.get("ai"):
        want("references/layers/ai-llm.md")

    read_when = [
        {"path": "references/core/archetypes.md", "when": "confirming the archetype with the user, or archetype_candidates is empty or ambiguous"},
        {"path": "references/core/invalidation-consistency.md", "when": "the plan adds an app cache, a CDN purge or a tag scheme"},
        {"path": "references/core/stampede-failure.md", "when": "the plan adds an app cache, a CDN purge or a tag scheme, or there are hot keys/expensive misses"},
        {"path": "references/core/observability-testing.md", "when": "writing the verify steps, monitoring and rollout"},
    ]
    if found.items.get("ci"):
        read_when.append({"path": "references/layers/build-ci-network.md", "when": "the user asks about build, CI, Docker layer, DNS or TLS caching"})
    if not (found.items.get("cdn") or found.items.get("hosting")) and web:
        read_when.append({"path": "references/layers/cdn-concepts.md", "when": "no CDN detected: ask what fronts production before choosing shared-cache headers"})
    return read, read_when


# --------------------------------------------------------------------------- main


def detect(root: Path) -> dict:
    scan = Scan(root)
    scan.walk()
    found = Findings()
    notes: list[str] = []
    declared = scan_node(scan, found, notes)
    scan_python(scan, found)
    scan_ruby(scan, found)
    scan_php(scan, found)
    scan_jvm(scan, found)
    scan_dotnet(scan, found)
    scan_go(scan, found)
    scan_elixir(scan, found)
    scan_mobile(scan, found)
    scan_cms_files(scan, found)
    scan_hosting_and_infra(scan, found, notes)
    scan_service_workers(scan, found)
    scan_ci(scan, found)
    inspect_framework_configs(scan, found, notes)
    for fw, orm in (("django", "django-orm"), ("rails", "active-record"), ("laravel", "eloquent"), ("phoenix", "ecto")):
        if found.fw(fw):
            found.add("orm", orm, f"implied by {fw}")

    if any(re.search(r"""gem\s+['"]sidekiq['"]""", read_text(g)) for g in scan.named("Gemfile")):
        notes.append("Sidekiq uses Redis: keep queue data on a separate instance/database from the cache (eviction policy).")
    if found.items.get("api", {}).get("apollo-server-legacy"):
        notes.append("Legacy apollo-server package found: Apollo Server 4 is end-of-life (2026-01-26); plan an upgrade to @apollo/server 5.")
    if not found.frameworks and not found.items.get("cms"):
        notes.append("No web framework or CMS detected: ask the user what serves the app, or point the script at the app's subdirectory.")
    if not found.items.get("cdn"):
        notes.append("No CDN detected in config: ask what fronts production (or probe a live URL with probe_headers.py).")

    read, read_when = route(found)
    def as_list(key: str) -> list[dict]:
        return sorted(found.items.get(key, {}).values(), key=lambda e: e["name"])

    result = {
        "repo": str(root),
        "frameworks": sorted(found.frameworks.values(), key=lambda e: e["name"]),
        "client_caches": as_list("client_caches"),
        "hosting": as_list("hosting"),
        "cdn": as_list("cdn"),
        "proxies": as_list("proxies"),
        "data_stores": as_list("data_stores"),
        "orm": as_list("orm"),
        "cms": as_list("cms"),
        "api": as_list("api"),
        "mobile": as_list("mobile"),
        "ai": as_list("ai"),
        "ci": as_list("ci"),
        "service_worker": as_list("service_worker"),
        "archetype_candidates": archetypes(found, declared),
        "read": read,
        "read_when": read_when,
        "notes": notes,
        "limits": {
            "files_scanned": len(scan.files),
            "max_files": MAX_FILES,
            "max_depth": MAX_DEPTH,
            "truncated": scan.truncated,
            "skipped_dirs": sorted(scan.skipped)[:40],
            "method": "manifests, lockfiles and config files only; source code is not parsed (run find_cache_primitives.py for code)",
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fingerprint a repo's stack and list the caching references to read.",
        epilog="Prints JSON on stdout. Exit 0 on success, 2 on bad usage.",
    )
    parser.add_argument("repo_dir", nargs="?", help="path to the repository root")
    parser.add_argument("--list-references", action="store_true", help="print every reference path this script can route to")
    args = parser.parse_args(argv)
    if args.list_references:
        json.dump(REFERENCES, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    if not args.repo_dir:
        parser.print_usage(sys.stderr)
        print("error: repo_dir is required", file=sys.stderr)
        return 2
    root = Path(args.repo_dir).resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    json.dump(detect(root), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
