def classFactory(iface):
    from .plugin import PlanetXPlugin
    return PlanetXPlugin(iface)
