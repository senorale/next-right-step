"""
Per-client rate limits on the endpoints that call the model, so one client
can't run up the paid key's bill or use up its quota for everyone.

The client is the X-Client-IP header the Next.js routes send (src/lib/agent-api.ts).
This service has no public domain on Railway, so only the frontend reaches it
and the header can't be forged from outside. Requests without it (local
development, evals) aren't limited.

Counts live in memory: they reset on deploy and assume one server process
(api/Procfile runs a single uvicorn worker).
"""

import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

MINUTE, DAY = 60, 24 * 60 * 60
# bucket -> (max requests, window in seconds). /chat and /retry-report share
# "report": both end in a report call, and /chat can run up to
# MAX_TOOL_ITERATIONS model calls before it.
LIMITS = {
    "report": [(10, MINUTE), (60, DAY)],
    "intake": [(60, MINUTE)],
}
# Drop clients idle past every window once this many are tracked.
SWEEP_AT = 10_000

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _sweep(now: float) -> None:
    longest = max(window for limits in LIMITS.values() for _, window in limits)
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > longest]:
        del _hits[key]


def rate_limit(bucket: str):
    """FastAPI dependency: 429 once the client is over any of the bucket's limits."""
    limits = LIMITS[bucket]
    longest = max(window for _, window in limits)

    async def check(request: Request) -> None:
        client = request.headers.get("x-client-ip")
        if not client:
            return
        now = time.time()
        if len(_hits) >= SWEEP_AT:
            _sweep(now)
        hits = _hits[(bucket, client)]
        while hits and now - hits[0] > longest:
            hits.popleft()
        for most, window in limits:
            recent = [t for t in hits if now - t <= window]
            if len(recent) >= most:
                retry_after = int(window - (now - recent[0])) + 1
                logger.warning("Rate limited %s on %s: %d in %ds", client, bucket, len(recent), window)
                raise HTTPException(
                    status_code=429,
                    detail="You've sent a lot of requests. Please wait a bit and try again.",
                    headers={"Retry-After": str(retry_after)},
                )
        hits.append(now)

    return check
