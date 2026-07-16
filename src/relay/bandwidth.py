"""Per-device, per-mode byte accounting -- the data source for the ~689x counter.

The workshop's headline number is a bandwidth ratio, but nothing in the original
relay measured bandwidth: neither /ingest_raw nor /ingest_features recorded how
many bytes arrived. This module is that missing measurement.

Bytes are taken from the request's Content-Length -- the count the LAN actually
carried. Re-serialising the parsed model instead would measure OUR encoder, not
the wire, and Mode 1's figure would be wrong by the JSON whitespace.

Totals are CUMULATIVE and survive a mode switch: that is what makes the ratio
appear on screen when a student switches Mode 1 -> Mode 2 with only one Jetson.
"""
import time

MODES = ("mode1", "mode2", "mode3")

# Smoothing for the live bytes/sec readout. A raw per-second delta is too jumpy
# to read; this is a compromise between responsive and legible.
EWMA_ALPHA = 0.3


def _blank():
    return {"total_bytes": 0, "last_seen": None, "ewma_bps": 0.0, "_prev_t": None}


class BandwidthTracker:
    """Cumulative byte totals + a smoothed rate, per device and per mode."""

    def __init__(self):
        self._d = {}

    def _dev(self, device):
        if device not in self._d:
            self._d[device] = {m: _blank() for m in MODES}
        return self._d[device]

    def record(self, device, mode, nbytes):
        """Called once per ingest. `nbytes` is Content-Length; None is ignored."""
        if mode not in MODES or not nbytes:
            return
        s = self._dev(device)[mode]
        now = time.time()

        s["total_bytes"] += int(nbytes)
        if s["_prev_t"] is not None:
            dt = now - s["_prev_t"]
            if dt > 0:
                bps = nbytes / dt
                s["ewma_bps"] = (bps if s["ewma_bps"] == 0.0
                                 else EWMA_ALPHA * bps + (1 - EWMA_ALPHA) * s["ewma_bps"])
        s["_prev_t"] = now
        s["last_seen"] = now

    def live_mode(self, device):
        """Which mode sent most recently -- 1, 2, 3, or None."""
        s = self._dev(device)
        seen = [(s[m]["last_seen"], m) for m in MODES if s[m]["last_seen"]]
        return int(max(seen)[1][-1]) if seen else None

    def snapshot(self, device):
        """The `bandwidth` block of an SSE event."""
        s = self._dev(device)
        m1, m2 = s["mode1"]["total_bytes"], s["mode2"]["total_bytes"]

        # Guard the ratio: with only one mode seen, "84 MB / 0" is meaningless.
        # The dashboard renders None as a dash until both modes have sent.
        ratio = (m1 / m2) if (m1 > 0 and m2 > 0) else None

        return {
            "mode1_total": m1,
            "mode2_total": m2,
            "mode3_total": s["mode3"]["total_bytes"],
            "mode1_bps": round(s["mode1"]["ewma_bps"], 1),
            "mode2_bps": round(s["mode2"]["ewma_bps"], 1),
            "mode3_bps": round(s["mode3"]["ewma_bps"], 1),
            "mode1_last_seen": s["mode1"]["last_seen"],
            "mode2_last_seen": s["mode2"]["last_seen"],
            "mode3_last_seen": s["mode3"]["last_seen"],
            "ratio": round(ratio, 1) if ratio else None,
            "live_mode": self.live_mode(device),
        }

    def reset(self, device=None):
        """Clear one device, or all. The next student pair needs a clean demo."""
        if device is None:
            self._d.clear()
        else:
            self._d.pop(device, None)

    def devices(self):
        return sorted(self._d)
