#!/usr/bin/env bash
# Two-session leak test through the real CDN/proxy. Read-only GETs; run only against URLs you own.
#
#   SESSION_A='session=...' SESSION_B='session=...' ./leak-test.sh https://www.example.com/account
#
# For each URL, on a fresh cache key (?__leak_probe=<random>):
#   1. user A requests it (may populate the shared cache)
#   2. an anonymous client requests the same URL     -> must NOT get A's body
#   3. user B requests the same URL                  -> must NOT get A's body
# Bodies are compared by hash; cookie values are never printed.
# Exit 1 if a leak is detected. Dynamic bodies (timestamps, nonces) can hide a leak but never
# fake one; scripts/probe_headers.py --cookie-a/--cookie-b does the same with more detail.
set -euo pipefail

if [[ $# -lt 1 || -z "${SESSION_A:-}" ]]; then
  echo "usage: SESSION_A='k=v' [SESSION_B='k=v'] $0 <url> [<url> ...]" >&2
  exit 2
fi

hash_body() { sha256sum | cut -c1-16; }
status_of() { grep -iE '^(cf-cache-status|x-cache|x-vercel-cache|age|cache-status):' | tr -d '\r' | paste -sd' ' -; }

leaks=0
for url in "$@"; do
  sep='?'; [[ "$url" == *\?* ]] && sep='&'
  probe="${url}${sep}__leak_probe=$(date +%s)$RANDOM"
  tmp=$(mktemp -d)

  curl -sS -o "$tmp/a" -D "$tmp/a.h" -H "Cookie: $SESSION_A" "$probe"
  curl -sS -o "$tmp/anon" -D "$tmp/anon.h" "$probe"
  a=$(hash_body < "$tmp/a"); anon=$(hash_body < "$tmp/anon")

  fresh_anon=$(curl -sS "${url}${sep}__leak_probe=fresh$RANDOM" | hash_body)
  echo "== $url"
  echo "   user A:        $a   $(status_of < "$tmp/a.h")"
  echo "   anonymous:     $anon   $(status_of < "$tmp/anon.h")"
  if [[ "$a" != "$fresh_anon" && "$anon" == "$a" ]]; then
    echo "   LEAK: anonymous request received user A's response" >&2
    leaks=$((leaks + 1))
  fi

  if [[ -n "${SESSION_B:-}" ]]; then
    curl -sS -o "$tmp/b" -D "$tmp/b.h" -H "Cookie: $SESSION_B" "$probe"
    b=$(hash_body < "$tmp/b")
    fresh_b=$(curl -sS -H "Cookie: $SESSION_B" "${url}${sep}__leak_probe=freshb$RANDOM" | hash_body)
    echo "   user B:        $b   $(status_of < "$tmp/b.h")"
    if [[ "$fresh_b" != "$a" && "$b" == "$a" ]]; then
      echo "   LEAK: user B received user A's response" >&2
      leaks=$((leaks + 1))
    fi
  fi
  rm -rf "$tmp"
done

if (( leaks > 0 )); then
  echo "$leaks leak(s) detected" >&2
  exit 1
fi
echo "no leaks detected"
