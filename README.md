# Claude-Cloud: drone waypoint flight planner

Plan in Google Earth, fly in DJI Fly. This repository turns a Google Earth route into a ready-to-load
**DJI Fly waypoint mission (`.kmz`) for the DJI Mini 4 Pro**, using the owner's cinematic flight rules
and UK safety checks.

- **How to send a flight request:** give a take-off point and a point of interest. Claude designs the rest
- **Drawing your own route instead:** [docs/google-earth-planning-guide.md](docs/google-earth-planning-guide.md)
- **Load it onto the RC 2:** [docs/loading-missions-dji-fly-rc2.md](docs/loading-missions-dji-fly-rc2.md)
- **Your settings:** [config/pilot-profile.json](config/pilot-profile.json)
- **Flown and planned missions:** [missions/](missions/)

Each mission folder contains:

| File | What it's for |
|---|---|
| `source.kml` / `source.kmz` | What you drew in Google Earth (only if you drew the route) |
| `mission.json` | The editable plan |
| `<name>.kmz` | **The file you load into DJI Fly** |
| `preview.kml` | Open in Google Earth to see the 3D flight path |
| `BRIEF.md` | Heights, timings, battery estimate, warnings and pre-flight checklist |

```bash
# Usual workflow: just a take-off point and a POI
python3 -m waypoint_planner new missions/2026-10-25-lake-reveal --home 53.61,-2.55 --poi 53.62,-2.54 --name "Lake reveal"
# Or import a route you drew yourself
python3 -m waypoint_planner import route.kml missions/2026-10-25-lake-reveal --name "Lake reveal"
python3 -m waypoint_planner build missions/2026-10-25-lake-reveal --terrain
python3 -m unittest
```
