"""Human-facing outputs: a 3D preview KML for Google Earth and a markdown flight brief."""

import math
from xml.sax.saxutils import escape


def preview_kml(plan):
    """3D flight path for Google Earth. Uses height above ground so it sits correctly on terrain."""
    w = plan.waypoints
    home = plan.home
    path = " ".join(f"{p.lon:.7f},{p.lat:.7f},{p.agl_m:.1f}" for p in w)
    fly_in = f"{home['lon']:.7f},{home['lat']:.7f},0 {w[0].lon:.7f},{w[0].lat:.7f},{w[0].agl_m:.1f}"
    marks = []
    for p in w:
        desc = (f"{p.agl_m:.0f} m above ground / {p.rel_m:.0f} m in DJI Fly, {p.speed_ms:g} m/s, "
                f"gimbal {p.gimbal_pitch_deg:.0f} deg" + (f", hover {p.hover_s:g}s" if p.hover_s else "")
                + (", REC start" if p.start_record else "") + (", REC stop" if p.stop_record else ""))
        marks.append(f"""    <Placemark><name>{escape(p.label)}</name><description>{escape(desc)}</description>
      <styleUrl>#wp</styleUrl><Point><altitudeMode>relativeToGround</altitudeMode><extrude>1</extrude>
      <coordinates>{p.lon:.7f},{p.lat:.7f},{p.agl_m:.1f}</coordinates></Point></Placemark>""")
    marks.append(f"""    <Placemark><name>Home (take-off)</name><styleUrl>#home</styleUrl>
      <Point><coordinates>{home['lon']:.7f},{home['lat']:.7f},0</coordinates></Point></Placemark>""")
    if plan.poi:
        p = plan.poi
        marks.append(f"""    <Placemark><name>POI: {escape(p.get('name', 'POI'))}</name><styleUrl>#poi</styleUrl>
      <Point><altitudeMode>relativeToGround</altitudeMode><extrude>1</extrude>
      <coordinates>{p['lon']:.7f},{p['lat']:.7f},{p['height_agl_m']:.1f}</coordinates></Point></Placemark>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{escape(plan.name)} (flight preview{"" if plan.terrain_known else ": HEIGHTS NOT TERRAIN-CHECKED"})</name>
    <Style id="route"><LineStyle><color>ff00d4ff</color><width>4</width></LineStyle>
      <PolyStyle><color>4000d4ff</color></PolyStyle></Style>
    <Style id="flyin"><LineStyle><color>ff9e9e9e</color><width>2</width></LineStyle></Style>
    <Style id="wp"><IconStyle><scale>0.8</scale><Icon><href>http://maps.google.com/mapfiles/kml/paddle/ylw-circle.png</href></Icon></IconStyle></Style>
    <Style id="home"><IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/paddle/H.png</href></Icon></IconStyle></Style>
    <Style id="poi"><IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/paddle/red-stars.png</href></Icon></IconStyle></Style>
    <Placemark><name>Flight path</name><styleUrl>#route</styleUrl>
      <LineString><extrude>1</extrude><tessellate>1</tessellate><altitudeMode>relativeToGround</altitudeMode>
      <coordinates>{path}</coordinates></LineString></Placemark>
    <Placemark><name>Fly-in from take-off (not recorded)</name><styleUrl>#flyin</styleUrl>
      <LineString><altitudeMode>relativeToGround</altitudeMode><coordinates>{fly_in}</coordinates></LineString></Placemark>
{chr(10).join(marks)}
  </Document>
</kml>
"""


def _deg(gradient):
    return "vertical" if math.isinf(gradient) else f"{math.degrees(math.atan(gradient)):+.0f}°"


def brief_md(plan, kmz_name):
    s, st = plan.settings, plan.stats
    status = "NOT READY: fix the errors below" if plan.errors else "Ready to load"
    lines = [
        f"# {plan.name}",
        "",
        f"**Status:** {status}  ",
        f"**Mission file:** `{kmz_name}` (DJI Fly / Mini 4 Pro)  ",
        f"**Terrain-corrected heights:** {'yes' if plan.terrain_known else 'no (flat ground assumed)'}",
        "",
        "## Summary",
        "",
        "| | |",
        "|---|---|",
        f"| Waypoints | {st['waypoints']} |",
        f"| Route length (recorded) | {st['route_m']} m |",
        f"| Video length | {st['video_s'] // 60} min {st['video_s'] % 60:02d} s |",
        f"| Total flight incl. take-off, fly-in, return | ~{st['total_min']} min (budget {st['battery_budget_min']} min) |",
        f"| Highest above ground | {st['max_agl_m']:.0f} m (UK limit 120 m) |",
        f"| Furthest from take-off | {st['max_dist_home_m']} m |",
        f"| Cruise speed | {s['speed_ms']:g} m/s |",
        f"| Steepest allowed climb | {_deg(s['max_climb_gradient'])} |",
        f"| At the end | {s['finish_action']} · signal lost: {s['rc_lost_action']} |",
    ]
    if plan.poi:
        p = plan.poi
        lines.append(f"| Point of interest | {p.get('name', 'POI')}, aim {p['height_agl_m']:.0f} m above its base |")
    lines += ["", "## Waypoints", "",
              "| # | Height in DJI Fly | Above ground | Leg | Climb | Speed | Gimbal | Facing | Actions |",
              "|---|---|---|---|---|---|---|---|---|"]
    for w in plan.waypoints:
        facing = {"towardPOI": "POI", "followWayline": "course"}.get(w.heading, f"{w.heading_deg:.0f}°")
        acts = [a for a, on in (("REC ▶", w.start_record), (f"hover {w.hover_s:g}s", w.hover_s > 0),
                                ("photo", w.photo), ("REC ■", w.stop_record)) if on]
        lines.append(f"| {w.label} | {w.rel_m:.0f} m | {w.agl_m:.0f} m | {w.leg_m:.0f} m | "
                     f"{_deg(w.climb_gradient)} | {w.speed_ms:g} m/s | {w.gimbal_pitch_deg:.0f}° | {facing} | "
                     f"{', '.join(acts) or '-'} |")
    lines.append("")
    lines.append("*Leg/Climb on the first row is the un-recorded diagonal fly-in from take-off.*")
    if plan.errors:
        lines += ["", "## ❌ Errors (mission not safe to load)", ""] + [f"- {e}" for e in plan.errors]
    if plan.warnings:
        lines += ["", "## ⚠️ Check before flying", ""] + [f"- {e}" for e in plan.warnings]
    lines += [
        "",
        "## Camera (set in DJI Fly before starting the mission)",
        "",
        "- 4K, 24 or 30 fps. D-Log M if you colour grade, otherwise Normal",
        "- Shutter about double the frame rate (1/50 or 1/60). Use an ND filter in daylight",
        "- Set white balance manually and lock exposure (AE lock) so the video doesn't flicker",
        "",
        "## Pre-flight (UK)",
        "",
        "- Take off **from the planned Home point**: every height is measured from where you launch",
        "- Check airspace and restrictions (flight restriction zones, NOTAMs) in NATS Drone Assist",
        "- Carry your Flyer ID and display your Operator ID on the drone. Get landowner permission to take off",
        "- Keep the drone in sight the whole time. Stay away from uninvolved people and never fly over crowds",
        "- Keep your thumbs on the sticks. Press Flight Pause on the RC 2 to stop the mission and hover",
    ]
    return "\n".join(lines) + "\n"
