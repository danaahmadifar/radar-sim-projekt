"""Klassisches Polar-Pattern, ergänzend kartesische Schnitte und Winkelkarte."""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox, QTabWidget
from .antenne import Antenne, ANTENNENTYPEN
from .antennendiagramm import berechne_diagramm, relative_db, polarschnitte
from .polardiagramm import PolarDiagramm


class AntennenAnsicht(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setToolTip("Vorschau der aktuellen Eingaben, unabhängig vom zuletzt berechneten Frame. Alle Winkel sind relativ zur Antennenachse. 0 dB bedeutet gleiche Leistung wie auf der Hauptachse, keine absolute Verstärkung in dBi. Die Keulenlänge beeinflusst dieses Diagramm nicht. Fernfeldmodell: keine Nahfeld-, Polarisations-, Kopplungs- oder Verlustberechnung.")
        layout.addWidget(self.info)
        self.ansichten = QTabWidget()
        layout.addWidget(self.ansichten, 1)
        self._baue_polaransicht()
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.ansichten.addTab(details, "Details · Schnitte und Karte")
        self.ganze_schnitte = QCheckBox("Gesamte Winkelschnitte zeigen (Azimut ±180°, Elevation ±90°)")
        self.ganze_schnitte.setToolTip("Sonst zoomt die Ansicht auf die Hauptkeule und die ersten Nebenkeulen. Die Winkelkarte zeigt immer diesen Ausschnitt; das Array besitzt weitere Nebenkeulen.")
        detail_layout.addWidget(self.ganze_schnitte)
        self.grafik = pg.GraphicsLayoutWidget()
        self.grafik.setBackground("#101a29")
        detail_layout.addWidget(self.grafik, 1)
        self.schnitte = []
        self.kurven = []
        for spalte, name in enumerate(("Azimut", "Elevation")):
            plot = self.grafik.addPlot(row=0, col=spalte, title=f"{name}-Schnitt · anderer Winkel = 0°")
            plot.setLabel("bottom", f"Lokaler {name}", units="°")
            plot.setLabel("left", "Leistung / Achsenleistung", units="dB")
            plot.showGrid(x=True, y=True, alpha=.15)
            plot.addLegend(offset=(8, 8))
            plot.addItem(pg.InfiniteLine(pos=10*np.log10(.5), angle=0,
                                        pen=pg.mkPen("#8593a6", style=Qt.PenStyle.DotLine)))
            einweg = plot.plot(pen=pg.mkPen("#59dcd0", width=2), name="Einweg · G")
            zweiweg = plot.plot(pen=pg.mkPen("#ffbd59", width=2, style=Qt.PenStyle.DashLine), name="Radar Zweiweg · G²")
            plot.setToolTip("Einweg: 10 log10(G), Radar-Zweiweg: 10 log10(G²). Die gepunktete Linie liegt bei −3,0103 dB. Nullstellen und schwache Pegel werden nur zur Anzeige bei −60 dB begrenzt. Die volle Halbwertsbreite wird aus dem linearen Modell berechnet.")
            self.schnitte.append(plot)
            self.kurven.append((einweg, zweiweg))
        self.kartenplot = self.grafik.addPlot(row=1, col=0, colspan=2, title="Einweg-Pattern · Winkelkarte um die Hauptachse")
        self.kartenplot.setLabel("bottom", "Lokaler Azimut", units="°")
        self.kartenplot.setLabel("left", "Lokale Elevation", units="°")
        self.kartenplot.setToolTip("Winkelkarte G(Azimut, Elevation), keine XY-Projektion. Beide Winkel sind relativ zur Antennenachse. Feste Anzahl Winkelzellen; sehr schmale Nebenkeulen können im Raster fehlen. Die Keulengrenze in der Flugansicht stammt aus demselben linearen Modell.")
        self.bild = pg.ImageItem(axisOrder="row-major")
        self.kartenplot.addItem(self.bild)
        self.farbskala = pg.ColorBarItem(values=(-60, 0), colorMap=pg.colormap.get("viridis"),
                                       label="10 log10(G), Achse = 0 dB", interactive=False)
        self.farbskala.setImageItem(self.bild, insert_in=self.kartenplot)
        self.ganze_schnitte.toggled.connect(self._setze_bereiche)
        self.daten = None

    def _baue_polaransicht(self) -> None:
        seite = QWidget()
        layout = QVBoxLayout(seite)
        layout.setContentsMargins(0, 0, 0, 0)
        optionen = QHBoxLayout()
        optionen.addWidget(QLabel("dB-Untergrenze"))
        self.db_grenze = QComboBox()
        for grenze in (-15, -30, -45, -60):
            self.db_grenze.addItem(f"{grenze} dB", grenze)
        self.db_grenze.setCurrentIndex(1)
        self.db_grenze.setToolTip("Außenkreis = 0 dB. Die gewählte Untergrenze liegt im Zentrum. Schwächere Werte werden nur zur Darstellung darauf begrenzt; die Antenne bleibt unverändert.")
        optionen.addWidget(self.db_grenze)
        self.zweiweg = QCheckBox("Radar-Zweiweg zusätzlich zeigen")
        self.zweiweg.setToolTip("Gestrichelte Kurven: relative Echoleistung G² bei derselben Sende- und Empfangsantenne. Durchgezogen: Einweg-Leistung G.")
        optionen.addWidget(self.zweiweg)
        optionen.addStretch()
        layout.addLayout(optionen)
        self.polar_grafik = pg.GraphicsLayoutWidget()
        self.polar_grafik.setBackground("#101a29")
        self.polarplot = PolarDiagramm()
        self.polar_grafik.addItem(self.polarplot)
        layout.addWidget(self.polar_grafik, 1)
        self.ansichten.addTab(seite, "Polar")
        self.db_grenze.currentIndexChanged.connect(lambda: self.polarplot.setze_untergrenze(self.db_grenze.currentData()))
        self.zweiweg.toggled.connect(self.polarplot.zeige_zweiweg)

    def zeige_antenne(self, a: Antenne, traeger_hz: float) -> None:
        self.daten = d = berechne_diagramm(a, traeger_hz)
        self.polarplot.zeige_daten(*polarschnitte(a, traeger_hz, d))
        for kurven, winkel, leistung in zip(self.kurven, (d.azimut, d.elevation), (d.leistung_az, d.leistung_el)):
            kurven[0].setData(winkel, relative_db(leistung))
            kurven[1].setData(winkel, relative_db(leistung**2))
        self.bild.setImage(relative_db(d.karte), autoLevels=False)
        dx, dy = d.karten_az[1]-d.karten_az[0], d.karten_el[1]-d.karten_el[0]
        rechteck = QRectF(d.karten_az[0]-dx/2, d.karten_el[0]-dy/2,
                         dx*len(d.karten_az), dy*len(d.karten_el))
        self.bild.setRect(rechteck)
        self.kartenplot.setRange(rect=rechteck, padding=0)
        self._setze_bereiche()
        wellenlaenge = 299_792_458 / traeger_hz
        def breite(wert: float | None) -> str:
            return "nicht definiert" if wert is None else f"{wert:.5g}°"
        details = "Idealer Vergleich ohne Richtwirkung."
        if a.typ == "patch_array":
            details = f"{a.elemente_horizontal} × {a.elemente_vertikal} Elemente, Abstand λ/2 = {wellenlaenge/2*1000:.4g} mm. Gleichphasig, gleich stark; vereinfachtes cos²-Element, keine Rückkeule."
        elif a.typ == "parabol":
            details = f"D = {a.durchmesser_m:g} m; β ≈ 70 λ/D in Grad. Gauß-Hauptkeule; reale Neben- und Rückkeulen fehlen."
            if a.durchmesser_m / wellenlaenge < 5:
                details += " Achtung: D ist nicht groß gegenüber λ; die schmale Reflektor-Hauptkeule ist hier keine belastbare Näherung."
        elif a.typ == "faecher":
            details = "Gauß-Hauptkeule mit vorgegebenen Halbwertsbreiten; reale Neben- und Rückkeulen fehlen."
        self.info.setText(f"{ANTENNENTYPEN[a.typ]} · fc = {traeger_hz/1e9:g} GHz · λ = {wellenlaenge*1000:.5g} mm\n"
                          f"Einweg-Halbwertsbreite: Azimut {breite(d.breite_az)}, Elevation {breite(d.breite_el)}. "
                          f"Ausrichtung im Raum: Azimut {a.azimut_grad:g}°, Elevation {a.elevation_grad:g}°.\n{details}")

    def _setze_bereiche(self) -> None:
        if self.daten is None:
            return
        for plot, voller_winkel, kartenwinkel in zip(self.schnitte, (180, 90), (self.daten.karten_az, self.daten.karten_el)):
            grenze = voller_winkel if self.ganze_schnitte.isChecked() else kartenwinkel[-1]
            plot.setRange(xRange=(-grenze, grenze), yRange=(-60, 1), padding=0)

    def diagramme(self) -> list[tuple[str, pg.PlotItem]]:
        return [("antenne_polar", self.polarplot), ("antenne_azimut", self.schnitte[0]), ("antenne_elevation", self.schnitte[1]),
                ("antenne_winkelkarte", self.kartenplot)]
