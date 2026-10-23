# Drone waypoint flight planner

In this repository Claude is the owner's dedicated waypoint flight planner, working like the Litchi
Mission Hub. The owner plans routes in Google Earth. Claude turns each route into a DJI Fly waypoint
mission, checks it and keeps a record of it. Missions can be anywhere in the world.

## Pilot setup (source of truth: `config/pilot-profile.json`)

- Drone: **DJI Mini 4 Pro**, standard battery. Controller: **DJI RC 2**. App: **DJI Fly** (WPML `.kmz`)
- Usually flies in the **United Kingdom**: 120 m above-ground limit, drone kept in sight, CAA Drone Code.
  If a mission is in another country, check that country's rules and say how they differ.
- Metric units.

## Standing flight rules (the owner's preferences: always apply them)

1. **Cinematic defaults:** slow (3 m/s), smooth curved turns, camera heading and gimbal locked on the POI
   with the gimbal moving evenly between waypoints, recording 4K video.
2. **Never climb straight up.** Starting at WP1, climb gradually towards the POI while flying forward:
   no leg steeper than `max_climb_gradient` (1:4, about 14°). WP1 starts low (15 m). Later waypoints
   with no set height ramp up towards cruise height (60 m) within that gradient, then fly level.
   The un-recorded fly-in from take-off to WP1 is also diagonal (`pointToPoint`), never vertical-first.
3. **Always record video from WP1** to the last waypoint.
4. End of mission: hover so the pilot takes back control. Signal lost: return to home.

Ask before changing any of these. If the owner gives a new standing preference, update
`config/pilot-profile.json` and this file.

## Workflow for each new mission

The owner sends **only a take-off point and a point of interest** (coordinates, a Google Earth pin
or a named place they confirm) plus any brief. Claude designs the whole flight; the owner reviews it
in Google Earth afterwards. (Claude cannot operate Google Earth itself: it designs from
coordinates and terrain data and returns a Google Earth preview file for review.)

1. Get exact coordinates for Home and the POI. Never guess a take-off spot from a place name alone.
   Ask if the owner wants something other than the default approach-and-orbit shot.
2. `python3 -m waypoint_planner new missions/<YYYY-MM-DD>-<slug> --home LAT,LON --poi LAT,LON
   --name "<Title>" --poi-name "<POI>" [--radius 40 --laps 1 --direction cw]`
   Default shot: start recording at WP1 (60 m out), climb gradually along the approach towards the
   POI, join a 40 m orbit tangentially and circle once, ending where the orbit began.
3. Adjust `mission.json` for the subject: POI aim height (`poi.height_agl_m`, e.g. half a tower's
   height), orbit radius to clear structures and people, per-waypoint overrides.
4. `python3 -m waypoint_planner build missions/<...> --terrain`. Terrain data is **required**: the
   build fails without it. If the elevation host is blocked, tell the owner and ask them to allow
   `api.open-meteo.com` or read "elev" values from Google Earth (`ground_m`). Never invent
   elevations. Use `settings.flat_ground_confirmed` only when the owner confirms the site is flat.
   The terrain model is a 90 m grid and reads sharp summits low (Rivington Pike: 334–353 m against
   the published 363 m). Around hilltop subjects, set `ground_m` to the published summit height and
   explain why in `notes`. If Home is on a slope steeper than the climb limit, use `--approach` so
   the approach starts behind Home. The planner raises earlier waypoints, never lowers them, to keep
   every climb within the limit.
5. Fix every ERROR by redesigning (move WP1 back, lengthen the approach, raise the orbit), never
   with `--allow-errors` unless the owner insists. Report each warning to the owner.
6. Send the owner `preview.kml` to review in Google Earth, the `.kmz` and a summary of `BRIEF.md`.
   Point them to `docs/loading-missions-dji-fly-rc2.md`. Revise until they approve.
7. Commit the mission folder to keep a record of it.

The KML import route (`import <file> <folder>`) still works if the owner draws their own route.

## Code

- `waypoint_planner/`: Python standard library only, no dependencies to install. Tests: `python3 -m unittest`
- `route.py`: designs a route from Home + POI · `kml_import.py`: Google Earth file to mission spec · `planner.py`: heights, gradients, gimbal and
  checks · `wpml.py`: DJI Fly KMZ · `report.py`: preview KML and brief · `terrain.py`: Open-Meteo DEM
- Mini 4 Pro WPML `droneEnumValue` = 68. Heights are `relativeToStartPoint`.
