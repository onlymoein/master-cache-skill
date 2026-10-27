"""Tests for the caching-strategy scripts (stdlib unittest; run: python -m unittest discover -s tests)."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "caching-strategy"
SCRIPTS = SKILL / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run(script: str, *args: str, stdin: str | None = None) -> tuple[int, dict | None, str]:
    proc = subprocess.run([sys.executable, str(SCRIPTS / script), *args], capture_output=True, text=True,
                          input=stdin, timeout=120)
    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else None
    except ValueError:
        data = None
    return proc.returncode, data, proc.stderr


def names(items: list[dict]) -> set[str]:
    return {i["name"] for i in items}


class DetectStackTest(unittest.TestCase):
    def detect(self, fixture: str) -> dict:
        code, data, err = run("detect_stack.py", str(FIXTURES / fixture))
        self.assertEqual(code, 0, err)
        return data

    def test_reference_list_matches_files(self):
        code, refs, _ = run("detect_stack.py", "--list-references")
        self.assertEqual(code, 0)
        on_disk = sorted(p.relative_to(SKILL).as_posix() for p in (SKILL / "references").rglob("*.md"))
        self.assertEqual(sorted(refs), on_disk)

    def test_next_vercel(self):
        d = self.detect("next-vercel")
        nxt = next(f for f in d["frameworks"] if f["name"] == "nextjs")
        self.assertEqual(nxt["version"], "16.4.3")
        self.assertTrue(nxt["config"]["cacheComponents"])
        self.assertEqual(nxt["config"]["model"], "cache-components")
        self.assertIn("vercel", names(d["hosting"]))
        self.assertIn("vercel", names(d["cdn"]))
        self.assertIn("redis", names(d["data_stores"]))
        self.assertIn("anthropic", names(d["ai"]))
        for ref in ("core/decision-framework.md", "core/http-semantics.md", "core/security.md",
                    "frameworks/nextjs.md", "platforms/vercel.md", "layers/distributed-cache.md",
                    "layers/ai-llm.md", "frameworks/client-data-caches.md"):
            self.assertIn(f"references/{ref}", d["read"])
        self.assertEqual(d["archetype_candidates"][0]["id"], "ai-llm-app")

    def test_django_compose(self):
        d = self.detect("django-nginx")
        self.assertIn("django", names(d["frameworks"]))
        self.assertIn("nginx", names(d["proxies"]))
        self.assertTrue({"redis", "postgres"} <= names(d["data_stores"]))
        self.assertIn("references/frameworks/django.md", d["read"])
        self.assertIn("references/layers/reverse-proxies.md", d["read"])
        self.assertIn("django-orm", names(d["orm"]))

    def test_pyproject_ignores_description_words(self):
        d = self.detect("fastapi-pyproject")
        self.assertEqual(names(d["frameworks"]), {"fastapi"})
        self.assertNotIn("django", names(d["frameworks"]))
        self.assertIn("cashews", names(d["data_stores"]))
        self.assertIn("sqlalchemy", names(d["orm"]))

    def test_rails(self):
        d = self.detect("rails-app")
        rails = next(f for f in d["frameworks"] if f["name"] == "rails")
        self.assertEqual(rails["version"], "8.1.3")
        self.assertIn("solid_cache", names(d["data_stores"]))
        self.assertTrue(any("Sidekiq" in n for n in d["notes"]))

    def test_wordpress(self):
        d = self.detect("wordpress-woo")
        self.assertIn("wordpress", names(d["cms"]))
        self.assertEqual(d["archetype_candidates"][0]["id"], "ecommerce")
        self.assertIn("references/cms/wordpress.md", d["read"])

    def test_go_terraform(self):
        d = self.detect("go-api")
        self.assertIn("cloudfront", names(d["cdn"]))
        self.assertTrue({"otter", "redis"} <= names(d["data_stores"]))
        self.assertIn("references/platforms/cloudfront.md", d["read"])
        self.assertIn("references/layers/api-graphql-rpc.md", d["read"])
        self.assertEqual(d["archetype_candidates"][0]["id"], "public-api")

    def test_sveltekit3_pnpm(self):
        d = self.detect("sveltekit-cloudflare")
        kit = next(f for f in d["frameworks"] if f["name"] == "sveltekit")
        self.assertEqual(kit["version"], "3.1.2")
        self.assertEqual(kit["config"]["adapter"], "cloudflare")
        self.assertIn("sanity", names(d["cms"]))
        self.assertIn("references/cms/headless-cms.md", d["read"])
        self.assertIn("references/platforms/cloudflare.md", d["read"])
        self.assertIsNone(next(h for h in d["hosting"] if h["name"] == "cloudflare")["version"])

    def test_flutter(self):
        d = self.detect("flutter-app")
        self.assertIn("flutter", names(d["mobile"]))
        self.assertIn("references/layers/mobile-native.md", d["read"])

    def test_bad_usage(self):
        self.assertEqual(run("detect_stack.py")[0], 2)
        self.assertEqual(run("detect_stack.py", "/definitely/not/here")[0], 2)


class FindPrimitivesTest(unittest.TestCase):
    def scan(self, fixture: str) -> dict:
        code, data, err = run("find_cache_primitives.py", str(FIXTURES / fixture))
        self.assertEqual(code, 0, err)
        return data

    def rules(self, data: dict) -> set[str]:
        return {w["rule"] for w in data["warnings"]}

    def test_next_warnings(self):
        d = self.scan("next-vercel")
        expected = {"next-revalidatetag-one-arg", "next-updatetag-in-route-handler", "vary-cookie-or-user-agent",
                    "module-level-dataloader", "redis-keys-command", "js-unbounded-lru", "public-cache-on-auth-path"}
        self.assertTrue(expected <= self.rules(d), self.rules(d))
        kinds = {f["kind"] for f in d["findings"]}
        self.assertTrue({"next-use-cache", "next-cache-life-tag", "next-invalidation"} <= kinds)

    def test_two_arg_revalidatetag_not_flagged(self):
        d = self.scan("next-vercel")
        flagged = [w for w in d["warnings"] if w["rule"] == "next-revalidatetag-one-arg"]
        self.assertTrue(all("," not in w["snippet"].split("revalidateTag(")[1].split(")")[0] for w in flagged))

    def test_django_warnings(self):
        d = self.scan("django-nginx")
        self.assertTrue({"django-cache-page-without-vary-cookie", "python-unbounded-cache", "redis-noeviction"} <= self.rules(d))
        self.assertIn("proxy", d["summary"]["by_layer"])
        self.assertFalse(any(f["file"] == "docker-compose.yml" and f["layer"] == "proxy" and f["line"] == 6 for f in d["findings"]))

    def test_max_findings(self):
        code, d, _ = run("find_cache_primitives.py", str(FIXTURES), "--max-findings", "3")
        self.assertEqual(code, 0)
        self.assertEqual(len(d["findings"]), 3)
        self.assertTrue(d["limits"]["truncated"])


class ValidatePlanTest(unittest.TestCase):
    def test_example_plan_is_valid(self):
        code, d, err = run("validate_plan.py", str(SKILL / "assets" / "plan.example.json"))
        self.assertEqual(code, 0, d)
        self.assertTrue(d["valid"])
        self.assertEqual(d["errors"], [])

    def test_bad_plan(self):
        code, d, _ = run("validate_plan.py", str(FIXTURES / "plans" / "bad-plan.json"))
        self.assertEqual(code, 1)
        rules = {e["rule"] for e in d["errors"]}
        for rule in ("shared-cache-on-private-route", "public-directive-on-private-route", "personalized-without-private",
                     "sensitive-without-no-store", "unsafe-method-cached", "cacheable-without-invalidation",
                     "browser-ttl-over-budget", "shared-ttl-over-budget", "immutable-without-versioned-url",
                     "service-worker-max-age", "tag-format", "vary-cookie-user-agent", "tenant-missing-from-key",
                     "duplicate-route-id", "unknown-route", "schema"):
            self.assertIn(rule, rules)
        self.assertIn("cloudflare-swr-with-s-maxage", {w["rule"] for w in d["warnings"]})

    def test_event_driven_ttl_allowed(self):
        plan = json.loads((SKILL / "assets" / "plan.example.json").read_text())
        route = plan["routes"][1]  # R2: shared TTL 300 s > budget 60 s, but purged by events in 30 s
        self.assertGreater(route["shared"]["ttl_seconds"], route["staleness_budget_seconds"])
        route["invalidation"]["propagation_seconds"] = 120  # slower than the budget
        code, d, _ = run("validate_plan.py", "-", stdin=json.dumps(plan))
        self.assertEqual(code, 1)
        self.assertIn("invalidation-slower-than-budget", {e["rule"] for e in d["errors"]})

    def test_ttl_only_over_budget(self):
        plan = json.loads((SKILL / "assets" / "plan.example.json").read_text())
        route = plan["routes"][4]  # R5: TTL-only stock API, budget 10 s
        route["shared"]["ttl_seconds"] = 30
        code, d, _ = run("validate_plan.py", "-", stdin=json.dumps(plan))
        self.assertEqual(code, 1)
        self.assertIn("shared-ttl-over-budget", {e["rule"] for e in d["errors"]})

    def test_invalid_json(self):
        code, d, _ = run("validate_plan.py", "-", stdin="{")
        self.assertEqual(code, 1)
        self.assertEqual(d["errors"][0]["rule"], "json")


class SizeCacheTest(unittest.TestCase):
    def test_math(self):
        code, d, _ = run("size_cache.py", "--rps", "500", "--hit-ratio", "0.9", "--hit-ms", "1", "--miss-ms", "50",
                         "--target-ms", "6", "--origin-capacity-rps", "100", "--keys", "1000", "--avg-bytes", "900")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(d["latency"]["effective_ms"], 6.0)
        self.assertAlmostEqual(d["origin"]["rps_with_cache"], 50.0)
        self.assertAlmostEqual(d["origin"]["required_hit_ratio_for_capacity"], 0.8)
        self.assertAlmostEqual(d["target"]["required_hit_ratio"], 0.9)
        per_key = 40 + 900 + 60
        self.assertEqual(d["memory"]["with_fragmentation_and_headroom_bytes"], round(1000 * per_key * 1.2 / 0.75))

    def test_bad_usage(self):
        self.assertEqual(run("size_cache.py", "--rps", "1", "--hit-ratio", "1.5", "--hit-ms", "1", "--miss-ms", "2")[0], 2)
        self.assertEqual(run("size_cache.py", "--rps", "1", "--hit-ratio", "0.5", "--hit-ms", "1", "--miss-ms", "2", "--keys", "5")[0], 2)


# --------------------------------------------------------------------------- probe_headers


class FakeEdge(BaseHTTPRequestHandler):
    """A tiny origin + 'CDN' with deliberate bugs, for the header probe."""

    shared: dict[str, tuple[bytes, dict]] = {}
    lock = threading.Lock()

    def log_message(self, *args):  # silence
        pass

    def send(self, status: int, body: bytes, headers: dict) -> None:
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path
        cookie = self.headers.get("Cookie", "")
        user = cookie.split("=", 1)[1] if "=" in cookie else "anonymous"
        if path.startswith("/public"):
            if self.headers.get("If-None-Match") == '"v1"':
                return self.send(304, b"", {"ETag": '"v1"', "Cache-Control": "no-cache"})
            with self.lock:
                hit = path in self.shared
                self.shared.setdefault(path, (b"public", {}))
            return self.send(200, b"public page", {
                "Content-Type": "text/html", "Cache-Control": "no-cache", "CDN-Cache-Control": "max-age=60",
                "ETag": '"v1"', "X-Cache": "HIT" if hit else "MISS", "Age": "3" if hit else "0"})
        if path.startswith("/leaky"):
            # BUG: a shared cache keyed on the URL only, storing per-user responses
            with self.lock:
                if path in self.shared:
                    body, _ = self.shared[path]
                    return self.send(200, body, {"Content-Type": "text/html", "Cache-Control": "public, s-maxage=60", "X-Cache": "HIT", "Age": "1"})
                body = f"hello {user}".encode()
                self.shared[path] = (body, {})
            return self.send(200, body, {"Content-Type": "text/html", "Cache-Control": "public, s-maxage=60", "X-Cache": "MISS"})
        if path.startswith("/account"):
            # BUG: origin ignores the suffix (path confusion) and the 'CDN' caches by extension
            body = f"account of {user}".encode()
            if path.endswith(".css"):
                with self.lock:
                    if path in self.shared:
                        cached, _ = self.shared[path]
                        return self.send(200, cached, {"Content-Type": "text/html", "X-Cache": "HIT", "Age": "2"})
                    self.shared[path] = (body, {})
                return self.send(200, body, {"Content-Type": "text/html", "Cache-Control": "private, no-cache", "X-Cache": "MISS"})
            return self.send(200, body, {"Content-Type": "text/html", "Cache-Control": "private, no-cache"})
        if path.startswith("/nocc"):
            return self.send(200, b"x", {"Content-Type": "text/html", "Set-Cookie": "tracking=secretvalue; Path=/"})
        return self.send(404, b"nope", {"Cache-Control": "no-store"})


class ProbeHeadersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeEdge)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeEdge.shared.clear()

    def probe(self, *args: str) -> dict:
        code, d, err = run("probe_headers.py", *args, "--delay", "0")
        self.assertEqual(code, 0, err)
        return d

    def test_public_hit_and_304(self):
        r = self.probe(self.base + "/public")["results"][0]
        self.assertEqual([x["cache_status"] for x in r["requests"]], ["MISS", "HIT"])
        self.assertTrue(r["conditional"]["ok"])
        self.assertFalse(any(f["severity"] == "high" for f in r["findings"]))

    def test_leak_detected_and_cookie_values_hidden(self):
        out = self.probe(self.base + "/leaky", "--cookie-a", "session=alice", "--cookie-b", "session=bob")
        r = out["results"][0]
        self.assertTrue(r["leak_test"]["verdict"].startswith("LEAK"), r["leak_test"])
        self.assertEqual(r["findings"][0]["rule"], "cross-user-leak")
        text = json.dumps(out)
        self.assertNotIn("alice", text)
        self.assertNotIn("bob", text)

    def test_private_route_no_leak(self):
        r = self.probe(self.base + "/account", "--cookie-a", "session=alice")["results"][0]
        self.assertEqual(r["leak_test"]["verdict"], "no-leak-detected")

    def test_deception(self):
        r = self.probe(self.base + "/account", "--cookie-a", "session=alice", "--deception")["results"][0]
        high = [v for v in r["deception"]["variants"] if v.get("severity") == "high"]
        self.assertTrue(high, r["deception"])
        self.assertIn("web-cache-deception", {f["rule"] for f in r["findings"]})

    def test_missing_cache_control_and_set_cookie_redacted(self):
        out = self.probe(self.base + "/nocc")
        r = out["results"][0]
        self.assertIn("missing-cache-control", {f["rule"] for f in r["findings"]})
        self.assertNotIn("secretvalue", json.dumps(out))

    def test_bad_usage(self):
        self.assertEqual(run("probe_headers.py", "ftp://example.com")[0], 2)
        self.assertEqual(run("probe_headers.py", "http://x.invalid", "--cookie-b", "a=b")[0], 2)


if __name__ == "__main__":
    unittest.main()
