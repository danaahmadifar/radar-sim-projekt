"""Kompakte Eingaben für die offen beschriebenen Störmodelle."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QWidget, QVBoxLayout, QFormLayout, QComboBox, QPushButton, QLabel, QCheckBox
from .effekt_config import Stoereffekte
from .effektbeispiele import effektbeispiele
from .regler import zahlenfeld, ParameterRegler, feldwert, setze_feldwert
from .parametergrenzen import ParameterBereich


class EffektFelder(QScrollArea):
    demo_laden = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        box = QWidget()
        self.setWidget(box)
        layout = QVBoxLayout(box)
        self.demo = QComboBox()
        self.demo.setMinimumContentsLength(12)
        self.demo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.demo.addItems(effektbeispiele())
        layout.addWidget(QLabel("Effekt-Demos"))
        layout.addWidget(self.demo)
        laden = QPushButton("Effekt-Demo laden")
        laden.clicked.connect(lambda: self.demo_laden.emit(self.demo.currentText()))
        layout.addWidget(laden)
        self.erklaerung = QLabel()
        self.erklaerung.setWordWrap(True)
        layout.addWidget(self.erklaerung)
        self.demo.currentTextChanged.connect(self._erklaere_demo)
        self._erklaere_demo(self.demo.currentText())
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        layout.addLayout(form)
        self.controls = {}
        self.regler = {}
        self.skalen = {}
        for name, text, tipp in (
            ("leakage", "TX→RX-Leakage", "Ein verzögerter Kopplungsweg des eigenen Senders in den Empfänger. Beim Pulsradar ist der Empfänger während der Sendezeit gesperrt; nur der nachlaufende Anteil bleibt. Passivradar hat stattdessen den Fremdsender-Direktweg."),
            ("saettigung", "Empfängersättigung", "Begrenzt den Betrag der komplexen Empfangssumme vor FFT und digitaler Unterdrückung. Das verändert Echos und Störsignale gemeinsam. Keine AGC oder ADC-Quantisierung."),
            ("phasenrauschen", "Phasenrauschen", "Ein gemeinsamer glatter Gauß-Phasenprozess. Aktiv bleibt φ(t)−φ(t−Laufzeit); bei kurzem Weg hebt sich viel auf. Passiv verwenden beide Empfangskanäle denselben LO."),
            ("erdkruemmung", "Erdkrümmung / Sichtgrenze", "Berechnet Laufwege und freie Sicht auf einer effektiven Erdkugel. Hinter dem Horizont gibt es kein direktes Echo. Die XYZ-Ansicht bleibt eine schematische Karte, keine ECEF-Darstellung."),
            ("atmosphaere", "Atmosphärische Dämpfung", "Ein vorgegebener Dämpfungswert pro Kilometer auf dem gesamten Signalweg. Keine automatische Wetter-, Regen- oder Gaslinienberechnung."),
            ("bodenclutter", "Bodenclutter", "Feste Bodenflächen streuen das Sendesignal zurück. RCS = sigma0 × Fläche; zufällige komplexe Streuung bleibt über Frames fest. Bewegung des Radars erzeugt Clutter-Doppler."),
            ("teilpulse", "Puls-Nahbereich mit auswerten", "Erlaubt unvollständig empfangene Pulse unterhalb c·Tp/2. Die Sendezeit bleibt gesperrt. Kleine Laufzeit bedeutet wenig verbleibende Empfangsenergie, nicht automatisch exakt null Echo."),
        ):
            feld = QCheckBox(text)
            feld.setToolTip(tipp)
            form.addRow(feld)
            self.controls[name] = feld
        for name, label, unten, oben, skala, ganz, tipp in (
            ("leakage_db", "Leakage / dB", -80, 100, 1, False, "Leistung des Kopplungswegs relativ zu Aref²=1 bei TX Peak 0 dB. Aktive Leakage skaliert mit TX Peak. Vor Begrenzung; keine absolute Isolation gegenüber einer bekannten Sendeleistung."),
            ("leakage_delay_s", "Leakage-Laufzeit / ns", 0, 1e6, 1e-9, False, "Verzögerung des Kopplungswegs. Bei FMCW ergibt sich S×Laufzeit als Leakage-Beat. Größere Verzögerung hinterlässt mehr gemeinsames Phasenrauschen."),
            ("saettigung_db", "Amplitude-Limit / dB", -60, 100, 1, False, "Maximale momentane Leistung |x|² relativ zu Aref²=1. Darüber wird der Betrag begrenzt. Ein niedrigeres Limit übersteuert früher."),
            ("phase_rms_rad", "Oszillatorphase RMS / rad", 0, 3, 1, False, "Standardabweichung der Phase des einzelnen Oszillators. Die aktive Restphase hängt zusätzlich von Laufzeit und Korrelation ab."),
            ("phase_zeit_s", "Phasenkorrelation / µs", .001, 1e6, 1e-6, False, "Zeitmaß Tc des gaußkorrelierten Phasenmodells. Kleiner bedeutet schnellere Schwankungen. Kein aus einem PLL-Datenblatt abgeleitetes 1/f-Spektrum."),
            ("erdradius_faktor", "Effektiver Erdradius k", 1, 2, 1, False, "k=1: geometrische Erde. k=4/3: übliche vereinfachte Refraktionsannahme; keine Garantie für eine konkrete Atmosphäre."),
            ("stationshoehe_m", "Radar-Mast / m", 0, 10000, 1, False, "Zusätzliche Antennenhöhe über Boden oder Radarflugzeug. Ändert Geometrie und Sichtgrenze; benötigt räumliche Flugbahnen."),
            ("daempfung_db_km", "Dämpfung / dB/km", 0, 100, 1, False, "Vorgegebene homogene spezifische Dämpfung. Aktiv zählt der Hin- und Rückweg, passiv Tx→Target→Rx. Höhere Dämpfung senkt das tatsächliche Echo-SNR."),
            ("sigma0_db", "Bodenreflektivität σ0 / dB", -80, 0, 1, False, "Mittlere RCS pro Quadratmeter Boden. Kein automatisches Land-, Bewuchs- oder Frequenzmodell; bistatisch eine vorgegebene effektive Reflektivität."),
            ("clutter_innen_m", "Bodenfläche ab / m", 1, 1e6, 1, False, "Innerer Kartenradius der festen Clutterfläche um den Ursprung. Alle Streuer bleiben an denselben Weltorten."),
            ("clutter_aussen_m", "Bodenfläche bis / m", 2, 1e6, 1, False, "Äußerer Kartenradius. Die Fläche muss zu Laufzeit, Abtastung und Doppler des Radarprofils passen."),
            ("clutter_ringe", "Clutter-Ringe", 1, 12, 1, True, "Radiale Flächenunterteilung. Höchstens 128 Flächen insgesamt und ein zusätzliches Rechenbudget begrenzen den Aufwand."),
            ("clutter_sektoren", "Clutter-Sektoren", 4, 36, 1, True, "Winkelunterteilung über 360°. Ein komplexer Punktstreuer je Fläche ist eine grobe quadratische Näherung des Bodenechos."),
        ):
            feld = zahlenfeld(unten, oben, tipp, 6, ganz)
            regler = ParameterRegler(feld, ParameterBereich(unten, oben, 1 if ganz else 0),
                                    logarithmisch=unten > 0 and oben/unten > 1000)
            form.addRow(label, regler)
            self.controls[name] = feld
            self.regler[name] = regler
            self.skalen[name] = skala
        layout.addStretch()

    def _erklaere_demo(self, name):
        self.erklaerung.setText(effektbeispiele()[name][0])

    def lese(self) -> Stoereffekte:
        return Stoereffekte(**{name: feldwert(feld)*self.skalen.get(name, 1) if name in self.skalen else feldwert(feld)
                              for name, feld in self.controls.items()})

    def setze(self, effekte: Stoereffekte) -> None:
        for name, feld in self.controls.items():
            wert = getattr(effekte, name)
            setze_feldwert(feld, wert/self.skalen[name] if name in self.skalen else wert)
            if name in self.regler:
                self.regler[name]._zeige_wert()
