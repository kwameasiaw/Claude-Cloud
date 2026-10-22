import math
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from waypoint_planner import kml_import, planner, wpml

FIXTURE = Path(__file__).parent / "fixtures" / "sample_route.kml"
W = "{http://www.dji.com/wpmz/1.0.6}"


def spec_line(n=4, spacing_deg=0.002, **wp_overrides):
    wps = [{"lat": 51.17 + i * spacing_deg, "lon": -1.80} for i in range(n)]
    for i, extra in wp_overrides.items():
        wps[int(i[2:])].update(extra)
    return {"name": "Test", "home": {"lat": 51.1695, "lon": -1.80}, "poi": None,
            "settings": {}, "waypoints": wps}


class ImportTests(unittest.TestCase):
    def test_sample_kml(self):
        spec = kml_import.kml_to_spec(FIXTURE)
        self.assertEqual(spec["name"], "Sample hilltop reveal")
        self.assertEqual([w["label"] for w in spec["waypoints"]], ["WP1", "WP2", "WP3", "WP4"])
        self.assertEqual(spec["poi"]["name"], "Monument")
        self.assertEqual(spec["poi"]["height_agl_m"], 8.0)
        self.assertEqual(spec["waypoints"][2]["hover_s"], 3.0)
        self.assertEqual(spec["waypoints"][3]["alt_agl_m"], 55.0)
        self.assertIsNotNone(spec["home"])

    def test_tags(self):
        self.assertEqual(kml_import.parse_tags("alt=40 speed=2.5 photo gimbal=-30"),
                         {"alt_agl_m": 40.0, "speed_ms": 2.5, "gimbal_pitch_deg": -30.0, "photo": True})


class PlanTests(unittest.TestCase):
    def test_auto_ramp_respects_gradient(self):
        plan = planner.build_plan(spec_line(n=6, spacing_deg=0.0005))
        self.assertFalse(plan.errors, plan.errors)
        grad = plan.settings["max_climb_gradient"]
        for w in plan.waypoints[1:]:
            self.assertLessEqual(abs(w.climb_gradient), grad + 0.005)
        self.assertEqual(plan.waypoints[0].agl_m, plan.settings["start_alt_agl_m"])
        self.assertTrue(plan.waypoints[0].start_record and plan.waypoints[-1].stop_record)

    def test_steep_explicit_climb_is_error(self):
        plan = planner.build_plan(spec_line(wp1={"alt_agl_m": 80}))
        self.assertTrue(any("steeper" in e for e in plan.errors))

    def test_uk_height_limit(self):
        spec = spec_line(n=3, spacing_deg=0.01, wp2={"alt_agl_m": 130})
        plan = planner.build_plan(spec)
        self.assertTrue(any("120 m" in e for e in plan.errors))

    def test_terrain_correction(self):
        spec = spec_line(n=3)
        spec["home"]["ground_m"] = 100.0
        for i, w in enumerate(spec["waypoints"]):
            w["ground_m"] = 100.0 + 10 * i
            w["alt_agl_m"] = 20
        plan = planner.build_plan(spec)
        self.assertTrue(plan.terrain_known)
        self.assertEqual([w.rel_m for w in plan.waypoints], [20, 30, 40])

    def test_fill_terrain_and_leg_samples(self):
        spec = spec_line(n=3)
        samples = planner.fill_terrain(spec, lambda pts: [50.0] * len(pts))
        self.assertEqual(set(samples), {0, 1, 2})
        plan = planner.build_plan(spec, leg_samples=samples)
        self.assertTrue(plan.terrain_known)
        self.assertIsNotNone(plan.waypoints[1].min_leg_agl_m)

    def test_poi_tracking_gimbal_points_down_at_target(self):
        spec = spec_line(n=3, wp2={"alt_agl_m": 40})
        spec["poi"] = {"name": "T", "lat": 51.1745, "lon": -1.80, "height_agl_m": 0}
        plan = planner.build_plan(spec)
        last = plan.waypoints[-1]
        expected = -math.degrees(math.atan2(last.rel_m, 111.2 * 0.5))
        self.assertAlmostEqual(last.gimbal_pitch_deg, expected, delta=1.0)
        self.assertEqual(last.heading, "towardPOI")


class KmzTests(unittest.TestCase):
    def test_kmz_structure(self):
        plan = planner.build_plan(kml_import.kml_to_spec(FIXTURE))
        with tempfile.TemporaryDirectory() as d:
            path = wpml.write_kmz(plan, Path(d) / "m.kmz")
            with zipfile.ZipFile(path) as z:
                self.assertEqual(sorted(z.namelist()), ["wpmz/template.kml", "wpmz/waylines.wpml"])
                ET.fromstring(z.read("wpmz/template.kml"))
                root = ET.fromstring(z.read("wpmz/waylines.wpml"))
        self.assertEqual(root.find(f".//{W}droneEnumValue").text, "68")
        self.assertEqual(root.find(f".//{W}flyToWaylineMode").text, "pointToPoint")
        pms = root.findall(".//{http://www.opengis.net/kml/2.2}Placemark")
        self.assertEqual(len(pms), 4)
        funcs = [[a.text for a in pm.iter(f"{W}actionActuatorFunc")] for pm in pms]
        self.assertIn("startRecord", funcs[0])
        self.assertIn("stopRecord", funcs[-1])
        self.assertIn("hover", funcs[2])
        ids = [int(e.text) for e in root.iter(f"{W}actionId")]
        self.assertEqual(ids, list(range(len(ids))))


if __name__ == "__main__":
    unittest.main()
