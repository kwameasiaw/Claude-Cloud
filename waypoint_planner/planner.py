"""Mission engine: spec + pilot profile -> fully resolved, validated waypoint plan.

Height terms used throughout:
  agl  - height above the ground directly below the drone (what the UK 120 m limit is about)
  rel  - height relative to the take-off point (what DJI Fly actually flies)
  amsl - ground / altitude above mean sea level (terrain data)
"""

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from . import geo

PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "pilot-profile.json"

RTH_SPEED_MS = 10.0          # Mini 4 Pro default RTH cruise
TAKEOFF_LANDING_S = 60.0     # take-off, checks and landing overhead
PHOTO_S = 2.0
LEG_SAMPLES = 10             # terrain samples per leg when terrain data is available


@dataclass
class Waypoint:
    index: int
    lat: float
    lon: float
    label: str = ""
    ground_m: float | None = None
    agl_m: float = 0.0
    rel_m: float = 0.0
    speed_ms: float = 3.0
    gimbal_pitch_deg: float = -15.0
    heading: str = "followWayline"     # followWayline | towardPOI | fixed
    heading_deg: float = 0.0
    hover_s: float = 0.0
    photo: bool = False
    start_record: bool = False
    stop_record: bool = False
    leg_m: float = 0.0                 # horizontal distance from the previous point (or home)
    climb_gradient: float = 0.0        # signed rise/run of the leg arriving here
    min_leg_agl_m: float | None = None


@dataclass
class Plan:
    name: str
    profile: dict
    settings: dict
    home: dict
    poi: dict | None
    waypoints: list
    terrain_known: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def load_profile(path=PROFILE_PATH):
    with open(path) as f:
        return json.load(f)


def _ground(point):
    return point.get("ground_m") if point else None


def fill_terrain(spec, lookup):
    """Fill missing ground_m values (home, poi, waypoints) and return leg samples.

    lookup: callable(list[(lat, lon)]) -> list[float]. Returns {leg_index: [ground_m...]}
    or None if the lookup fails (caller decides how loudly to complain).
    """
    pts, refs = [], []
    for key in ("home", "poi"):
        if spec.get(key) and spec[key].get("ground_m") is None:
            pts.append((spec[key]["lat"], spec[key]["lon"]))
            refs.append(spec[key])
    for wp in spec["waypoints"]:
        if wp.get("ground_m") is None:
            pts.append((wp["lat"], wp["lon"]))
            refs.append(wp)
    chain = ([spec["home"]] if spec.get("home") else []) + spec["waypoints"]
    sample_pts = []
    for a, b in zip(chain, chain[1:]):
        for s in range(1, LEG_SAMPLES):
            sample_pts.append(geo.interpolate(a["lat"], a["lon"], b["lat"], b["lon"], s / LEG_SAMPLES))
    values = lookup(pts + sample_pts)
    for ref, v in zip(refs, values[:len(pts)]):
        ref["ground_m"] = round(v, 1)
    # keyed by the index of the waypoint each leg arrives at (0 = take-off -> WP1)
    samples, rest = {}, values[len(pts):]
    offset = 0 if spec.get("home") else 1
    for leg in range(len(chain) - 1):
        samples[leg + offset] = rest[leg * (LEG_SAMPLES - 1):(leg + 1) * (LEG_SAMPLES - 1)]
    return samples


def build_plan(spec, profile=None, leg_samples=None):
    profile = copy.deepcopy(profile or load_profile())
    s = {**profile["mission_defaults"], **(spec.get("settings") or {})}
    limits = profile["limits"]
    plan = Plan(name=spec.get("name") or "Untitled mission", profile=profile, settings=s,
                home=None, poi=copy.deepcopy(spec.get("poi")), waypoints=[], terrain_known=False)
    raw = spec["waypoints"]
    if len(raw) < 2:
        plan.errors.append("A DJI Fly mission needs at least 2 waypoints.")
    if len(raw) > limits["max_waypoints"]:
        plan.errors.append(f"{len(raw)} waypoints exceeds the DJI Fly limit of {limits['max_waypoints']}.")

    home = copy.deepcopy(spec.get("home"))
    if not home:
        home = {"lat": raw[0]["lat"], "lon": raw[0]["lon"], "ground_m": raw[0].get("ground_m"), "assumed": True}
        plan.warnings.append("No Home placemark: assuming take-off right below WP1. Heights are relative "
                             "to wherever you actually take off, so launch there.")
    plan.home = home

    plan.terrain_known = _ground(home) is not None and all(w.get("ground_m") is not None for w in raw)
    if not plan.terrain_known:
        plan.warnings.append("No terrain data: heights assume the ground is level with the take-off point. "
                             "Check hills/valleys along the route before flying.")
    home_ground = _ground(home) or 0.0

    def to_rel(agl, ground):
        return agl + ((ground - home_ground) if plan.terrain_known else 0.0)

    # --- altitude profile: gentle ramp from WP1 towards cruise, never steeper than max gradient
    grad = s["max_climb_gradient"]
    prev = None
    for i, w in enumerate(raw):
        ground = w.get("ground_m")
        leg = geo.distance_m(prev.lat, prev.lon, w["lat"], w["lon"]) if prev else \
            geo.distance_m(home["lat"], home["lon"], w["lat"], w["lon"])
        wp = Waypoint(index=i, lat=w["lat"], lon=w["lon"], label=w.get("label", f"WP{i + 1}"),
                      ground_m=ground, leg_m=leg, speed_ms=w.get("speed_ms", s["speed_ms"]),
                      hover_s=w.get("hover_s", 0.0), photo=bool(w.get("photo")))
        if "alt_rel_m" in w:
            wp.rel_m = w["alt_rel_m"]
            wp.agl_m = w["alt_rel_m"] - ((ground - home_ground) if plan.terrain_known else 0.0)
        else:
            if "alt_agl_m" in w:
                wp.agl_m = w["alt_agl_m"]
            elif "alt_amsl_m" in w and ground is not None:
                wp.agl_m = w["alt_amsl_m"] - ground
            elif prev is None:
                wp.agl_m = s["start_alt_agl_m"]
            else:
                step = s["cruise_alt_agl_m"] - prev.agl_m
                wp.agl_m = prev.agl_m + max(-grad * leg, min(grad * leg, step))
            wp.rel_m = to_rel(wp.agl_m, ground or home_ground)
        wp.agl_m, wp.rel_m = round(wp.agl_m, 1), round(wp.rel_m, 1)
        plan.waypoints.append(wp)
        prev = wp

    # --- POI height relative to take-off
    if plan.poi:
        plan.poi.setdefault("height_agl_m", s["poi_height_agl_m"])
        pg = _ground(plan.poi)
        plan.poi["rel_m"] = round(plan.poi["height_agl_m"] +
                                  ((pg - home_ground) if (plan.terrain_known and pg is not None) else 0.0), 1)

    # --- heading, gimbal, recording
    wps = plan.waypoints
    for w, src in zip(wps, raw):
        h = str(src.get("heading", s["heading"])).lower()
        if h in ("auto", "poi") and plan.poi:
            w.heading = "towardPOI"
        elif h in ("auto", "path", "course", "followwayline"):
            w.heading = "followWayline"
        else:
            try:
                w.heading, w.heading_deg = "fixed", float(h) % 360
            except ValueError:
                plan.errors.append(f"{w.label}: unknown heading '{h}'.")
        if "gimbal_pitch_deg" in src:
            w.gimbal_pitch_deg = src["gimbal_pitch_deg"]
        elif s["gimbal"] == "track_poi" and plan.poi:
            d = geo.distance_m(w.lat, w.lon, plan.poi["lat"], plan.poi["lon"])
            w.gimbal_pitch_deg = -math.degrees(math.atan2(w.rel_m - plan.poi["rel_m"], max(d, 1.0)))
        else:
            w.gimbal_pitch_deg = s["default_gimbal_pitch_deg"]
        w.gimbal_pitch_deg = round(max(-90.0, min(20.0, w.gimbal_pitch_deg)), 1) + 0.0  # no "-0"
    if s["record_video_from_wp1"] and wps:
        wps[0].start_record = True
        wps[-1].stop_record = True
        if any(w.photo for w in wps):
            plan.warnings.append("Photo actions are set while video is recording; the Mini 4 Pro cannot "
                                 "take stills mid-recording, so those photos will be skipped.")

    _validate(plan, limits, leg_samples or {})
    _stats(plan, limits)
    return plan


def _validate(plan, limits, leg_samples):
    s = plan.settings
    home_ground = _ground(plan.home) or 0.0
    prev_rel = 0.0
    for i, w in enumerate(plan.waypoints):
        rise = w.rel_m - prev_rel
        w.climb_gradient = rise / w.leg_m if w.leg_m > 0.5 else (math.inf if abs(rise) > 0.5 else 0.0)
        g = abs(w.climb_gradient)
        if i == 0:
            if g > s["max_transit_gradient"]:
                plan.warnings.append(
                    f"Take-off -> {w.label}: {_angle(g)} climb on the diagonal fly-in. Move WP1 further from "
                    f"the take-off point or lower it for a shallower approach.")
        elif g > s["max_climb_gradient"] + 0.005:
            need = abs(rise) / s["max_climb_gradient"]
            plan.errors.append(
                f"{plan.waypoints[i - 1].label} -> {w.label}: {'climb' if rise > 0 else 'descent'} of "
                f"{abs(rise):.0f} m over {w.leg_m:.0f} m is {_angle(g)}, steeper than your "
                f"{_angle(s['max_climb_gradient'])} limit. Needs ~{need:.0f} m of horizontal travel.")
        prev_rel = w.rel_m

        if w.agl_m > limits["max_agl_m"] + 0.05:
            plan.errors.append(f"{w.label}: {w.agl_m:.0f} m above ground exceeds the UK 120 m limit.")
        if w.agl_m < limits["min_agl_warn_m"]:
            plan.warnings.append(f"{w.label}: only {w.agl_m:.0f} m above ground; check trees, wires and buildings.")
        if w.speed_ms > limits["max_speed_ms"] or w.speed_ms <= 0:
            plan.errors.append(f"{w.label}: speed {w.speed_ms} m/s outside 0-{limits['max_speed_ms']} m/s.")
        d_home = geo.distance_m(plan.home["lat"], plan.home["lon"], w.lat, w.lon)
        if d_home > limits["vlos_warn_m"]:
            plan.warnings.append(f"{w.label}: {d_home:.0f} m from take-off. You must keep the drone in "
                                 f"direct sight; consider a spotter or a closer launch point.")

        samples = leg_samples.get(i)
        if samples and plan.terrain_known:
            a_rel = plan.waypoints[i - 1].rel_m if i else 0.0
            n = len(samples) + 1
            agls = [a_rel + (w.rel_m - a_rel) * k / n + home_ground - ground
                    for k, ground in enumerate(samples, start=1)]
            w.min_leg_agl_m = round(min(agls), 1)
            if i and min(agls) < limits["min_agl_warn_m"]:
                plan.warnings.append(f"Leg into {w.label}: terrain brings the drone down to "
                                     f"{min(agls):.0f} m above ground.")
            if max(agls) > limits["max_agl_m"]:
                plan.errors.append(f"Leg into {w.label}: ground drops away; drone reaches "
                                   f"{max(agls):.0f} m above ground (UK limit 120 m).")


def _angle(gradient):
    if math.isinf(gradient):
        return "vertical (90 deg)"
    return f"{math.degrees(math.atan(gradient)):.0f} deg (1:{1 / gradient:.1f})" if gradient else "level"


def _stats(plan, limits):
    s, wps = plan.settings, plan.waypoints
    route_m = sum(w.leg_m for w in wps[1:])
    mission_s = 0.0
    for a, b in zip(wps, wps[1:]):
        mission_s += math.hypot(b.leg_m, b.rel_m - a.rel_m) / a.speed_ms
    mission_s += sum(w.hover_s + (PHOTO_S if w.photo else 0) for w in wps)
    fly_in_s = math.hypot(wps[0].leg_m, wps[0].rel_m) / s["transitional_speed_ms"] if wps else 0
    back_m = geo.distance_m(wps[-1].lat, wps[-1].lon, plan.home["lat"], plan.home["lon"]) if wps else 0
    back_s = back_m / RTH_SPEED_MS + (wps[-1].rel_m / 3.0 if wps else 0)
    total_s = mission_s + fly_in_s + back_s + TAKEOFF_LANDING_S
    plan.stats = {
        "waypoints": len(wps),
        "route_m": round(route_m),
        "video_s": round(mission_s),
        "total_min": round(total_s / 60, 1),
        "max_agl_m": max((w.agl_m for w in wps), default=0),
        "max_rel_m": max((w.rel_m for w in wps), default=0),
        "max_dist_home_m": round(max((geo.distance_m(plan.home["lat"], plan.home["lon"], w.lat, w.lon)
                                      for w in wps), default=0)),
        "battery_budget_min": limits["battery_budget_min"],
    }
    if total_s / 60 > limits["battery_budget_min"]:
        plan.errors.append(f"Estimated flight {total_s / 60:.1f} min exceeds the {limits['battery_budget_min']} min "
                           f"battery budget (standard battery, with reserve). Split it into two missions.")
