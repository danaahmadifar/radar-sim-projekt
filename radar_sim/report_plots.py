"""PNG-Export mit demselben pyqtgraph wie in der Desktop-Anwendung."""

from pathlib import Path
import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter

from .pipeline import FrameResult
from .processing import power_db
from .qt_support import ensure_font


def export_plot(item: pg.PlotItem, path: str | Path) -> None:
    exporter = ImageExporter(item)
    exporter.parameters()["width"] = 1400
    exporter.export(str(path))


def _plotfenster(breite: int = 1100, hoehe: int = 650):
    """Öffnet ein einfaches Berichtsfenster und stellt die Schrift bereit."""
    app = QApplication.instance() or QApplication([])
    ensure_font(app)
    fenster = pg.PlotWidget()
    fenster.resize(breite, hoehe)
    fenster.show()
    return app, fenster, fenster.getPlotItem()


def export_report_plots(path: Path, frame: FrameResult, sweep: list[dict], noise: list[dict]) -> None:
    pg.setConfigOptions(antialias=True, background="#101a29", foreground="#dce7f5", imageAxisOrder="row-major")
    app, widget, p = _plotfenster(1000, 650)
    s = frame.spectrum
    image = pg.ImageItem(power_db(s.power), axisOrder="row-major")
    image.setColorMap(pg.colormap.get("viridis"))
    image.setLevels((-70, 5))
    p.addItem(image)
    dx, dy = float(np.diff(s.apparent_range_m)[0]), float(np.diff(s.velocity_mps)[0])
    image.setRect(QRectF(s.apparent_range_m[0] - dx / 2, s.velocity_mps[0] - dy / 2,
                        dx * len(s.apparent_range_m), dy * len(s.velocity_mps)))
    p.setLabel("bottom", "Scheinentfernung c fb/(2S)", units="m")
    p.setLabel("left", "Geschwindigkeit (+ entfernt)", units="m/s")
    p.setTitle("Range-Doppler · 10 log10(P / Aref²), Aref=1 · Farbskala −70…+5 dB")
    for target in frame.config.targets:
        apparent = target.range_m + target.velocity_mps * frame.config.carrier_hz / frame.config.slope
        p.plot([apparent], [target.velocity_mps], pen=None, symbol="x", symbolPen="#ffffff", symbolSize=13)
    p.plot([c.apparent_range_m for c in frame.candidates], [c.velocity_mps for c in frame.candidates],
           pen=None, symbol="o", symbolPen="#ffbd59", symbolBrush=None, symbolSize=16)
    app.processEvents()
    export_plot(p, path / "range_doppler.png")
    p.clear()
    p.setLabel("left", "Leistung / Aref²", units="dB")
    p.setTitle("Entfernungsspektrum · Mittelwert der Leistung über Chirps · Aref=1")
    p.plot(s.apparent_range_m, power_db(s.range_power), pen=pg.mkPen("#50d9d0", width=2))
    app.processEvents()
    export_plot(p, path / "range_spectrum.png")
    p.clear()
    p.setLabel("bottom", "SNR vor FFT / Einheitsreferenz", units="dB")
    p.setLabel("left", "Zugeordnete Ziele / Sollziele")
    p.setTitle("Kleine SNR-Stichprobe · je 16 Frames × 2 Ziele")
    p.plot([x["snr_db"] for x in sweep], [x["detection_fraction"] for x in sweep],
           pen=pg.mkPen("#50d9d0", width=2), symbol="o")
    app.processEvents()
    export_plot(p, path / "snr_sweep.png")
    p.clear()
    p.setLabel("bottom", "Fenster: 0 = Rechteck, 1 = Hann")
    p.setLabel("left", "Empirische Fehlalarmrate / CUT")
    p.setTitle("CFAR · nominal Pfa=0,001 · 96 unabhängige Frames je Fenster")
    p.plot([-0.3, 1.3], [0.001, 0.001], pen=pg.mkPen("#ffbd59", style=Qt.PenStyle.DashLine))
    p.plot([0, 1], [x["empirical_pfa"] for x in noise], pen=None, symbol="o", symbolSize=12)
    p.addItem(pg.ErrorBarItem(x=np.array([0., 1.]), y=np.array([x["empirical_pfa"] for x in noise]),
                             height=np.array([3.92 * x["standard_error"] for x in noise]), beam=0.12))
    app.processEvents()
    export_plot(p, path / "cfar_pfa.png")
    widget.close()


def export_flug_plots(path: Path, bericht: dict) -> None:
    """Drei Diagramme der bekannten Flugbahnen und der zugehörigen Radar-Schätzwerte."""
    app, fenster, plot = _plotfenster(1100, 650)
    plot.addLegend()
    farben = ("#59dcd0", "#ffbd59", "#8ba8ff", "#ff85b0")
    einstellungen = [
        ("flugbahnen.png", "Bekannte Flugbahnen · Radarstation bei (0, 0)", "Horizontaler Ort", "m", "Höhe über Radar", "m", "x_m", "hoehe_m", None),
        ("flug_entfernung.png", "Entfernung · Linie: Soll, Punkte: Radar-Schätzung", "Flugzeit", "s", "Entfernung", "m", "zeit_s", "entfernung_soll_m", "entfernung_geschaetzt_m"),
        ("flug_geschwindigkeit.png", "Radiale Geschwindigkeit · negativ: Annäherung, positiv: Entfernung", "Flugzeit", "s", "Radiale Geschwindigkeit", "m/s", "zeit_s", "geschwindigkeit_soll_mps", "geschwindigkeit_geschaetzt_mps"),
    ]
    for datei, titel, x_name, x_einheit, y_name, y_einheit, x_feld, y_feld, schaetz_feld in einstellungen:
        plot.clear()
        plot.setTitle(titel)
        plot.setLabel("bottom", x_name, units=x_einheit)
        plot.setLabel("left", y_name, units=y_einheit)
        farbnummer = 0
        for szene in bericht["szenen"]:
            objekt_nummern = sorted({wert["objekt"] for wert in szene["messwerte"]})
            for nummer in objekt_nummern:
                werte = [wert for wert in szene["messwerte"] if wert["objekt"] == nummer]
                farbe = farben[farbnummer]
                farbnummer += 1
                name = szene["dateiname"] + f" / Objekt {nummer}"
                plot.plot([wert[x_feld] for wert in werte], [wert[y_feld] for wert in werte],
                          pen=pg.mkPen(farbe, width=2), name=name)
                if schaetz_feld is not None:
                    vorhanden = [wert for wert in werte if wert[schaetz_feld] is not None]
                    plot.plot([wert[x_feld] for wert in vorhanden], [wert[schaetz_feld] for wert in vorhanden],
                              pen=None, symbol="o", symbolSize=3, symbolBrush=farbe, symbolPen=None)
        if datei == "flugbahnen.png":
            plot.plot([0], [0], pen=None, symbol="t1", symbolSize=15, symbolBrush="#ffffff", name="Radarstation")
        plot.enableAutoRange()
        app.processEvents()
        export_plot(plot, path / datei)
    fenster.close()


def export_detektions_plot(path: Path) -> None:
    """Roh-CFAR und tatsächliche Peaks getrennt sichtbar machen."""
    from .config import RadarConfig
    from .flugbahn import flugszenen
    from .pipeline import simulate_frame
    result = simulate_frame(RadarConfig(targets=(), noise_enabled=False,
                                        flugszene=flugszenen()["06_ueberflug"]))
    _, r = np.unravel_index(np.argmax(result.spectrum.power), result.spectrum.power.shape)
    v = result.spectrum.velocity_mps
    leistung = result.spectrum.power[:, r]
    schwelle = result.cfar.threshold[:, r]
    roh = result.cfar.mask[:, r]
    app, fenster, plot = _plotfenster(1100, 700)
    plot.addLegend()
    plot.setTitle("Ohne AWGN · Hann · Dopplerschnitt durch stärksten Entfernungsbin")
    plot.setLabel("bottom", "Radiale Geschwindigkeit", units="m/s")
    plot.setLabel("left", "Leistung / Aref² (Aref=1)", units="dB")
    plot.plot(v, power_db(leistung), pen=pg.mkPen("#59dcd0", width=2), name="Spektrum")
    plot.plot(v, power_db(schwelle), pen=pg.mkPen("#ffbd59", width=2), name="CFAR-Schwelle")
    plot.plot(v[roh], power_db(leistung[roh]), pen=None, symbol="+", symbolSize=9,
              symbolPen="#ff85b0", name="Rohe CFAR-Zellen")
    kandidaten_im_schnitt = [k for k in result.candidates if k.range_bin == r]
    plot.plot([k.velocity_mps for k in kandidaten_im_schnitt],
              [10 * np.log10(k.power) for k in kandidaten_im_schnitt], pen=None, symbol="o", symbolSize=15,
              symbolPen="#ffffff", symbolBrush=None, name="Peak-Kandidat")
    plot.setYRange(-145, 5)
    app.processEvents()
    export_plot(plot, path / "detektion_schnitt.png")
    fenster.close()


def export_routen_plot(path: Path, bericht: dict) -> None:
    app, fenster, plot = _plotfenster(1100, 650)
    plot.addLegend()
    plot.setTitle("Gezeichnete Route · konstantes Flugtempo und wechselnde radiale Geschwindigkeit")
    plot.setLabel("bottom", "Flugzeit", units="s")
    plot.setLabel("left", "Geschwindigkeit", units="m/s")
    zeiten = [m["zeit_s"] for m in bericht["messwerte"]]
    plot.plot(zeiten, [m["flugtempo_mps"] for m in bericht["messwerte"]],
              pen=pg.mkPen("#59dcd0", width=2), name="Flugtempo entlang der Route")
    plot.plot(zeiten, [m["radialgeschwindigkeit_mps"] for m in bericht["messwerte"]],
              pen=pg.mkPen("#ffbd59", width=2), name="Radiale Geschwindigkeit zum Radar")
    app.processEvents()
    export_plot(plot, path / "routen_tempo.png")
    fenster.close()
