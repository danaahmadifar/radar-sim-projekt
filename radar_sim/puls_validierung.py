"""Reproduzierbare Messungen für Puls-Doppler und die bewegte Radarplattform."""

from dataclasses import replace
from pathlib import Path
import numpy as np
from .config import RadarConfig, Target
from .pulsradar import puls_config
from .pipeline import simulate_frame
from .flughafen import flughafen_config
from .evaluation import match_targets, schaetztoleranzen
from .io import schreibe_json, schreibe_markdown


def pruefe_pulsradar() -> dict:
    """Diskrete Peaks gegen bekannte R/v; keine Sollwerte im Detektor.

    Puls-R-Toleranz: halber ADC-Laufzeitbin plus Fehler der Dopplerkorrektur.
    v-Toleranz: halber Dopplerbin. Hauptkeulenauflösung ist NICHT der ADC-Bin.
    Bei kleinen Zeit-Bandbreite-Produkten und knapper Abtastung sind außerdem
    Hüllkurven-/Rastereffekte möglich; die Beispiele prüfen die realen Fehler.
    """
    basis = replace(puls_config(RadarConfig()), targets=(), snr_db=20, pfa=1e-6)
    szenarien = {
        "stationaer_ohne_awgn": replace(basis, noise_enabled=False, targets=(Target(5000),)),
        "gegenverkehr_ohne_awgn": replace(basis, noise_enabled=False, targets=(Target(4100,-40), Target(8100,30))),
        "gleiche_entfernung": replace(basis, noise_enabled=False, targets=(Target(6000,-40), Target(6000,40))),
    }
    pruefungen = []
    for name, c in szenarien.items():
        f = simulate_frame(c)
        paare = match_targets(c, f.candidates)
        rt, vt = schaetztoleranzen(c)
        pruefungen.append({"name": name, "soll": len(c.targets), "zugeordnet": len(paare),
                          "extras": len(f.candidates)-len(paare), "toleranz_r_m": rt, "toleranz_v_mps": vt,
                          "max_r_fehler_m": max((abs(p.range_error_m) for p in paare), default=None),
                          "max_v_fehler_mps": max((abs(p.velocity_error_mps) for p in paare), default=None),
                          "bestanden": len(paare)==len(c.targets) and all(abs(p.range_error_m)<=rt*1.01 and abs(p.velocity_error_mps)<=vt*1.01 for p in paare)})
    bewegung = []
    for modus, awgn in (("fmcw", False), ("fmcw", True), ("pulse_doppler", False), ("pulse_doppler", True)):
        c = flughafen_config("15_zwei_flugzeuge_radar")
        c = puls_config(c) if modus == "pulse_doppler" else c
        c = replace(c, noise_enabled=awgn)
        zeilen = []
        for nummer in range(c.flugszene.letzter_frame+1):
            f = simulate_frame(c, nummer)
            paare = match_targets(f.config, f.candidates)
            rt, vt = schaetztoleranzen(c)
            # Bei AWGN kann das diskrete Maximum den nächstliegenden ADC-Bin
            # verlassen. Für diese 20-dB-Stichprobe: halbe nominelle Auflösung,
            # nicht die engere, nur rauschfrei begründete halbe Rasterweite.
            if awgn:
                rt = max(rt, c.range_resolution/2)
            p = paare[0] if paare else None
            zeilen.append({"zeit_s": f.zeit_s, "radar_x_m": f.radar_zustand.x_m,
                           "target_x_m": f.flugzustaende[0].x_m, "range_m": f.config.targets[0].range_m,
                           "v_rel_mps": f.config.targets[0].velocity_mps,
                           "r_fehler_m": p.range_error_m if p else None, "v_fehler_mps": p.velocity_error_mps if p else None,
                           "extras": len(f.candidates)-len(paare),
                           "halb_bin_ueberschritten": p is not None and abs(p.range_error_m)>schaetztoleranzen(c)[0]*1.01,
                           "bestanden": p is not None and abs(p.range_error_m)<=rt*1.01 and abs(p.velocity_error_mps)<=vt*1.01})
        bewegung.append({"modus": modus, "awgn": awgn, "toleranz_r_m": rt, "toleranz_v_mps": vt,
                         "frames": len(zeilen), "fehlend": sum(z["r_fehler_m"] is None for z in zeilen),
                         "extras": sum(z["extras"] for z in zeilen), "bestanden": all(z["bestanden"] for z in zeilen),
                         "messwerte": zeilen})
    snr_werte = []
    for snr in (-35, -20, 0, 20):
        c = replace(basis, snr_db=snr, targets=(Target(5000, -35),))
        treffer = extras = 0
        for nummer in range(24):
            f = simulate_frame(c, nummer)
            n = len(match_targets(c, f.candidates))
            treffer += n
            extras += len(f.candidates)-n
        snr_werte.append({"snr_db": snr, "frames": 24, "zugeordnet": treffer, "extras": extras})
    rauschen = []
    for fenster in ("rect", "hann"):
        c = replace(basis, targets=(), window=fenster, pfa=1e-3, seed=20261020)
        raten = []
        anzahl = alarms = 0
        for nummer in range(48):
            f = simulate_frame(c, nummer)
            n, a = int(f.cfar.valid.sum()), int(f.cfar.mask.sum())
            anzahl += n
            alarms += a
            raten.append(a/n)
        mittel = alarms/anzahl
        fehler = float(1.96*np.std(raten, ddof=1)/np.sqrt(len(raten)))
        rauschen.append({"fenster": fenster, "frames": 48, "cut": anzahl, "alarme": alarms,
                         "pfa_nominell": c.pfa, "pfa_gemessen": mittel,
                         "ci95_frame_mittel": [max(0,mittel-fehler), mittel+fehler],
                         "hinweis": "Korrelierte Entfernungszellen nach Kompression; keine behauptete Einhaltung der unabhängigen CA-CFAR-Formel."})
    return {"bestanden": all(p["bestanden"] for p in pruefungen+bewegung), "pulspruefungen": pruefungen,
            "bewegte_plattform": bewegung, "snr": snr_werte, "rauschen": rauschen}


def schreibe_pulsbericht(ordner: Path, daten: dict) -> None:
    schreibe_json(ordner/"puls_und_plattform.json", daten)
    zeilen = ["# Puls-Doppler und bewegtes Radar", "", "Reproduzieren: `python -m radar_sim --validate`.", "",
              "Lehrprofil: fc=3 GHz, B=2 MHz, Tp=4 µs, Tr=200 µs, fs=5 MHz, M=64; komplexer LFM-Empfang und lineare Pulskompression.",
              "ΔR=74,9481 m, ADC-Bin=29,9792 m, Δv=3,90355 m/s, |v|<124,914 m/s. Theoretisch Runamb=29.979,2 m; volle Echos bei 599,585≤R≤29.379,7 m. CFAR-Ränder begrenzen die Detektion zusätzlich.", "",
              "| Pulsprüfung | Soll | Zugeordnet | Extra | Max. Fehler R / m | Max. Fehler v / m/s | Ergebnis |", "|---|---:|---:|---:|---:|---:|---|"]
    for p in daten["pulspruefungen"]:
        zeilen.append(f"| {p['name']} | {p['soll']} | {p['zugeordnet']} | {p['extras']} | {p['max_r_fehler_m']} | {p['max_v_fehler_mps']} | {'OK' if p['bestanden'] else 'FEHLER'} |")
    zeilen += ["", "Toleranzen: halber ADC-Entfernungsbin plus Dopplerkorrekturfehler; halber Dopplerbin. Kein interpolierter Schätzer.", "",
               "## Zwei Flugzeuge, eines mit Radar", "",
               "Radar: 160 m/s bei 1800 m; Target: 200 m/s bei 2100 m, seitlich 300 m versetzt. 40 s. R und v werden aus der Differenz beider Weltbewegungen berechnet. Die Plattform ist kein Eigenziel.", "",
               "Rauschfrei gilt die halbe Rasterweite plus Kopplungskorrektur. Bei AWGN kann ein benachbarter Bin gewinnen; für die hier gemessene 20-dB-Stichprobe wird höchstens eine halbe nominelle Entfernungsauflösung zugelassen. Das ist kein allgemeines Genauigkeitsversprechen für beliebiges SNR.", "",
               "| Modus | AWGN | Frames | Fehlend | Extra | Max. Fehler R / m | Max. Fehler v / m/s | Ergebnis |", "|---|---|---:|---:|---:|---:|---:|---|"]
    hinweise = []
    for b in daten["bewegte_plattform"]:
        r = max((abs(z["r_fehler_m"]) for z in b["messwerte"] if z["r_fehler_m"] is not None), default=None)
        v = max((abs(z["v_fehler_mps"]) for z in b["messwerte"] if z["v_fehler_mps"] is not None), default=None)
        zeilen.append(f"| {b['modus']} | {b['awgn']} | {b['frames']} | {b['fehlend']} | {b['extras']} | {r} | {v} | {'OK' if b['bestanden'] else 'FEHLER'} |")
        hinweise.append(f"{b['modus']}, AWGN={b['awgn']}: R-Toleranz {b['toleranz_r_m']:.6g} m; {sum(z['halb_bin_ueberschritten'] for z in b['messwerte'])} Frames überschreiten die engere rauschfreie Halb-Bin-Grenze.")
    zeilen += [""] + hinweise
    zeilen += ["", "## Reines Rauschen", "", "48 unabhängige Frames je Fenster. Intervall aus der Streuung der Frame-Raten, keine Unabhängigkeitsannahme über einzelne CUTs.", "",
               "| Fenster | CUTs | Alarme | Pfa nominal | Pfa gemessen | 95-%-Intervall |", "|---|---:|---:|---:|---:|---|"]
    for r in daten["rauschen"]:
        zeilen.append(f"| {r['fenster']} | {r['cut']} | {r['alarme']} | {r['pfa_nominell']} | {r['pfa_gemessen']:.6g} | {r['ci95_frame_mittel']} |")
    zeilen += ["", "Entfernungszellen nach Pulskompression sind korreliert, auch bei Rechteck. Die nominale Pfa ist kein kalibriertes Fehlalarmversprechen.", "",
               "## SNR-Stichprobe", "", "SNR vor Kompression, bezogen auf ein aktives Echo mit Amplitude 1, kein PRI-Mittel und kein aufsummiertes Szenen-SNR.", "",
               "| SNR / dB | Zugeordnet / 24 | Extra |", "|---:|---:|---:|"]
    zeilen += [f"| {s['snr_db']} | {s['zugeordnet']} | {s['extras']} |" for s in daten["snr"]]
    zeilen += ["", "![Pulse Range-Doppler](puls_range_doppler.png)", "![Relative Bewegung](bewegtes_radar.png)", "",
               "Die unabhängigen Unit-Tests vergleichen RX gegen verzögerte Basisbandpulse und die FFT-Kompression gegen direkte Korrelation. Sie prüfen außerdem Blindbereich, Doppler-/PRI-Grenzen, ADC und Speicher, JSON, Slider und Null-Doppler ohne Rundungsgeister.", "",
               "Gesamtergebnis der harten Schätzprüfungen: **"+("BESTANDEN" if daten["bestanden"] else "FEHLER")+"**.",
               "Herleitung und ehrliche Vor-/Nachteile: [Puls-Doppler und Plattform](../docs/PULS_DOPPLER.md)."]
    schreibe_markdown(ordner/"PULS_UND_PLATTFORM.md", zeilen)


def export_pulsplots(ordner: Path, daten: dict) -> None:
    from PyQt6.QtCore import QRectF
    import pyqtgraph as pg
    from .processing import power_db
    from .report_plots import _plotfenster, export_plot
    app, fenster, plot = _plotfenster()
    f = simulate_frame(puls_config(flughafen_config("15_zwei_flugzeuge_radar")))
    s = f.spectrum
    image = pg.ImageItem(power_db(s.power), axisOrder="row-major")
    image.setColorMap(pg.colormap.get("viridis"))
    image.setLevels((-90, 5))
    dx, dy = f.config.range_bin_m, f.config.velocity_resolution
    image.setRect(QRectF(s.apparent_range_m[0]-dx/2, s.velocity_mps[0]-dy/2, dx*len(s.apparent_range_m), dy*len(s.velocity_mps)))
    plot.addItem(image)
    plot.setTitle("Puls-Doppler · 10 log10(P/Aref²), Farbskala −90…+5 dB")
    plot.setLabel("bottom", "Scheinentfernung nach Pulskompression", units="m")
    plot.setLabel("left", "Radialgeschwindigkeit relativ zum Radar", units="m/s")
    app.processEvents()
    export_plot(plot, ordner/"puls_range_doppler.png")
    plot.clear()
    plot.setTitle("Air-to-Air · Sollentfernung und aus Pulsen geschätzte Entfernung")
    plot.setLabel("bottom", "Flugzeit", units="s")
    plot.setLabel("left", "Relative Entfernung", units="m")
    plot.addLegend()
    werte = next(b["messwerte"] for b in daten["bewegte_plattform"] if b["modus"]=="pulse_doppler" and b["awgn"])
    plot.plot([z["zeit_s"] for z in werte], [z["range_m"] for z in werte], pen="#59dcd0", name="Soll")
    plot.plot([z["zeit_s"] for z in werte if z["r_fehler_m"] is not None], [z["range_m"]+z["r_fehler_m"] for z in werte if z["r_fehler_m"] is not None], pen=None, symbol="o", symbolSize=4, symbolBrush="#ffbd59", name="Puls-Schätzung")
    app.processEvents()
    export_plot(plot, ordner/"bewegtes_radar.png")
    fenster.close()
