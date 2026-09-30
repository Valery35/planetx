# PlanetX. Manual

[Русская версия](MANUAL.md)

Version 0.18.0

PlanetX is a 3D globe inside QGIS. The
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

![The globe window over Perm](figures/en/window.jpg)

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
| Record tour | Records the camera movement as a tour into My Places |
| Time slider | Opens and closes the placemark time slider. It is available when visible placemarks have a time |
| View snapshot | Saves the view to a PNG or JPEG file |
| View to layout | Puts the view into a QGIS layout as a picture |
| Scene | The menu Save Scene… and Open Scene… |
| Demo | Ready scenes by body, see [Demo](#demo) |
| Body | The menu Earth, Mars, Moon and Sky, see [Mars and the Moon](#mars-and-the-moon) and [Starry sky](#starry-sky) |
| View properties | Base map, terrain, labels, link with the map, update, coordinate format |
| About | Controls, data sources, links |

### Status line

The status line sits under the left panel. It usually shows the camera
height, for example "Overview from 2 000 km". The second line shows the
coordinates and elevation of the point under the cursor. The coordinate
format is chosen in the view properties.

The line also reports loading:

- "loading 12" - this many tiles, layer pictures and labels still wait
  for loading.
- "loading has stalled for 7 s" - data waits and nothing has arrived for
  5 seconds or longer.
- "places are heavy, 250 thousand vertices" - your own objects exceed
  200 thousand vertices, turning may become slow.
- "The base map did not load" and "The vector base did not load" - the
  source answered with an error.

While loading goes on, a blue icon spins to the right of the icon bar.
A short load does not light it, it appears after half a second. When
loading stalls, the icon turns orange. Its tooltip tells how much still
waits.

Messages of search, scenes, tours and recording stay for 5 seconds.

---

## Navigation

Navigation uses the mouse, the keys and the navigation controls.

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

The navigation controls stand in the top right corner of the view.

<img src="figures/en/navpad.png" width="90" alt="Navigation controls">

| Control | What it does |
|---|---|
| Compass ring | Dragging turns the view. The letter N shows north |
| Letter N | A click puts north up |
| Stick inside the ring | While the button is held, the view looks toward the press |
| Lower stick | While the button is held, the view moves toward the press |
| Plus and minus | While the button is held, the camera zooms in or out smoothly |
| Slider | The thumb stands at the camera height, dragging sets a new one |

The speed of the sticks grows with the distance from the middle. The
controls are always shown. While the cursor is far away, they stand
as a faint outline and do not cover the view. When the cursor comes
near the corner of the view, they are drawn in full.

### Place search

Type a place name into the Search field at the top of the panel, for
example `Perm`, or coordinates. Enter or the Search button starts the
search.

| Format | Example |
|---|---|
| Decimal degrees | `58.0105, 56.2294` |
| Degrees, minutes, seconds | `58°00′37.8″ N, 56°13′45.8″ E` or `58 00 37.8 N 56 13 45.8 E` |
| UTM | `40V 454464 6430139` |
| MGRS | `40V DK 54464 30138` |

Search also understands the coordinates copied from the status line
of the globe together with the elevation.

- Coordinates start a flight at once. The camera lands no higher than
  2 km from the point.
- A name goes to the Nominatim service in the label language. The camera
  flies to the first place found and frames it whole.
- When several places are found, they are listed under the field. A
  click on a row starts a flight.
- The found place carries a red pin. Clearing the field removes the pin
  and closes the list.

Over a long distance the camera rises and lands smoothly. The mouse interrupts a flight.

---

## Left panel

The panel has three sections - Places, Project layers and Layers. A
click on a header collapses the section, and the open sections take its
place. The globe remembers which sections are collapsed.

### Layers section

Its check boxes
take effect at once, without the Refresh button.

| Group | Rows |
|---|---|
| Borders and names | Borders, Places, Water names |
| Transport | Roads, Road numbers, Railways, Airports |
| Nature | Rivers, Lakes and reservoirs, Peaks, Reserves and national parks |
| Terrain | Mapzen Terrain Tiles elevations and hill shading |
| Grid | Parallels and meridians with labels, the equator, tropics and polar circles in yellow |
| Stars | Stars brighter than magnitude 6 and the Milky Way at their places in the sky |
| Clouds | Clouds from NASA GIBS VIIRS imagery of the last complete day |
| Temperature | Surface temperature of land by day over 8 days (MODIS) and of the sea over a day (GHRSST MUR) with a scale in degrees |
| 3D buildings | OpenStreetMap buildings as blocks from OpenFreeMap tiles, off by default |
| Sun | Light of the terrain, buildings and air by the position of the sun, the night side of the Earth is dark, off by default |

The vector base comes from OpenFreeMap tiles. On the first opening
borders, places, terrain and stars are on. The tooltip of each row
tells how the feature is drawn and from what height it is visible.

The grid step follows the camera height, from 30° from space to
seconds near the ground. The stars stand where they stand over the
Earth at this minute and fade when the camera goes below 150 km. The
Milky Way image, about 10 MB, is downloaded when the stars are first
shown and comes from the QGIS cache afterwards.
Clouds lie as a veil over the imagery. Snow and ice get into the
clouds too, they have the same colour.

Temperature colours land and sea with their own scales, the scales in
degrees Celsius are in the bottom left corner of the view. Land shows
the temperature of the surface itself by day, not of the air, over 8
days. Land may have gaps under clouds. Sea shows the water temperature
near the surface over a day.

The Sun row lights the terrain and buildings from the side of the
sun. The night side of the Earth is dark, the air over it does not
glow. The sun time is the end of the interval of the open time
slider, so the light of the hour of a placemark shows. Without the
slider the sun follows the computer clock. Without the Sun row the
light falls from the north-west at 45°, as on a relief map. The
position of the sun is computed to about 0.01°, there are no
shadows.

Labels stay level at any turn and tilt and do not overlap. A place
behind a mountain or beyond the horizon has no label.

### 3D buildings

The 3D buildings row of the Layers section puts OpenStreetMap buildings
on the globe as blocks. Outlines and heights come from the same
OpenFreeMap vector tiles as the vector base. The row is off by default.

<img src="figures/en/buildings.jpg" width="600" alt="3D buildings in the centre of Perm">

Buildings show when the camera is closer than 6 km to the ground. The
globe keeps up to 32 building tiles around the camera, the nearest
first. Tiles behind the camera are not loaded.

The height of a building is its height in OpenStreetMap, otherwise the
number of floors times 3.66 m. A building without either gets a height
of 5 m. In the centre of Perm two thirds of the buildings have a height
of their own, in the centre of Moscow almost all. In the outskirts many
houses have the same height. The colour of a building comes from
OpenStreetMap, otherwise the building is light grey. Roofs are flat.

The bottom of a building stands at the lowest point of the terrain
under its outline. A view snapshot waits until all buildings of the
frame are loaded. A scene remembers whether buildings are on.

### View properties

<img src="figures/en/properties.png" width="240" alt="View properties">

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
| Coordinates | Format | Decimal degrees, degrees-minutes-seconds, UTM or MGRS in the status line and the Features window. North of 84° and south of 80° UTM and MGRS are replaced with decimal degrees |

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

Layers lie on the globe as a picture drawn by QGIS, with the styles of
the map. The picture lies on the terrain, it cannot be raised or
extruded.

Labels of vector layers come separately, like city names. They stay
level at any turn and tilt, do not overlap and hide behind mountains
and the horizon. The text, colour and size come from the layer labels
in QGIS, rule-based labels too. A point label stands to the right of
the point, a line label at its middle, a polygon label inside it.
Features around the view point are labelled, at most 500 per layer.
The scale visibility of QGIS labels is not used on the globe.

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
in the QGIS profile folder and are visible in any project.

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
| My Places | Play tour, New Folder, Open KML or KMZ…, Save as KML…, Copy, Paste, Add the places layers to the project |
| Folder | Play tour, New Folder, Open KML or KMZ…, Save as KML…, Copy, Paste, Rename…, Delete |
| Place | Fly to, Tour along the path, Snapshot view, Properties…, New Folder, Copy, Paste, Rename…, Delete |
| Several rows | Copy, Show selected, Hide selected, Delete selected |
| Empty space | New Folder, Open KML or KMZ…, Paste |

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

<img src="figures/en/placeprops.png" width="340" alt="Place properties">

The Properties… item opens the properties window. The window does not
block the globe, the view can be turned and zoomed. Each change shows
on the globe at once. OK writes the changes to the place, Cancel
brings the previous look back.

| Field | What it sets |
|---|---|
| Name | Name in the list and label on the globe |
| Description | Text of the placemark, it goes into KML too |
| Icon | Point icon from the QGIS set, in KML a standard icon of the same theme |
| Color, Width | Color of the point icon, color and width of the line and outline |
| Fill | Fill color of the polygon and of the wall |
| Height above ground | Lift of the object above the terrain in metres. The Ground - Space slider under the field sets it from the ground to 100 km |
| Extend to ground | A wall from the object to the ground, a post for a placemark |
| Time | Moment or interval of the placemark for the time slider |
| Place view | Look point, range, heading, tilt of the camera at the place and the view date |

Extending works with a height above zero. A path becomes a wall, a
polygon becomes a block.

### Place view

Any place can have a view of its own.
A view is the point the camera looks at, the range to it, the heading
and the tilt. The look point may differ from the place. Fly to, a double
click on the place and a tour stop follow the view.

Snapshot view in the place menu makes the current globe view the view of
the place. The properties window has the same values in the Place view
section. The Snapshot current view button takes the globe view, Reset
brings back the view the place had when the window opened. Clearing the
section check box removes the view, then the camera frames the whole
place. The view goes into KML as a LookAt element and is read from it.

### Copy and paste

Copy or Ctrl+C puts the selected places and folders into the
clipboard as KML text. The text can be pasted
into a text editor, edited and copied back. Paste or Ctrl+V puts the
places from the clipboard into a folder. On a place it is the folder
of that place, on empty space the root of My Places. Folders from the
clipboard come in as folders. KML copied in Google Earth pastes the
same way.

### Placemark time and the time slider

A placemark can have a time of its own. It is a
moment or an interval, the Time field of the placemark properties. In
KML the time is written as TimeStamp and TimeSpan. The view of a
placemark has its own time, the Date/time field of the Place view
section.

<img src="figures/en/demo.jpg" width="600" alt="Perm demo with the time slider">

The time slider opens with the Time slider button on the icon bar.
The button is available when visible placemarks have a time. The
slider spans the placemark times from the earliest to the latest. A
closed slider hides no placemarks, all of them show.

| Part | What it does |
|---|---|
| Handles | Set the interval. Placemarks outside it are hidden, placemarks without a time always show |
| Bar between the handles | Dragging moves the whole interval, a click on the bar centres it on the click |
| ▶ | Playback, the interval moves along the slider |
| ×1 | Playback speed, at ×1 the slider is crossed in 20 seconds |

A flight to a placemark and a tour set the slider to the time of the
placemark view, without it to the time of the placemark itself. A
closed slider opens then. The
slider is its own and does not depend on the QGIS Temporal Controller
that drives tracks.

### KML and KMZ

Open KML or KMZ… puts a KML or KMZ file, including one from Google
Earth, into My Places as a new folder named after the file.
Folders, styles, icons, times and placemark views are kept, `gx:Tour` becomes a recorded tour. The
camera flies to the contents of the file.

Save as KML… saves a folder or the whole My Places to KMZ or KML. The
file extension chooses the format.

---

## Ruler

The Ruler icon opens a window with the tabs Line, Path, Polygon,
Circle, 3D path and 3D polygon. Points are put with clicks on the globe, a rubber band follows
the cursor.

<img src="figures/en/ruler.png" width="300" alt="Ruler">

| Tab | Values |
|---|---|
| Line | Map length, ground length, heading. The third click starts a new line |
| Path | Map length, ground length |
| Polygon | Perimeter, area |
| Circle | Radius, perimeter, area. The first click is the center, the second sets the radius |
| 3D path | Length by straight segments in space |
| 3D polygon | Perimeter, area in the plane of the polygon, tilt of the plane |

Map length, perimeter and area are computed on the WGS84 ellipsoid.
Ground length runs along the surface with its rises and falls. Heading
is the azimuth of the start of the line clockwise from north. Each value
has its own units - metres, kilometres, miles, nautical miles, and for
the area square metres, hectares, square kilometres, square miles.

Heights for the ground length come from Mapzen Terrain Tiles. Missing
height tiles along the line are loaded, even when terrain is off. While
they load, the ground length is preceded by «≈».

A ruler point can be grabbed with the mouse and dragged, Backspace
removes the last point. Each segment on the globe is labelled with its
length.

The Save button puts the shape into My Places together with the
measurement. The name is offered with a number, for example Line 1. The
measurement shows in the row tooltip.

The 3D path and 3D polygon tabs put a point on the roof or wall of
a 3D building when the ray from the eye meets it before the
terrain. They keep the height of the point. Segments run straight
between the points and do not follow the terrain. The area of a
3D polygon is measured in its plane, so for a roof slope or a wall
it is the real one. Tilt is the angle of the plane to the horizon,
0 is a flat roof, 90 a wall. A saved 3D shape goes to KML with
altitudeMode absolute.

The Ruler and New placemark windows are open one at a time. Opening one
closes the other.

### Elevation profile

The Elevation profile button of the ruler opens a chart of height along
the line. The Elevation profile item in the menu of
a path in My Places does the same.

<img src="figures/en/profile.png" width="600" alt="Elevation profile of a path over Elbrus">

Under the chart are the map and ground length, the lowest and highest
height, ascent and descent, the mean and maximum slope. The cursor over
the chart shows the distance, height and slope at that place, and a
mark with the height shows the point on the globe. The profile of the
ruler follows its points.

Heights are taken as for the ground length. The slope is measured over a
stretch not shorter than three pixels of height data, so roughness of
the data does not pass for a cliff. On steep mountains the maximum slope
may exceed 100 %, that is 45°.

---

## Tours

A tour flies over the checked places of a folder in the list order,
including nested folders.

- A place with a view of its own brings back its look point, range,
  heading and tilt.
- Along a path the camera travels the line.
- Other places are framed whole.

A tour starts with Play tour in the menu of My Places or a folder. A path
has Tour along the path in its menu. The ▶ button under the places list
starts a tour too. It tours the selected folder or path, and with a
place selected it tours the folder holding the place. A tour goes
through the places of the body now on the globe. When no places are
checked, the status line says so.

The tour bar appears at the bottom of the view:

| Button | What it does |
|---|---|
| Slider | Shows how much of the tour has passed and winds the tour. The camera moves to the chosen point at once, after release the tour goes on from it |
| ⏮, ⏭ | Previous and next stop |
| ⏸, ▶ | Pause and continue |
| Pause | How many seconds the camera stays at a stop |
| ⟳ | Loops the tour. After the last stop the tour starts again from the first. The button state is kept between sessions |
| ⏺ | Records the tour as PNG frames |
| ✕ | Ends the tour |

Moving the camera with the mouse pauses the tour.

### Recording a tour from the screen

The record button ⏺ on the icon bar records the camera movement.
The camera can be moved with the mouse,
keys, flights and the navigation controls. A second click ends the
recording and asks for a name. The tour goes into My Places with a film
icon and is not drawn on the globe.

Play tour in the menu of such a tour plays the recording. The camera
first flies to the start of the recording. The slider of the tour bar
and recording to PNG frames work as for a tour over places. In KML a
recorded tour is saved as `gx:Tour`, and Google Earth plays it.

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
load.

The bar shows the frame number. The cross on the bar stops the
recording.

### Making a video from the frames

PlanetX writes frames, not a video file. Any program that opens an image
sequence assembles a video from them.

The free program ffmpeg (ffmpeg.org) makes an MP4 with one command in
the folder with the frames:

```
ffmpeg -framerate 25 -i frame_%05d.png -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" -c:v libx264 -pix_fmt yuv420p -crf 18 tour.mp4
```

The rate 25 matches the recording rate, so the video runs at the pace
of the tour. The `pad` filter adds a pixel when a frame side is odd, the
H.264 codec needs even sides. A smaller `-crf` value gives better
quality and a larger file.

The video editors Shotcut and DaVinci Resolve open numbered frames as
one clip. Music, captions and several tours joined together can be
added there.

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
- the rows of the Layers section, the grid, stars, clouds,
  temperature and 3D buildings.
- the selected folder of My Places with its tour.

A database password does not go into the file, a link to a QGIS
connection setting stays. When the whole My Places folder or nothing is
selected, no places go into the scene.

When a scene opens, a layer is looked up in the project by its source
and added if missing. The other project layers are unchecked on the
globe. The places of the scene come in as a new folder, and the camera
flies to the scene pose. The status line lists the layers that were not
found and did not open.


### Demo

The Demo icon with an academic cap on the icon bar opens prepared scenes.
Each scene puts its places into My Places as a new folder, the ▶ button
under the list plays a tour over them. The folder can be deleted.

| Section | Scene | What it holds |
|---|---|---|
| Earth | Perm | Places with icons and the moments of a walk, place views with a date, a route, an extruded polygon, a path along the Kama, a recorded flight over the centre, 3D buildings |
| Earth | Boca Chica, Starbase | The Starbase launch site and factory, the beach, nearby towns, the highway from Brownsville, a recorded flight around the launch site |
| Mars | Rover landing sites | Olympus Mons, Valles Marineris, the landing sites of Curiosity, Perseverance, Zhurong, Spirit and Opportunity |
| Moon | Apollo and Lunokhod sites | The landing sites of six Apollo missions, Lunokhod 1 and Lunokhod 2 |
| Sky | Constellations and bright sky objects | Orion, the Pleiades, the Andromeda Galaxy (M31), Cassiopeia, Ursa Major, Lyra with Vega, the Southern Cross |

The Perm walk time is fictional. Landing coordinates are rounded to
hundredths of a degree.

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

## Mars and the Moon

The Body icon on the icon bar opens the menu Earth, Mars and Moon.
The chosen body replaces the Earth. The size of the globe, the imagery
and the atmosphere change, and the camera flies to the start point of
the body. On Mars it is Olympus Mons, on the Moon it is the Sea of
Tranquility, the Apollo 11 landing site.

Mars imagery is the Viking MDIM2.1 colour mosaic, about 650 m per
pixel. Moon imagery is the LOLA albedo map with hill shading, about
670 m per pixel. Mars has a thin, dusty atmosphere, the Moon has none.

On Mars and the Moon the navigation, grid, stars, ruler, My Places,
tours, view snapshot and scenes work. Functions with Earth-only data
are off:

- terrain, vector base, clouds, temperature, 3D buildings and sunlight
- project layers and their labels, tracks
- synchronization with the QGIS map and feature identification
- place search by name. Coordinates in the search field work

Each place remembers its body. My Places lists the places of all
bodies, the globe shows only the places of the current one. A flight
to a place on another body switches the body first. A tour goes
through the stops of the current body. A scene keeps its body and
opens on it.

## Starry sky

The Sky item of the Body menu shows the sky from the centre of the
celestial sphere. It holds the Milky Way, 5080 stars down to
magnitude 6, lines and names of 88 constellations and names of bright
stars. The Sun, the Moon and the planets from Mercury to Neptune are
there too. The north celestial pole is up and east is on the left, as
on a star chart.

| Action | What it does |
|---|---|
| Drag with the left button | The sky follows the cursor |
| Wheel, PageUp, PageDown, plus, minus | Changes the field of view from 2° to 110° |
| Double click with the left button | The point moves to the centre, the field of view halves |
| Double click with the right button | The field of view doubles |
| Arrows | The view moves by a tenth of the window height |

The status bar shows the field of view, the right ascension and the
declination of the point under the cursor. Equatorial coordinates
refer to the epoch J2000.0. The Sun, the Moon and the planets are
placed at the end of the open time slider range, otherwise at the
computer clock time. Planet positions differ from the JPL Horizons
ephemerides by at most 0.2° in the years 1800-2050, the Moon position
by at most 0.3°.

The Constellations item of the same menu hides and shows the
constellation lines and names. Stars, their names, the Sun, the Moon
and the planets stay.

Places and tours work in the sky. Save view puts a place with the
view direction and the field of view. New place puts a point with a
click on the sky. Record tour records the motion over the sky. Sky
places are kept in My Places with the others and are shown in the sky
as yellow circles with a label. A tour and the ▶ button in the sky go through the
sky places, between distant points the field of view widens on the
way. A flight to a sky place from the list opens the sky.

The ruler, synchronization and feature identification are off in the
sky. A view snapshot saves the sky with its labels. A scene keeps the
view direction and the field of view. To return to a body, choose it
in the same menu.

---

## Limitations

- Project layers lie on the terrain as a picture, a layer cannot be
  raised or extruded by a field. Your own places have lift and extrusion.
- Pictures of project layers are not filtered by the controller time.
- Above latitude 85° the poles are covered with the ocean color, the Web
  Mercator tile grid ends there.
- Recording a tour takes longer than the tour itself.
- Buildings are blocks with flat roofs, roof shapes and facades
  are not shown.
- Mars and the Moon are smooth spheres, the relief shows only as hill
  shading in the imagery. KML does not store the body of a place,
  places from a KML file go to the current body.
- The sky is shown from the centre of the Earth, without the horizon
  of an observing site. Coordinates are not reduced to the date, by
  2026 precession shifts them by about 0.36°.

## Data sources

Imagery - Esri World Imagery, Esri sets the terms. Map data ©
OpenStreetMap contributors. Vector tiles and 3D buildings - OpenFreeMap. Terrain - Mapzen
Terrain Tiles, SRTM, GMTED, ETOPO1 and other data. Clouds - NASA GIBS,
VIIRS imagery. Temperature - NASA GIBS, MODIS and GHRSST MUR. Stars - the Yale Bright Star Catalogue. Milky Way -
NASA/Goddard Space Flight Center Scientific Visualization Studio, Gaia
DR2: ESA/Gaia/DPAC. Place search - Nominatim. Mars - NASA, USGS,
Viking MDIM2.1, the Moon - USGS, LRO LOLA, tiles of both bodies -
OpenPlanetaryMap. Constellation lines, names and star names -
d3-celestial, © Olaf Frohn. Planet positions are computed from JPL
orbital elements, the Moon position from the formulae of the
Astronomical Almanac.

The terms of all sources are described in [SOURCES.md](SOURCES.md).
Tiles go through the QGIS network settings and cache, the plugin keeps
no cache of its own.

Developed with the support of Inform++ LLC. License GNU GPL version 3.
