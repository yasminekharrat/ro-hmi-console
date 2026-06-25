# modules/diagnostics/diagnostics_routes.py
# ---------------------------------------------------------------------------
# Blueprint: diagnostics_bp  (url_prefix = /api/diagnostics)
#
# Routes
# ──────
# GET /api/diagnostics/stats
#     Query params:
#       window   = "1h" | "6h" | "24h" | "7d"  (default "24h")
#       tags     = comma-separated tag_ids       (default: all pressure & analog)
#     Response: { tag_id: { count, min, max, mean, std, last_value,
#                           last_ts, trend_per_hour, sparkline } }
#     sparkline: array of { ts, value } sampled at ≤120 points for the
#                frontend charts — downsampled so the payload stays small.
#
# GET /api/diagnostics/sparkline/<tag_id>
#     Fine-grained sparkline for a single tag (up to 500 points).
#     Query params: window (same as above)
# ---------------------------------------------------------------------------

import time
from flask import Blueprint, jsonify, request

from main.services import telemetry_history as hist

diagnostics_bp = Blueprint("diagnostics_bp", __name__,
                            url_prefix="/api/diagnostics")

# Tags shown by default in the diagnostic view (pressures + flow + conductivity)
DEFAULT_DIAG_TAGS = [
    "instruments-pressure_in",
    "instruments-pressure_out",
    "instruments-dp_sand",
    "instruments-dp_cartridge",
    "instruments-flow",
    "instruments-conductivity",
    "tanks-level_raw",
    "tanks-level_product",
]

WINDOWS = {
    "1h":  3_600,
    "6h":  21_600,
    "24h": 86_400,
    "7d":  604_800,
}


def _downsample(samples: list, n_points: int = 120) -> list:
    """
    Downsample *samples* to at most *n_points* by averaging equal-width buckets.
    Returns [{"ts": float, "value": float}, …].
    """
    if not samples:
        return []
    if len(samples) <= n_points:
        return [{"ts": t, "value": v} for t, v in samples]

    bucket_size = len(samples) / n_points
    result = []
    for i in range(n_points):
        start = int(i * bucket_size)
        end   = int((i + 1) * bucket_size)
        chunk = samples[start:end]
        avg_ts  = sum(t for t, _ in chunk) / len(chunk)
        avg_val = sum(v for _, v in chunk
                      if isinstance(v, (int, float))) / len(chunk)
        result.append({"ts": round(avg_ts, 1), "value": round(avg_val, 4)})
    return result


@diagnostics_bp.route("/stats", methods=["GET"])
def stats():
    window_key = request.args.get("window", "24h")
    window_sec = WINDOWS.get(window_key, WINDOWS["24h"])

    raw_tags = request.args.get("tags", "")
    tag_ids  = [t.strip() for t in raw_tags.split(",") if t.strip()] \
               or DEFAULT_DIAG_TAGS

    now   = time.time()
    since = now - window_sec

    result = {}
    for tag_id in tag_ids:
        s      = hist.stats_for_tag(tag_id, since=since, until=now)
        samples = hist.get_samples(tag_id, since=since, until=now)
        s["sparkline"] = _downsample(samples, n_points=120)
        result[tag_id] = s

    return jsonify({
        "window":    window_key,
        "window_sec": window_sec,
        "since":     since,
        "until":     now,
        "tags":      result,
    })


@diagnostics_bp.route("/sparkline/<tag_id>", methods=["GET"])
def sparkline(tag_id):
    window_key = request.args.get("window", "24h")
    window_sec = WINDOWS.get(window_key, WINDOWS["24h"])
    now        = time.time()
    since      = now - window_sec

    samples = hist.get_samples(tag_id, since=since, until=now)
    return jsonify({
        "tag_id":    tag_id,
        "window":    window_key,
        "count":     len(samples),
        "sparkline": _downsample(samples, n_points=500),
    })