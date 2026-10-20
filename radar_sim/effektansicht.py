"""Direkter Spektrenvergleich; die Referenz wird nicht zur Detektion verwendet."""

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from .processing import power_db


class EffektAnsicht(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.info = QLabel("Ein Effektbeispiel im linken Tab Effekte laden.")
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        grafik = pg.GraphicsLayoutWidget()
        grafik.setBackground("#101a29")
        layout.addWidget(grafik)
        self.range_plot = grafik.addPlot(row=0, col=0, title="Maximum der Kartenleistung je Entfernung / Umweg")
        self.doppler_plot = grafik.addPlot(row=1, col=0, title="Maximum der Kartenleistung je Dopplerbin")
        self.kurven = []
        for plot in (self.range_plot, self.doppler_plot):
            plot.addLegend()
            plot.showGrid(x=True, y=True, alpha=.15)
            plot.setLabel("left", "10 log10(P / Aref²)", units="dB")
            ideal = plot.plot(pen=pg.mkPen("#95a5bd", width=2), name="Ohne zuschaltbare Störungen")
            echt = plot.plot(pen=pg.mkPen("#f9bd60", width=2), name="Aktuelle Simulation")
            self.kurven.append((ideal, echt))

    def zeige(self, result):
        c, e = result.input_config, result.input_config.effekte
        aktiv = [titel for name, titel in (("leakage", "Leakage"), ("saettigung", "Sättigung"),
                 ("phasenrauschen", "Phasenrauschen"), ("erdkruemmung", "Erdkrümmung"),
                 ("atmosphaere", "Atmosphäre"), ("bodenclutter", "Bodenclutter")) if getattr(e, name)]
        text = "Aktiv: "+(", ".join(aktiv) if aktiv else "keine zuschaltbaren Störungen")
        text += f". Begrenzt: {100*result.echo.clipped_fraction:.2f} % der Empfangssamples."
        if result.passiv_empfang:
            text += f" Referenzkanal: {100*result.passiv_empfang.reference_clipped_fraction:.2f} %."
        text += " Gleiche Wellenform, Seed und Masthöhe; die Puls-Empfangssperre bleibt auch im Vergleich aktiv. Maxima sind keine Target-SNR-Schätzung."
        if e.erdkruemmung:
            text += " XYZ zeigt Kartenkoordinaten; Sichtgrenze, Laufweg und Doppler werden auf der effektiven Kugel berechnet."
        self.info.setText(text)
        self.range_plot.setLabel("bottom", "Bistatischer Umweg ΔL" if c.radar_mode == "passive" else "Scheinentfernung", units="m")
        self.doppler_plot.setLabel("bottom", "Wegänderungsrate" if c.radar_mode == "passive" else "Radiale Geschwindigkeit", units="m/s")
        for plot_nr, achse in enumerate(("apparent_range_m", "velocity_mps")):
            ideal, aktuell = self.kurven[plot_nr]
            for spektrum, kurve in ((result.vergleich, ideal), (result.spectrum, aktuell)):
                if spektrum is None:
                    kurve.setData([], [])
                else:
                    power = np.max(spektrum.power, axis=0 if plot_nr == 0 else 1)
                    kurve.setData(getattr(spektrum, achse), power_db(power))
