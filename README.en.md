# PlanetX

**English** · [Русский](README.md)

[![Install in QGIS](https://img.shields.io/badge/Install%20in%20QGIS-blue.svg)](https://plugins.qgis.org/plugins/planetx/)

<img src="planetx/icon.svg" width="96" align="right" alt="PlanetX">

A 3D globe inside QGIS in the spirit of Google Earth. PlanetX version 0.1.0.

The globe opens in its own window and shows the whole Earth with the
OpenStreetMap base map, from space down to single streets.

## Features

- **Grab the Earth.** Drag the Earth with the left mouse button. After
  release it keeps rotating by inertia.
- **Zoom to the cursor.** The wheel zooms to the point under the cursor,
  and the point stays in place.
- **Turn and tilt.** The middle button or Shift with the left button turns
  and tilts the view.
- **Fly to.** Type coordinates in degrees in the field at the bottom
  of the window, for example `58.0105, 56.2294`. The camera flies there
  along the van Wijk and Nuij path. Over long distances it rises and then
  lands smoothly.
- **No holes in the base map.** Tiles are chosen by screen-space error.
  A parent tile stays on screen until all its children are loaded.

Tiles come through the QGIS network settings and cache.

## Installation

In QGIS open **Plugins → Manage and Install Plugins**, find PlanetX
and install it. The globe opens from **Web → PlanetX** or with the button
on the Web toolbar.

## Requirements

- QGIS 3.40 or newer, QGIS 4 included. Tested on QGIS 3.36 with Qt 5
  and on QGIS 4.0 with Qt 6.
- A graphics card with OpenGL 3.3.
- The PyOpenGL Python module. QGIS builds for Windows include it.

## Next

Terrain, other base maps and layers of the current project on the globe
are planned for the next versions.

## Sources

Base map © OpenStreetMap contributors, [terms of use](https://www.openstreetmap.org/copyright).

Developed with the support of Inform++ LLC (https://www.informpp.ru/).
License GNU GPL version 3.
