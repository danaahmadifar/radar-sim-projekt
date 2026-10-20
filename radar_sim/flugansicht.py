"""Räumliche Flugansicht mit NumPy-Projektion und pyqtgraph, ohne OpenGL.

Die Simulation liefert XYZ in Metern. Für den Bildschirm projizieren wir diese
Punkte auf zwei senkrechte Kameravektoren. Das ist eine orthografische Ansicht:
Es gibt keine perspektivische Verkleinerung und keine Überhöhung der Z-Achse.
Diese Darstellung zeigt bekannte Simulationswerte, keine Radar-Winkelschätzung.
"""

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
import pyqtgraph as pg


def projiziere(punkte: np.ndarray, azimut: float, elevation: float) -> np.ndarray:
    """XYZ-Array [N,3] in m → Bildschirmkoordinaten [N,2] in m.

    Kamerawinkel in Grad. Die beiden Einheitsvektoren sind orthogonal; X, Y
    und Z behalten denselben räumlichen Maßstab. Die sichtbare Verkürzung
    entsteht allein durch den Blickwinkel. NaN trennt Liniensegmente.
    """
    a, e = np.deg2rad([azimut, elevation])
    rechts = [-np.sin(a), np.cos(a), 0.]
    oben = [-np.sin(e)*np.cos(a), -np.sin(e)*np.sin(a), np.cos(e)]
    return np.asarray(punkte, dtype=float).reshape(-1, 3) @ np.array([rechts, oben]).T


class RaumViewBox(pg.ViewBox):
    gedreht = pyqtSignal(float, float)
    zuruecksetzen = pyqtSignal()

    def __init__(self) -> None:
        super().__init__(enableMenu=False)
        self.setAspectLocked(True)
        self.disableAutoRange()

    def mouseDragEvent(self, event, axis=None) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            delta = event.pos() - event.lastPos()
            self.gedreht.emit(float(delta.x())*.4, float(delta.y())*.3)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            # Verschieben statt des normalen Rechtszieh-Zooms von pyqtgraph.
            delta = self.mapToView(event.pos()) - self.mapToView(event.lastPos())
            self.translateBy(x=-delta.x(), y=-delta.y())
            event.accept()
        else:
            super().mouseDragEvent(event, axis=axis)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.zuruecksetzen.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)


class FlugAnsicht(pg.PlotItem):
    """Wiederverwendete Plot-Elemente; pro Frame ändern sich nur Target-Punkte."""

    def __init__(self) -> None:
        ansicht = RaumViewBox()
        super().__init__(viewBox=ansicht, title="Flugbahn · XYZ")
        self.azimut = -45.
        self.elevation = 25.
        # Zu jedem Linien-/Punktobjekt speichern wir seine ursprünglichen XYZ.
        self.geometrie: dict[pg.PlotDataItem, np.ndarray] = {}
        self.rahmen_objekte: set[pg.PlotDataItem] = set()
        self.fokus_objekte: list[pg.PlotDataItem] = []
        self.achsen_texte: list[pg.TextItem] = []
        self.achsen_daten: list[tuple[pg.PlotDataItem, np.ndarray]] = []
        self.text_positionen: list[np.ndarray] = []
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.hideButtons()
        self.addLegend(offset=(8, 8), labelTextSize="9pt")
        self.setToolTip(
            "Räumliche Ansicht der bekannten Flugbahn: X und Y am Boden, Z = Höhe über Boden; "
            "alle Koordinaten in Metern. Links ziehen: drehen. Mausrad: zoomen. "
            "Rechts ziehen: verschieben. Doppelklick: Ausgangsansicht. "
            "Gelb: Einweg-Halbwertskeule (−3 dB relativ zur Hauptachse); "
            "ihre Zeichenlänge ist keine Reichweitengrenze. Keine Winkelschätzung."
        )
        ansicht.gedreht.connect(self.drehen)
        ansicht.zuruecksetzen.connect(self.zuruecksetzen)

    def setze_punkte(self, objekt: pg.PlotDataItem, punkte, rahmen: bool = True) -> None:
        """Originalpunkte [N,3] speichern und projizieren; rahmen steuert Auto-Fit."""
        p = np.asarray(punkte, dtype=float).reshape(-1, 3)
        self.geometrie[objekt] = p
        if rahmen:
            self.rahmen_objekte.add(objekt)
        else:
            self.rahmen_objekte.discard(objekt)
        bild = projiziere(p, self.azimut, self.elevation)
        objekt.setData(bild[:, 0], bild[:, 1], connect="finite")

    def entferne(self, objekt: pg.PlotDataItem) -> None:
        self.geometrie.pop(objekt, None)
        self.rahmen_objekte.discard(objekt)
        self.removeItem(objekt)

    def rahmen_aktualisieren(self) -> None:
        """Achsen/Bodenraster nur bei geänderter Flugbahn oder Keule aufbauen."""
        for objekt, _ in self.achsen_daten:
            self.removeItem(objekt)
        for text in self.achsen_texte:
            self.removeItem(text)
        self.achsen_daten.clear()
        self.achsen_texte.clear()
        self.text_positionen.clear()
        objekte = self.fokus_objekte or self.rahmen_objekte
        daten = np.vstack([np.zeros((1, 3)), *[self.geometrie[o] for o in objekte]])
        daten = daten[np.isfinite(daten).all(axis=1)]
        unten, oben = daten.min(axis=0), daten.max(axis=0)
        groesse = max(float(np.max(oben-unten)), 100.)
        # Auch bei einer geraden Flugbahn bleiben alle drei Achsen sichtbar.
        unten[:2] = np.minimum(unten[:2], -groesse*.12)
        oben = np.maximum(oben, groesse*.22)
        self.grenzen = np.array([unten, oben])

        def linie(punkte, farbe, breite=1):
            objekt = self.plot(pen=pg.mkPen(farbe, width=breite))
            self.achsen_daten.append((objekt, np.asarray(punkte)))
            objekt.setZValue(-10)

        def text(ort, inhalt, farbe, gross=False):
            objekt = pg.TextItem(inhalt, color=farbe, anchor=(.5, 0), fill="#101a29")
            if gross:
                font = objekt.textItem.font()
                font.setBold(True)
                font.setPointSize(11)
                objekt.setFont(font)
            self.addItem(objekt)
            self.achsen_texte.append(objekt)
            self.text_positionen.append(np.asarray(ort, dtype=float))

        # Ein gemeinsamer Rasterabstand in Metern macht Größen vergleichbar.
        ziel = groesse/5
        basis = 10**np.floor(np.log10(ziel))
        schritt = next(f for f in (1, 2, 5, 10) if f*basis >= ziel)*basis
        for achse in (0, 1):
            for wert in np.arange(np.ceil(unten[achse]/schritt), np.floor(oben[achse]/schritt)+1)*schritt:
                p = np.zeros((2, 3))
                p[:, achse] = wert
                p[:, 1-achse] = [unten[1-achse], oben[1-achse]]
                linie(p, "#2c3b4b")
        for achse, (name, farbe) in enumerate(zip(("X [m]", "Y [m]", "Z · Höhe [m]"),
                                                 ("#ff8f8f", "#83dfa1", "#91baff"))):
            p = np.zeros((2, 3))
            p[:, achse] = [unten[achse], oben[achse]*1.2]
            linie(p, farbe, 2)
            text(p[1], name, farbe, True)
            # Zahlen liegen auf den räumlichen Achsen, nicht auf Bildschirmachsen.
            for wert in np.arange(np.ceil(unten[achse]/schritt), np.floor(oben[achse]/schritt)+1)*schritt:
                if wert != 0:
                    ort = np.zeros(3)
                    ort[achse] = wert
                    text(ort, f"{wert:g}", farbe)
        text([0, 0, 0], "0", "#deE8f5")
        self._neu_projizieren()
        self.einpassen()

    def _neu_projizieren(self) -> None:
        for objekt, punkte in list(self.geometrie.items()) + self.achsen_daten:
            bild = projiziere(punkte, self.azimut, self.elevation)
            objekt.setData(bild[:, 0], bild[:, 1], connect="finite")
        if self.text_positionen:
            bild = projiziere(np.array(self.text_positionen), self.azimut, self.elevation)
            for text, ort in zip(self.achsen_texte, bild):
                text.setPos(*ort)

    def einpassen(self) -> None:
        if not self.achsen_daten:
            return
        if self.fokus_objekte:
            # Die Route bestimmt den Blick, nicht die frei wählbare Keulenlänge.
            # In der begrenzenden Bildschirmrichtung nimmt sie etwa 60 % ein.
            punkte = np.vstack([self.geometrie[o] for o in self.fokus_objekte])
            bild = projiziere(punkte, self.azimut, self.elevation)
            mitte = (bild.min(axis=0)+bild.max(axis=0))/2
            spanne = np.maximum(np.ptp(bild, axis=0), 1.)/.6
            self.setRange(xRange=(mitte[0]-spanne[0]/2, mitte[0]+spanne[0]/2),
                          yRange=(mitte[1]-spanne[1]/2, mitte[1]+spanne[1]/2), padding=0)
            return
        # Einpassen einschließlich aller räumlichen Achsen, ohne NaN-Trennstellen.
        punkte = np.vstack([*[self.geometrie[o] for o in self.rahmen_objekte],
                            *[p for _, p in self.achsen_daten], self.text_positionen])
        bild = projiziere(punkte[np.isfinite(punkte).all(axis=1)], self.azimut, self.elevation)
        self.setRange(xRange=(float(bild[:, 0].min()), float(bild[:, 0].max())),
                      yRange=(float(bild[:, 1].min()), float(bild[:, 1].max())), padding=.12)

    def drehen(self, delta_azimut: float, delta_elevation: float) -> None:
        self.azimut = (self.azimut + delta_azimut) % 360
        self.elevation = float(np.clip(self.elevation + delta_elevation, 5, 85))
        self._neu_projizieren()

    def zuruecksetzen(self) -> None:
        self.azimut, self.elevation = -45., 25.
        self._neu_projizieren()
        self.einpassen()
