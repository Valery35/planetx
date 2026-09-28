# PlanetX. Manual

[Русская версия](MANUAL.md)

Version 0.8.0

PlanetX is a 3D globe inside QGIS in the spirit of Google Earth. The
globe opens in its own window and shows the whole Earth with terrain
and atmosphere, from space down to single streets. Layers of the current
project, your own placemarks, paths and polygons lie on the globe. Tours
fly over the places, and a tour recording gives frames for a video.

Plugin page - [www.informpp.ru](https://www.informpp.ru/главная-страница/qgis-planetx).

---

## Installation

The plugin runs in QGIS 3.36 and newer, including QGIS 4. It is tested on
QGIS 3.36 with Qt 5 and on QGIS 4.0 with Qt 6. It needs a graphics card
with OpenGL 3.3 and the Python module PyOpenGL. QGIS builds for Windows
include PyOpenGL.

Open **Plugins → Manage and Install Plugins**, search for PlanetX and
install it. QGIS does not need a restart.

The globe opens with the button on the PlanetX toolbar or from
**Web → PlanetX**. The same menu holds About PlanetX. If the QGIS build
has no PyOpenGL, the plugin says so and does not open the window.

## Interface language

The language follows the QGIS settings, not the system. With Russian in
QGIS the plugin is in Russian, with any other language it is in English.
The label language on the globe is set separately, in the view
properties.

---

## The globe window

The panel is on the left, the globe view on the right. The icon bar
sits in the top left corner of the view, the data source credits in the
bottom right corner. The border between the panel and the view is
dragged with the mouse.

### Icon bar

| Icon | What it does |
|---|---|
| Sidebar | Hides and shows the left panel, the view takes its place |
| Refresh | Shows new settings and layers. It turns orange when there is something to show |
| Synchronization | Links the globe with the QGIS map window |
| Identify features | Turns on identify by a click on the globe |
| Ruler | Opens the Ruler window |
| New placemark | Opens the New placemark window |
| Save view | Puts a placemark at the look-at point with height, heading and tilt |
| View snapshot | Saves the view to a PNG or JPEG file |
| View to layout | Puts the view into a QGIS layout as a picture |
| Scene | The menu Save Scene… and Open Scene… |
| View properties | Base map, terrain, labels, link with the map, update, navigation controls |
| About | Controls, data sources, links |

### Status line

The status line sits under the left panel. It usually shows the camera
height, for example "Overview from 2 000 km". The second line shows the
coordinates and elevation of the point under the cursor.

The line also reports loading:

- "loading 12" - this many tiles, layer pictures and labels still wait
  for loading.
- "loading has stalled for 7 s" - data waits and nothing has arrived for
  5 seconds or longer.
- "places are heavy, 250 thousand vertices" - your own objects exceed
  200 thousand vertices, turning may become slow.
- "The base map did not load" and "The vector base did not load" - the
  source answered with an error.

Messages of search, scenes, tours and recording stay for 5 seconds.

---

## Navigation

Navigation follows Google Earth.

### Mouse

| Action | What happens |
|---|---|
| Left button drag | The Earth follows the cursor. After release it spins on by inertia |
| Wheel | Zooms in and out. The point under the cursor stays in place |
| Left double click | Flies to the point under the cursor and zooms in 2.5 times |
| Right double click | Zooms out 2.5 times |
| Right button drag | Up - closer, down - farther, toward the press point |
| Middle button or left with Shift | Turn and tilt around the look-at point |
| Left button with Ctrl | Looks around, the eye stays in place |

The camera does not go lower than 50 m above the terrain. The tilt is
limited to 85°. While the ruler, drawing or identify is on, a double
click stays two plain clicks and places points.

### Keys

Keys work when the globe view has focus. A click on the globe gives it
focus.

| Key | What happens |
|---|---|
| Arrows | Move the view by a twentieth of the window width |
| Shift and arrows | Turn and tilt by 3° |
| Ctrl and arrows | Look around by 3° |
| PageUp, plus | Zoom in by a wheel step |
| PageDown, minus | Zoom out by a wheel step |
| N | North up |
| U | Look straight down |
| R | North up and look straight down |
| Space | Stop inertia and flight |

### On-screen controls

The navigation controls stand in the top right corner of the view,
as in Google Earth.

| Control | What it does |
|---|---|
| Compass ring | Dragging turns the view. The letter N shows north |
| Letter N | A click puts north up |
| Stick inside the ring | While the button is held, the view looks toward the press |
| Lower stick | While the button is held, the view moves toward the press |
| Plus and minus | While the button is held, the camera zooms in or out smoothly |
| Slider | The thumb stands at the camera height, dragging sets a new one |

The speed of the sticks grows with the distance from the middle. The
controls appear when the cursor comes near the corner of the view. The
check box Navigation controls always on screen in the view properties
keeps them all the time.

### Place search

Type a place name into the Search field at the top of the panel, for
example `Perm`, or coordinates in degrees, for example
`58.0105, 56.2294`. Enter or the Search button starts the search.

- Coordinates start a flight at once. The camera lands no higher than
  2 km from the point.
- A name goes to the Nominatim service in the label language. The camera
  flies to the first place found and frames it whole.
- When several places are found, they are listed under the field. A
  click on a row starts a flight.
- The found place carries a red pin. Clearing the field removes the pin
  and closes the list.

The flight follows the path of van Wijk and Nuij. Over a long distance
the camera rises and lands smoothly. The mouse interrupts a flight.

---

## Left panel

The panel has three sections - Places, Project layers and Layers. A
click on a header collapses the section, and the open sections take its
place. The globe remembers which sections are collapsed.

### Layers section

The section follows the Layers panel of Google Earth. Its check boxes
take effect at once, without the Refresh button.

| Group | Rows |
|---|---|
| Borders and names | Borders, Places, Water names |
| Transport | Roads, Road numbers, Railways, Airports |
| Nature | Rivers, Lakes and reservoirs, Peaks, Reserves and national parks |
| Terrain | Mapzen Terrain Tiles elevations and hill shading |

The vector base comes from OpenFreeMap tiles. On the first opening
borders, places and terrain are on. The tooltip of each row tells how
the feature is drawn and from what height it is visible.

Labels stay level at any turn and tilt and do not overlap. A place
behind a mountain or beyond the horizon has no label.

### View properties

The View properties icon on the icon bar opens the View properties
window. The window does not block work with the globe.

| Group | Field | What it sets |
|---|---|---|
| Base map | List | Source of imagery or map |
| Terrain | Vertical exaggeration | Height multiplier from 0.5 to 10 |
| Labels | Language | Language of labels and search |
| QGIS map | Synchronization | Direction of the link with the map |
| QGIS map | Layers as on the QGIS map | The globe shows the layers switched on in the QGIS legend |
| QGIS map | New layers straight to the globe | A new project layer is checked on the globe at once |
| Update | Update automatically | The globe refreshes after every change without the Refresh button |
| Navigation | Navigation controls always on screen | The ring, sticks and slider stay all the time, not only near the corner |

The default base map is Esri World Imagery, listed as an example. Esri
sets its terms of use. OpenStreetMap comes next, then the XYZ Tiles
connections from the QGIS browser. Terrain connections are not listed.
A new connection appears in the list the next time the window opens.

The label language is chosen from a list. As in QGIS takes the QGIS
interface language, Local names keep the names in the language of the
country. Fifteen languages follow. When there is no name in the chosen
language, Latin-script languages get the Latin name, the others the
local one.

A change of base map, terrain exaggeration or project layers shows after
the Refresh button on the icon bar. The status line reminds about it.
The label language changes at once.

### Project layers section

The section lists the layers of the current project in the order of the
QGIS map, each with its type - raster, points, lines, polygons or
table. The check box of a layer shows it on the globe and does not
change its visibility on the map. In a new project the boxes are clear.
The checks are stored in the project.

Layers lie on the globe as a picture drawn by QGIS, with the styles and
labels of the map. The picture lies on the terrain, it cannot be raised
or extruded.

A double click on a layer flies to its extent, looking straight down.
The right-click menu:

- Fly to - a flight to the extent of the layer.
- Transparency slider - the transparency of the QGIS layer itself, it
  changes on the map too.
- Track… - for point layers, see [Tracks](#tracks).
- Layer Properties… - the standard QGIS layer properties window.

### Places section

The section holds the My Places folder, described in the chapter
[My Places](#my-places).

---

## Link with the QGIS map

### Synchronization

The synchronization icon on the icon bar links the globe with the QGIS
map window. The direction is chosen in the view properties:

- Both ways - the default.
- Map leads the globe - the globe moves to the map extent and keeps its
  tilt and heading.
- Globe leads the map - the map centers on the look-at point of the
  globe once the globe stops.

Any map coordinate system works. The map width on the ground equals the
width of the globe view.

### Selection

Features selected on the QGIS map are highlighted on the globe.

### Identify features

The Identify features icon turns identify on, the cursor becomes a
cross. A click on the globe puts a pin with the coordinates and opens
the Features window.

- The top of the window shows the coordinates and elevation of the
  point.
- Below are the project layers checked on the globe, their features
  under the point and the feature fields. A raster shows its values at
  the point.
- The Select on map button selects the found features in the QGIS
  layers. The selection shows on the map, in the attribute table and on
  the globe.

---

## My Places

My Places is the folder at the top of the Places section, marked with a
star. It holds placemarks, paths, polygons, saved views and
measurements. The places are kept in one file `PlanetX/myplaces.gpkg`
in the QGIS profile folder and are visible in any project, like My
Places in Google Earth.

### List rows

The row icon shows the kind of object - placemark, path, polygon, saved
view or folder. A check box shows and hides the object on the globe, a
folder check box does it for the whole folder. A double click on a
place flies there.

Places and folders are rearranged by dragging, including from folder to
folder. The tour follows the list order.

Several rows are selected with Ctrl and Shift. The selection is dragged
together, and the Del key deletes it after a question.

### Menus

| Where | Items |
|---|---|
| My Places | Play tour, New Folder, Open KML or KMZ…, Save as KML…, Add the places layers to the project |
| Folder | Play tour, New Folder, Open KML or KMZ…, Save as KML…, Rename…, Delete |
| Place | Fly to, Tour along the path, Properties…, New Folder, Rename…, Delete |
| Several rows | Show selected, Hide selected, Delete selected |
| Empty space | New Folder, Open KML or KMZ… |

Only paths have Tour along the path.

A new folder appears at once with the name New Folder and is renamed
later. On a folder it is created inside, on a place right below it. A
folder is deleted with its contents after a question.

Add the places layers to the project adds the three layers of the places
file to the project - points, lines and polygons. Their attributes and
undo are the standard ones.

### New placemark

The New placemark icon opens a window with the tabs Placemark, Path and
Polygon.

- A placemark is put with a click on the globe, a new click moves it.
- Path points and polygon vertices are put with clicks on the globe.
- The Name field is filled at once with a numbered name - My placemark
  1, My path 1, My polygon 1. Each kind counts on its own. The name can
  be changed in the same field.
- Color sets the color of the line and outline, the polygon fill has the
  same color, half transparent. Width is set in screen pixels.

The Save button writes the object to the selected folder of My Places.
The window stays open for the next object. The Clear button removes the
points put so far.

### Saved view

The Save view icon puts a placemark at the look-at point. The name is
offered with a number - View 1, View 2. The placemark keeps the camera
distance, heading and tilt. A flight to such a placemark brings the
whole view back.

### Place properties

The Properties… item opens the properties window.

| Field | What it sets |
|---|---|
| Name | Name in the list and label on the globe |
| Description | Text of the placemark, it goes into KML too |
| Color, Width | Color and width of the line and outline |
| Fill | Fill color of the polygon and of the wall |
| Height above ground | Lift of the object above the terrain in metres |
| Extend to ground | A wall from the object to the ground, a post for a placemark |

Extending works with a height above zero. A path becomes a wall, a
polygon becomes a block.

### KML and KMZ

Open KML or KMZ… puts a Google Earth file into My Places as a new folder
named after the file. Folders, styles and placemark views are kept. The
camera flies to the contents of the file.

Save as KML… saves a folder or the whole My Places to KMZ or KML. The
file extension chooses the format.

---

## Ruler

The Ruler icon opens a window with the tabs Line, Path, Polygon and
Circle. Points are put with clicks on the globe, a rubber band follows
the cursor.

| Tab | Values |
|---|---|
| Line | Length. The third click starts a new line |
| Path | Length |
| Polygon | Perimeter, area |
| Circle | Radius, perimeter, area. The first click is the center, the second sets the radius |

The values are computed on the WGS84 ellipsoid. Each value has its own
units - metres, kilometres, miles, nautical miles, and for the area
square metres, hectares, square kilometres, square miles.

The Save button puts the shape into My Places together with the
measurement. The name is offered with a number, for example Line 1. The
measurement shows in the row tooltip.

The Ruler and New placemark windows are open one at a time. Opening one
closes the other.

---

## Tours

A tour flies over the checked places of a folder in the list order,
including nested folders.

- A saved view brings back its distance, heading and tilt.
- Along a path the camera travels the line.
- Other places are framed whole.

A tour starts with Play tour in the menu of My Places or a folder. A path
has Tour along the path in its menu. The ▶ button under the places list
starts a tour too. When no places are checked, the status line says so.

The tour bar appears at the bottom of the view:

| Button | What it does |
|---|---|
| ⏮, ⏭ | Previous and next stop |
| ⏸, ▶ | Pause and continue |
| Pause | How many seconds the camera stays at a stop |
| ⏺ | Records the tour as PNG frames |
| ✕ | Ends the tour |

Moving the camera with the mouse pauses the tour.

### Recording a tour for a video

The ⏺ button asks for a folder and records the tour into it as PNG
frames, 25 frames per second of the tour. The frame size equals the
window size. The source credits stand in the corner of each frame. The
files are named `frame_00000.png`, `frame_00001.png` and on, frames
with the same numbers in the folder are replaced.

Each frame waits for the tiles, so recording takes longer than the tour
and the frames have no blurred spots. A frame that waits longer than 20
seconds is taken as it is. Recording always starts at the first stop, so
a repeated recording gives the same frames.

A file `frames.json` lies next to the frames - frame rate, size, camera
pose and data time of each frame, numbers of frames that did not fully
load. Any video editor assembles a video from the frames.

The bar shows the frame number. The cross on the bar stops the
recording.

---

## Tracks

A track shows the path of moving objects over time. The source is a
point layer of the project with a time field, and the QGIS Temporal
Controller sets the time.

The Track… item in the menu of a point layer opens the settings window:

| Field | What it sets |
|---|---|
| Time | A field with date and time, ISO 8601 text or seconds since 1970 |
| Object | A field that tells the objects apart. One object - all points form one path |
| Color | Color of the travelled path |
| Camera follows | The camera keeps the first object in the middle of the view along the motion |

Each object grows its travelled path up to the end of the current
controller range, and a label with its name marks the current point.
With the controller off, whole tracks are shown. The Remove track button
returns the layer to its usual look. Track settings are stored in the
project.

During a tour recording the tracks grow along the tour over the whole
controller range.

---

## Scenes

A scene saves the whole view and can be passed to other people. The
Scene icon opens the menu Save Scene… and Open Scene…. A scene file has
the extension `.planetx`.

A scene holds:

- the camera pose.
- the time of the Temporal Controller.
- the project layers checked on the globe, as a link to their source.
- the base map, terrain, terrain exaggeration, groups of the Layers
  section and the label language.
- the selected folder of My Places with its tour.

A database password does not go into the file, a link to a QGIS
connection setting stays. When the whole My Places folder or nothing is
selected, no places go into the scene.

When a scene opens, a layer is looked up in the project by its source
and added if missing. The other project layers are unchecked on the
globe. The places of the scene come in as a new folder, and the camera
flies to the scene pose. The status line lists the layers that were not
found and did not open.

---

## View snapshot and view to layout

### View snapshot

The View snapshot icon opens a window with the snapshot width and height
in pixels. A snapshot can be larger than the window, the globe loads
detailed tiles for it. The Window proportions check box keeps the height
in step with the width.

The Save… button asks for a PNG or JPEG file and starts the snapshot.
The camera stands still meanwhile. The Take now button does not wait
for the remaining tiles. The source credits stand in the bottom right
corner of the snapshot.

### View to layout

The View to layout icon puts the view as a fixed picture into a QGIS
layout, an existing one or a new one.

| Field | What it sets |
|---|---|
| Layout | An existing layout or New layout |
| Width, Height | Size of the picture on the page in millimetres |
| Resolution | Output resolution of the layout, it sets the snapshot size in pixels |

The picture is kept inside the project. The layout window opens after
the insertion.

---

## Limitations

- Project layers lie on the terrain as a picture, a layer cannot be
  raised or extruded by a field. Your own places have lift and extrusion.
- Pictures of project layers are not filtered by the controller time.
- Above latitude 85° the poles are covered with the ocean color, the Web
  Mercator tile grid ends there.
- Recording a tour takes longer than the tour itself.

## Data sources

Imagery - Esri World Imagery, Esri sets the terms. Map data ©
OpenStreetMap contributors. Vector tiles - OpenFreeMap. Terrain - Mapzen
Terrain Tiles, SRTM, GMTED, ETOPO1 and other data. Place search -
Nominatim.

The terms of all sources are described in [SOURCES.md](SOURCES.md).
Tiles go through the QGIS network settings and cache, the plugin keeps
no cache of its own.

Developed with the support of Inform++ LLC. License GNU GPL version 3.
