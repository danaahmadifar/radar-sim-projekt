"""Mauseingabe im Flugfeld; die eigentliche Bewegung steht in route.py."""

from PyQt6.QtCore import Qt, pyqtSignal
import pyqtgraph as pg


class ZeichenAnsicht(pg.ViewBox):
    punkt_gesetzt = pyqtSignal(object)  # Ein Linksklick, genau ein Punkt.
    punkt_einfuegen = pyqtSignal(object)  # Rechtsklick nahe der vorhandenen Kurve.

    def __init__(self):
        super().__init__()
        self.zeichnen = False
        self.bearbeiten = False

    def _punkt(self, scene_pos) -> tuple[float, float]:
        p = self.mapSceneToView(scene_pos)
        return float(p.x()), float(p.y())

    def mouseDragEvent(self, event, axis=None) -> None:
        if self.zeichnen and event.button() == Qt.MouseButton.LeftButton:
            # Eine gezogene Mausbewegung setzt bewusst keine zusätzlichen Punkte.
            event.accept()
        else:
            super().mouseDragEvent(event, axis=axis)

    def mouseClickEvent(self, event) -> None:
        if self.zeichnen and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.punkt_gesetzt.emit(self._punkt(event.scenePos()))
        elif self.bearbeiten and event.button() == Qt.MouseButton.RightButton:
            event.accept()
            self.punkt_einfuegen.emit(self._punkt(event.scenePos()))
        else:
            super().mouseClickEvent(event)
