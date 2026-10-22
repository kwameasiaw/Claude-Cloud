"""Turn a Google Earth KML/KMZ into a mission spec (a plain dict, saved as mission.json).

Conventions (see docs/google-earth-planning-guide.md):
  * A Point placemark named "Home" / "Takeoff" / "H" is the take-off point.
  * A Point placemark whose name starts with "POI" is the point of interest.
  * Every other Point placemark is a waypoint, in document order unless they are
    numbered ("WP1", "2", "Waypoint 3" ...), in which case they are sorted by number.
  * A LineString (Google Earth "Path") adds one waypoint per vertex.
  * Optional per-point settings go in the placemark description as key=value
    tokens, e.g. "alt=40 speed=2 hover=3 gimbal=-30 photo".
"""

import re
import zipfile
import xml.etree.ElementTree as ET

KML_NS = "{http://www.opengis.net/kml/2.2}"
GX_NS = "{http://www.google.com/kml/ext/2.2}"

HOME_NAMES = {"home", "takeoff", "take off", "take-off", "h", "launch"}

# description token -> (spec key, type)
TAGS = {
    "alt": ("alt_agl_m", float),
    "agl": ("alt_agl_m", float),
    "rel": ("alt_rel_m", float),
    "speed": ("speed_ms", float),
    "gimbal": ("gimbal_pitch_deg", float),
    "hover": ("hover_s", float),
    "heading": ("heading", str),
    "ground": ("ground_m", float),
    "height": ("height_agl_m", float),
}


def _read_kml_bytes(path):
    if str(path).lower().endswith(".kmz"):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                raise ValueError(f"{path}: no .kml inside the .kmz")
            name = "doc.kml" if "doc.kml" in names else names[0]
            return z.read(name)
    with open(path, "rb") as f:
        return f.read()


def _strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _parse_coords(text):
    pts = []
    for tok in (text or "").split():
        parts = tok.split(",")
        if len(parts) < 2:
            continue
        lon, lat = float(parts[0]), float(parts[1])
        alt = float(parts[2]) if len(parts) > 2 and parts[2] else 0.0
        pts.append((lat, lon, alt))
    return pts


def parse_tags(description):
    """Parse 'alt=40 speed=2 photo' style tokens out of a placemark description."""
    out = {}
    text = re.sub(r"<[^>]+>", " ", description or "")
    for key, val in re.findall(r"([A-Za-z_]+)\s*[=:]\s*(-?[\w.]+)", text):
        key = key.lower()
        if key in TAGS:
            spec_key, typ = TAGS[key]
            try:
                out[spec_key] = typ(val)
            except ValueError:
                pass
    if re.search(r"\bphoto\b", text, re.I):
        out["photo"] = True
    return out


def _altitude_mode(el):
    for tag in ("altitudeMode",):
        found = el.find(f".//{tag}")
        if found is not None and found.text:
            return found.text.strip()
    return "clampToGround"


def _number_in(name):
    m = re.search(r"(\d+)", name or "")
    return int(m.group(1)) if m else None


def _apply_altitude(entry, alt, mode):
    if alt and mode == "relativeToGround" and "alt_agl_m" not in entry:
        entry["alt_agl_m"] = round(alt, 1)
    elif alt and mode == "absolute" and "alt_amsl_m" not in entry:
        entry["alt_amsl_m"] = round(alt, 1)


def kml_to_spec(path, name=None):
    root = _strip_ns(ET.fromstring(_read_kml_bytes(path)))
    spec = {"name": name, "home": None, "poi": None, "settings": {}, "waypoints": []}
    numbered, ordered = [], []

    for pm in root.iter("Placemark"):
        pm_name = (pm.findtext("name") or "").strip()
        tags = parse_tags(pm.findtext("description"))
        mode = _altitude_mode(pm)
        point = pm.find(".//Point/coordinates")
        line = pm.find(".//LineString/coordinates")

        if point is not None:
            pts = _parse_coords(point.text)
            if not pts:
                continue
            lat, lon, alt = pts[0]
            entry = {"lat": round(lat, 8), "lon": round(lon, 8), **tags}
            key = pm_name.lower()
            if key in HOME_NAMES:
                entry.pop("alt_agl_m", None)
                spec["home"] = entry
            elif key.startswith("poi"):
                label = pm_name[3:].strip(" :-") or "POI"
                entry = {"name": label, **entry}
                if "alt_agl_m" in entry:
                    entry["height_agl_m"] = entry.pop("alt_agl_m")
                elif alt and mode == "relativeToGround":
                    entry["height_agl_m"] = round(alt, 1)
                spec["poi"] = entry
            else:
                if pm_name:
                    entry = {"label": pm_name, **entry}
                _apply_altitude(entry, alt, mode)
                num = _number_in(pm_name)
                (numbered if num is not None else ordered).append((num, entry))
        elif line is not None:
            for lat, lon, alt in _parse_coords(line.text):
                entry = {"lat": round(lat, 8), "lon": round(lon, 8)}
                _apply_altitude(entry, alt, mode)
                ordered.append((None, entry))
            if not spec["name"] and pm_name:
                spec["name"] = pm_name

    if numbered and not ordered:
        numbered.sort(key=lambda t: t[0])
        spec["waypoints"] = [e for _, e in numbered]
    else:
        spec["waypoints"] = [e for _, e in numbered + ordered]

    if not spec["name"]:
        doc_name = root.findtext(".//Document/name") or root.findtext(".//Folder/name")
        spec["name"] = (doc_name or "Untitled mission").strip()
    if not spec["waypoints"]:
        raise ValueError(f"{path}: no waypoints found (need Point placemarks or a Path)")
    return spec
