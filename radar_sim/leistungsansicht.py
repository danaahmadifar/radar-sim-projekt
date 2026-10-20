"""Sendehüllkurven vergleichen und echte Pulskompression sichtbar machen."""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDoubleSpinBox

from .config import C
from .pipeline import FrameResult
from .sendeleistung import compare_power


class LeistungsAnsicht(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.result: FrameResult | None = None
        self._settings = None
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Vergleich:"))
        self.normalization = QComboBox()
        self.normalization.addItems(["Gleiche mittlere Leistung", "Gleiche Spitzenleistung"])
        self.normalization.setToolTip("Die gewählte Normierung passt nur den Vergleichssender an. TX Peak unter Radar bestimmt die tatsächlich simulierten Echos.")
        controls.addWidget(self.normalization)
        self.duty_label = QLabel("Puls-Referenz: Tastgrad / %")
        controls.addWidget(self.duty_label)
        self.reference_duty = QDoubleSpinBox()
        self.reference_duty.setRange(.1, 100)
        self.reference_duty.setValue(10)
        self.reference_duty.setSuffix(" %")
        self.reference_duty.setToolTip("Nur bei aktivem FMCW: Sendezeit der hypothetischen Puls-Referenz relativ zum PRI. Die tatsächlichen Radarparameter bleiben erhalten.")
        controls.addWidget(self.reference_duty)
        controls.addStretch()
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.graphs = pg.GraphicsLayoutWidget()
        self.graphs.setBackground("#101a29")
        layout.addWidget(self.graphs, 1)
        self.plots = []
        for row, col, title, ylabel in (
            (0, 0, "FMCW", "Leistung P/P0"),
            (0, 1, "Puls-Doppler", "Leistung P/P0"),
            (1, 0, "Aufsummierte Sendeenergie · erste drei PRI", "Energie / (P0·µs)"),
            (1, 1, "Empfang vor und nach Pulskompression", "Leistung / Aref²"),
        ):
            plot = self.graphs.addPlot(row=row, col=col, title=title)
            plot.setLabel("bottom", "Zeit", units="s")
            plot.setLabel("left", ylabel)
            plot.showGrid(x=True, y=True, alpha=.12)
            self.plots.append(plot)
        self.fmcw_plot, self.pulse_plot, self.energy_plot, self.compression_plot = self.plots
        self.pulse_plot.setXLink(self.fmcw_plot)
        self.pulse_plot.setYLink(self.fmcw_plot)
        self.energy_plot.setXLink(self.fmcw_plot)
        self.fmcw_curve = self.fmcw_plot.plot(pen=pg.mkPen("#59dcd0", width=2), fillLevel=0, brush=(89, 220, 208, 65))
        self.pulse_curve = self.pulse_plot.plot(pen=pg.mkPen("#ffbd59", width=2), fillLevel=0, brush=(255, 189, 89, 90))
        self.energy_plot.addLegend(offset=(8, 8))
        self.fmcw_energy = self.energy_plot.plot(pen=pg.mkPen("#59dcd0", width=2), name="FMCW")
        self.pulse_energy = self.energy_plot.plot(pen=pg.mkPen("#ffbd59", width=2), name="Puls-Doppler")
        self.compression_plot.addLegend(offset=(8, 8))
        self.rx_curve = self.compression_plot.plot(pen="#8ba8ff", name="RX · erster Puls")
        self.compressed_curve = self.compression_plot.plot(pen=pg.mkPen("#ffbd59", width=2), name="Matched Filter")
        self.compression_plot.setToolTip("Tatsächlicher erster Empfangsblock und Filterausgang aus dem Worker. Filter durch Summe der Gewichte normiert: kein künstlicher Peak-Gain. Ausgangsfläche ist keine Sendeenergie. Bei Null-Doppler-Abzug zeigt der Filter das bereinigte Signal.")
        self.energy_plot.setToolTip("Integral der Sendeleistung. Gleiche mittlere Leistung und gleiche Frame-Dauer ergeben gleiche Frame-Energie. P0 ist relativ, keine Watt- oder Jouleangabe.")
        self.normalization.currentIndexChanged.connect(self._refresh)
        self.reference_duty.valueChanged.connect(self._refresh)

    def _refresh(self) -> None:
        if self.result is not None:
            self._show_power()

    def show_result(self, result: FrameResult) -> None:
        self.result = result
        self._show_power()
        c = result.config
        compressed = result.spectrum.compressed_first
        if c.radar_mode == "pulse_doppler" and compressed is not None:
            self.rx_curve.setData(result.echo.fast_time_s, np.abs(result.echo.beat[0])**2)
            self.compressed_curve.setData(2*result.spectrum.apparent_range_m/C, np.abs(compressed)**2)
            self.compression_plot.setTitle("RX & Matched Filter · erster Puls · Aref²=1")
        else:
            self.rx_curve.setData([], [])
            self.compressed_curve.setData([], [])
            self.compression_plot.setTitle("Pulskompression: im Puls-Doppler-Modus sichtbar")

    def _show_power(self) -> None:
        c = self.result.config
        active = c.radar_mode != "passive"
        self.normalization.setEnabled(active)
        for field in (self.duty_label, self.reference_duty):
            field.setVisible(c.radar_mode == "fmcw")
        if not active:
            self.summary.setText("Passivradar sendet nicht. Kein eigenes TX-Leistungsbudget; der Fremdsender bleibt separat modelliert.")
            self.fmcw_plot.setTitle("FMCW · kein eigener Sender im passiven Modus")
            self.pulse_plot.setTitle("Puls-Doppler · kein eigener Sender im passiven Modus")
            for curve in (self.fmcw_curve, self.pulse_curve, self.fmcw_energy, self.pulse_energy):
                curve.setData([], [])
            self._settings = None
            return
        equal_average = self.normalization.currentIndex() == 0
        actual, reference = compare_power(c, self.reference_duty.value()/100, equal_average)
        fmcw, pulse = (reference, actual) if c.radar_mode == "pulse_doppler" else (actual, reference)
        key = (c.radar_mode, actual, reference)
        if key == self._settings:
            return
        self._settings = key
        rows = []
        for name, budget, curve, energy_curve in (
            ("FMCW", fmcw, self.fmcw_curve, self.fmcw_energy),
            ("Puls-Doppler", pulse, self.pulse_curve, self.pulse_energy),
        ):
            label = "simulierter Sender" if budget is actual else "Vergleichsreferenz"
            t, p, e = budget.waveform()
            curve.setData(t, p)
            energy_curve.setData(t, e*1e6)
            plot = self.fmcw_plot if name == "FMCW" else self.pulse_plot
            plot.setTitle(f"{name} · {label}<br>aktiv {budget.duration_s*1e6:.3g} µs · "
                          f"Pause {(budget.interval_s-budget.duration_s)*1e6:.3g} µs · PRI {budget.interval_s*1e6:.3g} µs")
            rows.append(f"<tr><td>{name} ({label})</td><td>{budget.peak:.4g}</td><td>{budget.average:.4g}</td>"
                        f"<td>{100*budget.duty_cycle:.3g} %</td><td>{budget.pulse_energy*1e6:.4g}</td><td>{budget.frame_energy*1e6:.4g}</td></tr>")
        self.summary.setText("<table cellspacing='6'><tr><th>Sender</th><th>Peak / P0</th><th>Mittel / P0</th>"
                             "<th>Tastgrad</th><th>E je Chirp/Puls / (P0·µs)</th><th>E je Frame / (P0·µs)</th></tr>"
                             + "".join(rows) + "</table>Fläche = Energie. P0 ist eine feste relative Referenz, keine Wattangabe. "
                             "Die Referenz vergleicht nur das Sendebudget, keine Detektionsreichweite. "
                             "Pulsdauer und Pause stehen oben; TX Peak unter Radar beeinflusst die echten Echos.")
        self.fmcw_plot.setYRange(0, max(fmcw.peak, pulse.peak)*1.15, padding=0)
        self.fmcw_plot.setXRange(0, min(3, c.chirps)*c.repetition_s, padding=.01)
        self.energy_plot.enableAutoRange(axis='y')

    def diagramme(self) -> list[tuple[str, pg.PlotItem]]:
        return list(zip(("tx_fmcw_power", "tx_pulse_power", "tx_energy", "pulse_compression"), self.plots))
