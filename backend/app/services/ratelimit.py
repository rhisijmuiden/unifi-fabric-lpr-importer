"""In-memory rate limiting (the app runs as one process).

Counts events per key in a sliding window: failed sign-ins per user name and per
IP address, and requests per API key. Counters reset when the app restarts.
"""

import threading
import time
from collections import deque

_lock = threading.Lock()
_events: dict[str, deque[float]] = {}


def _trim(events: deque[float], window: float, now: float) -> None:
    while events and events[0] <= now - window:
        events.popleft()


def count(key: str, window: float) -> int:
    now = time.monotonic()
    with _lock:
        events = _events.get(key)
        if not events:
            return 0
        _trim(events, window, now)
        return len(events)


def hit(key: str, window: float) -> int:
    """Record an event and return the number of events in the window, this one included."""
    now = time.monotonic()
    with _lock:
        events = _events.setdefault(key, deque())
        _trim(events, window, now)
        events.append(now)
        return len(events)


def retry_after(key: str, window: float) -> int:
    """Seconds until the oldest event in the window expires."""
    now = time.monotonic()
    with _lock:
        events = _events.get(key)
        if not events:
            return 0
        return max(1, int(events[0] + window - now) + 1)


def clear(key: str) -> None:
    with _lock:
        _events.pop(key, None)


def reset() -> None:
    with _lock:
        _events.clear()
