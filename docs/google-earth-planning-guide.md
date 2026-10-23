# Planning a route in Google Earth

> **Usual workflow:** you don't need to draw anything. Send the take-off point and the point of
> interest (right-click a spot in Google Earth, then click the coordinates to copy them). Claude designs
> the route and sends back `preview.kml` for you to review in Google Earth. This guide is for when you
> want to draw a route yourself.

This works in Google Earth Pro (desktop, recommended) or Google Earth on the web.

## 1. Make a folder for the mission

In Google Earth Pro, right-click **My Places**, then **Add → Folder**. Name it after the flight,
e.g. "Lake reveal". Put every placemark for this flight in that folder.

## 2. Drop the placemarks

Click the yellow pin (**Add Placemark**) and name each one:

| Name | Meaning |
|---|---|
| `Home` | Where you will take off. **Every height in the mission is measured from here, so launch from this exact spot.** |
| `POI <name>` (e.g. `POI Castle`) | What the camera keeps looking at. The drone turns to face it and the gimbal tilts to keep it in frame. |
| `WP1`, `WP2`, `WP3` ... | Waypoints in flight order. Recording starts at WP1 and ends at the last waypoint. |

You can also draw the route with **Add Path** (the ruler-line icon) instead of WP placemarks. Each corner of
the path becomes a waypoint.

**Tips for good shots**

- Put WP1 at least 60 m from Home. The drone flies a shallow diagonal to WP1, and recording starts there.
- Leave room to climb. The drone never climbs steeper than 1:4, so gaining 40 m needs about 160 m of travel.
  If there isn't room, I'll tell you and suggest a fix.
- Fewer, well-spaced waypoints give smoother curves than lots of close ones.
- Keep the whole route where you can see the drone. As a rule of thumb, stay within 400 m of Home.

## 3. Optional settings per waypoint

Type these into a placemark's **Description** box, in any order:

| Setting | Example | Meaning |
|---|---|---|
| `alt=` | `alt=40` | Height above the ground at this waypoint, in metres |
| `speed=` | `speed=2` | Speed in m/s for the stretch *after* this waypoint |
| `hover=` | `hover=4` | Hover here for 4 seconds (keeps recording) |
| `gimbal=` | `gimbal=-30` | Fixed gimbal tilt in degrees instead of tracking the POI |
| `heading=` | `heading=path`, `heading=poi`, `heading=270` | Which way the drone faces |
| `height=` (on the POI) | `height=12` | Aim the camera this many metres above the POI's base, e.g. a tower's midpoint |
| `ground=` | `ground=87` | Ground elevation in metres. Move the cursor over the spot and read "elev" at the bottom-right of Google Earth. Only needed if I ask for it. |

Leave anything out and I'll use your cinematic defaults.

## 4. Export and send

Right-click the mission folder, choose **Save Place As...**, then **KMZ** or **KML**. Upload the file
in the chat along with a sentence or two on the shot you want, e.g. "slow rising reveal of the
castle, hover at the end".
