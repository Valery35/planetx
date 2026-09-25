from qgis.PyQt.QtWidgets import QAction, QMessageBox


class PlanetXPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        self.action = QAction("PlanetX", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu("PlanetX", self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removePluginWebMenu("PlanetX", self.action)
            self.action = None

    def run(self):
        QMessageBox.information(
            self.iface.mainWindow(), "PlanetX",
            "PlanetX 0.0.1: заготовка модуля, глобус появится в фазе 0.")
