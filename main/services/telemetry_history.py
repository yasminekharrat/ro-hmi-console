# main/services/telemetry_history.py
# ---------------------------------------------------------------------------
# Thread-safe rolling buffer of telemetry samples.
# Written by the poll loop in hmi-app (via /api/telemetry) — or you can
# call record_sample() directly from a background poller.
#
# Used by:
#   - report_engine.py   (daily / weekly Excel reports)
#   - diagnostics routes (/api/diagnostics/stats)
#
# All timestamps are Unix epoch floats (time.time()).
# ---------------------------------------------------------------------------

import threading
import time
from collections import deque
from config.report_config import MAX_HISTORY_SAMPLES


_lock    = threading.Lock()

# { tag_id: deque([(timestamp, value), ...]) }
_buffers: dict[str, deque] = {}


def record_sample(tag_id: str, value, ts: float | None = None) -> None:
    """Append one (timestamp, value) pair for *tag_id*."""
    if ts is None:
        ts = time.time()
    with _lock:
        if tag_id not in _buffers:
            _buffers[tag_id] = deque(maxlen=MAX_HISTORY_SAMPLES)
        _buffers[tag_id].append((ts, value))


def record_batch(telemetry: dict, ts: float | None = None) -> None:
    """Convenience: record a whole {tag_id: value} dict at once."""
    if ts is None:
        ts = time.time()
    for tag_id, value in telemetry.items():
        if value is not None:
            record_sample(tag_id, value, ts)


def get_samples(
    tag_id: str,
    since: float | None = None,
    until: float | None = None,
) -> list[tuple[float, float]]:
    """
    Return [(ts, value), …] for *tag_id* in the optional [since, until] window.
    Returns an empty list if the tag has never been recorded.
    """
    with _lock:
        buf = _buffers.get(tag_id)
        if not buf:
            return []
        samples = list(buf)

    if since is not None:
        samples = [(t, v) for t, v in samples if t >= since]
    if until is not None:
        samples = [(t, v) for t, v in samples if t <= until]
    return samples


def get_all_tag_ids() -> list[str]:
    with _lock:
        return list(_buffers.keys())


def clear_tag(tag_id: str) -> None:
    with _lock:
        if tag_id in _buffers:
            _buffers[tag_id].clear()


def stats_for_tag(
    tag_id: str,
    since: float | None = None,
    until: float | None = None,
) -> dict:
    """
    Return a stats dict for *tag_id* over [since, until]:
      { count, min, max, mean, std, last_value, last_ts, trend_per_hour }
    trend_per_hour: linear regression slope (units / hour), None if < 2 samples.
    """
    samples = get_samples(tag_id, since=since, until=until)
    if not samples:
        return {
            "count": 0, "min": None, "max": None, "mean": None,
            "std": None, "last_value": None, "last_ts": None,
            "trend_per_hour": None,
        }

    values = [v for _, v in samples if isinstance(v, (int, float))]
    if not values:
        last_ts, last_val = samples[-1]
        return {
            "count": len(samples), "min": None, "max": None, "mean": None,
            "std": None, "last_value": last_val, "last_ts": last_ts,
            "trend_per_hour": None,
        }

    n      = len(values)
    mean   = sum(values) / n
    vmin   = min(values)
    vmax   = max(values)
    std    = (sum((x - mean) ** 2 for x in values) / n) ** 0.5

    # Linear trend (least-squares slope) in units-per-hour
    trend = None
    if n >= 2:
        ts_vals = [(t, v) for t, v in samples if isinstance(v, (int, float))]
        t0      = ts_vals[0][0]
        xs      = [(t - t0) / 3600 for t, _ in ts_vals]   # hours
        ys      = [v for _, v in ts_vals]
        xm      = sum(xs) / n
        ym      = sum(ys) / n
        denom   = sum((x - xm) ** 2 for x in xs)
        if denom > 0:
            trend = sum((xs[i] - xm) * (ys[i] - ym) for i in range(n)) / denom

    last_ts, last_val = samples[-1]
    return {
        "count":          n,
        "min":            round(vmin, 4),
        "max":            round(vmax, 4),
        "mean":           round(mean, 4),
        "std":            round(std, 4),
        "last_value":     last_val,
        "last_ts":        last_ts,
        "trend_per_hour": round(trend, 6) if trend is not None else None,
    }