"""Design a route from just a take-off point and a POI.

Default style "approach_orbit": leave Home towards the POI, start recording at WP1, climb
gradually along the approach (planner.py enforces the gradient), join the orbit tangentially on
the near side and circle the POI, finishing where the orbit began.
"""

import math

from . import geo


def approach_orbit(home, poi, radius_m, wp1_offset_m, spacing_m, points_per_lap, laps, direction,
                   approach_m=None):
    dist = geo.distance_m(home["lat"], home["lon"], poi["lat"], poi["lon"])
    if dist <= radius_m:
        raise ValueError(f"Home is {dist:.0f} m from the POI, inside the {radius_m:.0f} m orbit. "
                         f"Take off further away or use a smaller radius.")
    out_bearing = geo.bearing_deg(home["lat"], home["lon"], poi["lat"], poi["lon"])
    entry_bearing = (out_bearing + 180) % 360            # from POI to the near side of the circle
    step = 360 / points_per_lap * (1 if direction == "cw" else -1)

    # The approach runs along the POI-Home line to the circle's near point. approach_m (WP1 -> orbit
    # entry) lets it start behind the take-off point, e.g. when Home sits on a slope too steep to
    # climb within the gradient limit.
    if approach_m:
        start = radius_m + approach_m              # WP1 distance from the POI
    else:
        run = dist - radius_m
        start = dist - min(wp1_offset_m, run * 0.3)
    waypoints = []
    n_legs = max(1, math.ceil((start - radius_m) / spacing_m))
    for k in range(n_legs + 1):
        d = start - (start - radius_m) * k / n_legs
        lat, lon = geo.destination(poi["lat"], poi["lon"], entry_bearing, d)
        waypoints.append({"label": f"WP{len(waypoints) + 1}", "lat": round(lat, 8), "lon": round(lon, 8)})
    waypoints[-1]["label"] += " (orbit entry)"

    for k in range(1, points_per_lap * laps + 1):
        lat, lon = geo.destination(poi["lat"], poi["lon"], entry_bearing + step * k, radius_m)
        waypoints.append({"label": f"WP{len(waypoints) + 1}", "lat": round(lat, 8), "lon": round(lon, 8)})
    return waypoints


def generate_spec(name, home, poi, profile, **overrides):
    r = {**profile["route_defaults"], **{k: v for k, v in overrides.items() if v is not None}}
    if r["style"] != "approach_orbit":
        raise ValueError(f"Unknown route style {r['style']!r}")
    wps = approach_orbit(home, poi, r["orbit_radius_m"], r["wp1_offset_m"], r["approach_spacing_m"],
                         r["orbit_points_per_lap"], r["orbit_laps"], r["orbit_direction"], r.get("approach_m"))
    return {"name": name, "home": home, "poi": poi, "route": r, "settings": {}, "waypoints": wps}
