"""Ground elevation lookup (metres above sea level) via the free Open-Meteo API.

Uses the Copernicus 90 m DEM: good enough to correct waypoint heights over hills and
valleys, not for clearing individual trees or buildings. Needs outbound HTTPS to
api.open-meteo.com; callers should fall back gracefully when it is unreachable.
"""

import json
import urllib.parse
import urllib.request

API = "https://api.open-meteo.com/v1/elevation"
BATCH = 100


def lookup(points, timeout=15):
    """points: list of (lat, lon). Returns a list of elevations in metres AMSL."""
    out = []
    for i in range(0, len(points), BATCH):
        chunk = points[i:i + BATCH]
        query = urllib.parse.urlencode({
            "latitude": ",".join(f"{p[0]:.6f}" for p in chunk),
            "longitude": ",".join(f"{p[1]:.6f}" for p in chunk),
        })
        with urllib.request.urlopen(f"{API}?{query}", timeout=timeout) as resp:
            data = json.load(resp)
        out.extend(float(e) for e in data["elevation"])
    return out
