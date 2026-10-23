# Rivington Pike orbit

**Status:** NOT READY: fix the errors below  
**Mission file:** `rivington-pike-orbit.kmz` (DJI Fly / Mini 4 Pro)  
**Terrain-corrected heights:** no (flat ground assumed)

## Summary

| | |
|---|---|
| Waypoints | 11 |
| Route length (recorded) | 309 m |
| Video length | 1 min 43 s |
| Total flight incl. take-off, fly-in, return | ~3.1 min (budget 18 min) |
| Highest above ground | 30 m (UK limit 120 m) |
| Furthest from take-off | 171 m |
| Cruise speed | 3 m/s |
| Steepest allowed climb | +14° |
| At the end | hover · signal lost: rth |
| Point of interest | Rivington Pike Tower, aim 4 m above its base |

## Waypoints

| # | Height in DJI Fly | Above ground | Leg | Climb | Speed | Gimbal | Facing | Actions |
|---|---|---|---|---|---|---|---|---|
| WP1 | 15 m | 15 m | 27 m | +29° | 3 m/s | -6° | POI | REC ▶ |
| WP2 | 23 m | 23 m | 32 m | +14° | 3 m/s | -15° | POI | - |
| WP3 (orbit entry) | 30 m | 30 m | 32 m | +12° | 3 m/s | -34° | POI | - |
| WP4 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP5 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP6 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP7 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP8 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP9 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP10 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | - |
| WP11 | 30 m | 30 m | 31 m | +0° | 3 m/s | -34° | POI | REC ■ |

*Leg/Climb on the first row is the un-recorded diagonal fly-in from take-off.*

## ❌ Errors (mission not safe to load)

- No terrain data: without ground heights the drone could fly into rising ground. Run build with --terrain, add ground_m values, or set settings.flat_ground_confirmed once the pilot confirms the site is flat.

## Camera (set in DJI Fly before starting the mission)

- 4K, 24 or 30 fps. D-Log M if you colour grade, otherwise Normal
- Shutter about double the frame rate (1/50 or 1/60). Use an ND filter in daylight
- Set white balance manually and lock exposure (AE lock) so the video doesn't flicker

## Pre-flight (UK)

- Take off **from the planned Home point**: every height is measured from where you launch
- Check airspace and restrictions (flight restriction zones, NOTAMs) in NATS Drone Assist
- Carry your Flyer ID and display your Operator ID on the drone. Get landowner permission to take off
- Keep the drone in sight the whole time. Stay away from uninvolved people and never fly over crowds
- Keep your thumbs on the sticks. Press Flight Pause on the RC 2 to stop the mission and hover
