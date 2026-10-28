"""Sanity checks for the eval fixtures and files (stdlib unittest)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
DETECT = ROOT / "skills" / "caching-strategy" / "scripts" / "detect_stack.py"

# fixture -> (expected top archetype, references that must be in "read")
EXPECTED = {
    "next16-vercel-store": ("ecommerce", ["frameworks/nextjs.md", "platforms/vercel.md"]),
    "next15-k8s-cloudfront": ("news-media", ["frameworks/nextjs.md", "platforms/cloudfront.md", "cms/headless-cms.md"]),
    "django-saas-redis": ("saas-multitenant", ["frameworks/django.md", "layers/distributed-cache.md"]),
    "rails-news-fastly": ("news-media", ["frameworks/rails.md", "platforms/fastly.md"]),
    "wordpress-apo": ("news-media", ["cms/wordpress.md", "platforms/cloudflare.md"]),
    "express-apollo-graphql": ("public-api", ["frameworks/node-backends.md", "layers/api-graphql-rpc.md"]),
    "expo-avatars": ("mobile-backend", ["layers/mobile-native.md", "layers/api-graphql-rpc.md", "frameworks/client-data-caches.md"]),
    "rag-support-bot": ("ai-llm-app", ["layers/ai-llm.md", "frameworks/python-web.md"]),
}


class EvalFixturesTest(unittest.TestCase):
    def test_every_fixture_is_expected(self):
        on_disk = {p.name for p in (EVALS / "fixtures").iterdir() if p.is_dir()}
        self.assertEqual(on_disk, set(EXPECTED))

    def test_detect_stack_routes_fixtures(self):
        for fixture, (archetype, refs) in EXPECTED.items():
            with self.subTest(fixture=fixture):
                proc = subprocess.run([sys.executable, str(DETECT), str(EVALS / "fixtures" / fixture)],
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                data = json.loads(proc.stdout)
                self.assertTrue(data["archetype_candidates"], "no archetype candidates")
                self.assertEqual(data["archetype_candidates"][0]["id"], archetype)
                for ref in refs:
                    self.assertIn(f"references/{ref}", data["read"])

    def test_instance_counts(self):
        expected = {"next15-k8s-cloudfront": (4, False), "django-saas-redis": (3, False), "next16-vercel-store": (None, True)}
        for fixture, (max_instances, serverless) in expected.items():
            with self.subTest(fixture=fixture):
                proc = subprocess.run([sys.executable, str(DETECT), str(EVALS / "fixtures" / fixture)],
                                      capture_output=True, text=True, timeout=60)
                data = json.loads(proc.stdout)
                self.assertEqual(data["instances"]["max"], max_instances)
                self.assertEqual(data["instances"]["serverless"], serverless)
                self.assertTrue(data["instances"]["multiple"])
        proc = subprocess.run([sys.executable, str(DETECT), str(EVALS / "fixtures" / "next15-k8s-cloudfront")],
                              capture_output=True, text=True, timeout=60)
        self.assertTrue(any("cacheHandler" in n and "several" in n for n in json.loads(proc.stdout)["notes"]))

    def test_scanner_flags_planted_problems(self):
        scanner = DETECT.parent / "find_cache_primitives.py"
        planted = {
            "next16-vercel-store": "next-revalidatetag-one-arg",
            "django-saas-redis": "constant-key-in-user-scoped-code",
            "rails-news-fastly": "rails-public-shared-ttl",
            "wordpress-apo": "cookie-on-every-request",
            "express-apollo-graphql": "module-level-dataloader",
            "expo-avatars": "client-cache-never-stale",
            "rag-support-bot": "llm-volatile-prompt-prefix",
        }
        for fixture, rule in planted.items():
            with self.subTest(fixture=fixture):
                proc = subprocess.run([sys.executable, str(scanner), str(EVALS / "fixtures" / fixture)],
                                      capture_output=True, text=True, timeout=60)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(rule, {w["rule"] for w in json.loads(proc.stdout)["warnings"]})

    def test_snippets_raise_no_warnings(self):
        scanner = DETECT.parent / "find_cache_primitives.py"
        proc = subprocess.run([sys.executable, str(scanner), str(DETECT.parent.parent / "assets" / "snippets")],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(proc.stdout)["warnings"], [])

    def test_evals_json(self):
        data = json.loads((EVALS / "evals.json").read_text())
        self.assertEqual(data["skill_name"], "caching-strategy")
        ids = [c["id"] for c in data["evals"]]
        self.assertEqual(len(ids), len(set(ids)))
        used = set()
        for case in data["evals"]:
            self.assertTrue(case["prompt"] and case["expected_output"] and case["expectations"])
            for f in case["files"]:
                self.assertTrue((EVALS / f).exists(), f)
                used.add(Path(f).name)
        self.assertEqual(used, set(EXPECTED))

    def test_trigger_queries(self):
        items = json.loads((EVALS / "trigger_queries.json").read_text())
        for split in ("train", "validation"):
            pos = [q for q in items if q["split"] == split and q["should_trigger"]]
            neg = [q for q in items if q["split"] == split and not q["should_trigger"]]
            self.assertGreaterEqual(len(pos), 4, split)
            self.assertGreaterEqual(len(neg), 4, split)
        self.assertEqual(len({q["query"] for q in items}), len(items))


if __name__ == "__main__":
    unittest.main()
