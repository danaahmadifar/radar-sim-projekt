"""Messbericht der Flughafenszenen mit 3D-Geometrie und Antennenwirkung."""

from pathlib import Path
from .io import schreibe_json, schreibe_markdown
import numpy as np
from .flughafen import flughafen_config, flughafenszenen
from .flugbahn import relativer_zustand
from .pipeline import simulate_frame
from .evaluation import match_targets, schaetztoleranzen


def pruefe_airport() -> dict:
    """Jeden Frame mit Richtwirkung auswerten. Außerhalb der Keule sind Ausfälle erlaubt.

    Harte Kriterien: korrekte 3D-Projektion, Schätzfehler innerhalb FFT-Toleranz
    und vollständige Zuordnung im Einweg-Halbwertsbereich G>=0,5. Zusätzlich
    werden ALLE fehlenden Zuordnungen und alle zusätzlichen Peaks ausgewiesen.
    Die Zuordnung dient nur der Auswertung, sie verändert keine Detektion.
    """
    szenen = []
    bestanden = True
    for name in flughafenszenen():
        config = flughafen_config(name)
        zeilen = []
        fehler = []
        for frame_nummer in range(config.flugszene.letzter_frame+1):
            ergebnis = simulate_frame(config, frame_nummer)
            paare = {zuordnung.target_index: zuordnung for zuordnung in match_targets(ergebnis.config, ergebnis.candidates)}
            for ziel_nummer, (zustand, ziel) in enumerate(zip(ergebnis.flugzustaende, ergebnis.config.targets)):
                ort = np.array(zustand.position_m)
                tempo = np.array([zustand.geschwindigkeit_x_mps, zustand.geschwindigkeit_y_mps, zustand.geschwindigkeit_hoehe_mps])
                if ergebnis.radar_zustand is not None:
                    radar = ergebnis.radar_zustand
                    ort -= radar.position_m
                    tempo -= (radar.geschwindigkeit_x_mps, radar.geschwindigkeit_y_mps, radar.geschwindigkeit_hoehe_mps)
                entfernung_soll = float(np.linalg.norm(ort))
                geschwindigkeit_soll = float(ort@tempo/entfernung_soll)
                dt = 1e-4
                bahn = config.flugszene.bahnen[ziel_nummer]
                if 0 < ergebnis.zeit_s < config.flugszene.dauer_s:
                    r_a = relativer_zustand(bahn, config.flugszene.radar_bahn, ergebnis.zeit_s-dt).entfernung_m
                    r_b = relativer_zustand(bahn, config.flugszene.radar_bahn, ergebnis.zeit_s+dt).entfernung_m
                    if abs((r_b-r_a)/(2*dt)-geschwindigkeit_soll) > 1e-5:
                        fehler.append(f"Frame {frame_nummer}, Target {ziel_nummer+1}: Ableitung von R passt nicht zu v_radial")
                if abs(ziel.range_m-entfernung_soll)>1e-8 or abs(ziel.velocity_mps-geschwindigkeit_soll)>1e-8:
                    fehler.append(f"Frame {frame_nummer}: Raumprojektion fehlerhaft")
                zuordnung = paare.get(ziel_nummer)
                if ziel.antenna_gain >= .5 and zuordnung is None:
                    fehler.append(f"Frame {frame_nummer}: Target {ziel_nummer+1} innerhalb der Halbwertskeule fehlt")
                entfernungstoleranz, geschwindigkeitstoleranz = schaetztoleranzen(config)
                if zuordnung and (abs(zuordnung.range_error_m)>1.01*entfernungstoleranz or abs(zuordnung.velocity_error_mps)>1.01*geschwindigkeitstoleranz):
                    fehler.append(f"Frame {frame_nummer}: FFT-Fehlertoleranz überschritten")
                zeilen.append({"zeit_s": ergebnis.zeit_s, "target": ziel_nummer+1, "x_m": zustand.x_m, "y_m": zustand.y_m, "z_m": zustand.hoehe_m,
                               "range_m": entfernung_soll, "velocity_mps": geschwindigkeit_soll, "gain_one_way": ziel.antenna_gain,
                               "range_error_m": zuordnung.range_error_m if zuordnung else None,
                               "velocity_error_mps": zuordnung.velocity_error_mps if zuordnung else None,
                               "extra_targets_frame": len(ergebnis.candidates)-len(paare) if ziel_nummer==0 else 0})
        bestanden = bestanden and not fehler
        szenen.append({"name": name, "frames": config.flugszene.letzter_frame+1, "samples": config.samples,
                       "range_resolution_m": config.range_resolution, "velocity_resolution_mps": config.velocity_resolution,
                       "sollwerte": len(zeilen), "fehlend": sum(zustand["range_error_m"] is None for zustand in zeilen),
                       "fehlend_in_halbwertskeule": sum(zustand["range_error_m"] is None and zustand["gain_one_way"]>=.5 for zustand in zeilen),
                       "extras": sum(zustand["extra_targets_frame"] for zustand in zeilen),
                       "max_range_error_m": max((abs(zustand["range_error_m"]) for zustand in zeilen if zustand["range_error_m"] is not None), default=None),
                       "max_velocity_error_mps": max((abs(zustand["velocity_error_mps"]) for zustand in zeilen if zustand["velocity_error_mps"] is not None), default=None),
                       "fehler": fehler, "messwerte": zeilen})
    return {"bestanden": bestanden, "szenen": szenen}


def schreibe_airportbericht(ordner: Path, bericht: dict) -> None:
    schreibe_json(ordner / "airport_3d.json", bericht)
    lines = ["# Flughafen, Raumbewegung und Antennenkeule", "",
             "Reproduzieren: `python -m radar_sim --validate`. Seed 42, AWGN eingeschaltet, relative RCS- und Entfernungsabhängigkeit, Antennenwirkung aktiv.", "",
             "| Szene | Frames | Sollwerte | Fehlend gesamt | Davon in Halbwertskeule | Extra Targets | max. ΔR abs. / m | max. Δv abs. / m/s |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for s in bericht["szenen"]:
        lines.append(f"| {s['name']} | {s['frames']} | {s['sollwerte']} | {s['fehlend']} | {s['fehlend_in_halbwertskeule']} | {s['extras']} | {s['max_range_error_m']:.6f} | {s['max_velocity_error_mps']:.6f} |")
    lines += ["", "3D-Referenz: R=||p|| und v_radial=p·v/||p||; zusätzlich Ableitung der Entfernung mit dt=0,1 ms geprüft.",
              "FFT-Toleranz: 1,01·(ΔR/2 + fc/S·Δv/2) und 1,01·Δv/2. Keine Peak-Interpolation.",
              "Ausfälle außerhalb der Einweg-Halbwertskeule sind im Gesamtwert enthalten und kein harter Fehler. Der Höhenbogen verlässt den fest ausgerichteten Sektor; ein Vorbeiflug muss daher nicht bis zum Ende sichtbar sein.",
              "Normierte Einweg-Leistung G wird als Amplitudenfaktor verwendet: monostatische Echoleistung proportional G². Keulenlänge ist ausschließlich eine Zeichenhilfe.",
              "Die neuen Unit-Tests prüfen außerdem verzögerte Echo-Mischung im ADC-Fenster, Halbwertsgrenzen aller drei Richtantennen, Patch-Nullstelle, Zweiweg-Leistung und Gleichheit der Echos bei veränderter Zeichenlänge.", "",
              "![3D-Szene](airport_route.png)", "",
              "Gesamtergebnis: **"+("BESTANDEN" if bericht["bestanden"] else "FEHLER")+"**. Rohwerte: [airport_3d.json](airport_3d.json)."]
    schreibe_markdown(ordner / "AIRPORT_3D.md", lines)


def export_airport_plot(ordner: Path, bericht: dict) -> None:
    """Drei bekannte Projektionen der räumlichen Route als eigenständige Grafik."""
    from PyQt6.QtWidgets import QApplication
    import pyqtgraph as pg
    from .report_plots import export_plot
    from .qt_support import ensure_font
    app = QApplication.instance() or QApplication([])
    ensure_font(app)
    w = pg.GraphicsLayoutWidget()
    w.resize(1600, 600)
    w.show()
    daten = next(s["messwerte"] for s in bericht["szenen"] if s["name"] == "13_flughafen_route3d")
    for i, (a,b) in enumerate((("x_m","y_m"),("x_m","z_m"),("y_m","z_m"))):
        p = w.addPlot(row=0, col=i, title=a[0].upper()+b[0].upper()+" · vorgegebene Route")
        p.setLabel("bottom", a[0].upper(), units="m")
        p.setLabel("left", b[0].upper(), units="m")
        p.plot([z[a] for z in daten], [z[b] for z in daten], pen=pg.mkPen("#59dcd0", width=2))
        p.plot([0],[0],pen=None,symbol="t1",symbolBrush="#ffbd59",symbolSize=12)
        p.showGrid(x=True, y=True, alpha=.15)
    app.processEvents()
    # ImageExporter kann auch das gesamte GraphicsLayout exportieren.
    export_plot(w.ci, ordner/"airport_route.png")
    w.close()
