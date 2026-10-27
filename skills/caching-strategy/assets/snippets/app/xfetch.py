"""Probabilistic early expiration (XFetch; Vattani, Chierichetti, Lowenstein, VLDB 2015).

Each reader recomputes slightly before expiry with a probability that rises as expiry nears and
with how long the recomputation takes, so one hot key is refreshed by one early reader instead
of a herd at the exact expiry moment. No locks, no coordination.

    recompute if  now - delta * beta * ln(rand())  >=  expiry

delta = how long the last recomputation took (seconds); beta = 1.0 default (> 1 favors earlier refresh).

Store {value, delta, expiry} together. Pair with a hard TTL slightly above `ttl` so the key
eventually disappears if nobody reads it. Works with any cache client; redis-py shown.
"""

from __future__ import annotations

import json
import math
import random
import time
from typing import Any, Callable


def xfetch(redis, key: str, recompute: Callable[[], Any], ttl: float, beta: float = 1.0) -> Any:
    raw = redis.get(key)
    if raw is not None:
        entry = json.loads(raw)
        early = entry["delta"] * beta * math.log(random.random() or 1e-12)  # log(rand) <= 0
        if time.time() - early < entry["expiry"]:
            return entry["value"]
    start = time.time()
    value = recompute()
    delta = time.time() - start
    entry = {"value": value, "delta": delta, "expiry": time.time() + ttl}
    # hard TTL a bit above ttl; jitter it if many keys are written together
    redis.set(key, json.dumps(entry), ex=int(ttl * 1.2) + 1)
    return value
