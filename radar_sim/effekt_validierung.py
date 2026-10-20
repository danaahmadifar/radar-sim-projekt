"""Messbericht der Störmodelle: analytische Checks und tatsächliche Demo-Peaks."""

from dataclasses import replace
from pathlib import Path
import math
import numpy as np
from .config import C, RadarConfig, Target
from .effekt_config import Stoereffekte
from .effektbeispiele import effektbeispiele
from .pipeline import simulate_frame
from .empfaenger import Phasenprozess, begrenze_empfang
from .ausbreitung import ERDRADIUS_M, erdkoordinaten, freie_sicht
from .bodenclutter import bodenpunkte
from .pulsradar import generate_pulsed_echo, process_pulses
from .evaluation import match_targets
from .io import schreibe_json, schreibe_markdown


def pruefe_stoermodelle() -> dict:
    """Keine Erfolgsbedingung für Detektion unter Störung; Ausfälle sind Messwerte."""
    demos = []
    for name, (beschreibung, c) in effektbeispiele().items():
        nummern = sorted({0, c.flugszene.letzter_frame//2, c.flugszene.letzter_frame}) if c.flugszene else [0]
        for nummer in nummern:
            f = simulate_frame(c, nummer)
            paare = match_targets(f.config, f.candidates)
            demos.append({"name": name, "beschreibung": beschreibung, "frame": nummer,
                          "soll": len(f.config.targets), "zugeordnet": len(paare),
                          "extras": len(f.candidates)-len(paare), "begrenzt": f.echo.clipped_fraction,
                          "peak_power": float(f.spectrum.power.max()),
                          "referenz_peak_power": float(f.vergleich.power.max()) if f.vergleich else None,
                          "target_path_gains": [z.path_gain for z in f.config.targets]})
    checks = []
    def check(name, ist, soll, toleranz):
        checks.append({"name": name, "ist": float(ist), "soll": float(soll), "toleranz": float(toleranz),
                       "bestanden": bool(abs(ist-soll) <= toleranz)})
    c = RadarConfig(targets=(), chirps=32, noise_enabled=False, window="rect")
    tau = 16*c.sample_rate_hz/(c.samples*c.slope)
    leak = replace(c, effekte=Stoereffekte(leakage=True, leakage_db=20, leakage_delay_s=tau))
    f = simulate_frame(leak)
    check("Leakage-Leistung am binzentrierten Peak / Aref²", f.spectrum.power.max(), 100, 1e-9)
    frequenz = f.spectrum.beat_hz[np.argmax(f.spectrum.range_power)]
    check("Leakage-Beat / Hz", frequenz, c.slope*tau, 1e-7)
    e = Stoereffekte(phasenrauschen=True, phase_rms_rad=.5, phase_zeit_s=10e-6)
    phase_c = replace(c, chirps=128, effekte=e)
    t = np.arange(50, 5000)*e.phase_zeit_s/8
    kurz, lang = [], []
    for n in range(12):
        p = Phasenprozess(phase_c, n, 100e-6)
        kurz.extend(p.restphase(t, e.phase_zeit_s))
        lang.extend(p.restphase(t, 8*e.phase_zeit_s))
    check("Restphasenvarianz bei τ=Tc / rad²", np.mean(np.square(kurz)), .5*(1-math.exp(-.5)), .02)
    check("Restphasenvarianz bei τ=8Tc / rad²", np.mean(np.square(lang)), .5, .05)
    satt, anteil = begrenze_empfang(np.array([0, 1, -2j, 3+4j]), Stoereffekte(saettigung=True, saettigung_db=0))
    check("Amplitude-Limit / Aref", abs(satt).max(), 1, 1e-14)
    check("Begrenzter Anteil im Vier-Sample-Beispiel", anteil, .5, 1e-14)
    erde = Stoereffekte(erdkruemmung=True)
    re = ERDRADIUS_M*erde.erdradius_faktor
    horizont = re*(math.acos(re/(re+20))+math.acos(re/(re+1000)))
    rx, _ = erdkoordinaten((0, 0, 20), (0, 0, 0), erde)
    for faktor, erwartet in ((.999, 1), (1.001, 0)):
        ziel, _ = erdkoordinaten((faktor*horizont, 0, 1000), (0, 0, 0), erde)
        check(f"Sichtbarkeit bei {faktor:g} × Horizont", int(freie_sicht(rx, ziel, erde)), erwartet, 0)
    atmos = effektbeispiele()["Fernbereich · atmosphärische Dämpfung"][1]
    af = simulate_frame(atmos)
    ist = 10*np.log10(af.spectrum.power.max()/af.vergleich.power.max())
    soll = -atmos.effekte.daempfung_db_km*2*af.config.targets[0].range_m/1000
    check("Atmosphäre, Zweiweg-Leistungsverlust / dB", ist, soll, 1e-9)
    nah = replace(effektbeispiele()["Puls · unvollständiges Nah-Echo"][1], targets=(Target(C*30/(2*5e6)),))
    p = process_pulses(generate_pulsed_echo(nah).beat, nah)
    check("Teilpuls: Peakleistung bei halbem Empfang", p.power.max(), .25, 1e-10)
    kurz_c = replace(nah, chirp_s=4e-6)
    p = process_pulses(generate_pulsed_echo(kurz_c).beat, kurz_c)
    check("Kurzer Puls: vollständige Peakleistung", p.power.max(), 1, 1e-10)
    clutter = replace(c, effekte=Stoereffekte(bodenclutter=True, clutter_innen_m=20, clutter_aussen_m=80, sigma0_db=-20))
    werte = [sum(q[1] for q in bodenpunkte(replace(clutter, seed=n))) for n in range(200)]
    soll = .01*np.pi*(80**2-20**2)
    check("Mittlere Boden-RCS über 200 Seeds / m²", np.mean(werte), soll, .04*soll)
    return {"checks": checks, "demos": demos, "horizont_bogen_m": horizont,
            "bestanden": all(q["bestanden"] for q in checks)}


def schreibe_effektbericht(ordner: Path, bericht: dict) -> None:
    schreibe_json(ordner/"stoereffekte.json", bericht)
    text = ["# Zuschaltbare Störmodelle: tatsächliche Ergebnisse", "",
            "Reproduzieren: `python -m radar_sim --validate`. Unabhängige Zusatzprüfungen: `python -m unittest tests.test_effekte -v`.", "",
            "Die Prüfkriterien beziehen sich auf die dokumentierten Ersatzmodelle, nicht auf eine Hardware- oder Wetterkalibrierung.", "",
            "| Analytischer / statistischer Check | Ist | Soll | Toleranz | Ergebnis |", "|---|---:|---:|---:|---|"]
    for q in bericht["checks"]:
        text.append(f"| {q['name']} | {q['ist']:.10g} | {q['soll']:.10g} | {q['toleranz']:.5g} | {'OK' if q['bestanden'] else 'FEHLER'} |")
    text += ["", "Phasenstatistik: zwölf unabhängige Realisierungen, je 4950 Samples auf Tc/8-Raster; Samples sind korreliert. Die festen Toleranzen berücksichtigen diese endliche Stichprobe und die diskrete Filterung.",
             f"Sichthorizont als Bogenentfernung für 20 m und 1000 m bei k=4/3: {bericht['horizont_bogen_m']:.3f} m.", "",
             "## Demonstrationsszenen", "", "Detektionsausfälle und zusätzliche Peaks sind hier ausdrücklich erwartete, gemessene Folgen. Extras können Clutter, Leakage oder Nebenkeulen sein; sie werden nicht pauschal als Rauschfehlalarme bezeichnet.", "",
             "| Szene | Frame | Soll | Zugeordnet | Extra | Begrenzt / % |", "|---|---:|---:|---:|---:|---:|"]
    for q in bericht["demos"]:
        text.append(f"| {q['name']} | {q['frame']} | {q['soll']} | {q['zugeordnet']} | {q['extras']} | {100*q['begrenzt']:.3f} |")
    text += ["", "Die Puls-Nahbereichsdemo nutzt Rechteckgewichtung für die einfache analytische Teilpuls-Referenz. Ihre Nebenkeulen können zusätzliche lokale CFAR-Peaks erzeugen. Hann verändert Hauptkeule und Teilpuls-Gewichtung.",
             "Keine gleiche mittlere Sendeleistung zwischen Radarverfahren behauptet. Der graue Vergleich behält Wellenform, Seed, Masthöhe und Puls-Sendesperre; nur die sechs optionalen Störungen entfallen.", ""]
    for n, name in enumerate(effektbeispiele(), 21):
        text += [f"![{name}](effekt_{n}.png)", ""]
    text += ["[Signalmodell und Grenzen](../docs/STOEREFFEKTE.md)", "",
             "Gesamtergebnis der Modellprüfungen: **"+("BESTANDEN" if bericht["bestanden"] else "FEHLER")+"**."]
    schreibe_markdown(ordner/"STOEREFFEKTE.md", text)


def export_effektplots(ordner: Path) -> None:
    from .report_plots import _plotfenster, export_plot
    from .processing import power_db
    import pyqtgraph as pg
    app, fenster, plot = _plotfenster()
    try:
        for nummer, (name, (_, c)) in enumerate(effektbeispiele().items(), 21):
            f = simulate_frame(c)
            plot.clear()
            if plot.legend is None:
                plot.addLegend()
            plot.setTitle(name+" · Maximum der Kartenleistung pro Entfernung")
            plot.setLabel("bottom", "Umweg" if c.radar_mode == "passive" else "Scheinentfernung", units="m")
            plot.setLabel("left", "10 log10(P / Aref²)", units="dB")
            for s, farbe, titel in ((f.vergleich, "#95a5bd", "Ohne zuschaltbare Störungen"),
                                    (f.spectrum, "#f9bd60", "Aktuelle Simulation")):
                if s is not None:
                    plot.plot(s.apparent_range_m, power_db(s.power.max(axis=0)), pen=pg.mkPen(farbe, width=2), name=titel)
            if c.radar_mode == "fmcw" and c.flugszene is None:
                plot.setXRange(0, 150, padding=0)
            elif c.radar_mode == "pulse_doppler" and c.flugszene is None:
                plot.setXRange(0, 3000, padding=0)
            else:
                plot.enableAutoRange()
            app.processEvents()
            export_plot(plot, ordner/f"effekt_{nummer}.png")
    finally:
        fenster.close()
