"""Small geodesy helpers (spherical earth is plenty accurate at mission scale)."""

import math

EARTH_RADIUS_M = 6371008.8


def distance_m(lat1, lon1, lat2, lon2):
    """Great-circle (haversine) distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from true north (0-360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def interpolate(lat1, lon1, lat2, lon2, fraction):
    """Linear interpolation between two nearby points."""
    return lat1 + (lat2 - lat1) * fraction, lon1 + (lon2 - lon1) * fraction


def destination(lat, lon, bearing, distance):
    """Point reached by travelling `distance` metres from (lat, lon) on initial `bearing` degrees."""
    p1, l1 = math.radians(lat), math.radians(lon)
    b, d = math.radians(bearing), distance / EARTH_RADIUS_M
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180
