# PlanetX subsurface mode

The manual section on a mode hidden until its own release.

## Subsurface mode

The Subsurface mode icon on the icon bar opens a window of the same
name. The mode shows drill holes, bed roofs, section walls and a block
cut under the surface.

### Data

The data are tables in the same layout as in Isoliner.

| Table | Fields | What it sets |
|---|---|---|
| collar | hole_id, z, eoh, point geometry | Hole collar, collar elevation, end-of-hole depth along the hole |
| interval | hole_id, from, to, code | Intervals along the hole, positive downward, code is the bed or lithology |
| survey | hole_id, depth, azimuth, dip or zenith | Survey. Without it the hole is vertical |
| beds | code, ord, color, surface | Order of beds from top to bottom, colour "#rrggbb", roof raster file |
| sections | line geometry | Section lines |
| cut | polygon geometry | Block cut |

Fields are also found by other common names, for example bhid, elev,
td, from_m, to_m, litho. A dip angle with negative values is counted
from the horizontal, -90 is straight down. A bed roof is a raster of
elevations in metres in any coordinate system, GDAL reads it.

The source is chosen in the window. GeoPackage file takes the tables
with these names from one file. It finds the roof rasters by the
surface field of the beds table, the path is relative to the folder of
the file. Project layers takes the tables from layers of the current
project and the roofs from the rasters checked in the list. The bed
code of a roof is the layer name.

### Display

The Build button reads the data, loads the terrain heights under the
model and builds it.

- A drill hole follows the survey by the minimum curvature method.
  Intervals take the colour of their bed, the hole number stands
  above the collar.
- A bed roof is a surface in the colour of the bed.
- A section is a set of walls along the line from the terrain to the
  model bottom, beds between the roofs have their own colours.
- The model bottom is the end of the deepest hole, without holes it
  is 20 m below the deepest roof.

Depth is stretched by the terrain scale, like the surface. With the
terrain off, elevations are counted from the surface.

The Surface opacity slider makes the terrain inside the model frame
transparent, the drill holes and roofs show through it. Outside the
frame the surface stays opaque. The Block cut checkbox removes the
surface and the roofs inside the cut polygon. Walls with beds stand
along the cut edge, a plane at the model bottom lies at its floor. The
Camera under ground checkbox lets the camera go below the terrain down
to the model bottom. Inside the model frame the camera then moves along
its bottom. The Remove button removes the subsurface objects from the
globe. The window settings are kept in the project.

The Permian deposits demo in the Demo icon opens a synthetic site
near Berezniki, on the Verkhnekamsk deposit. It has 24 drill holes, 9 bed roofs of the Verkhnekamsk
section, two sections and a cut of the north-east quarter. The data are
made up for the example, they are not a survey.
