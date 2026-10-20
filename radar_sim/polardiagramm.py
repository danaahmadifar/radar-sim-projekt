"""Klassisches dB-Polardiagramm mit pyqtgraph, ohne weitere Plot-Bibliothek."""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from .antennendiagramm import polarkoordinaten


class PolarDiagramm(pg.PlotItem):
    def __init__(self) -> None:
        super().__init__(title="Normiertes Radiation Pattern · geometrische Hauptschnitte")
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.setAspectLocked(True)
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self.setRange(xRange=(-1.2, 1.2), yRange=(-1.2, 1.2), padding=0)
        self.addLegend(offset=(8, 8))
        self.raster = []
        self.untergrenze_db = -30.
        self.winkel = np.array([])
        self.leistungen = (np.array([]), np.array([]))
        self.kurven = []
        for farbe, name in (("#59dcd0", "Azimut"), ("#ffbd59", "Höhenschnitt")):
            einweg = self.plot(pen=pg.mkPen(farbe, width=2.5), name=f"{name} · Einweg")
            zweiweg = self.plot(pen=pg.mkPen(farbe, width=1.5, style=Qt.PenStyle.DashLine), name=f"{name} · Zweiweg")
            zweiweg.hide()
            self.legend.removeItem(zweiweg)
            self.kurven.append((einweg, zweiweg))
        self.setToolTip("0° ist die Antennenachse, +90° liegt rechts, −90° links, 180° hinten. Außenkreis: 0 dB zur Achsenleistung. Heller Ring: Einweg-Halbwert −3,0103 dB. Innenringe: relative Einweg-Leistung 10 log10(G); optional gestrichelt Zweiweg 10 log10(G²). Pegel unter der gewählten dB-Grenze liegen im Zentrum. Die beiden Kurven sind geometrische Hauptschnitte; eine E-/H-Ebenenzuordnung erfordert ein Polarisationsmodell.")
        self._zeichne_raster()

    def _text(self, text: str, x: float, y: float) -> None:
        item = pg.TextItem(text, color="#bac8dc", anchor=(.5, .5))
        item.setPos(x, y)
        item.setZValue(2)
        self.addItem(item)
        self.raster.append(item)

    def _linie(self, x, y, halbwert: bool = False) -> None:
        farbe = "#8798b0" if halbwert else "#405169"
        linie = self.plot(x, y, pen=pg.mkPen(farbe, style=Qt.PenStyle.DotLine))
        linie.setZValue(-1)
        self.raster.append(linie)

    def _zeichne_raster(self) -> None:
        for item in self.raster:
            self.removeItem(item)
        self.raster.clear()
        theta = np.linspace(0, 2*np.pi, 721)
        schritt = 5 if self.untergrenze_db >= -30 else 10
        for db in np.arange(0, self.untergrenze_db, -schritt):
            radius = 1 - db / self.untergrenze_db
            self._linie(radius*np.sin(theta), radius*np.cos(theta))
            self._text(f"{db:g} dB", radius/np.sqrt(2), -radius/np.sqrt(2))
        halbwert_radius = 1 - (10*np.log10(.5)) / self.untergrenze_db
        self._linie(halbwert_radius*np.sin(theta), halbwert_radius*np.cos(theta), halbwert=True)
        for grad in range(-150, 181, 30):
            winkel = np.deg2rad(grad)
            self._linie([0, np.sin(winkel)], [0, np.cos(winkel)])
            self._text(f"{grad}°", 1.1*np.sin(winkel), 1.1*np.cos(winkel))
        self._text(f"≤ {self.untergrenze_db:g} dB", 0, -.045)

    def zeige_daten(self, winkel: np.ndarray, horizontal: np.ndarray, vertikal: np.ndarray) -> None:
        self.winkel = winkel
        self.leistungen = (horizontal, vertikal)
        self._aktualisiere_kurven()

    def setze_untergrenze(self, db: float) -> None:
        self.untergrenze_db = db
        self._zeichne_raster()
        self._aktualisiere_kurven()

    def _aktualisiere_kurven(self) -> None:
        for kurven, leistung in zip(self.kurven, self.leistungen):
            kurven[0].setData(*polarkoordinaten(self.winkel, leistung, self.untergrenze_db))
            kurven[1].setData(*polarkoordinaten(self.winkel, leistung**2, self.untergrenze_db))

    def zeige_zweiweg(self, sichtbar: bool) -> None:
        for _, zweiweg in self.kurven:
            if zweiweg.isVisible() != sichtbar:
                zweiweg.setVisible(sichtbar)
                if sichtbar:
                    self.legend.addItem(zweiweg, zweiweg.name())
                else:
                    self.legend.removeItem(zweiweg)
