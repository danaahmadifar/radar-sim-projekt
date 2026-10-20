"""Radarplots, Flugansicht und Ergebnistabelle; berechnet selbst keine Radarframes."""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QLabel, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QVBoxLayout, QCheckBox
from .ansichtsgruppe import AnsichtsGruppe
from .config import RadarConfig, Target
from .flugbahn import flugbahn_punkte, relative_bahngrenzen, relativer_zustand, grenzen_der_flugbahn
from .pipeline import FrameResult
from .evaluation import match_targets
from .model import target_amplitude
from .processing import power_db
from .antenne import keulenlinien
from .flugansicht import FlugAnsicht
from .routen_editor import RoutenEditor
from .antennenansicht import AntennenAnsicht
from .radarvergleich import RadarVergleich


class Ergebnisansichten(QTabWidget):
    """Hält dieselben Plotelemente zwischen Frames und erhält den gewählten Zoom."""

    def __init__(self, kennzahlen: list[QLabel], status: QLabel) -> None:
        super().__init__()
        self.metric_labels = kennzahlen
        self.run_status = status
        self._plot_settings = None
        self._signal_config = None
        self._angezeigte_flugszene = None
        self._baue_uebersicht()
        self._baue_signalplots()
        self._baue_ergebnistabelle()
        self.route_editor = RoutenEditor()
        self.antennenansicht = AntennenAnsicht()
        self.vergleich = RadarVergleich()
        from .effektansicht import EffektAnsicht
        self.effektansicht = EffektAnsicht()
        from .leistungsansicht import LeistungsAnsicht
        self.leistungsansicht = LeistungsAnsicht()
        self._gruppiere_ansichten()

    def _gruppiere_ansichten(self) -> None:
        overview = QWidget()
        layout = QVBoxLayout(overview)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.graphs, 1)
        self.results_toggle = QCheckBox("Results-Tabelle anzeigen")
        self.results_toggle.setToolTip("Sollwerte, Schätzwerte und Fehler unter der Radarübersicht einblenden.")
        layout.addWidget(self.results_toggle)
        self.results_table.setMinimumHeight(150)
        self.results_table.setMaximumHeight(220)
        layout.addWidget(self.results_table)
        self.results_table.hide()
        self.results_toggle.toggled.connect(self.results_table.setVisible)
        self.overview = overview
        self.gruppen = (
            AnsichtsGruppe((("Radar & Results", overview), ("Route 3D", self.route_editor))),
            AnsichtsGruppe((("Empfang & FFT", self.signal_graphs), ("Power / Energy", self.leistungsansicht))),
            AnsichtsGruppe((("Effektvergleich", self.effektansicht), ("Radarvergleich", self.vergleich))),
        )
        self.addTab(self.gruppen[0], "Simulation")
        self.addTab(self.gruppen[1], "Signale")
        self.addTab(self.antennenansicht, "Antenne")
        self.addTab(self.gruppen[2], "Vergleich")

    def zeige_ansicht(self, widget: QWidget) -> None:
        """Eine konkrete Ansicht öffnen, unabhängig von ihrer Funktionsgruppe."""
        if widget is self.results_table:
            self.results_toggle.setChecked(True)
            widget = self.overview
        if self.indexOf(widget) >= 0:
            self.setCurrentWidget(widget)
            return
        for gruppe in self.gruppen:
            if gruppe.zeige(widget):
                self.setCurrentWidget(gruppe)
                return
        raise ValueError("Unbekannte Ergebnisansicht.")

    def zeige_ergebnis(self, result: FrameResult, elapsed: float) -> None:
        # Qt zeichnet erst wieder, wenn alle Diagramme denselben Frame zeigen.
        ansichten = (self.graphs, self.signal_graphs, self.results_table)
        for ansicht in ansichten:
            ansicht.setUpdatesEnabled(False)
        try:
            self._zeige_daten(result, elapsed)
            self.effektansicht.zeige(result)
            self.leistungsansicht.show_result(result)
        finally:
            for ansicht in ansichten:
                ansicht.setUpdatesEnabled(True)

    def diagramme(self) -> list[tuple[str, pg.PlotItem]]:
        """Alle exportierbaren Diagramme mit festen, verständlichen Dateinamen."""
        return [("effekt_entfernung", self.effektansicht.range_plot), ("effekt_doppler", self.effektansicht.doppler_plot),
                ("range_doppler", self.rd_plot), ("chirp", self.chirp_plot),
                ("beat", self.beat_plot), ("range_spectrum", self.range_plot),
                ("flugbahn", self.flug_plot),
                *[(f"route_{name.lower()}", plot) for name, plot in self.route_editor.plots.items()],
                *self.antennenansicht.diagramme(), *self.leistungsansicht.diagramme()]

    def _baue_uebersicht(self) -> None:
        """Nur Flugfeld und Radarbild: Beide erhalten die volle verfügbare Höhe."""
        self.graphs = pg.GraphicsLayoutWidget()
        self.graphs.setBackground("#101a29")
        self.flug_plot = FlugAnsicht()
        self.graphs.addItem(self.flug_plot, row=0, col=0)
        self.sichtkeule = self.flug_plot.plot([], [], pen=pg.mkPen("#c49b48", width=1),
                                            name="Antennenkeule · −3 dB (Einweg)")
        self.sichtkeule.setZValue(-5)
        self.radar_marker = self.flug_plot.plot([0], [0], pen=None, symbol="t1", symbolSize=14,
                                                symbolBrush="#ffbd59", name="Radar · Tx/Rx")
        self.radar_marker.setZValue(5)
        self.flug_plot.setze_punkte(self.radar_marker, [[0, 0, 0]])
        self.flug_kurven: list[pg.PlotDataItem] = []
        self.flug_punkte: list[pg.PlotDataItem] = []
        self.radar_kurve = self.flug_plot.plot([], [], pen=pg.mkPen("#ffbd59", width=2, style=Qt.PenStyle.DashLine))
        self.boden_marker = self.flug_plot.plot([], [], pen=None, symbol="o", symbolSize=4,
                                               symbolBrush="#8995a5", symbolPen=None)
        self._boden_settings = None
        self._radarort = np.zeros(3)
        self.rd_plot = self.graphs.addPlot(row=0, col=1, title="Range-Doppler · × Soll · ○ Target")
        self.rd_plot.setLabel("bottom", "Scheinentfernung c fb/(2S)", units="m")
        self.rd_plot.setLabel("left", "Geschwindigkeit (+ entfernt)", units="m/s")
        self.rd_plot.setToolTip("Die Karte zeigt Rapp = R + fc·v/S. Kreise benötigen CFAR-Schwellenüberschreitung und ein lokales Maximum. Sie sind mögliche Objekte, keine bestätigten Ziele. Pfa gilt pro geprüfter Zelle; bei Rauschen können zusätzliche Kreise entstehen. Tabelle: korrigierte Entfernung R = c(fb−fd)/(2S).")
        self.image = pg.ImageItem(axisOrder="row-major")
        self.rd_plot.addItem(self.image)
        self.colorbar = pg.ColorBarItem(values=(-90, 5), colorMap=pg.colormap.get("viridis"),
                                       label="10 log10(P / Aref²), Aref=1 [dB]", interactive=False)
        self.colorbar.setImageItem(self.image, insert_in=self.rd_plot)
        self.truth_item = pg.ScatterPlotItem(symbol="x", size=14, pen=pg.mkPen("#ffffff", width=2))
        self.detection_item = pg.ScatterPlotItem(symbol="o", size=17, pen=pg.mkPen("#ffbd59", width=2), brush=None)
        self.rd_plot.addItem(self.truth_item)
        self.rd_plot.addItem(self.detection_item)
        self.rd_plot.showGrid(x=True, y=True, alpha=0.12)
        self.graphs.ci.layout.setColumnStretchFactor(0, 3)
        self.graphs.ci.layout.setColumnStretchFactor(1, 3)

    def _baue_signalplots(self) -> None:
        """Die drei Signalplots bekommen eine eigene Ansicht mit zwei großen Zeilen."""
        self.signal_graphs = pg.GraphicsLayoutWidget()
        self.signal_graphs.setBackground("#101a29")
        self.chirp_plot = self.signal_graphs.addPlot(row=0, col=0, title="TX-Chirps · schematisch")
        self.chirp_plot.setLabel("bottom", "Zeit", units="s")
        self.chirp_plot.setLabel("left", "Frequenzoffset zu fc", units="Hz")
        self.chirp_curve = self.chirp_plot.plot(pen=pg.mkPen("#8ba8ff", width=2))
        self.referenz_im_curve = self.chirp_plot.plot(pen=pg.mkPen("#ffbd59", width=1))
        self.referenz_im_curve.hide()
        self.beat_plot = self.signal_graphs.addPlot(row=0, col=1, title="Beat · erster Chirp, bis zu 160 Samples")
        self.beat_plot.setLabel("bottom", "Zeit innerhalb des Chirps", units="s")
        self.beat_plot.setLabel("left", "Amplitude / Aref")
        self.beat_plot.addLegend(offset=(5, 5))
        self.real_curve = self.beat_plot.plot(pen="#59dcd0", name="Real")
        self.imag_curve = self.beat_plot.plot(pen="#ffbd59", name="Imaginär")
        self.range_plot = self.signal_graphs.addPlot(row=1, col=0, colspan=2, title="Range-Spektrum · Mittel über Chirps")
        self.range_plot.setLabel("bottom", "Scheinentfernung", units="m")
        self.range_plot.setLabel("left", "Leistung / Aref²", units="dB")
        self.range_curve = self.range_plot.plot(pen=pg.mkPen("#59dcd0", width=2))
        for plot in (self.chirp_plot, self.beat_plot, self.range_plot):
            plot.showGrid(x=True, y=True, alpha=0.12)

    def _baue_ergebnistabelle(self) -> None:
        """Soll und Schätzung vergleichen, ohne den Diagrammen Platz wegzunehmen."""
        self.results_table = QTableWidget(0, 9)
        self.results_table.setHorizontalHeaderLabels(["Zuordnung", "R Soll / m", "R Ist / m", "ΔR / m", "v Soll / m/s", "v Ist / m/s", "Δv / m/s", "P / Aref² [dB]", "Über Schwelle / dB"])
        self.results_table.horizontalHeaderItem(8).setToolTip("10 log10(P / CFAR-Schwelle). Auch ein knapp über der Schwelle liegender Rauschpeak kann ein Fehlalarm sein.")
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setToolTip("Die Entfernung ist um den Doppleranteil korrigiert. Extra Targets sind keinem Sollobjekt zugeordnet und können Fehlalarme sein. Alle Werte gehören zum zuletzt berechneten Frame.")

    def zeige_antenne(self, config: RadarConfig) -> None:
        self.vergleich.zeige_config(config)
        a = config.antenne
        if (a, config.carrier_hz) == getattr(self, "_sichtkeule_config", None):
            return
        p = keulenlinien(a, config.carrier_hz, ringe=(.25, .5, .75, 1.), mantellinien=8)
        self._keulenpunkte = p
        self.flug_plot.setze_punkte(self.sichtkeule, p+self._radarort)
        self.route_editor.zeige_antenne(a, config.carrier_hz)
        self.antennenansicht.zeige_antenne(a, config.carrier_hz)
        self.flug_plot.rahmen_aktualisieren()
        self._sichtkeule_config = (a, config.carrier_hz)

    def _zeige_daten(self, result: FrameResult, elapsed: float) -> None:
        if result.config.radar_mode == "passive":
            self._zeige_passiv(result, elapsed)
            return
        c, s = result.config, result.spectrum
        if hasattr(self, "sender_marker"):
            self.sender_marker.hide()
            self.flug_plot.setze_punkte(self.sender_marker, np.empty((0, 3)), rahmen=False)
            self.flug_plot.legend.removeItem(self.sender_marker)
            self._sender_legende = False
            self.flug_plot.setze_punkte(self.bistatische_wege, np.empty((0, 3)), rahmen=False)
        if getattr(self, "_rx_passiv", False):
            self.flug_plot.legend.removeItem(self.radar_marker)
            self.flug_plot.legend.addItem(self.radar_marker, "Radar · Tx/Rx")
            self._rx_passiv = False
        self.referenz_im_curve.hide()
        self.chirp_plot.setLabel("bottom", "Zeit", units="s")
        self.chirp_plot.setLabel("left", "Frequenzoffset zu fc", units="Hz")
        self.results_table.setHorizontalHeaderLabels(["Zuordnung", "R Soll / m", "R Ist / m", "ΔR / m", "v Soll / m/s", "v Ist / m/s", "Δv / m/s", "P / Aref² [dB]", "Über Schwelle / dB"])
        puls = c.radar_mode == "pulse_doppler"
        self.metric_labels[0].setText(f"ΔR nominal  {c.range_resolution:.3f} m\nΔv nominal  {c.velocity_resolution:.3f} m/s")
        safe_range = c.apparent_range_limit - c.carrier_hz * c.max_velocity / c.slope
        timing_range = c.timing_range_limit
        model_velocity = min(c.max_velocity, 0.25 * c.range_resolution / (c.chirps * c.repetition_s))
        self.metric_labels[1].setText(f"|v rel| < {c.max_velocity:.2f} m/s · Modell ≤ {model_velocity:.2f}\n" +
            (f"{0 if c.effekte.teilpulse else c.minimum_range_m:.1f} ≤ R ≤ {timing_range:.1f} m · {'Teilpulse' if c.effekte.teilpulse else 'Vollpulse'}" if puls else f"R < {min(safe_range, timing_range):.1f} m (alle v, Timinglimit)"))
        self.metric_labels[1].setToolTip(f"|2SR/c + 2v/λ| < fs/2. ADC-Start {c.adc_start_s*1e6:g} µs, Messfenster {c.adc_duration_s*1e6:g} µs, {c.samples} Samples. Mit Vorlauf muss das Echo bis zum ADC-Start da sein, sonst gilt das alte 2,5-%-Nahmodell. Wanderung ≤ ¼ ΔR/Frame.")
        zeittext = f"Flugzeit {result.zeit_s:.1f} s" if result.flugzustaende else f"Messpaket {result.frame_index}"
        self.metric_labels[2].setText(f"{len(c.targets)} Soll · {len(result.candidates)} Targets\n{zeittext}")
        self.metric_labels[2].setToolTip(
            "Targets sind CFAR-Peaks und können Fehlalarme sein. Diagramme und Exporte gehören zum letzten berechneten Frame.\n"
            f"CFAR: {result.cfar.training_cells} Trainingszellen, Faktor α = {result.cfar.alpha:.3f}.\n"
            + "\n".join(result.warnings))
        self.metric_labels[0].setToolTip("ΔR=c/(2·S·Tadc), Δv=λ/(2MTr): nominell für Rechteck. Der ADC-Vorlauf verkürzt Tadc und die beobachtete Bandbreite. Hann hat ca. doppelte erste-Nullstellen-Breite. Kein Zero-Padding.")
        if puls:
            self.metric_labels[0].setToolTip(f"LFM-Puls: ΔR=c/(2B)={c.range_resolution:.4g} m; ADC-Binabstand c/(2fs)={c.range_bin_m:.4g} m. Δv=λ/(2MTr). Hann am Kompressionsfilter verbreitert das Maximum. Keine Auflösungsverbesserung durch FFT-Nullauffüllen.")
            self.metric_labels[1].setToolTip(f"Theoretisch eindeutige Laufzeit: R<c·Tr/2={c.apparent_range_limit:.1f} m. Voller Empfang nur c·Tp/2≤R≤c·(Tr−Tp)/2. Tastgrad Tp/Tr={100*c.chirp_s/c.repetition_s:.3g} %. Maximale eindeutige Relativgeschwindigkeit λ/(4Tr). Keine Entfaltung mehrdeutiger Ziele.")
        self.image.setImage(power_db(s.power), autoLevels=False)
        dx = c.range_bin_m
        dy = c.velocity_resolution
        einstellungen = (c.radar_mode, c.carrier_hz, c.bandwidth_hz, c.chirp_s, c.repetition_s, c.sample_rate_hz, c.chirps, c.adc_skip_samples, c.effekte.teilpulse)
        radar_geaendert = einstellungen != self._plot_settings
        if radar_geaendert:
            self.image.setRect(QRectF(s.apparent_range_m[0] - dx / 2, s.velocity_mps[0] - dy / 2,
                                     dx * len(s.apparent_range_m), dy * c.chirps))
            self.rd_plot.setLabel("bottom", "Scheinentfernung nach Pulskompression" if puls else "Scheinentfernung c fb/(2S)", units="m")
            self.rd_plot.setLabel("left", "Radialgeschwindigkeit relativ zum Radar (+ entfernt)", units="m/s")
            self.rd_plot.setToolTip("LFM-Puls: lineare Pulskompression und Doppler-FFT. Rapp≈R+c·fd/(2S); Tabelle korrigiert die LFM-Kopplung. Die Antenne misst keine Winkel. CFAR-Pfa ist durch korrelierte Filterzellen nominell." if puls else "FMCW: Range-FFT und Doppler-FFT. Rapp=R+fc·v/S; Tabelle korrigiert die Kopplung. CFAR-Targets können Fehlalarme sein.")
            self.rd_plot.setXRange(float(s.apparent_range_m[0]), float(s.apparent_range_m[-1]), padding=0)
            self.range_plot.setRange(xRange=(float(s.apparent_range_m[0]), float(s.apparent_range_m[-1])),
                                     yRange=(-100, 10), padding=0)
            self.beat_plot.disableAutoRange()
            self.chirp_plot.setRange(xRange=(0, 2 * c.repetition_s + c.chirp_s),
                                     yRange=((-c.bandwidth_hz/2, c.bandwidth_hz/2) if puls else (0, c.bandwidth_hz)), padding=0.05)
            zeiten, frequenzen = [], []
            for index in range(3):
                zeiten.extend([index * c.repetition_s, index * c.repetition_s + c.chirp_s, np.nan])
                frequenzen.extend([-c.bandwidth_hz/2 if puls else 0, c.bandwidth_hz/2 if puls else c.bandwidth_hz, np.nan])
            self.chirp_curve.setData(zeiten, frequenzen, connect="finite")
            self.chirp_plot.setTitle(f"{'LFM-Sendepulse' if puls else 'Sendechirps'} · schematisch · fc={c.carrier_hz / 1e9:g} GHz")
            self.beat_plot.setTitle("RX* · erster Puls, Empfang während Senden gesperrt" if puls else "Beat · erster Chirp, bis zu 160 Samples")
            self.range_plot.setTitle("Pulskompression · Leistungsmittel über Pulse" if puls else "Range-Spektrum · Mittel über Chirps")
            self.beat_plot.setLabel("bottom", "Zeit im Pulsintervall" if puls else "Zeit innerhalb des Chirps", units="s")
            self.beat_plot.setToolTip("Konjugierter Basisbandempfang vor Pulskompression, kein dechirptes FMCW-Signal. Während Tp sind Signal und Rauschen gesperrt. Referenzamplitude 1 gilt während eines Echos." if puls else "Komplexes FMCW-Beat-Signal nach tx·conj(rx). Referenzamplitude Aref=1.")
            self._plot_settings = einstellungen
        if radar_geaendert or result.input_config != self._signal_config:
            # Über die ganze Szene stabil: kein Springen der Achse pro Frame.
            # Die FFT-Achse selbst bleibt λ/(2*M*Tr); wir wählen nur den Ausschnitt.
            geschwindigkeiten = [abs(t.velocity_mps) for t in c.targets]
            szene = result.input_config.flugszene
            if szene is not None:
                for bahn in szene.bahnen:
                    # Sichere Schranke: |v_radial| <= Flugtempo, auch zwischen Frames.
                    geschwindigkeiten.append(relative_bahngrenzen(bahn, szene).tempo_max_mps)
                if c.effekte.bodenclutter and szene.radar_bahn is not None:
                    geschwindigkeiten.append(grenzen_der_flugbahn(szene.radar_bahn, szene.dauer_s).tempo_max_mps)
            if c.effekte.phasenrauschen or c.effekte.saettigung:
                geschwindigkeiten.append(c.max_velocity)
            v_max = max(geschwindigkeiten, default=0.)
            grenze = min(c.max_velocity, max(4*dy, 1.15*v_max+2*dy))
            self.rd_plot.setYRange(-grenze, grenze, padding=0)
        if result.input_config != self._signal_config:
            # Die Skala passt zur gesamten Szene, nicht zum zufälligen Maximum
            # jedes Frames. So bleibt die Darstellung auch bei Rauschen ruhig.
            amplitude_grenze = sum(target_amplitude(c, ziel) for ziel in c.targets)
            szene = result.input_config.flugszene
            if szene is not None:
                amplitude_grenze = 0.0
                for bahn in szene.bahnen:
                    zustaende = [relativer_zustand(bahn, szene.radar_bahn, float(t)) for t in np.linspace(0, szene.dauer_s, 201)]
                    kleinste_entfernung = min(z.entfernung_m for z in zustaende)
                    amplitude_grenze += target_amplitude(c, Target(kleinste_entfernung, strength=bahn.staerke))
            amplitude_grenze += np.sqrt(result.echo.leakage_power)
            amplitude_grenze += np.sqrt(result.echo.clutter_power*c.effekte.clutter_ringe*c.effekte.clutter_sektoren)
            if c.effekte.saettigung:
                amplitude_grenze = min(amplitude_grenze, 10**(c.effekte.saettigung_db/20))
            rauschanteil = 4 * np.sqrt(result.echo.noise_power / 2)
            signal_grenze = max(0.1, amplitude_grenze + rauschanteil)
            self.beat_plot.setYRange(-signal_grenze, signal_grenze, padding=0.05)
            spitze_db = 20 * np.log10(max(amplitude_grenze, np.sqrt(result.echo.noise_power), 0.01))
            self.range_plot.setYRange(min(-100, spitze_db - 100), max(10, spitze_db + 6), padding=0)
            obergrenze = max(5, 10*np.ceil(spitze_db/10)) if c.effekte.leakage or c.effekte.bodenclutter or c.tx_peak_db else 5
            self.colorbar.setLevels((-90, obergrenze))
            self._signal_config = result.input_config
        self.truth_item.setData([t.range_m + c.carrier_hz * t.velocity_mps / c.slope for t in c.targets],
                                [t.velocity_mps for t in c.targets])
        self.detection_item.setData([d.apparent_range_m for d in result.candidates], [d.velocity_mps for d in result.candidates])
        count = c.samples if puls else min(160, c.samples)
        if radar_geaendert:
            self.beat_plot.setXRange(result.echo.fast_time_s[0], result.echo.fast_time_s[count - 1], padding=0.02)
        self.real_curve.setData(result.echo.fast_time_s[:count], result.echo.beat[0, :count].real)
        self.imag_curve.setData(result.echo.fast_time_s[:count], result.echo.beat[0, :count].imag)
        self.range_curve.setData(s.apparent_range_m, power_db(s.range_power))
        self._zeige_tabelle(result)
        self.zeige_antenne(c)
        self._zeige_flug(result)
        self.route_editor.zeige_szene(result.input_config.flugszene, result.flugzustaende, c.antenne, c.carrier_hz, result.radar_zustand)
        self.run_status.setText(f"Frame {result.frame_index} · {elapsed * 1000:.0f} ms")

    def _zeige_passiv(self, result: FrameResult, elapsed: float) -> None:
        """Passive Größen ausdrücklich als Umweg und Wegänderungsrate anzeigen."""
        c, s = result.config, result.spectrum
        kanal = result.passiv_empfang
        self.metric_labels[0].setText(f"ΔUmweg nominal {c.range_resolution:.2f} m\nΔWegänderungsrate {c.velocity_resolution:.3f} m/s")
        self.metric_labels[0].setToolTip("Passiv: c/B und λ/T; keine monostatischen Faktoren 1/2. Umweg-Raster c/fs; keine XYZ-Lokalisierung.")
        self.metric_labels[1].setText(f"Umweg 0…{c.timing_range_limit/1000:.1f} km\nDoppler-Suche |dΔL/dt| < {c.max_velocity:.1f} m/s")
        self.metric_labels[1].setToolTip("Empfänger sendet nicht. Fester Fremdsender und Rx im Ursprung. Der angezeigte Dopplerbereich ist ein begrenztes Suchraster, keine Puls-PRF und keine fundamentale passive Aliasinggrenze. Integration T=M·Tr.")
        self.metric_labels[2].setText(f"Passivradar · {len(c.targets)} Soll · {len(result.candidates)} Targets\nFlugzeit {result.zeit_s:.1f} s")
        self.metric_labels[2].setToolTip("\n".join(result.warnings))
        self.image.setImage(power_db(s.power), autoLevels=False)
        key = ("passive", result.input_config)
        if key != self._plot_settings:
            obergrenze = max(5, 10*np.ceil(float(power_db(s.power).max())/10)) if c.effekte.bodenclutter else 5
            self.colorbar.setLevels((-90, obergrenze))
            dx, dy = c.range_bin_m, c.velocity_resolution
            self.image.setRect(QRectF(-dx/2, s.velocity_mps[0]-dy/2, dx*c.range_bins, dy*c.chirps))
            self.rd_plot.setXRange(0, c.timing_range_limit, padding=0)
            self.rd_plot.setYRange(-c.max_velocity, c.max_velocity, padding=0)
            self.range_plot.setXRange(0, c.timing_range_limit, padding=0)
            self.range_plot.setYRange(-100, 65, padding=0)
            self.rd_plot.setLabel("bottom", "Bistatischer Umweg ΔL", units="m")
            self.rd_plot.setLabel("left", "Wegänderungsrate dΔL/dt (+ Weg wächst)", units="m/s")
            self.rd_plot.setToolTip("CAF aus Referenz- und Überwachungskanal. ΔL=Rt+Rr−Basislinie, Rate=λf. Die Karte ist keine monostatische Entfernung-/Radialgeschwindigkeitsmessung. CFAR-Pfa ist nominell.")
            self.range_plot.setTitle("Passiv · CAF-Maximum über den Doppler-Suchbereich")
            self.range_plot.setLabel("bottom", "Bistatischer Umweg", units="m")
            self.chirp_plot.setTitle("Referenzkanal · Real blau, Imaginär orange · optional LO-/Begrenzungseffekte")
            self.chirp_plot.setLabel("bottom", "Zeit im Referenzausschnitt", units="s")
            self.chirp_plot.setLabel("left", "Amplitude / Aref")
            self.beat_plot.setTitle("Überwachung* · Real und Imaginär, vor Direktweg-Projektion")
            self.beat_plot.setLabel("bottom", "Zeit im Empfangsausschnitt", units="s")
            self._plot_settings = key
        n = min(1000, len(kanal.referenz))
        t = np.arange(n)/c.sample_rate_hz
        self.chirp_curve.setData(t, kanal.referenz[:n].real)
        self.referenz_im_curve.setData(t, kanal.referenz[:n].imag)
        self.referenz_im_curve.show()
        self.real_curve.setData(t, kanal.ueberwachung[:n].real)
        self.imag_curve.setData(t, -kanal.ueberwachung[:n].imag)
        if result.input_config != self._signal_config:
            for plot in (self.chirp_plot, self.beat_plot):
                plot.enableAutoRange()
            self._signal_config = result.input_config
        self.range_curve.setData(s.apparent_range_m, power_db(s.range_power))
        self.truth_item.setData([t.range_m for t in c.targets], [t.velocity_mps for t in c.targets])
        self.detection_item.setData([d.range_m for d in result.candidates], [d.velocity_mps for d in result.candidates])
        self.results_table.setHorizontalHeaderLabels(["Zuordnung", "ΔL Soll / m", "ΔL Ist / m", "Fehler ΔL / m", "Rate Soll / m/s", "Rate Ist / m/s", "Fehler Rate / m/s", "CAF / Aref² [dB]", "Über Schwelle / dB"])
        self._zeige_tabelle(result)
        self.zeige_antenne(c)
        self._zeige_flug(result)
        self.flug_plot.setTitle("Passivradar · bekannte Tx-/Rx-/Target-Geometrie")
        if not hasattr(self, "sender_marker"):
            self.sender_marker = self.flug_plot.plot([], [], pen=None, symbol="star", symbolBrush="#ff85b0", symbolSize=18, name="Fremdsender · Tx")
            self.bistatische_wege = self.flug_plot.plot([], [], pen=pg.mkPen("#887a95", width=1, style=Qt.PenStyle.DashLine))
            self._sender_legende = True
        if not self._sender_legende:
            self.flug_plot.legend.addItem(self.sender_marker, "Fremdsender · Tx")
            self._sender_legende = True
        self.sender_marker.show()
        if not getattr(self, "_rx_passiv", False):
            self.flug_plot.legend.removeItem(self.radar_marker)
            self.flug_plot.legend.addItem(self.radar_marker, "Passiver Empfänger · Rx")
            self._rx_passiv = True
        self.flug_plot.setze_punkte(self.sender_marker, [c.passiv.senderort])
        rx = [0., 0., c.effekte.stationshoehe_m]
        wege = [rx, c.passiv.senderort]
        for ziel in result.flugzustaende:
            wege.extend([ziel.position_m, rx, [np.nan]*3, c.passiv.senderort])
        self.flug_plot.setze_punkte(self.bistatische_wege, wege, rahmen=False)
        if c.passiv.senderort != getattr(self, "_senderort", None):
            self.flug_plot.rahmen_aktualisieren()
            self._senderort = c.passiv.senderort
        self.route_editor.zeige_szene(result.input_config.flugszene, result.flugzustaende, c.antenne, c.carrier_hz)
        self.run_status.setText(f"Passivradar · Frame {result.frame_index} · {elapsed*1000:.0f} ms")

    def _zeige_flug(self, result: FrameResult) -> None:
        """Die Bahn einmal zeichnen. Danach bewegen wir nur die Objektpunkte."""
        szene = result.input_config.flugszene
        if self.route_editor.aktiv:
            return
        if szene != self._angezeigte_flugszene:
            for kurve in self.flug_kurven + self.flug_punkte:
                self.flug_plot.entferne(kurve)
            self.flug_kurven.clear()
            self.flug_punkte.clear()
            self.flug_plot.fokus_objekte = []
            ueberflug = False
            if szene is not None:
                self.flug_plot.setTitle("Flugbahn · XYZ")
                farben = ("#59dcd0", "#ffbd59", "#8ba8ff", "#ff85b0")
                for nummer, bahn in enumerate(szene.bahnen):
                    punkte_xyz = flugbahn_punkte(bahn, szene.dauer_s)
                    horizontal = punkte_xyz[:, :2]
                    # Beim direkten Überflug liegt die Bodenprojektion nahe am
                    # Radar. Etwas Reserve berücksichtigt die Zeichenabtastung.
                    abstand = np.linalg.norm(horizontal, axis=1).min()
                    toleranz = max(1., .02*float(np.ptp(horizontal, axis=0).max()))
                    ueberflug = ueberflug or abstand <= toleranz
                    farbe = farben[nummer % len(farben)]
                    name = f"Target {nummer + 1}" if bahn.route is None else f"Target {nummer + 1} · eigene Route"
                    kurve = self.flug_plot.plot(pen=pg.mkPen(farbe, width=2), name=name)
                    self.flug_plot.setze_punkte(kurve, punkte_xyz)
                    self.flug_kurven.append(kurve)
                    self.flug_punkte.append(self.flug_plot.plot([], [], pen=None, symbol="o", symbolSize=12,
                                                               symbolBrush=farbe, symbolPen="#ffffff"))
            self.flug_plot.fokus_objekte = list(self.flug_kurven) if ueberflug else []
            self.flug_plot.legend.removeItem(self.radar_kurve)
            if szene is not None and szene.radar_bahn is not None:
                self.flug_plot.setTitle("Air-to-Air · bekannte Weltpositionen, Radar bewegt")
                self.flug_plot.legend.addItem(self.radar_kurve, "Radarflugzeug · Bahn")
                self.flug_plot.setze_punkte(self.radar_kurve, flugbahn_punkte(szene.radar_bahn, szene.dauer_s))
                self.flug_plot.fokus_objekte = [*self.flug_kurven, self.radar_kurve]
            else:
                self.flug_plot.setze_punkte(self.radar_kurve, np.empty((0, 3)))
            self.flug_plot.rahmen_aktualisieren()
            self._angezeigte_flugszene = szene
        if szene is None:
            self.flug_plot.setTitle("XYZ · keine Flugroute (siehe Targets)")
        else:
            for punkt, zustand in zip(self.flug_punkte, result.flugzustaende):
                self.flug_plot.setze_punkte(punkt, [zustand.position_m], rahmen=False)
        self._radarort = np.array(result.radar_zustand.position_m if result.radar_zustand else (0., 0., 0.))
        self._radarort[2] += result.input_config.effekte.stationshoehe_m
        self.flug_plot.setze_punkte(self.radar_marker, [self._radarort], rahmen=False)
        if hasattr(self, "_keulenpunkte"):
            self.flug_plot.setze_punkte(self.sichtkeule, self._keulenpunkte+self._radarort, rahmen=result.radar_zustand is None)
        e = result.input_config.effekte
        boden_settings = (e.bodenclutter, e.clutter_innen_m, e.clutter_aussen_m,
                          e.clutter_ringe, e.clutter_sektoren, result.input_config.seed)
        if boden_settings != self._boden_settings:
            from .bodenclutter import bodenpunkte
            if e.bodenclutter:
                if not self._boden_settings or not self._boden_settings[0]:
                    self.flug_plot.legend.addItem(self.boden_marker, "Bodenstreuer · Modell")
                punkte = np.array([q[0] for q in bodenpunkte(result.input_config)])
                if self.flug_plot.fokus_objekte and self.boden_marker not in self.flug_plot.fokus_objekte:
                    self.flug_plot.fokus_objekte.append(self.boden_marker)
            else:
                punkte = np.empty((0, 3))
                if self._boden_settings and self._boden_settings[0]:
                    self.flug_plot.legend.removeItem(self.boden_marker)
            self.flug_plot.setze_punkte(self.boden_marker, punkte)
            self._boden_settings = boden_settings

    def _zeige_tabelle(self, result: FrameResult) -> None:
        matches = match_targets(result.config, result.candidates)
        by_target = {m.target_index: m for m in matches}
        used = {m.candidate_index for m in matches}
        rows = []
        for ti, target in enumerate(result.config.targets):
            match = by_target.get(ti)
            if match:
                candidate = result.candidates[match.candidate_index]
                rows.append([f"Target {ti + 1}", target.range_m, candidate.range_m, match.range_error_m,
                             target.velocity_mps, candidate.velocity_mps, match.velocity_error_mps,
                             10 * np.log10(max(candidate.power, 1e-16)),
                             10 * np.log10(candidate.power / candidate.threshold)])
            else:
                rows.append([f"Target {ti + 1}: fehlt", target.range_m, "—", "—", target.velocity_mps, "—", "—", "—", "—"])
        for ci, candidate in enumerate(result.candidates):
            if ci not in used:
                rows.append(["Extra Target", "—", candidate.range_m, "—", "—", candidate.velocity_mps, "—",
                             10 * np.log10(max(candidate.power, 1e-16)),
                             10 * np.log10(candidate.power / candidate.threshold)])
        if self.results_table.rowCount() != len(rows):
            self.results_table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            for ci, value in enumerate(row):
                text = value if isinstance(value, str) else f"{value:.4f}"
                item = self.results_table.item(ri, ci)
                if item is None:
                    self.results_table.setItem(ri, ci, QTableWidgetItem(text))
                elif item.text() != text:
                    item.setText(text)
