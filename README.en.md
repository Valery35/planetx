# PlanetX

**English** · [Русский](README.md)

[![Install in QGIS](https://img.shields.io/badge/Install%20in%20QGIS-blue.svg)](https://plugins.qgis.org/plugins/planetx/)

<img src="planetx/icon.svg" width="96" align="right" alt="PlanetX">

A 3D globe inside QGIS in the spirit of Google Earth. PlanetX version 0.4.3.

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
- **Layers panel.** At the bottom left, as in Google Earth, there are
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
  a layer on the globe and leaves the map unchanged.

![The Earth from space](doc/images/earth.jpg)

## Controls

- **Grab the Earth.** Drag the Earth with the left mouse button. After
  release it keeps rotating by inertia.
- **Zoom to the cursor.** The wheel zooms to the point under the cursor,
  and the point stays in place.
- **Turn and tilt.** The middle button or Shift with the left button turns
  and tilts the view.
- **Search.** Type a place name in the Search field at the top left,
  for example `Perm`, or coordinates in degrees, for example
  `58.0105, 56.2294`. The camera flies there along the van Wijk and Nuij
  path. Over long distances it rises and then lands smoothly. The place
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
- **Selection.** Features selected on the QGIS map are highlighted on the
  globe, features found by a click on the globe are selected on the map.
- **Ruler.** Line, path, polygon and circle by clicks on the globe.
  Length, perimeter and area on the WGS84 ellipsoid. The measurement
  is saved to My Places.
- **My Places.** Placemarks, paths and polygons are drawn by clicks right
  on the globe. They, saved views and measurements sit in the My Places
  folder under the Globe row, as in Google Earth. The places file is
  shared by the QGIS profile, so places are visible in any project.
  A double click on a place flies there.
- **Identify features.** In the Identify features mode a click on the
  globe shows the coordinates and elevation of the point and the features
  of the project layers checked on the globe.

A double click on the Globe row opens the view properties. Tiles come
through the QGIS network settings and cache. The About button in the
globe window lists the controls and the data sources.

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
come from [OpenFreeMap](https://openfreemap.org/).

Terrain comes from [Mapzen Terrain Tiles](https://github.com/tilezen/joerd/blob/master/docs/attribution.md),
data from SRTM, GMTED, ETOPO1 and other sources.

Data sources and their terms of use are described in [doc/SOURCES.md](doc/SOURCES.md), in Russian.

Developed with the support of Inform++ LLC (https://www.informpp.ru/).
License GNU GPL version 3.
