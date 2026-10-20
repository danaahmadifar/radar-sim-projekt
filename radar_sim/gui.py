"""PyQt6-Oberfläche. Alle NumPy-Frameberechnungen laufen außerhalb des GUI-Threads."""

import logging
from dataclasses import replace
from pathlib import Path
import time
from typing import Callable

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QDialog, QDialogButtonBox,
)
import pyqtgraph as pg

from .config import RadarConfig, Target, validate_config
from .flugbahn import Flugbahn, Flugszene, flugszenen, erstelle_routenszene, grenzen_der_flugbahn
from .route import GezeichneteRoute, berechne_routendaten
from .parametergrenzen import ParameterBereich, berechne_parameterbereiche, bereich_fuer_tabellenwert
from .regler import CompactDoubleSpinBox, ParameterRegler, feldwert, setze_feldwert, wertsignal
from .io import export_candidates, export_flugzustaende, load_config, save_config
from .pipeline import FrameResult, simulate_frame
from .report_plots import export_plot
from .qt_support import ensure_font
from .flughafen import flughafen_config, flughafenszenen
from .eingabefelder import Eingabefelder
from .ergebnisansichten import Ergebnisansichten
from .tempo_anpassung import passe_radar_an_tempo

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
RADAR_SKALEN = {"carrier_hz": 1e9, "bandwidth_hz": 1e6, "sample_rate_hz": 1e6,
                "chirp_s": 1e-6, "repetition_s": 1e-6}
AUTO_RADAR_FELDER = ("carrier_hz", "bandwidth_hz", "repetition_s", "chirps", "chirp_s", "adc_skip_samples")

STYLE = (Path(__file__).parent / "assets/style.qss").read_text(encoding="utf-8").replace(
    "__ASSETS__", (Path(__file__).resolve().parent / "assets").as_posix())

class WorkerSignals(QObject):
    result = pyqtSignal(object, float)
    error = pyqtSignal(str)

class FrameWorker(QRunnable):
    def __init__(self, config: RadarConfig, index: int):
        super().__init__()
        self.config, self.index = config, index
        self.signals = WorkerSignals()

    def run(self) -> None:
        start = time.perf_counter()
        try:
            result = simulate_frame(self.config, self.index)
            self.signals.result.emit(result, time.perf_counter() - start)
        except Exception as exc:
            LOGGER.exception("Frameberechnung fehlgeschlagen")
            self.signals.error.emit(str(exc))

class MainWindow(QMainWindow):
    def __init__(self, config: RadarConfig | None = None):
        super().__init__()
        ensure_font(QApplication.instance())
        self.setWindowTitle("Radar Lab · FMCW, Puls-Doppler und Passivradar")
        self.resize(1600, 1000)
        self.setMinimumSize(1080, 640)
        self.setStyleSheet(STYLE)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.busy = False
        self.frame_index = 0
        self._last_input_config: RadarConfig | None = None
        self._lade_eingaben = False
        self._tempo_anpassung_noetig = False
        self._speed_radar_basis: dict[str, float | int] | None = None
        self.result: FrameResult | None = None
        self._eingaben_gueltig = True
        self._routen_entwurf: GezeichneteRoute | None = None
        self.grenzen_timer = QTimer(self)
        self.grenzen_timer.setSingleShot(True)
        self.grenzen_timer.timeout.connect(self._aktualisiere_grenzen)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.start_frame)
        self._build()
        # Standard-Qt-Kürzel statt einer zusätzlichen Menüstruktur.
        self.vollbild_kuerzel = QShortcut(QKeySequence("F11"), self)
        self.vollbild_kuerzel.activated.connect(self.toggle_fullscreen)
        self.fenster_kuerzel = QShortcut(QKeySequence("Esc"), self)
        self.fenster_kuerzel.activated.connect(self.leave_fullscreen)
        self._verbinde_eingaben()
        self.set_config(config or flughafen_config())
        QTimer.singleShot(0, self.start_frame)

    def _button(self, text: str, callback: Callable, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(callback)
        if primary:
            button.setObjectName("primary")
        return button

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        title = QLabel("RADAR LAB")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.run_status = QLabel("Bereit")
        self.run_status.setObjectName("subtitle")
        header.addWidget(self.run_status)
        layout.addLayout(header)
        toolbar = QHBoxLayout()
        self.run_button = self._button("Frame berechnen", self.start_frame, True)
        self.play_button = self._button("Play", self.toggle_play)
        self.play_button.setCheckable(True)
        self.play_button.setToolTip("Bewegt die Flugobjekte Schritt für Schritt. Bei festen Radar-Zielen wird nur das Rauschen erneuert.")
        self.reset_button = self._button("Reset", self.reset_seed)
        self.reset_button.setToolTip("Flugzeit und Rauschfolge auf den Anfang zurücksetzen.")
        self.load_button = self._button("JSON öffnen", self.open_json)
        self.save_button = self._button("JSON speichern", self.save_json)
        self.csv_button = self._button("CSV", self.save_csv)
        self.csv_button.setToolTip("Targets des letzten Frames mit zugehöriger Konfiguration exportieren.")
        self.png_button = self._button("PNG", self.save_png)
        self.png_button.setToolTip("Alle Diagramme einschließlich Antenna Pattern als einzelne Bilder speichern. Die Antennendiagramme zeigen die aktuelle Vorschau; die Radarplots gehören zum zuletzt berechneten Frame.")
        for button in (self.run_button, self.play_button, self.reset_button, self.load_button, self.save_button, self.csv_button, self.png_button):
            toolbar.addWidget(button)
        toolbar.addStretch()
        self.fullscreen_button = self._button("Vollbild · F11", self.toggle_fullscreen)
        self.fullscreen_button.setToolTip("F11 wechselt zwischen Vollbild und Fenster. Esc verlässt das Vollbild.")
        toolbar.addWidget(self.fullscreen_button)
        layout.addLayout(toolbar)
        self.grenzen_hinweis = QLabel()
        self.grenzen_hinweis.setWordWrap(True)
        self.grenzen_hinweis.setToolTip("Die Bereiche gelten jeweils für eine veränderte Größe bei unveränderten übrigen Werten. Orange markierte Eingaben müssen erst korrigiert werden. Es werden außerdem Speicherbedarf und Flugbewegung geprüft.")
        layout.addWidget(self.grenzen_hinweis)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        self.tabs = Eingabefelder()
        self.tabs.setMinimumWidth(345)
        self.tabs.setMaximumWidth(460)
        splitter.addWidget(self.tabs)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 0, 0, 0)
        metrics = QHBoxLayout()
        self.metric_labels = []
        for _ in range(3):
            label = QLabel()
            label.setObjectName("metric")
            label.setWordWrap(True)
            metrics.addWidget(label, 1)
            self.metric_labels.append(label)
        content_layout.addLayout(metrics)
        self.views = Ergebnisansichten(self.metric_labels, self.run_status)
        content_layout.addWidget(self.views, 1)
        self.views.route_editor.route_geaendert.connect(self._entwurf_3d)
        self.views.route_editor.bearbeiten.connect(self.tabs.zeichnen_button.click)
        splitter.addWidget(content)
        splitter.setSizes([390, 1170])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def toggle_fullscreen(self) -> None:
        """F11 und der sichtbare Button führen dieselbe Aktion aus."""
        if self.isFullScreen():
            self.leave_fullscreen()
        else:
            self._war_maximiert = self.isMaximized()
            self.showFullScreen()

    def leave_fullscreen(self) -> None:
        if self.isFullScreen():
            if getattr(self, "_war_maximiert", True):
                self.showMaximized()
            else:
                self.showNormal()

    def flug_auswahl_geaendert(self) -> None:
        if self._lade_eingaben:
            return
        if self.views.route_editor.aktiv:
            self._zeichnen_abbrechen()
        szene = self.tabs.flug_auswahl.currentData()
        from .fernradar import fernszene, fern_config
        from .passivradar import passiv_config
        if szene is not None and szene.name == fernszene().name:
            modus = self.tabs.controls["radar_mode"].currentData()
            self.set_config(fern_config("fmcw" if modus == "fmcw" else "pulse_doppler"))
            self.start_frame()
            return
        if szene is not None and szene.name == passiv_config().flugszene.name:
            self.set_config(passiv_config())
            self.start_frame()
            return
        for name, airport_szene in flughafenszenen().items():
            if szene is not None and szene.name == airport_szene.name:
                config = flughafen_config(name)
                if self.tabs.controls["radar_mode"].currentData() == "pulse_doppler":
                    from .pulsradar import puls_config
                    config = puls_config(config)
                self.set_config(config)
                self.start_frame()
                return
        for beispiel in flugszenen().values():
            if szene is not None and szene.name == beispiel.name:
                config = RadarConfig(targets=(), flugszene=beispiel)
                if self.tabs.controls["radar_mode"].currentData() == "pulse_doppler":
                    from .pulsradar import puls_config
                    config = puls_config(config)
                self.set_config(config)
                self.start_frame()
                return
        self._lade_eingaben = True
        self._set_flight_inputs(self.tabs.flug_auswahl.currentData())
        self._lade_eingaben = False
        self.frame_index = 0
        self._eingaben_geaendert()

    def _radarmodus_geaendert(self) -> None:
        if self._lade_eingaben:
            return
        config = self.get_config(pruefen=False)
        modus = config.radar_mode
        if modus == "passive":
            from .passivradar import passiv_config
            self._vor_passiv = replace(config, radar_mode=getattr(self, "_radarmodus", "fmcw"))
            self.set_config(passiv_config())
            return
        if getattr(self, "_radarmodus", None) == "passive":
            config = replace(getattr(self, "_vor_passiv", flughafen_config()), radar_mode=modus)
        from .fernradar import fernszene, fern_config
        if config.flugszene is not None and config.flugszene.name == fernszene().name:
            basis = fern_config(modus)
            config = replace(config, **{name: getattr(basis, name) for name in RADAR_SKALEN},
                             chirps=basis.chirps, adc_skip_samples=basis.adc_skip_samples)
            self.set_config(config)
            return
        if config.radar_mode == "pulse_doppler":
            from .pulsradar import puls_config
            config = puls_config(config)
        else:
            basis = flughafen_config()
            config = replace(config, **{name: getattr(basis, name) for name in RADAR_SKALEN},
                             chirps=basis.chirps, adc_skip_samples=basis.adc_skip_samples)
        self.set_config(config)

    def _zeichenmodus(self) -> None:
        if not self.tabs.zeichnen_button.isChecked():
            self._zeichnen_abbrechen()
            return
        self.tabs.setCurrentIndex(0)
        self._flugzeiten_vor_zeichnen = (self.tabs.flug_dauer.value(), self.tabs.routen_tempo.value())
        self.tabs.dauer_regler.setEnabled(True)
        self.tabs.flug_dauer.setEnabled(True)
        self.tabs.schritt_regler.setEnabled(True)
        self.tabs.flug_schritt.setEnabled(True)
        self.views.zeige_ansicht(self.views.route_editor)
        self.tabs.bereiche["Targets"].hide()
        self.tabs.route_settings.show()
        self.tabs.routen_staerke_regler.show()
        self.tabs.staerke_label.show()
        self.tabs.route_button.show()
        self.tabs.abbrechen_button.show()
        self.tabs.routen_hinweis.show()
        self._routen_entwurf = None
        self.tabs.route_button.setEnabled(False)
        self.tabs.routen_hinweis.setText("Punkte einzeln anklicken, Vorschau prüfen und übernehmen. Dauer oder Speed sind einstellbar.")
        szene = self.tabs.flug_auswahl.currentData()
        route = szene.bahnen[0].route if szene is not None else None
        self.views.route_editor.begin(route,
                                min(10000, max(120, self.get_config(pruefen=False).timing_range_limit)))
        self._set_busy(self.busy)

    def _zeichnen_abbrechen(self) -> None:
        if self.views.route_editor.aktiv and hasattr(self, "_flugzeiten_vor_zeichnen"):
            dauer, tempo = self._flugzeiten_vor_zeichnen
            with QSignalBlocker(self.tabs.flug_dauer), QSignalBlocker(self.tabs.routen_tempo):
                self.tabs.flug_dauer.setValue(dauer)
                self.tabs.routen_tempo.setValue(tempo)
            self.tabs.dauer_regler._zeige_wert()
            self.tabs.tempo_regler._zeige_wert()
        self.tabs.zeichnen_button.setChecked(False)
        self.tabs.route_button.setEnabled(False)
        self._routen_entwurf = None
        self.views.route_editor.stop()
        if self.result is not None:
            self.views.route_editor.zeige_szene(self.result.input_config.flugszene, self.result.flugzustaende,
                                          self.result.config.antenne, self.result.config.carrier_hz)
        self.tabs.route_button.hide()
        self.tabs.abbrechen_button.hide()
        szene = self.tabs.flug_auswahl.currentData()
        hat_route = szene is not None and szene.bahnen[0].route is not None
        self.tabs.dauer_regler.setEnabled(szene is not None)
        self.tabs.schritt_regler.setEnabled(szene is not None)
        self.tabs.route_settings.setVisible(szene is not None)
        self.tabs.routen_staerke_regler.setVisible(hat_route)
        self.tabs.staerke_label.setVisible(hat_route)
        self.tabs.routen_hinweis.setVisible(hat_route)
        self.tabs.routen_hinweis.setText("Route gewählt. Speed und Echostärke sind einstellbar.")
        self._tempo_anpassung_noetig = False
        self._eingaben_geaendert()
        self._set_busy(self.busy)

    def _entwurf_3d(self, route: GezeichneteRoute | None) -> None:
        """Ein gemeinsamer 3D-Entwurf für die drei Projektionsansichten."""
        if not self.views.route_editor.aktiv:
            return
        self._routen_entwurf = route  # Geometrie und eingegebenes Flugtempo getrennt halten.
        self.tabs.route_button.setEnabled(route is not None)
        if route is None:
            self.tabs.routen_hinweis.setText("Route im Editor korrigieren; Übernehmen ist bis dahin gesperrt.")
        self._eingaben_geaendert()

    def _route_uebernehmen(self) -> None:
        if self._routen_entwurf is None:
            return
        try:
            vorher = self.get_config(pruefen=False)
            basis = self._speed_radar_basis or {name: getattr(vorher, name) for name in AUTO_RADAR_FELDER}
            config = passe_radar_an_tempo(replace(vorher, **basis))
        except ValueError as exc:
            self.tabs.routen_hinweis.setText(f"Route bleibt im Editor: {exc}")
            return
        # Erst nach erfolgreicher Gesamtprüfung den Editor schließen.
        self.set_config(config)
        self._speed_radar_basis = basis
        self._zeige_auto_radar(vorher, config)
        self.start_frame()

    def _set_flight_inputs(self, szene: Flugszene | None) -> None:
        aktiv = szene is not None
        hat_route = aktiv and szene.bahnen[0].route is not None
        self.tabs.route_settings.setVisible(aktiv)
        self.tabs.routen_staerke_regler.setVisible(hat_route)
        self.tabs.staerke_label.setVisible(hat_route)
        self.tabs.routen_hinweis.setVisible(hat_route)
        self.tabs.route_button.hide()
        self.tabs.abbrechen_button.hide()
        self.tabs.flug_tabelle.setVisible(aktiv and not hat_route)
        self.tabs.startwerte_label.setVisible(aktiv and not hat_route)
        for widget in (self.tabs.flug_tabelle, self.tabs.flug_dauer, self.tabs.flug_schritt):
            widget.setEnabled(aktiv)
        self.tabs.targets_table.setEnabled(not aktiv)
        self.tabs.bereiche["Targets"].setVisible(not aktiv)
        self.tabs.add_target_button.setEnabled(not aktiv)
        self.tabs.remove_target_button.setEnabled(not aktiv)
        self.tabs.flug_tabelle.setRowCount(0)
        if szene is None:
            self.tabs.dauer_regler.setEnabled(False)
            self.tabs.schritt_regler.setEnabled(False)
            return
        self.tabs.schritt_regler.setEnabled(True)
        self._set_dauer(szene.dauer_s)
        self.tabs.flug_schritt.setMaximum(max(self.tabs.flug_schritt.maximum(), szene.zeitschritt_s))
        self.tabs.flug_schritt.setValue(szene.zeitschritt_s)
        route = szene.bahnen[0].route if szene.bahnen else None
        if route is not None:
            self.tabs.routen_hinweis.setText(f"Route: {berechne_routendaten(route).laenge_m:.1f} m. Dauer = Länge / Speed.")
            self.tabs.routen_tempo.setMinimum(min(self.tabs.routen_tempo.minimum(), route.geschwindigkeit_mps))
            self.tabs.routen_tempo.setValue(route.geschwindigkeit_mps)
            self.tabs.routen_staerke.setMinimum(min(self.tabs.routen_staerke.minimum(), szene.bahnen[0].staerke))
            self.tabs.routen_staerke.setValue(szene.bahnen[0].staerke)
        else:
            alle_bahnen = szene.bahnen + ((szene.radar_bahn,) if szene.radar_bahn else ())
            tempo = max(grenzen_der_flugbahn(b, szene.dauer_s).tempo_max_mps for b in alle_bahnen)
            with QSignalBlocker(self.tabs.routen_tempo):
                self.tabs.routen_tempo.setValue(tempo)
        self.tabs.dauer_regler.setEnabled(True)
        bahnen = szene.bahnen + ((szene.radar_bahn,) if szene.radar_bahn else ())
        self.tabs.flug_tabelle.setToolTip("Weltkoordinaten in Metern. Bei Air-to-Air ist die letzte Zeile das Radarflugzeug (Sender und Empfänger), kein Echoziel. Antennenwinkel sind im Weltkoordinatensystem fest.")
        for nummer, bahn in enumerate(bahnen):
            self.tabs.flug_tabelle.insertRow(nummer)
            werte = (bahn.start_x_m, bahn.start_hoehe_m, bahn.geschwindigkeit_x_mps,
                     bahn.geschwindigkeit_hoehe_mps, bahn.beschleunigung_hoehe_mps2, bahn.staerke,
                     bahn.start_y_m, bahn.geschwindigkeit_y_mps)
            for spalte, wert in enumerate(werte):
                self.tabs.flug_tabelle.setItem(nummer, spalte, QTableWidgetItem(f"{wert:.12g}"))
        self.tabs.flug_tabelle.setVerticalHeaderLabels([f"Target {n+1}" for n in range(len(szene.bahnen))] + (["Radar · Tx/Rx"] if szene.radar_bahn else []))

    def _verbinde_eingaben(self) -> None:
        """Ein gemeinsamer Aktualisierungspfad für Zahlenfelder, Slider und Tabellen."""
        self.tabs.flug_auswahl.currentIndexChanged.connect(self.flug_auswahl_geaendert)
        self.tabs.zeichnen_button.clicked.connect(self._zeichenmodus)
        self.tabs.route_button.clicked.connect(self._route_uebernehmen)
        self.tabs.abbrechen_button.clicked.connect(self._zeichnen_abbrechen)
        self.tabs.add_target_button.clicked.connect(self.add_target)
        self.tabs.remove_target_button.clicked.connect(self.remove_target)
        self._tabelle_mit_reglern(self.tabs.flug_tabelle)
        self._tabelle_mit_reglern(self.tabs.targets_table)
        felder = (*self.tabs.controls.values(), *self.tabs.ant_controls.values(), *self.tabs.passiv_controls.values(), self.tabs.flug_dauer,
                  self.tabs.flug_schritt, self.tabs.routen_tempo, self.tabs.routen_staerke)
        for feld in felder:
            wertsignal(feld).connect(self._eingaben_geaendert)
        self.tabs.flug_dauer.valueChanged.connect(self._routendauer_geaendert)
        self.tabs.routen_tempo.valueChanged.connect(self._routentempo_geaendert)
        self.tabs.controls["radar_mode"].currentIndexChanged.connect(self._radarmodus_geaendert)
        self.tabs.effektfelder.demo_laden.connect(self._effektdemo_laden)
        for feld in self.tabs.effektfelder.controls.values():
            wertsignal(feld).connect(self._eingaben_geaendert)

    def _effektdemo_laden(self, name: str) -> None:
        from .effektbeispiele import effektbeispiele
        self.set_config(effektbeispiele()[name][1])
        self.views.zeige_ansicht(self.views.effektansicht)
        self.start_frame()

    def _eingaben_geaendert(self, *_args) -> None:
        if not self._lade_eingaben:
            if self.sender() in self.tabs.controls.values():
                # Manuelle Radaränderungen bilden die neue Ausgangskonfiguration.
                self._speed_radar_basis = None
            self.grenzen_timer.start(60)

    def _route_fuer_eingaben(self) -> GezeichneteRoute | None:
        """Beim Zeichnen den Entwurf, sonst die ausgewählte Route verwenden."""
        if self.views.route_editor.aktiv:
            return self._routen_entwurf
        szene = self.tabs.flug_auswahl.currentData()
        return szene.bahnen[0].route if szene is not None else None

    def _routendauer_geaendert(self, dauer: float) -> None:
        if self._lade_eingaben:
            return
        route = self._route_fuer_eingaben()
        if route is not None and dauer > 0:
            tempo = berechne_routendaten(route).laenge_m / dauer
            # Auch ungültige direkte Eingaben sichtbar lassen, nicht heimlich klemmen.
            with QSignalBlocker(self.tabs.routen_tempo):
                self.tabs.routen_tempo.setRange(min(self.tabs.routen_tempo.minimum(), tempo),
                                           max(self.tabs.routen_tempo.maximum(), tempo))
                self.tabs.routen_tempo.setValue(tempo)
            self.tabs.tempo_regler._zeige_wert()
            self._tempo_anpassung_noetig = True

    def _routentempo_geaendert(self, tempo: float) -> None:
        if self._lade_eingaben:
            return
        route = self._route_fuer_eingaben()
        if route is not None and tempo > 0:
            dauer = berechne_routendaten(route).laenge_m / tempo
            self._set_dauer(dauer)
        elif tempo > 0 and self.tabs.flug_auswahl.currentData() is not None and not self.views.route_editor.aktiv:
            # Zeit skalieren statt den Endpunkt des Beispiel-Flugs zu verschieben:
            # v_neu=k*v, a_neu=k²*a und T_neu=T/k ergeben dieselbe Raumkurve.
            try:
                szene = self.get_config(pruefen=False).flugszene
                alle_bahnen = szene.bahnen + ((szene.radar_bahn,) if szene.radar_bahn else ())
                bisher = max(grenzen_der_flugbahn(b, szene.dauer_s).tempo_max_mps for b in alle_bahnen)
            except (ValueError, ZeroDivisionError, OverflowError):
                # Eine andere, noch fehlerhafte Tabellenzelle zuerst korrigieren.
                self._tempo_anpassung_noetig = True
                self._eingaben_geaendert()
                return
            if bisher > 0:
                faktor = tempo/bisher
                with QSignalBlocker(self.tabs.flug_tabelle), QSignalBlocker(self.tabs.flug_dauer):
                    for zeile in range(self.tabs.flug_tabelle.rowCount()):
                        for spalte in (2, 3, 4, 7):
                            item = self.tabs.flug_tabelle.item(zeile, spalte)
                            wert = float(item.text().replace(",", "."))
                            item.setText(f"{wert*faktor**(2 if spalte == 4 else 1):.12g}")
                    dauer = szene.dauer_s/faktor
                    self._set_dauer(dauer)
        self._tempo_anpassung_noetig = True

    def _set_dauer(self, dauer: float) -> None:
        """Dauer sichtbar halten; der Slider wächst mit der Route mit."""
        with QSignalBlocker(self.tabs.flug_dauer):
            self.tabs.flug_dauer.setMaximum(max(self.tabs.flug_dauer.maximum(), dauer))
            self.tabs.flug_dauer.setValue(dauer)
        self.tabs.dauer_regler.set_bereich(ParameterBereich(1e-9, max(120, dauer),
                                                       hinweis="Positive Dauer; folgt bei Routen aus Länge / Speed."))

    def _aktualisiere_grenzen(self) -> None:
        """Nur kleine Formeln im GUI-Thread; keine FFT und keine Sample-Arrays."""
        if self._lade_eingaben:
            return
        fehler = None
        try:
            config = self.get_config(pruefen=False)
            self._aktualisiere_routentempo(config)
            if self.views.route_editor.aktiv:
                # Nur prüfen, noch keine Radarwerte oder die laufende Szene ändern.
                if self._routen_entwurf is not None:
                    passe_radar_an_tempo(config)
            else:
                if self._tempo_anpassung_noetig:
                    config = self._passe_radar_an_speed_an(config)
                    self._tempo_anpassung_noetig = False
                bereiche = berechne_parameterbereiche(config)
                for name, regler in self.tabs.regler.items():
                    regler.set_bereich(bereiche[name].skaliert(RADAR_SKALEN.get(name, 1)))
                self.tabs.schritt_regler.set_bereich(ParameterBereich(config.chirps * config.repetition_s, max(1, self.tabs.flug_schritt.value()),
                                                               hinweis="Mindestens die Dauer eines Radar-Messpakets"))
                self.views.zeige_antenne(config)
                self.tabs.zeige_antennenfelder()
                validate_config(config)
        except (ValueError, TypeError, OverflowError) as exc:
            fehler = str(exc)
        self._eingaben_gueltig = fehler is None
        if fehler:
            self.grenzen_hinweis.setText("Bitte anpassen: " + fehler + "  Andere Werte bleiben unverändert.")
            self.grenzen_hinweis.setStyleSheet("color: #ffbd59;")
        self.grenzen_hinweis.setVisible(fehler is not None)
        self._set_busy(self.busy)

    def _aktualisiere_routentempo(self, config: RadarConfig) -> None:
        # Das Flugtempo hat keinen vom aktuellen Radarprofil vorgegebenen Deckel.
        # Die automatische Anpassung erfolgt erst nach einer Speed-Eingabe.
        hinweis = ("Freie Speed-Eingabe; Puls-PRI und Träger bei Doppler-Aliasing bewusst anpassen. Keine automatische Pulsprofiländerung."
                   if config.radar_mode == "pulse_doppler" else "Freie Speed-Eingabe; Radarwerte folgen bei Bedarf.")
        if config.radar_mode == "passive":
            hinweis = "Speed ist einstellbar. Doppler-Suchraster, Integration und Umwegfenster bei Bedarf selbst anpassen."
        self.tabs.tempo_regler.set_bereich(ParameterBereich(.001, max(1000, self.tabs.routen_tempo.value()), hinweis=hinweis))
        route = self._route_fuer_eingaben()
        if route is None:
            if config.flugszene is not None and not self.views.route_editor.aktiv:
                szene = config.flugszene
                alle_bahnen = szene.bahnen + ((szene.radar_bahn,) if szene.radar_bahn else ())
                tempo = max(grenzen_der_flugbahn(b, szene.dauer_s).tempo_max_mps for b in alle_bahnen)
                with QSignalBlocker(self.tabs.routen_tempo):
                    self.tabs.routen_tempo.setValue(tempo)
                self.tabs.tempo_regler._zeige_wert()
            return
        daten = berechne_routendaten(route)
        self._set_dauer(daten.laenge_m/self.tabs.routen_tempo.value())
        if self._routen_entwurf is not None:
            self.tabs.routen_hinweis.setText(f"Vorschau: {daten.laenge_m:.1f} m, {daten.laenge_m / self.tabs.routen_tempo.value():.1f} s "
                                        f"bei {self.tabs.routen_tempo.value():g} m/s. Übernehmen oder neu zeichnen.")

    def _passe_radar_an_speed_an(self, config: RadarConfig) -> RadarConfig:
        basis = self._speed_radar_basis or {name: getattr(config, name) for name in AUTO_RADAR_FELDER}
        angepasst = passe_radar_an_tempo(replace(config, **basis))
        self._speed_radar_basis = basis
        self._set_radar_inputs(angepasst)
        self._zeige_auto_radar(config, angepasst)
        return self.get_config(pruefen=False)

    def _zeige_auto_radar(self, config: RadarConfig, angepasst: RadarConfig) -> None:
        aenderungen = [f"{name}: {getattr(config, name):g} → {getattr(angepasst, name):g} (SI)"
                       for name in AUTO_RADAR_FELDER if getattr(config, name) != getattr(angepasst, name)]
        if aenderungen:
            self.tabs.tempo_hinweis.setText(f"Auto-Radar: {angepasst.carrier_hz/1e9:.4g} GHz · "
                                       f"{angepasst.bandwidth_hz/1e6:.4g} MHz · {angepasst.chirps} Chirps")
            self.tabs.tempo_hinweis.setToolTip("\n".join(aenderungen) + "\nAuflösung und eindeutiger Bereich ändern sich entsprechend. Kein unverändertes Airport-Radarprofil.")

    def _tabelle_mit_reglern(self, tabelle: QTableWidget) -> None:
        tabelle.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabelle.cellDoubleClicked.connect(lambda zeile, spalte: self._tabellenwert_bearbeiten(tabelle, zeile, spalte))
        tabelle.itemChanged.connect(lambda item: self._tabellenwert_geaendert(tabelle, item))

    def _tabellenwert_geaendert(self, tabelle: QTableWidget, item: QTableWidgetItem) -> None:
        hinweis = tabelle.horizontalHeaderItem(item.column()).toolTip()
        if item.toolTip() != hinweis:
            item.setToolTip(hinweis)
        if not self._lade_eingaben and ((tabelle is self.tabs.flug_tabelle and item.column() in (2, 3, 7))
                                       or (tabelle is self.tabs.targets_table and item.column() == 1)):
            self._tempo_anpassung_noetig = True
        self._eingaben_geaendert()

    def _tabellenwert_bearbeiten(self, tabelle: QTableWidget, zeile: int, spalte: int) -> None:
        """Auch jeder Tabellenwert hat einen Slider, ohne die Tabelle zu überladen."""
        if not tabelle.isEnabled():
            return
        bereich = bereich_fuer_tabellenwert(self.get_config(pruefen=False), tabelle is self.tabs.flug_tabelle, zeile, spalte)
        if (tabelle is self.tabs.flug_tabelle and spalte in (2, 3, 7)) or (tabelle is self.tabs.targets_table and spalte == 1):
            bereich = ParameterBereich(-10000, 10000, hinweis="Freie Geschwindigkeit; Radarwerte werden bei Bedarf angepasst.")
        dialog = QDialog(self)
        dialog.setWindowTitle(tabelle.horizontalHeaderItem(spalte).text())
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        text = QLabel(tabelle.horizontalHeaderItem(spalte).toolTip())
        text.setWordWrap(True)
        layout.addWidget(text)
        zahl = CompactDoubleSpinBox()
        zahl.setDecimals(12)
        wert = float(tabelle.item(zeile, spalte).text().replace(",", "."))
        minimum = bereich.minimum if not bereich.leer else min(-1000, wert)
        maximum = bereich.maximum if not bereich.leer else max(1000, wert)
        zahl.setRange(min(minimum, wert), max(maximum, wert))
        zahl.setValue(wert)
        zahl.setToolTip(text.text())
        layout.addWidget(ParameterRegler(zahl, bereich,
                                          logarithmisch=minimum > 0 and maximum / minimum > 1000))
        layout.addWidget(QLabel("Die Radar- und Fluggrenzen werden nach dem Übernehmen neu geprüft."))
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        knoepfe.accepted.connect(dialog.accept)
        knoepfe.rejected.connect(dialog.reject)
        layout.addWidget(knoepfe)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            tabelle.item(zeile, spalte).setText(f"{zahl.value():.12g}")

    def add_target(self) -> None:
        if self.tabs.targets_table.rowCount() >= 32:
            return
        row = self.tabs.targets_table.rowCount()
        self.tabs.targets_table.insertRow(row)
        for col, value in enumerate((40.0, 0.0, 1.0, 0.0)):
            self.tabs.targets_table.setItem(row, col, QTableWidgetItem(str(value)))

    def remove_target(self) -> None:
        rows = sorted({item.row() for item in self.tabs.targets_table.selectedItems()}, reverse=True)
        for row in rows:
            self.tabs.targets_table.removeRow(row)

    def set_config(self, config: RadarConfig) -> None:
        if self.views.route_editor.aktiv:
            self._zeichnen_abbrechen()
        self._lade_eingaben = True
        self._radarmodus = config.radar_mode
        self.tabs.effektfelder.setze(config.effekte)
        self.tabs.effektfelder.controls["leakage"].setEnabled(config.radar_mode != "passive")
        for name, feld in self.tabs.passiv_controls.items():
            setze_feldwert(feld, getattr(config.passiv, name))
        self._tempo_anpassung_noetig = False
        self._speed_radar_basis = None
        self.tabs.tempo_hinweis.clear()
        for name, feld in self.tabs.ant_controls.items():
            setze_feldwert(feld, getattr(config.antenne, name))
        self.tabs.routen_tempo.setValue(70 if config.adc_skip_samples else 5)
        # Qt vergleicht Python-Dataclasses in findData nicht zuverlässig nach Wert.
        # Der Szenarioname ist unser stabiler Schlüssel, auch beim JSON-Import.
        index = 0 if config.flugszene is None else self.tabs.flug_auswahl.findText(config.flugszene.name)
        if index < 0:
            self.tabs.flug_auswahl.addItem(config.flugszene.name, config.flugszene)
            index = self.tabs.flug_auswahl.count() - 1
        self.tabs.flug_auswahl.setItemData(index, config.flugszene)
        self.tabs.flug_auswahl.setCurrentIndex(index)
        self._set_radar_inputs(config)
        self.tabs.zeige_radarmodus(config.radar_mode == "pulse_doppler")
        self.tabs.zeige_passivmodus(config.radar_mode == "passive")
        self.tabs.targets_table.setRowCount(0)
        for target in config.targets:
            self.add_target()
            for col, value in enumerate((target.range_m, target.velocity_mps, target.strength, target.phase_rad)):
                self.tabs.targets_table.setItem(self.tabs.targets_table.rowCount() - 1, col, QTableWidgetItem(f"{value:.12g}"))
        self.frame_index = 0
        self._set_flight_inputs(config.flugszene)
        self._lade_eingaben = False
        self._aktualisiere_grenzen()

    def _set_radar_inputs(self, config: RadarConfig) -> None:
        """Ein gemeinsamer Weg für JSON-Import und automatisch angepasste Werte."""
        for name, feld in self.tabs.controls.items():
            setze_feldwert(feld, getattr(config, name) / RADAR_SKALEN[name]
                          if name in RADAR_SKALEN else getattr(config, name))

    def get_config(self, pruefen: bool = True) -> RadarConfig:
        values = {name: feldwert(feld) * RADAR_SKALEN[name] if name in RADAR_SKALEN else feldwert(feld)
                  for name, feld in self.tabs.controls.items()}
        values["seed"] = int(values["seed"])
        targets = []
        anzahl_ziele = self.tabs.targets_table.rowCount() if self.tabs.flug_auswahl.currentData() is None else 0
        for row in range(anzahl_ziele):
            try:
                numbers = [float(self.tabs.targets_table.item(row, col).text().replace(",", ".")) for col in range(4)]
                targets.append(Target(*numbers))
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"Zielzeile {row + 1}: vier gültige Zahlen eingeben.") from exc
        values["targets"] = tuple(targets)
        values["antenne"] = self.tabs.lese_antenne()
        values["passiv"] = self.tabs.lese_passiv()
        values["effekte"] = self.tabs.effektfelder.lese()
        ausgewaehlte_szene = self.tabs.flug_auswahl.currentData()
        if ausgewaehlte_szene is not None or self.views.route_editor.aktiv:
            route = self._route_fuer_eingaben()
            if route is not None:
                route = replace(route, geschwindigkeit_mps=self.tabs.routen_tempo.value())
                szene = erstelle_routenszene(route, self.tabs.flug_schritt.value(), self.tabs.routen_staerke.value())
                values["flugszene"] = (szene if self.views.route_editor.aktiv else replace(szene, name=ausgewaehlte_szene.name))
                values["targets"] = ()
            elif not self.views.route_editor.aktiv:
                bahnen = []
                for zeile in range(self.tabs.flug_tabelle.rowCount()):
                    try:
                        zahlen = [float(self.tabs.flug_tabelle.item(zeile, s).text().replace(",", ".")) for s in range(8)]
                        bahnen.append(Flugbahn(*zahlen[:6], start_y_m=zahlen[6], geschwindigkeit_y_mps=zahlen[7]))
                    except (ValueError, AttributeError) as exc:
                        raise ValueError(f"Flugobjekt {zeile + 1}: acht gültige Zahlen eingeben.") from exc
                values["flugszene"] = Flugszene(ausgewaehlte_szene.name, tuple(bahnen),
                                               self.tabs.flug_dauer.value(), self.tabs.flug_schritt.value())
                if ausgewaehlte_szene.radar_bahn is not None:
                    values["flugszene"] = replace(values["flugszene"], bahnen=tuple(bahnen[:-1]), radar_bahn=bahnen[-1])
            values["targets"] = ()
        config = RadarConfig(**values)
        if pruefen:
            validate_config(config)
        return config

    def _set_busy(self, busy: bool) -> None:
        """Beim Abspielen bleiben die Bedienelemente durchgehend gleich gefärbt.

        Früher wurden sie für jeden Frame grau und danach wieder hell. Das war
        als Flackern sichtbar. Jetzt ändert sich der Zustand nur bei Start/Stop.
        """
        self.busy = busy
        bearbeiten = not busy and not self.play_button.isChecked()
        self.tabs.setEnabled(bearbeiten)
        self.load_button.setEnabled(bearbeiten)
        for button in (self.run_button, self.save_button, self.reset_button):
            button.setEnabled(bearbeiten and self._eingaben_gueltig and not self.views.route_editor.aktiv)
        self.play_button.setEnabled(self.play_button.isChecked() or (self._eingaben_gueltig and not self.views.route_editor.aktiv))
        for button in (self.csv_button, self.png_button):
            button.setEnabled(self.result is not None)

    def start_frame(self) -> None:
        if self.busy or self.views.route_editor.aktiv:
            return
        if self._tempo_anpassung_noetig:
            self.grenzen_timer.stop()
            self._aktualisiere_grenzen()
        try:
            config = self.get_config()
        except ValueError as exc:
            self.fail(str(exc))
            return
        if config != self._last_input_config:
            self.frame_index = 0
            self._last_input_config = config
        if config.flugszene is not None and self.frame_index > config.flugszene.letzter_frame:
            self.frame_index = 0
        self._set_busy(True)
        if not self.play_button.isChecked():
            self.run_status.setText("Berechne Frame …")
        self.worker = FrameWorker(config, self.frame_index)
        self.worker.signals.result.connect(self.show_result)
        self.worker.signals.error.connect(self.fail)
        self.pool.start(self.worker)

    def toggle_play(self) -> None:
        self.play_button.setText("Pause" if self.play_button.isChecked() else "Play")
        if self.play_button.isChecked():
            self.start_frame()
        else:
            self.timer.stop()
            self._set_busy(self.busy)

    def reset_seed(self) -> None:
        self.frame_index = 0
        self.start_frame()

    def fail(self, message: str) -> None:
        self.timer.stop()
        self.play_button.setChecked(False)
        self.play_button.setText("Play")
        self._set_busy(False)
        self.run_status.setText("Eingabe oder Berechnung prüfen")
        QMessageBox.warning(self, "Konfiguration prüfen", message)

    def show_result(self, result: FrameResult, elapsed: float) -> None:
        """Nur vorhandene Daten ändern: keine neuen Plots und kein Zurücksetzen des Zooms."""
        self.result = result
        self.frame_index = result.frame_index + 1
        self.views.zeige_ergebnis(result, elapsed)
        self._set_busy(False)
        szene = result.input_config.flugszene
        if szene is not None and result.frame_index >= szene.letzter_frame:
            self.play_button.setChecked(False)
            self.play_button.setText("Play")
            self._set_busy(False)
            self.run_status.setText(f"Flug beendet · {result.zeit_s:.2f} s")
        elif self.play_button.isChecked():
            wartezeit_ms = 1000 * min(1., szene.zeitschritt_s) if szene is not None else 350
            self.timer.start(max(1, round(wartezeit_ms - elapsed * 1000)))

    def open_json(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Szenario öffnen", str(ROOT / "examples"), "JSON (*.json)")
        if filename:
            try:
                self.set_config(load_config(filename))
                self.start_frame()
            except (OSError, ValueError) as exc:
                self.fail(str(exc))

    def save_json(self) -> None:
        try:
            config = self.get_config()
            filename, _ = QFileDialog.getSaveFileName(self, "Aktuelle Parameter speichern", "radar_config.json", "JSON (*.json)")
            if filename:
                save_config(filename, config)
        except (OSError, ValueError) as exc:
            self.fail(str(exc))

    def save_csv(self) -> None:
        if self.result is None:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Targets des berechneten Frames", "detections.csv", "CSV (*.csv)")
        if filename:
            try:
                export_candidates(filename, self.result.candidates)
                # Begleitdatei hält die berechnete Konfiguration und den Rausch-Frame fest.
                save_config(Path(filename).with_suffix(".config.json"), self.result.input_config)
                Path(filename).with_suffix(".frame.txt").write_text(
                    f"frame_index={self.result.frame_index}\nzeit_s={self.result.zeit_s}\n", encoding="utf-8")
                if self.result.flugzustaende:
                    export_flugzustaende(Path(filename).with_suffix(".flug.csv"), self.result.zeit_s,
                                         self.result.flugzustaende)
                if self.result.radar_zustand is not None:
                    export_flugzustaende(Path(filename).with_suffix(".radar.csv"), self.result.zeit_s,
                                         (self.result.radar_zustand,))
                self.run_status.setText("CSV gespeichert")
            except OSError as exc:
                self.fail(str(exc))

    def save_png(self) -> None:
        if self.result is None:
            return
        directory = QFileDialog.getExistingDirectory(self, "Alle Diagramme als PNG exportieren")
        if directory:
            try:
                diagramme = self.views.diagramme()
                for name, plot in diagramme:
                    export_plot(plot, Path(directory) / f"{name}.png")
                self.run_status.setText(f"{len(diagramme)} PNGs gespeichert")
            except Exception as exc:
                self.fail(str(exc))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.grenzen_timer.stop()
        self.play_button.setChecked(False)
        # Höchstens ein Job, keine Warteschlange. QObject-Signale überleben den Job.
        self.pool.waitForDone()
        event.accept()

def run_gui(config: RadarConfig | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Radar Lab")
    app.setStyle("Fusion")
    pg.setConfigOptions(antialias=True, foreground="#dce7f5", imageAxisOrder="row-major")
    window = MainWindow(config)
    window.showFullScreen()
    return app.exec()
