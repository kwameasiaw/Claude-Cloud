#!/usr/bin/env python3
"""Build celestial-calendar.ics for Whitley Woods, Chorley (PR6).

Always included (computed offline with astronomy-engine):
  full moons, eclipses, solstices/equinoxes, meteor showers,
  planetary oppositions / greatest elongations / close conjunctions.

Included when ISS orbit data (a TLE) is available:
  visible ISS passes over the observer. Needs `skyfield` + `sgp4`.

Usage:
  pip install astronomy-engine skyfield sgp4
  python3 generate_calendar.py                    # fetch TLE from CelesTrak
  python3 generate_calendar.py --tle iss.tle      # use a TLE file you saved
  python3 generate_calendar.py --no-iss           # astronomy events only

ISS predictions drift as the orbit changes (reboosts, drag): treat passes more
than ~2 weeks after the TLE epoch as approximate and re-run to refresh.
Every event gets a VALARM 1 hour before the start.
"""
import argparse
import datetime as dt
import math
import sys
import urllib.request
import uuid
from zoneinfo import ZoneInfo

import astronomy as ast

LAT, LON, ELEV = 53.65, -2.62, 100.0  # Whitley Woods, Chorley PR6 (approx.)
OBSERVER = ast.Observer(LAT, LON, ELEV)
LONDON = ZoneInfo("Europe/London")
UTC = dt.timezone.utc
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle"

NOW = dt.datetime.now(UTC).replace(microsecond=0)
END = NOW + dt.timedelta(days=365)

events = []  # (start_utc, duration, summary, description)


def to_dt(t):
    return t.Utc().replace(tzinfo=UTC) if hasattr(t, "Utc") else t


def ast_time(d):
    return ast.Time.Make(d.year, d.month, d.day, d.hour, d.minute, d.second)


def _radec(body, d):
    e = ast.Equator(body, ast_time(d), OBSERVER, True, True)
    return e.ra, e.dec


def add(start, minutes, summary, desc):
    if NOW <= start <= END:
        events.append((start, dt.timedelta(minutes=minutes), summary, desc))


def london_evening(d, hour=22):
    """UTC datetime for `hour`:00 UK local time on date d."""
    return dt.datetime(d.year, d.month, d.day, hour, 0, tzinfo=LONDON).astimezone(UTC)


def illum(d):
    return ast.Illumination(ast.Body.Moon, ast_time(d)).phase_fraction * 100


# ---------------------------------------------------------------- full moons
FULL_MOON_NAMES = {
    1: "Wolf Moon", 2: "Snow Moon", 3: "Worm Moon", 4: "Pink Moon",
    5: "Flower Moon", 6: "Strawberry Moon", 7: "Buck Moon",
    8: "Sturgeon Moon", 9: "Harvest/Corn Moon", 10: "Hunter's Moon",
    11: "Beaver Moon", 12: "Cold Moon",
}
t = ast_time(NOW)
while True:
    fm = ast.SearchMoonPhase(180, t, 40)
    if fm is None:
        break
    when = to_dt(fm)
    if when > END:
        break
    local = when.astimezone(LONDON)
    dist = ast.GeoVector(ast.Body.Moon, fm, False).Length() * ast.KM_PER_AU
    tag = " (Supermoon)" if dist < 360000 else (" (Micromoon)" if dist > 405000 else "")
    name = FULL_MOON_NAMES[local.month]
    add(when, 60, f"Full Moon: {name}{tag}",
        f"Full Moon at {local:%H:%M %Z, %a %d %b %Y}. Moon distance ~{dist:,.0f} km. "
        "Best viewed when it rises in the east around sunset.")
    t = fm.AddDays(1)

# ------------------------------------------------------------------ eclipses
le = ast.SearchLunarEclipse(ast_time(NOW))
while to_dt(le.peak) <= END:
    kind = {ast.EclipseKind.Penumbral: "Penumbral", ast.EclipseKind.Partial: "Partial",
            ast.EclipseKind.Total: "Total"}[le.kind]
    peak = to_dt(le.peak)
    moon = ast.Horizon(le.peak, OBSERVER, *_radec(ast.Body.Moon, peak), ast.Refraction.Normal)
    visible = moon.altitude > 0
    add(peak, int(le.sd_partial * 2) if le.sd_partial else int(le.sd_penum * 2),
        f"{kind} Lunar Eclipse" + ("" if visible else " (below horizon from Chorley)"),
        f"Greatest eclipse {peak.astimezone(LONDON):%H:%M %Z, %a %d %b %Y}. "
        f"Moon altitude from Chorley at peak: {moon.altitude:.0f} deg. "
        + ("Penumbral eclipses are very subtle to the eye." if kind == "Penumbral" else ""))
    le = ast.NextLunarEclipse(le.peak)

se = ast.SearchGlobalSolarEclipse(ast_time(NOW))
while to_dt(se.peak) <= END:
    kind = {ast.EclipseKind.Partial: "Partial", ast.EclipseKind.Annular: "Annular",
            ast.EclipseKind.Total: "Total"}[se.kind]
    local = ast.SearchLocalSolarEclipse(se.peak.AddDays(-1), OBSERVER)
    # the next local eclipse may be a different one; only use it if it matches
    near = abs((to_dt(local.peak.time) - to_dt(se.peak)).total_seconds()) < 86400
    if near and local.peak.altitude > 0:
        pk = to_dt(local.peak.time)
        add(to_dt(local.partial_begin.time), 120,
            f"Partial Solar Eclipse (visible from Chorley, max {local.obscuration*100:.0f}% sun covered)",
            f"Max at {pk.astimezone(LONDON):%H:%M %Z}, sun altitude {local.peak.altitude:.0f} deg. "
            "NEVER look at the Sun without certified eclipse glasses.")
    else:
        add(to_dt(se.peak), 60, f"{kind} Solar Eclipse (not visible from Chorley)",
            f"Global greatest eclipse {to_dt(se.peak):%H:%M UTC, %a %d %b %Y}. "
            "Not visible from the UK; live streams are usually available.")
    se = ast.NextGlobalSolarEclipse(se.peak)

# ------------------------------------------------------- seasons & planets
s0 = ast.Seasons(NOW.year)
s1 = ast.Seasons(NOW.year + 1)
for label, a in (("March Equinox", "mar_equinox"), ("June Solstice", "jun_solstice"),
                 ("September Equinox", "sep_equinox"), ("December Solstice", "dec_solstice")):
    for s in (s0, s1):
        when = to_dt(getattr(s, a))
        add(when, 60, label, f"{label} at {when.astimezone(LONDON):%H:%M %Z, %a %d %b %Y}.")

PLANETS = [ast.Body.Mercury, ast.Body.Venus]
for body in PLANETS:
    tt = ast_time(NOW)
    for _ in range(8):
        el = ast.SearchMaxElongation(body, tt)
        when = to_dt(el.time)
        if when > END:
            break
        side = "evening sky (after sunset)" if el.visibility == ast.Visibility.Evening else "morning sky (before sunrise)"
        add(when, 60, f"{body.name} greatest elongation ({el.elongation:.0f} deg)",
            f"Best time to spot {body.name}, in the {side}. Elongation {el.elongation:.1f} deg.")
        tt = el.time.AddDays(5)

for body in (ast.Body.Mars, ast.Body.Jupiter, ast.Body.Saturn):
    op = ast.SearchRelativeLongitude(body, 0.0, ast_time(NOW))
    when = to_dt(op)
    add(when, 60, f"{body.name} at opposition",
        f"{body.name} is closest and brightest, visible all night. {when.astimezone(LONDON):%a %d %b %Y}.")

# close conjunctions between naked-eye planets (separation < 2 deg)
BRIGHT = [ast.Body.Mercury, ast.Body.Venus, ast.Body.Mars, ast.Body.Jupiter, ast.Body.Saturn]
seen = set()
d = NOW
while d <= END:
    tm = ast_time(d)
    for i, a in enumerate(BRIGHT):
        for b in BRIGHT[i + 1:]:
            sep = ast.AngleBetween(ast.GeoVector(a, tm, True), ast.GeoVector(b, tm, True))
            sun = ast.AngleBetween(ast.GeoVector(a, tm, True), ast.GeoVector(ast.Body.Sun, tm, True))
            if sep < 2.0 and sun > 15:
                key = (a, b, d.year, d.month // 2)
                if key not in seen:
                    seen.add(key)
                    # report the day of minimum separation within +-10 days
                    best = min((ast.AngleBetween(ast.GeoVector(a, ast_time(d + dt.timedelta(days=k)), True),
                                                 ast.GeoVector(b, ast_time(d + dt.timedelta(days=k)), True)), k)
                               for k in range(-10, 11))
                    day = d + dt.timedelta(days=best[1])
                    add(london_evening(day, 21), 60,
                        f"{a.name}-{b.name} conjunction ({best[0]:.1f} deg apart)",
                        f"{a.name} and {b.name} appear very close together. Check sun separation: "
                        f"{sun:.0f} deg from the Sun. Look low in the twilight sky.")
    d += dt.timedelta(days=1)

# ------------------------------------------------------------ meteor showers
SHOWERS = [  # name, month, day, ZHR, note
    ("Leonids", 11, 17, 15, "Fast meteors, often bright trails"),
    ("Geminids", 12, 14, 150, "Best shower of the year; bright slow meteors"),
    ("Quadrantids", 1, 3, 80, "Sharp, short peak; best after midnight"),
    ("Lyrids", 4, 22, 18, "Occasional bright fireballs"),
    ("Eta Aquariids", 5, 6, 30, "Halley's debris; low from the UK, pre-dawn"),
    ("Perseids", 8, 12, 100, "Warm summer nights, plenty of fireballs"),
    ("Orionids", 10, 21, 20, "Also Halley's debris, fast meteors"),
]
for name, m, day, zhr, note in SHOWERS:
    for y in (NOW.year, NOW.year + 1):
        d0 = dt.datetime(y, m, day, tzinfo=UTC)
        pm = illum(dt.datetime(y, m, day, 23, 0, tzinfo=UTC))
        sky = "dark moonless sky - excellent" if pm < 25 else ("some moonlight" if pm < 60 else "bright Moon will wash out fainter meteors")
        add(london_evening(d0, 22 if m != 5 else 3) + (dt.timedelta(days=1) if m == 5 else dt.timedelta()),
            120, f"{name} meteor shower peak (~{zhr}/hr max)",
            f"{note}. Moon {pm:.0f}% illuminated: {sky}. "
            "Find a dark spot, give your eyes 20 min to adapt, look up and away from the Moon.")

# --------------------------------------------------------------------- ISS
def iss_passes(tle_lines, days):
    from skyfield.api import EarthSatellite, load, wgs84
    ts = load.timescale()
    sat = EarthSatellite(tle_lines[0], tle_lines[1], "ISS", ts)
    epoch_age = (ts.from_datetime(NOW) - sat.epoch)
    print(f"TLE epoch age: {epoch_age:.1f} days", file=sys.stderr)
    topos = wgs84.latlon(LAT, LON, ELEV)
    t0, t1 = ts.from_datetime(NOW), ts.from_datetime(NOW + dt.timedelta(days=days))
    times, kinds = sat.find_events(topos, t0, t1, altitude_degrees=10.0)
    out, cur = [], {}
    for tm, k in zip(times, kinds):
        cur[k] = tm
        if k == 2:  # set
            if 0 in cur and 1 in cur:
                out.append((cur[0], cur[1], cur[2]))
            cur = {}
    res = []
    for rise, culm, sett in out:
        d = culm.utc_datetime()
        sun_alt = ast.Horizon(ast_time(d), OBSERVER, *_radec(ast.Body.Sun, d), ast.Refraction.Normal).altitude
        if sun_alt > -6:
            continue  # sky too bright
        r = sat.at(culm).position.km
        sv = ast.GeoVector(ast.Body.Sun, ast_time(d), False)
        s = (sv.x, sv.y, sv.z)
        sl = math.sqrt(sum(c * c for c in s))
        proj = sum(a * b for a, b in zip(r, s)) / sl
        perp = math.sqrt(max(sum(a * a for a in r) - proj * proj, 0))
        if proj < 0 and perp < 6371:
            continue  # in Earth's shadow
        alt, az, _ = (sat - topos).at(culm).altaz()
        r_alt, r_az, _ = (sat - topos).at(rise).altaz()
        s_alt, s_az, _ = (sat - topos).at(sett).altaz()
        res.append((rise.utc_datetime(), sett.utc_datetime(), culm.utc_datetime(),
                    alt.degrees, az.degrees, r_az.degrees, s_az.degrees))
    return res


def compass(az):
    return ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"][int((az + 11.25) // 22.5) % 16]


def load_tle(path):
    text = open(path).read() if path else urllib.request.urlopen(TLE_URL, timeout=30).read().decode()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    l1 = next(ln for ln in lines if ln.startswith("1 25544"))
    l2 = next(ln for ln in lines if ln.startswith("2 25544"))
    return l1, l2


# --------------------------------------------------------------------- ICS
def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    out, b = [], line.encode()
    while len(b) > 74:
        cut = 74
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode())
        b = b[cut:]
        b = b" " + b
    out.append(b.decode())
    return "\r\n".join(out)


def write_ics(path):
    stamp = NOW.strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Celestial Calendar//Chorley PR6//EN",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Sky Events - Chorley PR6",
         "X-WR-TIMEZONE:Europe/London"]
    for start, dur, summ, desc in sorted(events, key=lambda e: e[0]):
        uid = uuid.uuid5(uuid.NAMESPACE_URL, f"{start.isoformat()}|{summ}")
        L += ["BEGIN:VEVENT", f"UID:{uid}@celestial-calendar", f"DTSTAMP:{stamp}",
              f"DTSTART:{start:%Y%m%dT%H%M%SZ}", f"DTEND:{start + dur:%Y%m%dT%H%M%SZ}",
              f"SUMMARY:{esc(summ)}", f"DESCRIPTION:{esc(desc)}",
              "LOCATION:Whitley Woods\\, Chorley PR6", "TRANSP:TRANSPARENT",
              "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(summ)}",
              "TRIGGER:-PT1H", "END:VALARM", "END:VEVENT"]
    L.append("END:VCALENDAR")
    with open(path, "w", newline="") as f:
        f.write("\r\n".join(fold(x) for x in L) + "\r\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tle", help="file containing the current ISS TLE")
    ap.add_argument("--no-iss", action="store_true")
    ap.add_argument("--iss-days", type=int, default=14)
    ap.add_argument("-o", "--out", default="celestial-calendar.ics")
    a = ap.parse_args()
    if not a.no_iss:
        try:
            for rise, sett, culm, alt, az, raz, saz in iss_passes(load_tle(a.tle), a.iss_days):
                mins = max(1, round((sett - rise).total_seconds() / 60))
                add(rise, mins, f"ISS pass: max {alt:.0f}° ({compass(raz)} to {compass(saz)})",
                    f"Visible ISS pass over Chorley. Rises {compass(raz)}, peaks at {alt:.0f}° "
                    f"({compass(az)}) at {culm.astimezone(LONDON):%H:%M:%S}, sets {compass(saz)}. "
                    "Bright, steady, non-blinking light moving fast across the sky.")
        except Exception as e:  # noqa: BLE001
            print(f"ISS passes skipped: {e}", file=sys.stderr)
    write_ics(a.out)
    print(f"Wrote {len(events)} events to {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
