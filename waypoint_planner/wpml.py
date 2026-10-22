"""Write a Plan as a DJI WPML mission KMZ in the layout DJI Fly saves for the Mini 4 Pro.

KMZ contents:  wpmz/template.kml  (mission config)   wpmz/waylines.wpml  (executable route)
"""

import time
import zipfile

WPML_NS = "http://www.dji.com/wpmz/1.0.6"
MINI_4_PRO_ENUM = 68
MINI_4_PRO_SUBENUM = 0

FINISH = {"hover": "noAction", "rth": "goHome", "land": "autoLand", "first_waypoint": "gotoFirstWaypoint"}
RC_LOST = {"rth": "goBack", "hover": "hover", "land": "landing"}
FLY_TO = {"diagonal": "pointToPoint", "vertical_first": "safely"}


def _mission_config(plan, indent):
    s = plan.settings
    pad = " " * indent
    lines = [
        "<wpml:missionConfig>",
        f"  <wpml:flyToWaylineMode>{FLY_TO[s['fly_to_first_waypoint']]}</wpml:flyToWaylineMode>",
        f"  <wpml:finishAction>{FINISH[s['finish_action']]}</wpml:finishAction>",
        "  <wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>",
        f"  <wpml:executeRCLostAction>{RC_LOST[s['rc_lost_action']]}</wpml:executeRCLostAction>",
        f"  <wpml:globalTransitionalSpeed>{s['transitional_speed_ms']:g}</wpml:globalTransitionalSpeed>",
        "  <wpml:droneInfo>",
        f"    <wpml:droneEnumValue>{MINI_4_PRO_ENUM}</wpml:droneEnumValue>",
        f"    <wpml:droneSubEnumValue>{MINI_4_PRO_SUBENUM}</wpml:droneSubEnumValue>",
        "  </wpml:droneInfo>",
        "</wpml:missionConfig>",
    ]
    return "\n".join(pad + l for l in lines)


def template_kml(plan, now_ms):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="{WPML_NS}">
  <Document>
    <wpml:author>fly</wpml:author>
    <wpml:createTime>{now_ms}</wpml:createTime>
    <wpml:updateTime>{now_ms}</wpml:updateTime>
{_mission_config(plan, 4)}
  </Document>
</kml>
"""


class _Actions:
    def __init__(self):
        self.group_id = 0
        self.action_id = 0

    def action(self, func, params):
        body = "\n".join(f"              <wpml:{k}>{v}</wpml:{k}>" for k, v in params)
        a = f"""          <wpml:action>
            <wpml:actionId>{self.action_id}</wpml:actionId>
            <wpml:actionActuatorFunc>{func}</wpml:actionActuatorFunc>
            <wpml:actionActuatorFuncParam>
{body}
            </wpml:actionActuatorFuncParam>
          </wpml:action>"""
        self.action_id += 1
        return a

    def group(self, start, end, trigger, actions):
        g = f"""        <wpml:actionGroup>
          <wpml:actionGroupId>{self.group_id}</wpml:actionGroupId>
          <wpml:actionGroupStartIndex>{start}</wpml:actionGroupStartIndex>
          <wpml:actionGroupEndIndex>{end}</wpml:actionGroupEndIndex>
          <wpml:actionGroupMode>sequence</wpml:actionGroupMode>
          <wpml:actionTrigger>
            <wpml:actionTriggerType>{trigger}</wpml:actionTriggerType>
          </wpml:actionTrigger>
{chr(10).join(actions)}
        </wpml:actionGroup>"""
        self.group_id += 1
        return g


def _gimbal_rotate(acts, pitch):
    return acts.action("gimbalRotate", [
        ("gimbalHeadingYawBase", "aircraft"),
        ("gimbalRotateMode", "absoluteAngle"),
        ("gimbalPitchRotateEnable", 1),
        ("gimbalPitchRotateAngle", f"{pitch:g}"),
        ("gimbalRollRotateEnable", 0),
        ("gimbalRollRotateAngle", 0),
        ("gimbalYawRotateEnable", 0),
        ("gimbalYawRotateAngle", 0),
        ("gimbalRotateTimeEnable", 0),
        ("gimbalRotateTime", 0),
        ("payloadPositionIndex", 0),
    ])


def _turn_mode(plan, i, w):
    last = i == len(plan.waypoints) - 1
    if plan.settings["turn"] == "stop" or i == 0 or last or w.hover_s > 0 or w.photo:
        return "toPointAndStopWithContinuityCurvature"
    return "toPointAndPassWithContinuityCurvature"


def _placemark(plan, i, w, acts):
    poi = plan.poi
    poi_point = f"{poi['lat']:.8f},{poi['lon']:.8f},{poi['rel_m']:.6f}" if poi else "0.000000,0.000000,0.000000"
    heading_mode = w.heading
    angle_enable = 1 if w.heading == "fixed" else 0
    heading_angle = w.heading_deg if w.heading == "fixed" else 0
    if heading_angle > 180:
        heading_angle -= 360
    if heading_mode == "fixed":
        heading_mode = "smoothTransition"

    groups = []
    on_arrival = [_gimbal_rotate(acts, w.gimbal_pitch_deg)]
    if w.hover_s > 0:
        on_arrival.append(acts.action("hover", [("hoverTime", f"{w.hover_s:g}")]))
    if w.photo and not plan.settings["record_video_from_wp1"]:
        on_arrival.append(acts.action("takePhoto", [("payloadPositionIndex", 0), ("useGlobalPayloadLensIndex", 0)]))
    if w.start_record:
        on_arrival.append(acts.action("startRecord", [("payloadPositionIndex", 0), ("useGlobalPayloadLensIndex", 0)]))
    if w.stop_record:
        on_arrival.append(acts.action("stopRecord", [("payloadPositionIndex", 0)]))
    groups.append(acts.group(i, i, "reachPoint", on_arrival))
    if i < len(plan.waypoints) - 1:
        nxt = plan.waypoints[i + 1]
        groups.append(acts.group(i, i + 1, "betweenAdjacentPoints", [acts.action("gimbalEvenlyRotate", [
            ("gimbalPitchRotateAngle", f"{nxt.gimbal_pitch_deg:g}"),
            ("payloadPositionIndex", 0),
        ])]))

    return f"""      <Placemark>
        <Point>
          <coordinates>
            {w.lon:.8f},{w.lat:.8f}
          </coordinates>
        </Point>
        <wpml:index>{i}</wpml:index>
        <wpml:executeHeight>{w.rel_m:g}</wpml:executeHeight>
        <wpml:waypointSpeed>{w.speed_ms:g}</wpml:waypointSpeed>
        <wpml:waypointHeadingParam>
          <wpml:waypointHeadingMode>{heading_mode}</wpml:waypointHeadingMode>
          <wpml:waypointHeadingAngle>{heading_angle:g}</wpml:waypointHeadingAngle>
          <wpml:waypointPoiPoint>{poi_point}</wpml:waypointPoiPoint>
          <wpml:waypointHeadingAngleEnable>{angle_enable}</wpml:waypointHeadingAngleEnable>
          <wpml:waypointHeadingPathMode>followBadArc</wpml:waypointHeadingPathMode>
          <wpml:waypointHeadingPoiIndex>0</wpml:waypointHeadingPoiIndex>
        </wpml:waypointHeadingParam>
        <wpml:waypointTurnParam>
          <wpml:waypointTurnMode>{_turn_mode(plan, i, w)}</wpml:waypointTurnMode>
          <wpml:waypointTurnDampingDist>0</wpml:waypointTurnDampingDist>
        </wpml:waypointTurnParam>
        <wpml:useStraightLine>0</wpml:useStraightLine>
{chr(10).join(groups)}
      </Placemark>"""


def waylines_wpml(plan):
    acts = _Actions()
    placemarks = "\n".join(_placemark(plan, i, w, acts) for i, w in enumerate(plan.waypoints))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="{WPML_NS}">
  <Document>
{_mission_config(plan, 4)}
    <Folder>
      <wpml:templateId>0</wpml:templateId>
      <wpml:executeHeightMode>relativeToStartPoint</wpml:executeHeightMode>
      <wpml:waylineId>0</wpml:waylineId>
      <wpml:distance>{plan.stats['route_m']}</wpml:distance>
      <wpml:duration>{plan.stats['video_s']}</wpml:duration>
      <wpml:autoFlightSpeed>{plan.settings['speed_ms']:g}</wpml:autoFlightSpeed>
{placemarks}
    </Folder>
  </Document>
</kml>
"""


def write_kmz(plan, path):
    now_ms = int(time.time() * 1000)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("wpmz/template.kml", template_kml(plan, now_ms))
        z.writestr("wpmz/waylines.wpml", waylines_wpml(plan))
    return path

