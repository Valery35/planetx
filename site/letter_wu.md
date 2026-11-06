Кому: Qiusheng Wu, qwu18@utk.edu (адрес с https://gishub.org/)
Тема: A home for Google Earth Pro users - PlanetX in QGIS, a Rust version later

Dear Dr. Wu,

This is Valery Hronusov, PhD (Valery35 on GitHub). Our field is the
Earth sciences and general geographic tasks. We develop open plugins
for QGIS at Inform++ LLC, and I read the announcement of RustGIS 0.1.0
with interest - our work goes in a close direction. You also build
QGIS plugins (GeoAI, NASA OPERA) and GeoLibre, so we work on the same
ground from two sides.

Google stops new downloads of Google Earth Pro on 25 June 2027:
https://support.google.com/earth/thread/448773864
For twenty years its users have been authors, not only viewers. They
made placemarks, paths and polygons, folders of My Places, image
overlays, 3D models, tours and network links, and shared their
knowledge as KML. These users need a desktop place where their work
keeps living and grows into GIS.

PlanetX is that place inside QGIS - a free 3D globe in Python under
GPL 3. It reads and writes what Google Earth users made:
- KML and KMZ files from Google Earth open in My Places, KML copied
  from Google Earth pastes in, and tours recorded in PlanetX play in
  Google Earth;
- folders and radio folders, styles and icons, placemark views
  (LookAt), TimeStamp and TimeSpan on a time slider, Region with
  distance hiding;
- ground, screen and photo overlays, Collada, glTF and OBJ models,
  gx:Track tracks and gx:Tour tours, network links with refresh;
- placemark editing on the globe, a ruler and an elevation profile
  along the terrain, tours with captions and MP4 recording.

Beyond Google Earth, the same placemarks meet the QGIS project and
open Earth data:
- the layers of the QGIS project on the globe, and globe data back to
  the project as layers;
- about 90 open data layers - Macrostrat geology, GLiM lithology,
  gravity and magnetic anomalies, seafloor age, heat flow, plates and
  active faults, ISC-GEM earthquakes since 1904, JRC water, SoilGrids,
  ESA WorldCover;
- a cutaway of the Earth with the CRUST1.0 crust, Slab2 slabs and
  earthquake foci, boreholes and geological models under transparent
  ground;
- Sentinel-2, Landsat since 1972, ASTER and MODIS of an area into the
  QGIS project;
- an AI assistant that makes placemarks from a description and runs
  the plugin actions.

- Source: https://github.com/Valery35/planetx
- QGIS catalogue: https://plugins.qgis.org/plugins/planetx/
- Site with screenshots:
  https://www.informpp.ru/главная-страница/qgis-planetx

PlanetX already uses your work. The sea depths of the globe come from
your COG copy of the GEBCO 2026 Grid on Source Cooperative:
https://source.coop/giswqs/gebco-bathymetry
GEBCO itself gives the grid only as an archive, so your copy makes
this possible.

The RustGIS roadmap names "3D: full scenes with terrain, beyond the
globe and 2.5D extrusion" as a next step:
https://github.com/opengeos/rustgis/blob/main/ROADMAP.md
PlanetX has this part working - terrain with level of detail,
camera-relative coordinates without jitter at street level, 3D
buildings and models, tours and a time slider, and the Google Earth
kind of authoring on top of it. Our plan is to keep PlanetX in Python
for QGIS and later build a light version in Rust. The same work could
become the 3D scene of RustGIS and give Google Earth users a second
home there - as a crate or as a WebAssembly plugin, whichever fits
your architecture. I know the ArcGIS Pro way of work that RustGIS
follows, so the scene could match its ribbon and commands.

I am also ready to take part with our professional tools and ideas:
- interpolation - Isoliner, grids by kriging and other methods and
  isolines: https://plugins.qgis.org/plugins/grid_isolines/
- topography processing - Topoliner, generalization and topology of
  contours: https://plugins.qgis.org/plugins/topoliner/
- geological models - Isoliner3D, surfaces, grids and boreholes in 3D:
  https://plugins.qgis.org/plugins/isoliner3d/

Three questions:
1. Would you be interested in a 3D scene for RustGIS built from
   PlanetX, with the Google Earth kind of placemarks, tours and KML?
   If yes, which form would you prefer - a crate or a plugin?
2. Would our interpolation, topography and geological model tools be
   useful in RustGIS?
3. Will the GEBCO copy stay at its address on Source Cooperative? The
   plugin takes it by default, and I would like to credit you and the
   copy correctly.

Valery Hronusov, PhD (Valery35)
PlanetX, Inform++ LLC
https://github.com/Valery35/planetx
