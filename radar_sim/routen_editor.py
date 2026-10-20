"""Drei gekoppelte Projektionen EINER räumlichen Flugroute, ohne OpenGL."""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                            QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox, QSplitter)

from .route import MAX_ROUTENPUNKTE, GezeichneteRoute, berechne_routendaten, routen_position_3d, punkt_auf_route
from .routen_zeichnen import ZeichenAnsicht
from .regler import ParameterRegler
from .parametergrenzen import ParameterBereich
from .antenne import Antenne, keulenlinien
from .flugbahn import flugbahn_punkte

PROJEKTIONEN = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}


def punkte_3d(route: GezeichneteRoute) -> np.ndarray:
    p = np.asarray(route.punkte, dtype=float)
    return np.column_stack((p[:, 0], np.zeros(len(p)), p[:, 1])) if p.shape[1] == 2 else p.copy()


class RoutenGriffe(pg.ScatterPlotItem):
    """Einen Stützpunkt mit der Maus verschieben; die dritte Koordinate bleibt gleich."""

    def __init__(self, callback):
        super().__init__(size=11, brush="#ff85b0", pen=pg.mkPen("white", width=1))
        self.callback = callback
        self.index = None
        self.verschieben_erlaubt = False
        self.setZValue(20)

    def mouseDragEvent(self, event) -> None:
        if not self.verschieben_erlaubt or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        if event.isStart():
            treffer = self.pointsAt(event.buttonDownPos())
            self.index = int(treffer[0].data()) if treffer else None
        if self.index is None:
            event.ignore()
            return
        event.accept()
        p = event.pos()
        self.callback(self.index, float(p.x()), float(p.y()), event.isFinish())
        if event.isFinish():
            self.index = None

    def mouseClickEvent(self, event) -> None:
        # Auch über einem Griff erreichen Klicks den gemeinsamen Zeichenbereich.
        event.ignore()


class RoutenEditor(QWidget):
    route_geaendert = pyqtSignal(object)  # gültiger Entwurf oder None bei fehlerhafter Geometrie
    bearbeiten = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.punkte = np.empty((0, 3))
        self.aktiv = False
        self._aktualisiere = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        toolbar = QHBoxLayout()
        self.edit_button = QPushButton("Route bearbeiten")
        self.edit_button.clicked.connect(self.bearbeiten.emit)
        toolbar.addWidget(self.edit_button)
        self.linie_button = QPushButton("Punkte setzen")
        self.linie_button.setCheckable(True)
        self.linie_button.setToolTip("Pro Linksklick genau einen Stützpunkt an die Route anhängen. Die dritte Koordinate wird vom letzten Punkt übernommen. Mit Punkte fertig zum Verschieben wechseln. Rechtsklick auf die Kurve fügt gezielt einen Punkt ein.")
        self.linie_button.toggled.connect(self._zeichenmodus)
        toolbar.addWidget(self.linie_button)
        self.neu_button = QPushButton("Neue Route")
        self.neu_button.setToolTip("Den Entwurf leeren und eine neue Route Punkt für Punkt beginnen. Abbrechen stellt die bisherige Simulation wieder her.")
        self.neu_button.clicked.connect(self._neue_route)
        toolbar.addWidget(self.neu_button)
        toolbar.addWidget(QLabel("Start-Z / m"))
        self.starthoehe = QDoubleSpinBox()
        self.starthoehe.setRange(1, 10000)
        self.starthoehe.setValue(300)
        self.starthoehe.setToolTip("Höhe einer ganz neuen, in XY gezeichneten Route. Bei vorhandenen Routen bleibt Z erhalten. In XZ und YZ zeichnest du die Höhe direkt.")
        self.hoehen_regler = ParameterRegler(self.starthoehe, ParameterBereich(1, 10000))
        self.hoehen_regler.setMaximumWidth(200)
        toolbar.addWidget(self.hoehen_regler)
        toolbar.addStretch()
        self.hinweis = QLabel("Route bearbeiten wählen oder unter Flug eine eigene Route beginnen.")
        self.hinweis.setWordWrap(True)
        self.hinweis.setMaximumWidth(420)
        toolbar.addWidget(self.hinweis)
        layout.addLayout(toolbar)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        self.graphs = pg.GraphicsLayoutWidget()
        self.graphs.setBackground("#101a29")
        splitter.addWidget(self.graphs)
        self.plots, self.ansichten, self.kurven, self.griffe = {}, {}, {}, {}
        self.keulen, self.positionen, self.radar_markierungen = {}, {}, {}
        for name, (a, b) in PROJEKTIONEN.items():
            view = ZeichenAnsicht()
            row, col = ((0, 0) if name == "XY" else (0, 1) if name == "XZ" else (1, 0))
            plot = self.graphs.addPlot(row=row, col=col, colspan=2 if name == "YZ" else 1,
                                      title=f"{name} · bekannte Flugroute", viewBox=view)
            plot.setLabel("bottom", name[0], units="m")
            plot.setLabel("left", name[1] + (" · Höhe über Radar" if b == 2 else ""), units="m")
            plot.showGrid(x=True, y=True, alpha=.12)
            plot.addLine(x=0, pen=pg.mkPen("#344960"))
            plot.addLine(y=0, pen=pg.mkPen("#344960"))
            self.radar_markierungen[name] = plot.plot([0], [0], pen=None, symbol="t1", symbolBrush="#ffbd59", symbolSize=13)
            plot.setToolTip("Dieselbe 3D-Route als Projektion. Punkte setzen: ein Linksklick je Stützpunkt. Punkte fertig: Griffe verschieben. Rechtsklick nahe der Kurve fügt einen Stützpunkt ein. Die Keule ist ebenfalls projiziert, kein Ebenenschnitt.")
            self.keulen[name] = plot.plot(pen=pg.mkPen("#c49b48", width=1), fillLevel=None)
            self.kurven[name] = plot.plot(pen=pg.mkPen("#59dcd0", width=2))
            self.positionen[name] = plot.plot(pen=None, symbol="o", symbolBrush="#ffffff", symbolSize=10)
            griffe = RoutenGriffe(lambda i, x, y, fertig, n=name: self._punkt_verschieben(n, i, x, y, fertig))
            plot.addItem(griffe)
            view.punkt_gesetzt.connect(lambda p, n=name: self._punkt_setzen(n, p))
            view.punkt_einfuegen.connect(lambda p, n=name: self._punkt_einfuegen(n, p))
            self.plots[name], self.ansichten[name], self.griffe[name] = plot, view, griffe
        self.tabelle = QTableWidget(0, 3)
        self.tabelle.setHorizontalHeaderLabels(["X / m", "Y / m", "Z / m"])
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabelle.setMinimumWidth(230)
        self.tabelle.setMaximumWidth(320)
        self.tabelle.setToolTip(f"Alle Ansichten verwenden dieselben Stützpunkte. Zahlen per Doppelklick ändern. Z muss über null bleiben. Höchstens {MAX_ROUTENPUNKTE} Punkte.")
        self.tabelle.itemChanged.connect(self._tabellenwert)
        splitter.addWidget(self.tabelle)
        splitter.setSizes([1050, 250])
        self.stop()

    def begin(self, route: GezeichneteRoute | None, reichweite_m: float) -> None:
        self.aktiv = True
        self.edit_button.setEnabled(False)
        self.linie_button.setEnabled(True)
        self.neu_button.setEnabled(True)
        self.hoehen_regler.setEnabled(True)
        self.tabelle.setEnabled(True)
        self.punkte = punkte_3d(route) if route is not None else np.empty((0, 3))
        if route is None:
            for name, plot in self.plots.items():
                plot.setRange(xRange=(-reichweite_m, reichweite_m),
                              yRange=(0, max(100, reichweite_m*.3)) if name.endswith("Z") else (-reichweite_m, reichweite_m), padding=.02)
        for plot in self.plots.values():
            plot.disableAutoRange()  # Beim Ziehen darf das Koordinatensystem nicht mitwandern.
        self.linie_button.setChecked(route is None)
        self._zeichenmodus(self.linie_button.isChecked())
        self._zeige_punkte(True)

    def stop(self) -> None:
        self.aktiv = False
        self.linie_button.setChecked(False)
        self.linie_button.setEnabled(False)
        self.neu_button.setEnabled(False)
        self.hoehen_regler.setEnabled(False)
        self.tabelle.setEnabled(False)
        self.edit_button.setEnabled(True)
        self._zeichenmodus(False)
        self._szene = object()  # Ein verworfener Entwurf darf nicht als Flugroute stehen bleiben.

    def _zeichenmodus(self, zeichnen: bool) -> None:
        self.linie_button.setText("Punkte fertig" if zeichnen else "Punkte setzen")
        for name, view in self.ansichten.items():
            view.zeichnen = self.aktiv and zeichnen
            view.bearbeiten = self.aktiv
            view.setMenuEnabled(not self.aktiv)
            self.griffe[name].setVisible(self.aktiv)
            self.griffe[name].verschieben_erlaubt = self.aktiv and not zeichnen

    def _neue_route(self) -> None:
        if not self.aktiv:
            return
        self.punkte = np.empty((0, 3))
        self.linie_button.setChecked(True)
        self._zeige_punkte(True)

    def _punkt_setzen(self, name: str, punkt) -> None:
        if not self.aktiv or not self.linie_button.isChecked():
            return
        if len(self.punkte) >= MAX_ROUTENPUNKTE:
            self.hinweis.setText(f"Höchstens {MAX_ROUTENPUNKTE} Stützpunkte. Vorhandene Punkte verschieben.")
            return
        neu = self.punkte[-1].copy() if len(self.punkte) else np.array([0., 0., self.starthoehe.value()])
        a, b = PROJEKTIONEN[name]
        neu[a], neu[b] = punkt
        if len(self.punkte) and np.linalg.norm(neu-self.punkte[-1]) < .05:
            self.hinweis.setText("Der nächste Punkt braucht mindestens 5 cm Abstand.")
            return
        self.punkte = np.vstack((self.punkte, neu))
        self._zeige_punkte(True)

    def _punkt_einfuegen(self, name: str, punkt) -> None:
        if not self.aktiv or len(self.punkte) < 2:
            return
        if len(self.punkte) >= MAX_ROUTENPUNKTE:
            self.hinweis.setText(f"Höchstens {MAX_ROUTENPUNKTE} Stützpunkte. Vorhandene Punkte verschieben.")
            return
        try:
            route = self.entwurf()
            view = self.ansichten[name]
            ursprung = view.mapViewToScene(QPointF(0., 0.))
            dx = view.mapViewToScene(QPointF(1., 0.))-ursprung
            dy = view.mapViewToScene(QPointF(0., 1.))-ursprung
            massstab = (np.hypot(dx.x(), dx.y()), np.hypot(dy.x(), dy.y()))
            sichtbare_punkte = self.punkte[:, list(PROJEKTIONEN[name])]
            if np.min(np.linalg.norm((sichtbare_punkte-punkt)*massstab, axis=1)) <= 7:
                self.hinweis.setText("Hier liegt bereits ein Stützpunkt. Diesen Griff verschieben.")
                return
            abschnitt, neu, abstand = punkt_auf_route(route, PROJEKTIONEN[name], punkt, massstab)
            if abstand > 10:
                self.hinweis.setText("Zum Einfügen direkt auf die Fluglinie rechtsklicken (höchstens 10 Pixel Abstand).")
                return
            if np.min(np.linalg.norm(self.punkte-neu, axis=1)) < .05:
                self.hinweis.setText("An dieser Stelle liegt bereits ein Stützpunkt.")
                return
            self.punkte = np.insert(self.punkte, abschnitt+1, neu, axis=0)
            self._zeige_punkte(True)
        except ValueError as exc:
            self.hinweis.setText(str(exc))

    def _punkt_verschieben(self, name: str, index: int, x: float, y: float, fertig: bool) -> None:
        if self.aktiv:
            a, b = PROJEKTIONEN[name]
            self.punkte[index, a], self.punkte[index, b] = x, y
            self._zeige_punkte(fertig)

    def _tabellenwert(self, item) -> None:
        if self._aktualisiere or not self.aktiv:
            return
        try:
            wert = float(item.text().replace(",", "."))
            if not np.isfinite(wert):
                raise ValueError("Eine endliche Zahl eingeben.")
            self.punkte[item.row(), item.column()] = wert
            self._zeige_punkte(True)
        except ValueError as exc:
            self.hinweis.setText(str(exc))
            self.route_geaendert.emit(None)

    def _zeige_punkte(self, fertig: bool) -> None:
        self._aktualisiere = True
        try:
            self.tabelle.setRowCount(len(self.punkte))
            for i, punkt in enumerate(self.punkte):
                for j, wert in enumerate(punkt):
                    self.tabelle.setItem(i, j, QTableWidgetItem(f"{wert:.6f}"))
            for name, (a, b) in PROJEKTIONEN.items():
                self.griffe[name].setData(pos=self.punkte[:, [a, b]], data=np.arange(len(self.punkte)))
                self.kurven[name].setData(self.punkte[:, a], self.punkte[:, b])
            if len(self.punkte) < 2:
                self.hinweis.setText(f"{len(self.punkte)} Punkt(e) · Linksklick setzt einen Punkt. Mindestens zwei sind nötig.")
                if fertig:
                    self.route_geaendert.emit(None)
                return
            route = self.entwurf()
            daten = berechne_routendaten(route)
            kurve = np.array([routen_position_3d(route, float(t))[:3]
                              for t in np.linspace(0, daten.laenge_m, max(250, 4*len(self.punkte)))])
            for name, (a, b) in PROJEKTIONEN.items():
                self.kurven[name].setData(kurve[:, a], kurve[:, b])
            self.hinweis.setText(f"{len(self.punkte)} Stützpunkte · {daten.laenge_m:.1f} m · Linksklick: anhängen im Modus Punkte setzen. Rechtsklick auf die Kurve: einfügen.")
            if fertig:
                self.route_geaendert.emit(route)
        except ValueError as exc:
            self.hinweis.setText(str(exc))
            if fertig:
                self.route_geaendert.emit(None)
        finally:
            self._aktualisiere = False

    def entwurf(self) -> GezeichneteRoute:
        """Gemeinsame Geometrie mit Hilfstempo 1; das Flugtempo setzt die GUI."""
        return GezeichneteRoute(tuple(map(tuple, self.punkte.tolist())), 1.)

    def zeige_szene(self, szene, zustaende, antenne: Antenne, traeger_hz: float, radar_zustand=None) -> None:
        if self.aktiv:
            return
        if szene != getattr(self, "_szene", None):
            route = szene.bahnen[0].route if szene is not None else None
            self.punkte = punkte_3d(route) if route is not None else np.empty((0, 3))
            self._zeige_punkte(False)
            for name, (a, b) in PROJEKTIONEN.items():
                x, y = [], []
                if szene is not None:
                    for bahn in szene.bahnen + ((szene.radar_bahn,) if szene.radar_bahn else ()):
                        p = flugbahn_punkte(bahn, szene.dauer_s)
                        x.extend([*p[:, a], np.nan]); y.extend([*p[:, b], np.nan])
                self.kurven[name].setData(x, y, connect="finite")
                self.plots[name].enableAutoRange()
            self._szene = szene
        for name, (a, b) in PROJEKTIONEN.items():
            self.positionen[name].setData([z.position_m[a] for z in zustaende], [z.position_m[b] for z in zustaende])
        self.zeige_antenne(antenne, traeger_hz)
        ort = np.array(radar_zustand.position_m if radar_zustand else (0., 0., 0.))
        self._radarort = ort
        p = self._keulenlokal+ort
        for name, (a, b) in PROJEKTIONEN.items():
            self.radar_markierungen[name].setData([ort[a]], [ort[b]])
            self.keulen[name].setData(p[:, a], p[:, b], connect="finite")
            self.plots[name].setLabel("left", name[1] + (" · Höhe über Boden" if b == 2 else ""), units="m")

    def zeige_antenne(self, antenne: Antenne, traeger_hz: float) -> None:
        if (antenne, traeger_hz) == getattr(self, "_antenne", None):
            return
        p = keulenlinien(antenne, traeger_hz)
        self._keulenlokal = p
        p = p + getattr(self, "_radarort", np.zeros(3))
        for name, (a, b) in PROJEKTIONEN.items():
            self.keulen[name].setData(p[:, a], p[:, b], connect="finite")
        self._antenne = (antenne, traeger_hz)
