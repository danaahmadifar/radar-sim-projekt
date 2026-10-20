"""Ein Zahlenfeld, ein Slider und der zugehörige erklärte Wertebereich."""

import math
from PyQt6.QtCore import Qt, QSignalBlocker
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QSpinBox, QSlider, QLabel, QVBoxLayout, QWidget

from .parametergrenzen import ParameterBereich


class CompactDoubleSpinBox(QDoubleSpinBox):
    def textFromValue(self, value: float) -> str:
        return self.locale().toString(value, "g", 12)


def zahlenfeld(unten: float, oben: float, tooltip: str, stellen: int = 12,
               ganz: bool = False, tracking: bool = False) -> QSpinBox | QDoubleSpinBox:
    """Zahlenfeld mit erklärter Einheit; Slider und Rechengrenzen bleiben getrennt."""
    feld = QSpinBox() if ganz else CompactDoubleSpinBox()
    if not ganz:
        feld.setDecimals(stellen)
    feld.setRange(unten, oben)
    feld.setToolTip(tooltip)
    feld.setKeyboardTracking(tracking)
    return feld


def feldwert(feld: QWidget) -> bool | str | float | int:
    """Liest einen Schalter, eine Auswahl oder ein Zahlenfeld einheitlich aus."""
    if isinstance(feld, QCheckBox):
        return feld.isChecked()
    return feld.currentData() if isinstance(feld, QComboBox) else feld.value()


def setze_feldwert(feld: QWidget, wert) -> None:
    """Lädt einen Wert ohne Änderungssignale und ohne unbemerktes Abschneiden."""
    with QSignalBlocker(feld):
        if isinstance(feld, QCheckBox):
            feld.setChecked(wert)
        elif isinstance(feld, QComboBox):
            feld.setCurrentIndex(feld.findData(wert))
        else:
            feld.setRange(min(feld.minimum(), wert), max(feld.maximum(), wert))
            feld.setValue(int(wert) if isinstance(feld, QSpinBox) else wert)


def wertsignal(feld: QWidget):
    """Das Qt-Signal, das zu diesem Eingabetyp gehört."""
    if isinstance(feld, QCheckBox):
        return feld.toggled
    return feld.currentIndexChanged if isinstance(feld, QComboBox) else feld.valueChanged


class ParameterRegler(QWidget):
    """Der Slider wählt nur Werte im berechneten Bereich.

    Direkte Eingaben bleiben sichtbar, auch wenn sie gerade ungültig sind.
    Andere Parameter werden niemals heimlich geklemmt. Die GUI zeigt dann die
    verletzte Bedingung an und verhindert eine ungültige Radarberechnung.
    """

    def __init__(self, spin: QDoubleSpinBox | QSpinBox, bereich: ParameterBereich,
                 logarithmisch: bool = False):
        super().__init__()
        self.spin = spin
        self.bereich = bereich
        self.logarithmisch = logarithmisch
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(spin)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setTracking(True)
        layout.addWidget(self.slider)
        self.anzeige = QLabel()
        self.anzeige.setWordWrap(True)
        self.anzeige.setStyleSheet("font-size: 8pt; color: #9cb0c8;")
        layout.addWidget(self.anzeige)
        self.slider.valueChanged.connect(self._slider_geaendert)
        self.spin.valueChanged.connect(self._zeige_wert)
        self.spin.editingFinished.connect(self._raster_einhalten)
        self.set_bereich(bereich)

    def set_bereich(self, bereich: ParameterBereich) -> None:
        self.bereich = bereich.im_raster()
        self.slider.setEnabled(not self.bereich.leer)
        tooltip = self.spin.toolTip() + "\n\nBereich: " + bereich.hinweis
        if not self.bereich.leer:
            tooltip += f"\nGrenzen in der angezeigten Einheit: {self.bereich.minimum:.12g} bis {self.bereich.maximum:.12g}."
        self.setToolTip(tooltip)
        self.slider.setToolTip(tooltip)
        self.anzeige.setToolTip(tooltip)
        self._zeige_wert()

    def _zeige_wert(self, *_args) -> None:
        b = self.bereich
        if b.leer:
            self.anzeige.setText("Kein Bereich bei diesen Eingaben – andere Größen anpassen.")
            self.anzeige.setStyleSheet("font-size: 8pt; color: #ffbd59;")
            return
        wert = float(self.spin.value())
        unten, oben = b.minimum, b.maximum
        position = 0.0
        if oben > unten:
            if self.logarithmisch and unten > 0:
                position = (math.log(max(wert, unten)) - math.log(unten)) / (math.log(oben) - math.log(unten))
            else:
                position = (wert - unten) / (oben - unten)
        blocker = QSignalBlocker(self.slider)
        self.slider.setValue(round(1000 * min(1, max(0, position))))
        del blocker
        im_bereich = unten - 1e-10 * max(1, abs(unten)) <= wert <= oben + 1e-10 * max(1, abs(oben))
        if b.schritt:
            im_bereich = im_bereich and abs(wert / b.schritt - round(wert / b.schritt)) < 1e-6
        im_bereich = im_bereich or (b.null_erlaubt and wert == 0)
        raster = f" · Raster {b.schritt:.5g}" if b.schritt else ""
        self.anzeige.setText(f"Bereich ca. {unten:.6g} … {oben:.6g}{raster}" + (" · Eingabe außerhalb" if not im_bereich else ""))
        if b.null_erlaubt:
            self.anzeige.setText("0: Nahmodell · sonst " + self.anzeige.text())
        farbe = "#9cb0c8" if im_bereich else "#ffbd59"
        self.anzeige.setStyleSheet(f"font-size: 8pt; color: {farbe};")

    def _slider_geaendert(self, position: int) -> None:
        b = self.bereich
        if b.leer:
            return
        anteil = position / 1000
        if position == 0 and b.null_erlaubt:
            self.spin.setValue(0)
            return
        if self.logarithmisch and b.minimum > 0:
            wert = math.exp(math.log(b.minimum) + anteil * math.log(b.maximum / b.minimum))
        else:
            wert = b.minimum + anteil * (b.maximum - b.minimum)
        wert = b.begrenze_wert(wert)
        self.spin.setValue(round(wert) if isinstance(self.spin, QSpinBox) else wert)

    def _raster_einhalten(self) -> None:
        b = self.bereich
        if not b.leer and b.schritt and b.minimum <= self.spin.value() <= b.maximum:
            wert = b.begrenze_wert(self.spin.value())
            self.spin.setValue(round(wert) if isinstance(self.spin, QSpinBox) else wert)
