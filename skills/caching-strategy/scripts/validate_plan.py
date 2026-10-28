#!/usr/bin/env python3
"""Validate a caching plan (plan.json) for structure and safety.

Usage:
    python scripts/validate_plan.py <plan.json>      (use - to read stdin)

Structure comes from assets/plan.schema.json (checked with a small built-in JSON Schema
subset: type, const, enum, required, properties, additionalProperties, items, minItems,
maxItems, minimum, maximum, minLength, pattern, anyOf, $ref). Safety rules are added on top:

errors (exit 1)
    shared caching or `public`/`s-maxage` on personalized, sensitive or mutation routes
    sensitive routes without `no-store`; non-GET/HEAD routes that aren't `no-store`
    cacheable routes without invalidation, owner or verify steps
    a TTL longer than the staleness budget (browser always; shared/app cache unless purged by events)
    event-driven invalidation slower than the staleness budget
    `immutable` without a versioned URL; service worker scripts with a browser max-age
    more than 50 tags, or tags not lowercase `entity:id`
    `Vary: Cookie`/`User-Agent`/`*` on a shared-cached route
    multi-tenant personalized app-cache keys without the tenant
    duplicate route ids, phases naming unknown routes
warnings
    kitchen-sink headers, Cloudflare SWR combined with s-maxage, no stale-if-error on public HTML,
    app caches without stampede protection, keys off the naming convention, stacked tier TTLs
    above the budget, missing `all` tag, empty monitoring/phases/invalidation map

Prints {"valid", "errors", "warnings", "summary"} as JSON. Exit 0 valid, 1 invalid, 2 bad usage.
Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "assets" / "plan.schema.json"

PRIVATE_CLASSES = {"personalized", "sensitive", "mutation"}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE", "QUERY"}
NONE_WORDS = {"", "none", "n/a", "na", "-", "null", "no", "nothing"}
TTL_TRIGGER = re.compile(r"^\s*(ttl|time|timer|expiry|expire|expiration|max-age|none)\b", re.I)
KEY_CONVENTION = re.compile(r"^[a-z0-9][a-z0-9_-]*:[a-z0-9{}_-]+:v[0-9{}]+:")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_.:/{}-]*$")
# Headers frameworks emit themselves for dynamic responses; the app can't trim them, so no kitchen-sink warning.
FRAMEWORK_DEFAULT_HEADERS = {"private,no-cache,no-store,max-age=0,must-revalidate"}  # Next.js dynamic routes


# --------------------------------------------------------------------------- mini JSON Schema


def _type_ok(value, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def schema_errors(value, schema: dict, root: dict, path: str = "$") -> list[dict]:
    errs: list[dict] = []

    def err(msg: str) -> None:
        errs.append({"path": path, "rule": "schema", "message": msg})

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            err(f"unsupported $ref {ref}")
            return errs
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        return schema_errors(value, target, root, path)
    if "anyOf" in schema:
        if not any(not schema_errors(value, sub, root, path) for sub in schema["anyOf"]):
            # report the errors of the closest branch (fewest errors)
            best = min((schema_errors(value, sub, root, path) for sub in schema["anyOf"]), key=len)
            return best or [{"path": path, "rule": "schema", "message": "does not match any allowed shape"}]
    if "const" in schema and value != schema["const"]:
        err(f"must be {json.dumps(schema['const'])}")
    if "enum" in schema and value not in schema["enum"]:
        err(f"must be one of {', '.join(map(str, schema['enum']))} (got {json.dumps(value)})")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            err(f"must be of type {' or '.join(types)} (got {type(value).__name__})")
            return errs
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            err("must not be empty" if schema.get("minLength") == 1 else f"shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            err(f"must match {schema['pattern']} (got {json.dumps(value)})")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            err(f"must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            err(f"must be <= {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            err(f"needs at least {schema['minItems']} item(s)")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            err(f"has {len(value)} items; at most {schema['maxItems']} allowed")
        if "items" in schema:
            for i, item in enumerate(value):
                errs += schema_errors(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errs.append({"path": f"{path}.{key}", "rule": "schema", "message": "is required"})
        props = schema.get("properties", {})
        for key, sub in value.items():
            if key in props:
                errs += schema_errors(sub, props[key], root, f"{path}.{key}")
            else:
                extra = schema.get("additionalProperties", True)
                if extra is False:
                    errs.append({"path": f"{path}.{key}", "rule": "schema", "message": "is not an allowed property"})
                elif isinstance(extra, dict):
                    errs += schema_errors(sub, extra, root, f"{path}.{key}")
    return errs


# --------------------------------------------------------------------------- directive helpers


def directives(value: str | None) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for part in (value or "").split(","):
        part = part.strip()
        if part:
            k, _, v = part.partition("=")
            out[k.strip().lower()] = v.strip().strip('"') or None
    return out


def seconds(d: dict, key: str) -> int | None:
    try:
        return int(d[key]) if d.get(key) is not None else None
    except ValueError:
        return None


def is_none_text(text: str | None) -> bool:
    return (text or "").strip().lower() in NONE_WORDS


# --------------------------------------------------------------------------- safety rules


def check_route(i: int, r: dict, plan: dict, errors: list, warnings: list) -> bool:
    """Returns True when the route is cacheable somewhere (browser TTL, shared or app cache)."""
    p = f"$.routes[{i}]"
    rid = r.get("id", f"#{i}")

    def e(rule: str, msg: str, sub: str = "") -> None:
        errors.append({"path": p + sub, "route": rid, "rule": rule, "message": msg})

    def w(rule: str, msg: str, sub: str = "") -> None:
        warnings.append({"path": p + sub, "route": rid, "rule": rule, "message": msg})

    browser_cc = (r.get("browser") or {}).get("cache_control") or ""
    bcc = directives(browser_cc)
    shared = r.get("shared") or {}
    layer = shared.get("layer", "none")
    shared_value = shared.get("value") or ""
    scc = directives(shared_value)
    shared_ttl = shared.get("ttl_seconds") or 0
    app = r.get("app_cache") or {}
    app_layer = app.get("layer", "none") if app else "none"
    app_ttl = app.get("ttl_seconds") or 0 if app else 0
    klass = r.get("data_class")
    audience = r.get("audience")
    methods = set(r.get("methods") or [])
    budget = r.get("staleness_budget_seconds")
    inv = r.get("invalidation") or {}
    tags = r.get("tags") or []
    vary = [v.strip().lower() for v in (r.get("vary") or [])]

    shared_cached = layer != "none" or shared_ttl > 0
    browser_max_age = seconds(bcc, "max-age") or 0
    cacheable = shared_cached or app_layer != "none" or browser_max_age > 0 or "immutable" in bcc

    # 1. personalized / sensitive / mutation never in shared caches
    private_route = klass in PRIVATE_CLASSES or audience in ("personalized", "sensitive")
    if private_route:
        if shared_cached:
            e("shared-cache-on-private-route",
              f"{klass}/{audience} route must not be stored in a shared cache (shared.layer={layer}, ttl={shared_ttl}). "
              "Bypass the CDN/proxy, or split a public shell from a private island.", ".shared")
        for label, d in (("browser.cache_control", bcc), ("shared.value", scc)):
            if "public" in d or "s-maxage" in d:
                e("public-directive-on-private-route", f"`public`/`s-maxage` in {label} of a {klass}/{audience} route.")
        if audience == "personalized" and "private" not in bcc and "no-store" not in bcc:
            e("personalized-without-private",
              "Personalized responses need `private` (or `no-store`): shared caches collapse requests even for no-cache/max-age=0.",
              ".browser.cache_control")
    # 2. sensitive must be no-store
    if (klass == "sensitive" or audience == "sensitive") and "no-store" not in bcc:
        e("sensitive-without-no-store", "Sensitive routes need `Cache-Control: no-store`.", ".browser.cache_control")
    # 3. unsafe methods
    unsafe = methods & UNSAFE_METHODS
    if unsafe and ("no-store" not in bcc or shared_cached):
        e("unsafe-method-cached", f"{'/'.join(sorted(unsafe))} responses must be `no-store` with no shared cache "
          "(split read and write routes into separate rows).")
    if klass == "mutation" and not unsafe:
        w("mutation-without-write-method", "data_class mutation but methods has no POST/PUT/PATCH/DELETE.")
    # 4. cacheable rows need invalidation, owner, verify
    if cacheable:
        if is_none_text(inv.get("trigger")) or is_none_text(inv.get("mechanism")):
            e("cacheable-without-invalidation",
              "Cacheable route needs an invalidation trigger and mechanism (event → tag purge, deploy → new URL, or 'ttl' with a TTL within budget).",
              ".invalidation")
        if is_none_text(r.get("owner")):
            e("cacheable-without-owner", "Cacheable route needs an owner.", ".owner")
        if not [v for v in (r.get("verify") or []) if not is_none_text(v)]:
            e("cacheable-without-verify", "Cacheable route needs at least one verification command.", ".verify")
    # 5. TTL vs staleness budget
    ttl_only = TTL_TRIGGER.match(inv.get("trigger") or "") is not None or inv.get("propagation_seconds") is None
    if budget is not None:
        if browser_max_age > budget:
            e("browser-ttl-over-budget",
              f"Browser max-age={browser_max_age}s exceeds the staleness budget {budget}s, and browser copies can't be purged. "
              "Use no-cache + ETag, or a versioned URL (staleness_budget_seconds: null).", ".browser.cache_control")
        if ttl_only:
            if shared_cached and shared_ttl > budget:
                e("shared-ttl-over-budget",
                  f"Shared TTL {shared_ttl}s exceeds the staleness budget {budget}s and invalidation is TTL-only. "
                  "Lower the TTL or add event-driven purge (and set invalidation.propagation_seconds).", ".shared.ttl_seconds")
            if app_layer != "none" and app_ttl > budget:
                e("app-ttl-over-budget",
                  f"App-cache TTL {app_ttl}s exceeds the staleness budget {budget}s and invalidation is TTL-only.", ".app_cache.ttl_seconds")
            swr = seconds(scc, "stale-while-revalidate") or 0
            stacked = (app_ttl if app_layer != "none" else 0) + (shared_ttl + swr if shared_cached else 0) + browser_max_age
            if stacked > budget and not any(x.get("route") == rid and x["rule"].endswith("over-budget") for x in errors):
                w("stacked-ttl-over-budget",
                  f"Worst-case staleness across tiers (app {app_ttl}s + shared {shared_ttl}s + SWR {swr}s + browser {browser_max_age}s = {stacked}s) "
                  f"exceeds the budget {budget}s. Tiers stack when each refills from a stale lower tier.")
        else:
            prop = inv.get("propagation_seconds")
            if prop is not None and prop > budget:
                e("invalidation-slower-than-budget",
                  f"Invalidation propagates in {prop}s but the staleness budget is {budget}s.", ".invalidation.propagation_seconds")
    # 6. immutable needs a versioned URL
    if ("immutable" in bcc or "immutable" in scc) and budget is not None:
        e("immutable-without-versioned-url",
          "`immutable` is only for versioned (fingerprinted) URLs; set staleness_budget_seconds to null if the URL changes with content, "
          "otherwise use no-cache + ETag.")
    if klass == "service-worker-script" and browser_max_age > 0:
        e("service-worker-max-age", "Service worker scripts must not get a browser max-age (stale SW pins old app versions); use no-cache.",
          ".browser.cache_control")
    # 7. tags
    if len(tags) > 50:
        e("too-many-tags", f"{len(tags)} tags; at most 50 per response.", ".tags")
    for t in tags:
        if t != t.lower() or not TAG_RE.match(t):
            e("tag-format", f"Tag {json.dumps(t)} must be lowercase entity:id (placeholders like {{id}} allowed).", ".tags")
    if shared_cached and tags and "all" not in tags:
        w("missing-all-tag", "Shared-cached route has tags but not the constant `all` tag used for emergency purges.", ".tags")
    # 8. Vary
    bad_vary = [v for v in vary if v in ("cookie", "user-agent", "*")]
    if bad_vary:
        (e if shared_cached else w)("vary-cookie-user-agent",
                                    f"Vary: {', '.join(bad_vary)} fragments or disables caching; key on a normalized header or bypass shared caches instead.",
                                    ".vary")
    # 9. app cache
    if app and app_layer != "none":
        if is_none_text(app.get("stampede")) and app_layer not in ("framework", "db"):
            w("app-cache-without-stampede-protection",
              "App cache has no stampede protection (single-flight, SWR/soft TTL, lease or lock).", ".app_cache.stampede")
        key = app.get("key_pattern") or ""
        if key and not KEY_CONVENTION.match(key):
            w("key-convention", f"Key {json.dumps(key)} doesn't follow {{app}}:{{env}}:v{{schema}}:[t:{{tenant}}:]{{entity}}:{{id}}.",
              ".app_cache.key_pattern")
        tenancy = ((plan.get("constraints") or {}).get("tenancy") or "single")
        if tenancy.startswith("multi") and audience != "public" and key and not re.search(r"(t:\{|tenant|org)", key, re.I):
            e("tenant-missing-from-key",
              "Multi-tenant plan: app-cache key for a non-public route must include the tenant (t:{tenant}).", ".app_cache.key_pattern")
    # 10. warnings
    framework_default = browser_cc.replace(" ", "").lower() in FRAMEWORK_DEFAULT_HEADERS
    if re.search(r"no-store", browser_cc, re.I) and len(bcc) >= 3 and not framework_default:
        w("kitchen-sink-headers", "`Cache-Control: no-store` alone is enough; drop no-cache/must-revalidate/max-age=0 (and Pragma/Expires).",
          ".browser.cache_control")
    stack = plan.get("app", {}).get("stack", {}) or {}
    platforms = " ".join(" ".join(v) for v in stack.values() if isinstance(v, list)).lower()
    header = (shared.get("header") or "").lower()
    if "cloudflare" in platforms and "stale-while-revalidate" in scc and header in ("cache-control", "") and \
            any(k in scc for k in ("s-maxage", "must-revalidate", "proxy-revalidate", "no-cache")):
        w("cloudflare-swr-with-s-maxage",
          "Cloudflare disables stale-while-revalidate when the same header has s-maxage/must-revalidate/proxy-revalidate/no-cache; "
          "use Cloudflare-CDN-Cache-Control: max-age=…, stale-while-revalidate=….", ".shared.value")
    if shared_cached and klass in ("public-html-stable", "public-html-volatile", "public-api-reference") and "stale-if-error" not in scc:
        w("no-stale-if-error", "Public shared-cached content without stale-if-error: origin outages become user-facing errors.", ".shared.value")
    if shared_cached and not (shared.get("header") and shared.get("value")):
        w("shared-layer-without-header", "shared.layer is set but header/value are empty: say which header sets the shared TTL.", ".shared")
    if klass in ("realtime", "llm-output") and shared_cached:
        w("shared-cache-on-live-or-llm-data",
          f"{klass} data is normally not shared-cached (cache a bootstrap snapshot or public FAQ answers only).", ".shared")
    if klass == "error-response" and shared_ttl > 60:
        w("long-error-ttl", "Error responses: 404 short TTL, 5xx at most 5–10 s at the CDN.", ".shared.ttl_seconds")
    if unsafe and klass != "sensitive" and r.get("decision_step") not in (0, None):
        w("decision-step", "Routes with write methods are decided at step 0.", ".decision_step")
    if klass == "sensitive" and r.get("decision_step") not in (1, 0, None):
        w("decision-step", "Sensitive routes are decided at step 1.", ".decision_step")
    return cacheable


def validate(plan) -> dict:
    schema = json.loads(SCHEMA_PATH.read_text())
    # tag format and count are reported by the friendlier safety rules below
    errors = [x for x in schema_errors(plan, schema, schema)
              if not (re.search(r"\.tags(\[\d+\])?$", x["path"]) and re.match(r"must match|has \d+ items", x["message"]))]
    warnings: list[dict] = []
    if not isinstance(plan, dict) or not isinstance(plan.get("routes"), list):
        return {"valid": False, "errors": errors, "warnings": warnings, "summary": {}}
    ids: dict[str, int] = {}
    cacheable = 0
    for i, r in enumerate(plan["routes"]):
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if rid in ids:
            errors.append({"path": f"$.routes[{i}].id", "route": rid, "rule": "duplicate-route-id",
                           "message": f"Route id {rid} is also used by routes[{ids[rid]}]."})
        elif rid is not None:
            ids[rid] = i
        try:
            cacheable += check_route(i, r, plan, errors, warnings)
        except (TypeError, AttributeError, KeyError) as exc:  # malformed row already reported by the schema
            errors.append({"path": f"$.routes[{i}]", "route": rid, "rule": "malformed-route", "message": str(exc)})
    for i, ph in enumerate(plan.get("phases") or []):
        if isinstance(ph, dict):
            for ref in ph.get("routes") or []:
                if ref not in ids:
                    errors.append({"path": f"$.phases[{i}].routes", "rule": "unknown-route", "message": f"Phase names unknown route {ref}."})
    if not plan.get("monitoring"):
        warnings.append({"path": "$.monitoring", "rule": "no-monitoring", "message": "No monitoring metrics: add hit ratio (excluding BYPASS), origin RPS, p95 latency and purge latency."})
    if not plan.get("phases"):
        warnings.append({"path": "$.phases", "rule": "no-phases", "message": "No rollout phases: ship safety fixes first, then caching by ROI, each with a rollback."})
    needs_map = any(isinstance(r, dict) and (r.get("tags") or (r.get("app_cache") or {}).get("layer", "none") != "none")
                    for r in plan["routes"])
    if needs_map and not plan.get("invalidation_map"):
        warnings.append({"path": "$.invalidation_map", "rule": "no-invalidation-map",
                         "message": "Routes use tags or app caches but invalidation_map is empty: list each write event, the keys/tags it clears and the order."})
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {"routes": len(plan["routes"]), "cacheable_routes": cacheable,
                    "errors": len(errors), "warnings": len(warnings)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a caching plan.json against assets/plan.schema.json plus safety rules.",
        epilog="Prints {valid, errors, warnings, summary} as JSON. Exit 0 valid, 1 invalid, 2 bad usage.",
    )
    parser.add_argument("plan", help="path to plan.json, or - for stdin")
    args = parser.parse_args(argv)
    try:
        text = sys.stdin.read() if args.plan == "-" else Path(args.plan).read_text()
    except OSError as exc:
        print(f"error: cannot read {args.plan}: {exc}", file=sys.stderr)
        return 2
    try:
        plan = json.loads(text)
    except ValueError as exc:
        json.dump({"valid": False, "errors": [{"path": "$", "rule": "json", "message": f"invalid JSON: {exc}"}],
                   "warnings": [], "summary": {}}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1
    result = validate(plan)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
