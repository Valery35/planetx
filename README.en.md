# PlanetX

**English** · [Русский](README.md)

[![Install in QGIS](https://img.shields.io/badge/Install%20in%20QGIS-blue.svg)](https://plugins.qgis.org/plugins/planetx/)
[![Plugin page](https://img.shields.io/badge/Plugin%20page-0f766e.svg)](https://www.informpp.ru/%D0%B3%D0%BB%D0%B0%D0%B2%D0%BD%D0%B0%D1%8F-%D1%81%D1%82%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B0/qgis-planetx)

<img src="planetx/icon.svg" width="96" align="right" alt="PlanetX">

A 3D globe inside QGIS. PlanetX version 0.19.0.

The globe opens in its own window and shows the whole Earth with terrain
and atmosphere, from space down to single streets.

![The Caucasus, Elbrus and Svaneti](doc/images/caucasus.jpg)

## Features

- **Satellite imagery.** By default the globe shows Esri World Imagery
  as an example base map. In the view properties the base map can be
  switched to OpenStreetMap or to XYZ Tiles connections from the QGIS
  browser.
- **Terrain.** Mountains and valleys are three-dimensional, slopes are
  shaded by light from the north-west. Vertical exaggeration is set in
  the view properties. The camera stays at least 50 m above the terrain.
- **Atmosphere.** A blue glow surrounds the planet. From a low altitude
  the sky is visible at the horizon, and distant mountains fade into haze.
- **Grid, stars, clouds.** A coordinate grid with labels, the equator,
  tropics and polar circles in yellow. The stars
  and the Milky Way stand at their places in the sky. Clouds come from NASA imagery of
  the last complete day. Land and sea temperature from NASA data
  colours the globe, the scale in degrees is in the corner of the view.
- **3D buildings.** OpenStreetMap buildings from OpenFreeMap tiles
  rise as blocks when the camera is closer than 6 km to the ground.
  The height comes from OpenStreetMap or from the number of floors.
- **Sun.** Terrain and buildings are lit by the position of the sun
  at the time slider time or by the clock, the night side of the
  Earth is dark.
- **Mars and the Moon.** An icon on the icon bar puts Mars or the Moon
  in place of the Earth, with NASA and USGS imagery. Navigation, grid,
  ruler, places, tours, view snapshots and scenes work on any body.
  A place remembers its body.
- **Starry sky.** The same icon opens the sky from the centre of the
  celestial sphere. It shows the Milky Way, stars, constellation lines
  and names, the Sun, the Moon and the planets at the chosen time.
- **Left panel.** The sections Places, Project layers and Layers
  collapse with a click on the header.
- **Layers section.** It holds
  the groups Borders and names, Transport and Nature. They hold borders,
  places, water names, roads and road numbers, railways, airports,
  rivers, lakes, peaks, nature reserves and national parks. Check boxes
  take effect at once.
- **Labels.** Labels stay upright at any turn and tilt and do not
  overlap. A place behind a mountain or beyond the horizon is not
  labelled. The label language follows QGIS or is chosen in the view
  properties.
- **Project layers.** Vector and raster layers of the project lie on the
  globe in the QGIS map order. A check mark in the window list shows
  a layer on the globe and leaves the map unchanged. Labels of vector
  layers stay level like city names, with the text and colour of the
  layer labels in QGIS.

![The Earth from space](doc/images/earth.jpg)

## Controls

- **Grab the Earth.** Drag the Earth with the left mouse button. After
  release it keeps rotating by inertia.
- **Zoom to the cursor.** The wheel zooms to the point under the cursor,
  and the point stays in place.
- **Turn and tilt.** The middle button or Shift with the left button turns
  and tilts the view.
- **Mouse and keys.** A left double click flies to the
  point and zooms in, a right double click zooms out. Dragging with the
  right button up zooms in, down zooms out. Ctrl with the left button
  looks around, the eye stays in place. Arrows move the view, with
  Shift they turn and tilt, with Ctrl they look around. PageUp and
  PageDown zoom, N puts north up, U looks straight down, R does both,
  Space stops.
- **On-screen controls.** The top right corner of the view holds
  the compass ring, the look and move sticks and the
  height slider with plus and minus buttons.
- **Search.** Type a place name in the Search field at the top left,
  for example `Perm`, or coordinates in degrees, for example
  `58.0105, 56.2294`. The camera flies there. Over long distances it rises and then lands smoothly. The place
  found is marked with a red pin. If several places are found, the
  others are listed below the field. Clearing the field removes the pin
  and closes the list.
- **Refresh.** A new base map, terrain exaggeration and project layers
  appear after the Refresh button in the corner of the view. Automatic
  refresh is switched on in the view properties.
- **Map synchronization.** The link button in the corner of the view ties
  the globe to the QGIS map window. The map leads the globe, the globe
  leads the map or both follow each other, as chosen in the view
  properties. Any map coordinate system works.
- **Save view.** The Save view button in the corner of the view puts a
  placemark at the look-at point. A double click on it restores the
  height, heading and tilt of the globe.
- **View snapshot.** The snapshot button in the corner of the view saves
  the view to PNG or JPEG, larger than the window if needed. The globe
  loads detailed tiles for that size, the source credits sit in the
  corner of the snapshot.
- **View to layout.** The layout button puts the view as a fixed picture
  into a QGIS layout, an existing or a new one. The snapshot size follows
  the picture size on the page and the output resolution of the layout.
  The picture is embedded in the project.
- **Layer transparency.** The menu of a project layer in the globe list
  changes the transparency of the QGIS layer with a slider and opens the
  layer properties. The transparency is shared with the map.
- **Selection.** Features selected on the QGIS map are highlighted on the
  globe, features found by a click on the globe are selected on the map.
- **Ruler.** Line, path, polygon and circle by clicks on the globe.
  Length, perimeter and area on the WGS84 ellipsoid, ground length
  and heading, a 3D path and a 3D polygon over roofs and walls of
  buildings. Points are dragged with the mouse. The elevation
  profile of a path shows ascent and slopes. The measurement is
  saved to My Places.
- **Coordinates.** Degrees, degrees-minutes-seconds, UTM or MGRS in
  the status line, search understands all four.
- **My Places.** Placemarks, paths and polygons are drawn by clicks
  on the globe. They, saved views and measurements sit in the My Places
  folder of the Places section. The places file is
  shared by the QGIS profile, so places are visible in any project.
  A double click on a place flies there.
- **Tour.** Play tour in the menu of My Places or any of its folders
  flies over the checked places in the list order, along a path the
  camera travels the line. Places and folders are rearranged by
  dragging. The bar at the bottom of the view pauses the tour, steps
  between stops and records the tour as PNG frames for a video. The
  record button records a tour from the screen.
- **Placemark time.** A placemark can have a moment or an interval. The
  time slider opens with a button on the icon bar and hides placemarks
  outside the interval.
- **Perm demo.** The Scene menu opens a scene with placemarks around
  Perm with icons, time, tours and 3D buildings.
- **Scenes.** The whole view - camera, time, layers, settings and a
  places folder with its tour - saves to a file and opens on another
  computer.
- **Tracks.** A point layer with a time field shows as growing paths of
  its objects along the QGIS Temporal Controller. The camera can follow
  along the motion.
- **Place properties.** Name, description, icon, colors, time,
  height above ground
  and extending to the ground. A path becomes a wall, a polygon a block.
- **KML and KMZ.** KML and KMZ files, including Google Earth
  ones, open into My Places with folders,
  styles and placemark views. A folder saves to KMZ or KML.
- **Copy and paste.** Places and folders are copied to the clipboard
  as KML text and pasted back, also after editing in a text editor and
  from Google Earth.
- **Identify features.** In the Identify features mode a click on the
  globe shows the coordinates and elevation of the point and the features
  of the project layers checked on the globe.

The View properties icon on the icon bar opens the view properties.
Tiles come
through the QGIS network settings and cache. The About button in the
globe window lists the controls and the data sources.

Everything is described in detail in the manual - [doc/MANUAL.en.md](doc/MANUAL.en.md).
A PDF manual with pictures ships with the plugin and opens from the
About window.

![Perm, roads and names](doc/images/perm.jpg)

## Installation

In QGIS open **Plugins → Manage and Install Plugins**, find PlanetX
and install it. The globe opens with the button on the PlanetX toolbar
or from **Web → PlanetX**.

## Requirements

- QGIS 3.36 or newer, QGIS 4 included. Tested on QGIS 3.36 with Qt 5
  and on QGIS 4.0 with Qt 6.
- A graphics card with OpenGL 3.3.
- The PyOpenGL Python module. QGIS builds for Windows include it.

## Sources

Satellite imagery is Esri World Imagery, credited to Esri, Vantor,
Earthstar Geographics, and the GIS User Community. Esri sets the terms
of use.

Map data © OpenStreetMap contributors,
[terms of use](https://www.openstreetmap.org/copyright). Vector tiles
and 3D buildings come from [OpenFreeMap](https://openfreemap.org/).

Terrain comes from [Mapzen Terrain Tiles](https://github.com/tilezen/joerd/blob/master/docs/attribution.md),
data from SRTM, GMTED, ETOPO1 and other sources.

Clouds come from [NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api),
VIIRS imagery. Temperature comes from NASA GIBS, MODIS and GHRSST MUR.
Stars come from the Yale Bright Star Catalogue. The
Milky Way comes from [NASA/Goddard Space Flight Center Scientific Visualization Studio](https://svs.gsfc.nasa.gov/4851),
Gaia DR2: ESA/Gaia/DPAC.

Mars comes from NASA, USGS, Viking MDIM2.1. The Moon comes from USGS,
LRO LOLA. Tiles of both bodies come from [OpenPlanetaryMap](https://github.com/openplanetary/opm/wiki/OPM-Basemaps).
Constellations and star names come from [d3-celestial](https://github.com/ofrohn/d3-celestial),
© Olaf Frohn. Planet positions come from JPL orbital elements.

Data sources and their terms of use are described in [doc/SOURCES.md](doc/SOURCES.md), in Russian.

Developed with the support of Inform++ LLC (https://www.informpp.ru/).
License GNU GPL version 3.
