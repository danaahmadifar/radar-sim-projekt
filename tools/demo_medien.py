"""Echte GUI-Bilder und kommentierte MP4-Demos ohne zusätzliche Pakete.

Start im Projektordner: python tools/demo_medien.py
Nur Bilder: python tools/demo_medien.py --images-only
Die Videos bestehen aus QWidget.grab()-Aufnahmen berechneter Radarframes.
Zeitlupe/Zeitraffer und Standbilder werden in der Bildunterschrift bezeichnet.
Es wird weder der Desktop noch ein Mikrofon aufgenommen.
"""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication
import pyqtgraph as pg
from radar_sim.gui import MainWindow
from radar_sim.io import load_config
from radar_sim.antenne import Antenne
from radar_sim.config import C
from radar_sim.effektbeispiele import effektbeispiele

FPS = 12
WIDTH, HEIGHT = 1920, 1080


class GuiAufnahmen:
    def __init__(self, app: QApplication):
        self.app = app
        self.fehler = []
        self.window = MainWindow(load_config(ROOT/"examples/11_flughafen_gegenverkehr.json"))
        self.window.fail = self._fehler
        self.window.resize(WIDTH, HEIGHT)
        self.window.show()
        self.warte()

    def _fehler(self, text):
        self.fehler.append(text)
        self.window._set_busy(False)

    def warte(self):
        ende = time.monotonic()+30
        while self.window.busy or self.window.result is None:
            self.app.processEvents()
            self.pruefe_fehler()
            if time.monotonic() > ende:
                raise TimeoutError("Radarframe nicht rechtzeitig fertig.")
            time.sleep(.002)
        self.app.processEvents()
        self.pruefe_fehler()

    def pruefe_fehler(self):
        if self.fehler:
            raise RuntimeError("; ".join(self.fehler))

    def lade(self, config, ansicht="overview", eingaben="Flug"):
        self.window.set_config(config)
        self.window.views.zeige_ansicht(getattr(self.window.views, ansicht))
        self.window.tabs.zeige_bereich(eingaben)
        self.window.start_frame()
        self.warte()
        self.window.tabs.zeige_bereich(eingaben)
        # Wie beim manuellen Zoomen: nur den Bildausschnitt ändern, keine Daten.
        if config.radar_mode == "fmcw" and config.flugszene is not None:
            self.window.views.rd_plot.setXRange(0, min(6500, config.timing_range_limit), padding=0)
        if ansicht == "route_editor":
            for name, plot in self.window.views.route_editor.plots.items():
                if name == "XY":
                    plot.setRange(xRange=(-2800, 2800), yRange=(-500, 500), padding=.03)
                elif name == "XZ":
                    plot.setRange(xRange=(-2800, 2800), yRange=(0, 900), padding=.03)
                else:
                    plot.setRange(xRange=(-500, 500), yRange=(0, 900), padding=.03)

    def frame(self, nummer: int):
        self.window.frame_index = nummer
        self.window.start_frame()
        self.warte()
        if self.window.result.frame_index != nummer:
            raise RuntimeError("Aufnahme und Simulationsframe passen nicht zusammen.")

    def bild(self) -> QImage:
        self.app.processEvents()
        return self.window.grab().toImage().convertToFormat(QImage.Format.Format_RGBA8888)

    def leistung_zoomen(self):
        """Nur der Bildausschnitt um den tatsächlichen Filterpeak wird vergrößert."""
        view = self.window.views.leistungsansicht
        self.window.views.zeige_ansicht(view)
        f = self.window.result
        index = int(abs(f.spectrum.compressed_first).argmax())
        delay = 2*f.spectrum.apparent_range_m[index]/C
        view.compression_plot.setXRange(max(0, delay-3*f.config.chirp_s),
                                       min(f.config.repetition_s, delay+5*f.config.chirp_s), padding=.02)

    def videobild(self, titel: str, beschreibung: str) -> QImage:
        bild = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGBA8888)
        bild.fill(QColor("#101827"))
        painter = QPainter(bild)
        painter.drawImage(0, 0, self.bild())
        painter.fillRect(0, HEIGHT-80, WIDTH, 80, QColor("#162338"))
        painter.setPen(QColor("#6ce1d3"))
        painter.setFont(QFont("Segoe UI", 15))
        painter.drawText(26, HEIGHT-49, titel)
        painter.setPen(QColor("#dee8f5"))
        painter.setFont(QFont("Segoe UI", 12))
        painter.drawText(26, HEIGHT-18, beschreibung)
        painter.end()
        return bild


class Mp4Aufnahme:
    """Qt-Encoder mit begrenzter Queue; keine Sammlung aller Bilder im RAM."""

    def __init__(self, app, datei: Path):
        # Nur die optionale Videoerstellung benötigt Qt >= 6.8.
        from PyQt6.QtMultimedia import QMediaCaptureSession, QMediaFormat, QMediaRecorder, QVideoFrameInput
        self.app, self.datei, self.anzahl = app, datei, 0
        self.kapitel = []
        self.session = QMediaCaptureSession()
        self.eingang = QVideoFrameInput()
        self.recorder = QMediaRecorder()
        self.session.setVideoFrameInput(self.eingang)
        self.session.setRecorder(self.recorder)
        format = QMediaFormat(QMediaFormat.FileFormat.MPEG4)
        format.setVideoCodec(QMediaFormat.VideoCodec.H264)
        if not format.isSupported(QMediaFormat.ConversionMode.Encode):
            raise RuntimeError("Qt bietet hier keinen H.264-MP4-Encoder. --images-only bleibt nutzbar.")
        self.recorder.setMediaFormat(format)
        self.recorder.setVideoResolution(WIDTH, HEIGHT)
        self.recorder.setVideoFrameRate(FPS)
        self.recorder.setVideoBitRate(5_000_000)
        self.recorder.setOutputLocation(QUrl.fromLocalFile(str(datei.resolve())))
        self.recorder.record()

    def sende(self, frame):
        from PyQt6.QtMultimedia import QMediaRecorder
        ende = time.monotonic()+20
        while not self.eingang.sendVideoFrame(frame):
            self.app.processEvents()
            if self.recorder.error() != QMediaRecorder.Error.NoError:
                raise RuntimeError(self.recorder.errorString())
            if time.monotonic() > ende:
                raise TimeoutError("Videoencoder nimmt keine weiteren Frames an.")
            time.sleep(.002)

    def schreibe(self, bild: QImage, wiederholungen: int):
        from PyQt6.QtMultimedia import QVideoFrame
        for _ in range(wiederholungen):
            frame = QVideoFrame(bild)
            frame.setStartTime(round(self.anzahl*1e6/FPS))
            frame.setEndTime(round((self.anzahl+1)*1e6/FPS))
            self.sende(frame)
            self.anzahl += 1
            self.app.processEvents()

    def kapitel_start(self, titel: str):
        self.kapitel.append({"start_s": self.anzahl/FPS, "titel": titel})
        print(f"  {self.datei.name}: {titel}", flush=True)

    def ende(self) -> dict:
        from PyQt6.QtMultimedia import QMediaRecorder, QVideoFrame
        self.sende(QVideoFrame())
        self.recorder.stop()
        ende = time.monotonic()+20
        while self.recorder.recorderState() != QMediaRecorder.RecorderState.StoppedState:
            self.app.processEvents()
            if time.monotonic() > ende:
                raise TimeoutError("Videoencoder beendet die Aufnahme nicht.")
            time.sleep(.002)
        if self.recorder.error() != QMediaRecorder.Error.NoError or not self.datei.is_file():
            raise RuntimeError(self.recorder.errorString() or "Keine Videodatei erzeugt.")
        return {"datei": self.datei.name, "frames": self.anzahl, "fps": FPS,
                "dauer_s": self.anzahl/FPS, "aufloesung": [WIDTH, HEIGHT],
                "bytes": self.datei.stat().st_size, "kapitel": self.kapitel}


def erstelle_bilder(gui, ordner) -> list[dict]:
    beispiele = effektbeispiele()
    polar = replace(load_config(ROOT/"examples/13_flughafen_route3d.json"),
                    antenne=Antenne(typ="patch_array", elemente_horizontal=12, elemente_vertikal=6))
    bilder = [
        ("01_fmcw_gegenverkehr.png", "11_flughafen_gegenverkehr", "overview", "Flug", 40),
        ("02_puls_doppler.png", "16_puls_doppler_air_to_air", "signal_graphs", "Radar", 16),
        ("03_route_3d.png", "13_flughafen_route3d", "route_editor", "Flug", 0),
        ("04_antenna_pattern.png", polar, "antennenansicht", "Antenne", 0),
        ("05_passivradar.png", "20_passiv_beta", "overview", "Passivradar", 10),
        ("06_effektvergleich.png", beispiele["FMCW · Leakage und Phasenrauschen"][1], "effektansicht", "Effekte", 0),
        ("07_bodenclutter.png", beispiele["Air-to-Air · bewegter Bodenclutter"][1], "overview", "Effekte", 0),
        ("08_power_energy.png", "16_puls_doppler_air_to_air", "leistungsansicht", "Radar", 16),
    ]
    resultate = []
    for datei, config, ansicht, eingaben, nummer in bilder:
        if isinstance(config, str):
            config = load_config(ROOT/"examples"/(config+".json"))
        gui.lade(config, ansicht, eingaben)
        if nummer:
            gui.frame(nummer)
        if ansicht == "effektansicht":
            gui.window.tabs.effektfelder.demo.setCurrentText("FMCW · Leakage und Phasenrauschen")
            gui.window.views.effektansicht.range_plot.setXRange(0, 70, padding=.02)
        elif datei == "07_bodenclutter.png":
            gui.window.tabs.effektfelder.demo.setCurrentText("Air-to-Air · bewegter Bodenclutter")
        elif ansicht == "leistungsansicht":
            gui.leistung_zoomen()
        if not gui.bild().save(str(ordner/datei)):
            raise OSError("PNG konnte nicht gespeichert werden: "+datei)
        f = gui.window.result
        resultate.append({"datei": datei, "modus": config.radar_mode, "frame": nummer,
                          "simulationszeit_s": f.zeit_s, "soll_targets": len(f.config.targets),
                          "cfar_peaks": len(f.candidates), "aufloesung": [WIDTH, HEIGHT]})
        print("Bild: "+datei, flush=True)
    return resultate


def erstelle_videos(gui, ordner) -> list[dict]:
    gui.window.resize(WIDTH, HEIGHT-80)
    movie = Mp4Aufnahme(gui.app, ordner/"01_gegenverkehr.mp4")
    movie.kapitel_start("FMCW: zwei entgegengesetzte Flugrichtungen")
    gui.lade(load_config(ROOT/"examples/11_flughafen_gegenverkehr.json"))
    for n in range(121):
        gui.frame(n)
        bild = gui.videobild("FMCW · zwei entgegengesetzte Flugrichtungen",
                "Berechnete GUI-Frames · 3× Zeitraffer · × Sollwerte, ○ CFAR-Peaks · positive Radialgeschwindigkeit = Entfernung")
        movie.schreibe(bild, 2)
    videos = [movie.ende()]
    movie = Mp4Aufnahme(gui.app, ordner/"02_verfahren_und_effekte.mp4")
    def stand(titel, text, sekunden):
        movie.kapitel_start(titel)
        movie.schreibe(gui.videobild(titel, "Standbild aus berechnetem Frame · "+text), round(sekunden*FPS))
    gui.lade(load_config(ROOT/"examples/16_puls_doppler_air_to_air.json"))
    movie.kapitel_start("Puls-Doppler: bewegtes Radar")
    for n in range(0, 21, 2):
        gui.frame(n)
        movie.schreibe(gui.videobild("Puls-Doppler · Radar auf einer bewegten Plattform",
                "Berechnete GUI-Frames · etwa 2× Zeitraffer · gemessen werden Entfernung und radiale Relativgeschwindigkeit"), 6)
    gui.window.views.zeige_ansicht(gui.window.views.signal_graphs)
    stand("Puls-Doppler · Empfang und Pulskompression", "RX* ist während der Sendezeit gesperrt; danach folgt die Pulskompression.", 3)
    gui.leistung_zoomen()
    stand("Power / Energy · hohe Spitzen, gleiches Sendebudget", "Gleiche mittlere Leistung: Puls-Spitzen sind höher, die Energie pro Frame bleibt gleich. P0 ist relativ.", 4)
    gui.lade(load_config(ROOT/"examples/13_flughafen_route3d.json"), "route_editor")
    stand("Eigene Route · Überflug mit leichter Sinusbewegung", "XY, XZ und YZ: 600 m Höhe, 70 m/s, seitliche Auslenkung ±100 m; XYZ sind bekannte Eingaben.", 3)
    polar = replace(load_config(ROOT/"examples/13_flughafen_route3d.json"),
                    antenne=Antenne(typ="patch_array", elemente_horizontal=12, elemente_vertikal=6))
    gui.lade(polar, "antennenansicht", "Antenne")
    stand("Antenna Pattern · klassisches Polardiagramm", "Ideales Patch-Feld, zwei Winkelschnitte; 0 dB entspricht der Achsenleistung.", 3)
    gui.lade(load_config(ROOT/"examples/20_passiv_beta.json"), "overview", "Passivradar")
    gui.frame(10)
    stand("Passivradar", "Fremdsender und zwei Empfangskanäle; Messgrößen sind Umweg ΔL und Wegänderungsrate.", 4)
    beispiele = effektbeispiele()
    gui.lade(beispiele["FMCW · Leakage und Phasenrauschen"][1], "effektansicht", "Effekte")
    gui.window.tabs.effektfelder.demo.setCurrentText("FMCW · Leakage und Phasenrauschen")
    gui.window.views.effektansicht.range_plot.setXRange(0, 70, padding=.02)
    stand("Leakage und Phasenrauschen · schwaches Target verdeckt", "Orange: mit Störungen. Grau: dieselbe Szene ohne zuschaltbare Störungen. Gleiche dB-Referenz.", 5)
    gui.lade(beispiele["Air-to-Air · bewegter Bodenclutter"][1], "overview", "Effekte")
    gui.window.tabs.effektfelder.demo.setCurrentText("Air-to-Air · bewegter Bodenclutter")
    movie.kapitel_start("Bewegtes Radar und Bodenclutter")
    for n in range(9):
        gui.frame(n)
        movie.schreibe(gui.videobild("Bodenclutter · Eigenbewegung erzeugt ein Dopplerband",
                "Berechnete GUI-Frames · ungefähr Originaltempo · graue Punkte: Bodenstreuer; Kreise sind keine bestätigten Flugzeuge"), 6)
    videos.append(movie.ende())
    return videos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT/"docs/media")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    # pyqtgraph hält die QApplication auch während seiner Exit-Aufräumarbeiten.
    app = pg.mkQApp("Radar Lab · Demo")
    gui = GuiAufnahmen(app)
    try:
        bilder = erstelle_bilder(gui, args.output)
        videos = [] if args.images_only else erstelle_videos(gui, args.output)
        manifest = {"erstellt_utc": datetime.now(timezone.utc).isoformat(),
                    "quelle": "QWidget.grab der unveränderten Anwendung; keine Desktop- oder Mikrofonaufnahme",
                    "bilder": bilder, "videos": videos}
        (args.output/"medien.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    finally:
        gui.window.close()
        app.closeAllWindows()
        app.processEvents()


if __name__ == "__main__":
    main()
