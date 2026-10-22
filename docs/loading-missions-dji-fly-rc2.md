# Loading a mission into DJI Fly on the DJI RC 2

DJI Fly has no "import" button, so you load a mission by replacing the file of a placeholder
mission with my `.kmz` file.

## One-off: make a placeholder mission

1. Turn on the drone and RC 2 and open DJI Fly. Go into the camera view, tap the waypoint icon on the
   left, and drop **any 2 waypoints**.
2. Save the mission. Calling it `PLACEHOLDER` makes it easy to find.

Each new mission needs its own placeholder. Make a few spare ones now and you won't have to later.

## Swap in the planned mission

1. Close DJI Fly. Connect the RC 2 to a computer with a USB-C data cable.
   - Windows: the RC 2 appears in File Explorer.
   - Mac: install **OpenMTP** or **Android File Transfer** to see it.
2. Open `Internal shared storage/Android/data/dji.go.v5/files/waypoint/`.
3. Inside are folders with long names like `3F2A9C1E-....`. Open the newest one (sort by date). It
   holds one file with the **same long name**, ending in `.kmz`.
4. Copy that file to your computer as a backup.
5. Rename my mission file (e.g. `lake-reveal.kmz`) to **exactly** that long name, including `.kmz`.
   Then copy it into the folder, replacing the original.
6. Optional: to refresh the thumbnail, delete the matching folder inside
   `.../waypoint/map_preview/`.
7. Disconnect and open DJI Fly. Go to waypoints, then the mission list, and open the placeholder.
   You should now see the planned route.

## Check before you fly

- Tap through the waypoints. The heights should match the **"Height in DJI Fly"** column in `BRIEF.md`.
- Check that the route on the map matches `preview.kml` in Google Earth.
- **The first time you use any new file, do a short test.** Run the mission at a quiet open site and
  watch the first two waypoints with your thumbs on the sticks. Then fly it for real.
- Press **Flight Pause** on the RC 2 at any time to stop the mission and hover.

## If DJI Fly won't open the mission

Check the file name matches exactly, including upper/lower case and `.kmz`. If it still won't open, keep
the original placeholder file and send it to me. I'll match my file to the format your version of
DJI Fly writes.
