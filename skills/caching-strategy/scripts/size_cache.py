#!/usr/bin/env python3
"""Cache ROI and sizing math: effective latency, origin load, hit ratio needed, memory estimate.

Usage:
    python scripts/size_cache.py --rps 500 --hit-ratio 0.9 --hit-ms 1 --miss-ms 50
        [--target-ms 10] [--origin-capacity-rps 100]
        [--keys 2000000 --avg-bytes 1200 --avg-key-bytes 40 --overhead-bytes 60
         --fragmentation 1.2 --reserved-pct 25]

Formulas (references/core/decision-framework.md):
    effective_latency = h·L_hit + (1 − h)·(L_hit + L_miss)
    origin_load       = (1 − h)·R
    benefit_ms_per_s  = R·h·L_miss            (latency saved per second of traffic)
    memory            = keys·(key + value + overhead)·fragmentation ÷ (1 − reserved)

The memory overhead default (60 bytes/key) is a planning number for Redis/Valkey; measure
with MEMORY USAGE on real keys before buying capacity.

Prints JSON. Exit 0 on success, 2 on bad usage. Python 3.9+, standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


def compute(a: argparse.Namespace) -> dict:
    h, r, lh, lm = a.hit_ratio, a.rps, a.hit_ms, a.miss_ms
    eff = h * lh + (1 - h) * (lh + lm)
    out: dict = {
        "inputs": {"rps": r, "hit_ratio": h, "hit_ms": lh, "miss_ms": lm},
        "latency": {
            "no_cache_ms": lm,
            "effective_ms": round(eff, 3),
            "speedup": round(lm / eff, 2) if eff > 0 else None,
        },
        "origin": {
            "rps_without_cache": r,
            "rps_with_cache": round((1 - h) * r, 3),
            "reduction_factor": round(1 / (1 - h), 1) if h < 1 else None,
        },
        "benefit": {"latency_saved_ms_per_second": round(r * h * lm, 1)},
        "what_if": [],
        "notes": [],
    }
    for hr in sorted({0.5, 0.8, 0.9, 0.95, 0.99, round(h, 4)}):
        out["what_if"].append({
            "hit_ratio": hr,
            "effective_ms": round(hr * lh + (1 - hr) * (lh + lm), 3),
            "origin_rps": round((1 - hr) * r, 3),
        })
    if a.target_ms is not None:
        if a.target_ms <= lh:
            out["target"] = {"target_ms": a.target_ms, "required_hit_ratio": None,
                             "note": "target is at or below the hit latency: unreachable by caching alone"}
        else:
            need = 1 - (a.target_ms - lh) / lm if lm > 0 else 0.0
            out["target"] = {"target_ms": a.target_ms, "required_hit_ratio": round(max(0.0, min(1.0, need)), 4)}
    if a.origin_capacity_rps is not None:
        need = 1 - a.origin_capacity_rps / r if r > 0 else 0.0
        out["origin"]["capacity_rps"] = a.origin_capacity_rps
        out["origin"]["required_hit_ratio_for_capacity"] = round(max(0.0, min(1.0, need)), 4)
        out["notes"].append("A cold cache (deploy, flush, failover) sends full traffic to the origin: plan warm-up, "
                            "request collapsing and stale serving if origin capacity is below rps_without_cache.")
    if a.keys is not None:
        if a.avg_bytes is None:
            raise ValueError("--keys needs --avg-bytes")
        per_key = a.avg_key_bytes + a.avg_bytes + a.overhead_bytes
        raw = a.keys * per_key
        total = raw * a.fragmentation / (1 - a.reserved_pct / 100)
        out["memory"] = {
            "keys": a.keys,
            "bytes_per_key": per_key,
            "data_bytes": raw,
            "with_fragmentation_and_headroom_bytes": round(total),
            "human": fmt_bytes(total),
            "assumptions": {"avg_key_bytes": a.avg_key_bytes, "overhead_bytes": a.overhead_bytes,
                            "fragmentation": a.fragmentation, "reserved_pct": a.reserved_pct},
        }
        out["notes"].append("Size maxmemory to the working set, not the whole dataset: a cache that holds the hot keys "
                            "(often the top 10–20%) gets most of the hit ratio.")
    if lm <= lh:
        out["notes"].append("Miss latency is not higher than hit latency: caching won't help latency here.")
    if h < 0.5:
        out["notes"].append("Hit ratio below 0.5: check key design (variants, query strings, Vary) before adding capacity.")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cache ROI and sizing math.", epilog="Prints JSON. Exit 0 on success, 2 on bad usage.")
    p.add_argument("--rps", type=float, required=True, help="request rate R (requests/second)")
    p.add_argument("--hit-ratio", type=float, required=True, help="hit ratio h, 0..1")
    p.add_argument("--hit-ms", type=float, required=True, help="latency of a cache hit in ms")
    p.add_argument("--miss-ms", type=float, required=True, help="extra latency of a miss (source fetch) in ms")
    p.add_argument("--target-ms", type=float, help="target average latency; prints the hit ratio needed")
    p.add_argument("--origin-capacity-rps", type=float, help="origin capacity; prints the hit ratio needed to stay under it")
    p.add_argument("--keys", type=int, help="number of keys to hold")
    p.add_argument("--avg-bytes", type=float, help="average value size in bytes (serialized, compressed if you compress)")
    p.add_argument("--avg-key-bytes", type=float, default=40.0, help="average key length in bytes (default 40)")
    p.add_argument("--overhead-bytes", type=float, default=60.0, help="per-key store overhead (default 60, measure it)")
    p.add_argument("--fragmentation", type=float, default=1.2, help="allocator fragmentation factor (default 1.2)")
    p.add_argument("--reserved-pct", type=float, default=25.0, help="headroom kept free, percent (default 25)")
    a = p.parse_args(argv)
    problems = []
    if not 0 <= a.hit_ratio <= 1:
        problems.append("--hit-ratio must be between 0 and 1")
    if a.rps < 0 or a.hit_ms < 0 or a.miss_ms < 0:
        problems.append("--rps, --hit-ms and --miss-ms must be >= 0")
    if a.fragmentation < 1:
        problems.append("--fragmentation must be >= 1")
    if not 0 <= a.reserved_pct < 100:
        problems.append("--reserved-pct must be in [0, 100)")
    if a.keys is not None and a.avg_bytes is None:
        problems.append("--keys needs --avg-bytes")
    if problems:
        for msg in problems:
            print(f"error: {msg}", file=sys.stderr)
        return 2
    json.dump(compute(a), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
