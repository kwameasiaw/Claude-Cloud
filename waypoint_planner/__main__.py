"""CLI.

  python -m waypoint_planner import <route.kml|kmz> <missions/YYYY-MM-DD-slug> [--name "..."]
      Create the mission folder with source file + editable mission.json.
  python -m waypoint_planner build <missions/YYYY-MM-DD-slug> [--terrain] [--allow-errors]
      Validate and write mission.kmz (DJI Fly), preview.kml (Google Earth) and BRIEF.md.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from . import kml_import, planner, report, terrain, wpml


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "mission"


def cmd_import(args):
    folder = Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    src = Path(args.source)
    shutil.copy(src, folder / f"source{src.suffix.lower()}")
    spec = kml_import.kml_to_spec(src, name=args.name)
    out = folder / "mission.json"
    out.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Imported {len(spec['waypoints'])} waypoints, home={'yes' if spec['home'] else 'no'}, "
          f"poi={'yes' if spec['poi'] else 'no'} -> {out}")


def cmd_build(args):
    folder = Path(args.folder)
    spec_path = folder / "mission.json"
    spec = json.loads(spec_path.read_text())
    samples = None
    if args.terrain:
        try:
            samples = planner.fill_terrain(spec, terrain.lookup)
            spec_path.write_text(json.dumps(spec, indent=2) + "\n")
            print("Terrain: ground elevations filled from Open-Meteo (Copernicus DEM).")
        except Exception as exc:  # network blocked, API down, etc.
            print(f"Terrain lookup failed ({exc}); continuing with whatever ground_m values exist.",
                  file=sys.stderr)
    plan = planner.build_plan(spec, leg_samples=samples)
    kmz_name = f"{slugify(plan.name)}.kmz"
    (folder / "BRIEF.md").write_text(report.brief_md(plan, kmz_name))
    (folder / "preview.kml").write_text(report.preview_kml(plan))
    for e in plan.errors:
        print(f"ERROR: {e}", file=sys.stderr)
    for w in plan.warnings:
        print(f"warn:  {w}", file=sys.stderr)
    if plan.errors and not args.allow_errors:
        stale = folder / kmz_name
        if stale.exists():
            stale.unlink()
        print(f"Not writing {kmz_name}: fix the errors (see {folder / 'BRIEF.md'}).", file=sys.stderr)
        return 1
    wpml.write_kmz(plan, folder / kmz_name)
    st = plan.stats
    print(f"Wrote {folder / kmz_name}: {st['waypoints']} wp, {st['route_m']} m, "
          f"~{st['total_min']} min, max {st['max_agl_m']:.0f} m AGL")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="waypoint_planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import")
    p.add_argument("source")
    p.add_argument("folder")
    p.add_argument("--name")
    p.set_defaults(func=cmd_import)
    p = sub.add_parser("build")
    p.add_argument("folder")
    p.add_argument("--terrain", action="store_true", help="fetch ground elevations from Open-Meteo")
    p.add_argument("--allow-errors", action="store_true", help="write the KMZ even if validation fails")
    p.set_defaults(func=cmd_build)
    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
