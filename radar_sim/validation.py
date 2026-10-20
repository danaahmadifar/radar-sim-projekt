"""Automatischer Bericht: echte Messwerte, PNGs mit pyqtgraph, keine Plot-Bibliothek extra."""

from dataclasses import asdict, replace
from pathlib import Path
from .io import schreibe_json, schreibe_markdown
import platform
import sys
import time
import numpy as np

from .config import RadarConfig, validate_config
from .evaluation import match_targets, schaetztoleranzen
from .model import generate_echo
from .pipeline import simulate_frame
from .processing import process_beat
from .detection import ca_cfar
from .scenarios import scenarios
from .flug_validierung import pruefe_fluege, schreibe_flugbericht
from .validiere_detektion import pruefe_detektionskandidaten, schreibe_detektionsbericht
from .routen_validierung import pruefe_route_und_regler, schreibe_routenbericht
from .antennen_validierung import pruefe_patterns, schreibe_antennenbericht, export_antennenplots
from .puls_validierung import pruefe_pulsradar, schreibe_pulsbericht, export_pulsplots
from .fern_passiv_validierung import pruefe_fern_und_passiv, schreibe_fern_passivbericht, export_fern_passivplots
from .effekt_validierung import pruefe_stoermodelle, schreibe_effektbericht, export_effektplots


def noise_experiment(window: str, trials: int = 96) -> dict:
    """Monte Carlo über unabhängige Frames; CI aus Streuung der Frame-Raten.

    Innerhalb eines Frames sind CFAR-Entscheidungen wegen überlappender Fenster
    abhängig. Deshalb KEIN naives binomiales Konfidenzintervall über alle CUTs.
    """
    config = RadarConfig(chirps=64, window=window, targets=(), pfa=1e-3, seed=2026)
    validate_config(config)
    fehlalarme, frame_raten, gepruefte_zellen = 0, [], 0
    for frame_nummer in range(trials):
        spectrum = process_beat(generate_echo(config, frame_nummer).beat, config)
        cfar = ca_cfar(spectrum.power, config)
        treffer, gueltige_zellen = int(cfar.mask.sum()), int(cfar.valid.sum())
        fehlalarme += treffer
        gepruefte_zellen += gueltige_zellen
        frame_raten.append(treffer / gueltige_zellen)
    fehlalarmrate = fehlalarme / gepruefte_zellen
    standardfehler = float(np.std(frame_raten, ddof=1) / np.sqrt(trials))
    return {"window": window, "trials": trials, "valid_cells": gepruefte_zellen, "false_alarms": fehlalarme,
            "nominal_pfa": config.pfa, "empirical_pfa": fehlalarmrate,
            "ci95_frame_mean": [max(0, fehlalarmrate - 1.96 * standardfehler), fehlalarmrate + 1.96 * standardfehler],
            "standard_error": standardfehler,
            "check": abs(fehlalarmrate - config.pfa) <= max(4 * standardfehler, 0.15 * config.pfa) if window == "rect" else None}


def run_validation(directory: str | Path = "reports") -> dict:
    """Schreibt Radar-, Flug-, Detektions- und Routenberichte mit PNG-Diagrammen."""
    startzeit = time.perf_counter()
    ordner = Path(directory)
    ordner.mkdir(parents=True, exist_ok=True)
    ergebnisse = []
    frames = {}
    beispiele = scenarios()
    for name, config in beispiele.items():
        if name == "noise_only":
            continue
        frame = simulate_frame(config)
        frames[name] = frame
        zuordnungen = match_targets(config, frame.candidates)
        # Diskrete Maximalzelle, kein Sub-Bin-Schätzer. Kopplungskorrektur addiert fd-Fehler.
        entfernungstoleranz, geschwindigkeitstoleranz = schaetztoleranzen(config)
        fehler_ok = all(abs(m.range_error_m) <= entfernungstoleranz * 1.01
                        and abs(m.velocity_error_mps) <= geschwindigkeitstoleranz * 1.01 for m in zuordnungen)
        grenzfall = name == "near_resolution"
        ergebnisse.append({"scenario": name, "targets": len(config.targets), "candidates": len(frame.candidates),
                        "matched": len(zuordnungen), "unmatched_candidates": len(frame.candidates) - len(zuordnungen),
                        "matches": [asdict(m) for m in zuordnungen], "range_tolerance_m": entfernungstoleranz,
                        "velocity_tolerance_mps": geschwindigkeitstoleranz,
                        "pass": None if grenzfall else len(zuordnungen) == len(config.targets) and fehler_ok,
                        "purpose": "Auflösungsgrenze: keine garantierte Trennung mit Hann" if grenzfall else "Schätzprüfung"})
    snr_reihe = []
    config = beispiele["04_cfar_noise"]
    for snr in (-40, -30, -20, 0, 15):
        zugeordnet = zusaetzliche = 0
        for wiederholung in range(16):
            frame = simulate_frame(replace(config, snr_db=snr), wiederholung)
            anzahl = len(match_targets(frame.config, frame.candidates))
            zugeordnet += anzahl
            zusaetzliche += len(frame.candidates) - anzahl
        snr_reihe.append({"snr_db": snr, "trials": 16, "matched_targets": zugeordnet,
                          "possible_targets": 32, "detection_fraction": zugeordnet / 32,
                          "extra_candidates": zusaetzliche})
    rauschversuche = [noise_experiment("rect"), noise_experiment("hann")]
    flugbericht = pruefe_fluege()
    detektionsbericht = pruefe_detektionskandidaten()
    routenbericht = pruefe_route_und_regler()
    from .airport_validierung import pruefe_airport, schreibe_airportbericht, export_airport_plot
    airportbericht = pruefe_airport()
    antennenbericht = pruefe_patterns()
    pulsbericht = pruefe_pulsradar()
    fern_passiv = pruefe_fern_und_passiv()
    stoerbericht = pruefe_stoermodelle()
    bericht = {"python": sys.version.split()[0], "numpy": np.__version__, "platform": platform.platform(),
              "seed": 42, "scenarios": ergebnisse, "snr_sweep": snr_reihe, "noise_experiments": rauschversuche,
              "flight_validation_passed": flugbericht["bestanden"],
              "detection_validation_passed": detektionsbericht["bestanden"],
              "route_validation_passed": routenbericht["bestanden"],
              "airport_3d_validation_passed": airportbericht["bestanden"],
              "antenna_validation_passed": antennenbericht["bestanden"],
              "pulse_platform_validation_passed": pulsbericht["bestanden"],
              "long_range_passive_validation_passed": fern_passiv["bestanden"],
              "impairment_validation_passed": stoerbericht["bestanden"],
              "passed": all(r["pass"] is not False for r in ergebnisse) and bool(rauschversuche[0]["check"])
                        and flugbericht["bestanden"] and detektionsbericht["bestanden"] and routenbericht["bestanden"]
                        and airportbericht["bestanden"] and antennenbericht["bestanden"] and pulsbericht["bestanden"] and fern_passiv["bestanden"] and stoerbericht["bestanden"]}
    # Qt erst zum Export laden: Der Rechenkern selbst benötigt keine GUI.
    from .report_plots import export_report_plots, export_flug_plots, export_detektions_plot, export_routen_plot
    export_report_plots(ordner, frames["05_dashboard"], snr_reihe, rauschversuche)
    export_flug_plots(ordner, flugbericht)
    schreibe_flugbericht(ordner, flugbericht)
    schreibe_detektionsbericht(ordner, detektionsbericht)
    export_detektions_plot(ordner)
    schreibe_routenbericht(ordner, routenbericht)
    export_routen_plot(ordner, routenbericht)
    export_airport_plot(ordner, airportbericht)
    schreibe_airportbericht(ordner, airportbericht)
    export_antennenplots(ordner)
    schreibe_antennenbericht(ordner, antennenbericht)
    schreibe_pulsbericht(ordner, pulsbericht)
    export_pulsplots(ordner, pulsbericht)
    schreibe_fern_passivbericht(ordner, fern_passiv)
    export_fern_passivplots(ordner)
    schreibe_effektbericht(ordner, stoerbericht)
    export_effektplots(ordner)
    bericht["elapsed_s"] = time.perf_counter() - startzeit
    schreibe_json(ordner / "validation.json", bericht)
    textzeilen = ["# Gemessener Validierungsbericht", "", f"Python {bericht['python']}, NumPy {bericht['numpy']}; {bericht['platform']}.",
             "Reproduzieren: `python -m radar_sim --validate`. Szenen-Seed 42; Rausch-Monte-Carlo Seed 2026.", "",
             "| Szenario | Soll | Kandidaten | Zugeordnet | max. ΔR abs. / m | max. Δv abs. / m/s | Ergebnis |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for ergebnis in ergebnisse:
        er = max((abs(m["range_error_m"]) for m in ergebnis["matches"]), default=0)
        ev = max((abs(m["velocity_error_mps"]) for m in ergebnis["matches"]), default=0)
        status = "DEMO" if ergebnis["pass"] is None else ("BESTANDEN" if ergebnis["pass"] else "FEHLER")
        textzeilen.append(f"| {ergebnis['scenario']} | {ergebnis['targets']} | {ergebnis['candidates']} | {ergebnis['matched']} | {er:.6f} | {ev:.6f} | {status} |")
    textzeilen += ["", "Nullzuordnungen sind fehlende Detektionen; ein Fehlerwert 0 bei fehlender Zuordnung ist kein erfolgreicher Schätzwert.",
              "Toleranz: ΔR/2 + c·Δfd/(4S), Δv/2. Es wird das Maximum einer diskreten FFT-Zelle verwendet, ohne Interpolation.",
              "Hann verbreitert Hauptkeulen; das Grenzfallbeispiel bewertet die beobachtete Trennung und ist kein Bestehenstest.", "",
              "## Rauschmessung", "", "| Fenster | Gültige CUTs | Fehlalarme | Pfa gemessen | 95-%-Intervall (Frame-Mittel) |", "|---|---:|---:|---:|---|"]
    for n in rauschversuche:
        lo, hi = n["ci95_frame_mean"]
        textzeilen.append(f"| {n['window']} | {n['valid_cells']} | {n['false_alarms']} | {n['empirical_pfa']:.6g} | [{lo:.6g}, {hi:.6g}] |")
    textzeilen += ["", "96 unabhängige Frames je Fenster, Pfa nominal 0,001. Intervalle: Normalapproximation aus der Streuung der Frame-Raten.",
              "Rechteck-Prüfung: Abweichung ≤ max(4 Standardfehler, 15 % der Pfa). Hann wird gemessen, aber nicht gegen die Unabhängigkeitsformel bestanden.",
              "Überlappende CFAR-Trainingsringe erzeugen abhängige Entscheidungen; Fensterung korreliert zusätzlich die FFT-Bins.", "",
              "## SNR-Sweep", "", "SNR ist vor Fenster/FFT auf Einheitsleistung bezogen, kein SNR der summierten Szene.",
              "16 Frames je SNR, zwei Ziele pro Frame. Die Zuordnungsquote innerhalb des Gates ist eine kleine Demonstrationsstichprobe, keine allgemeine Pd-Kurve.", "",
              "| SNR / dB | Zugeordnet / 32 | Zusätzliche Kandidaten |", "|---:|---:|---:|"]
    textzeilen.extend(f"| {s['snr_db']} | {s['matched_targets']} | {s['extra_candidates']} |" for s in snr_reihe)
    textzeilen += ["", "![Range-Doppler](range_doppler.png)", "![Entfernungsspektrum](range_spectrum.png)",
              "![Zuordnungsquote](snr_sweep.png)", "![CFAR](cfar_pfa.png)", "",
              "Die drei bewegten Flugbeispiele werden an jedem Zeitschritt geprüft: [Flugbericht](FLUEGE.md).", "",
              "Zusätzliche Prüfung ohne AWGN, analytische Grundlagen und Rechteck-Gegenbeispiel: [Detektionsbericht](DETEKTION.md).", "",
              "Eine frei definierte Flugkurve mit konstantem Tempo und die gekoppelten Parameterbereiche: [Route und Regler](ROUTE_UND_REGLER.md).", "",
              "Flughafenszenen mit 3D-Bewegung und aktiver Richtwirkung: [Airport und 3D](AIRPORT_3D.md).", "",
              "Antennendiagramme gegen Element-Summen und analytische Halbwerte: [Antennen](ANTENNEN.md).", "",
              "LFM-Puls-Doppler, Relativbewegung beider Flugzeuge und gemessene CFAR-Raten: [Puls und Plattform](PULS_UND_PLATTFORM.md).", "",
              "300-km-Profile, Trennungsdemo und passive bistatische CAF: [Fernbereich und Passivradar](FERN_UND_PASSIV.md).", "",
              "Leakage, Sättigung, Phasenrauschen, Horizont, Atmosphäre und Bodenclutter: [Störmodelle](STOEREFFEKTE.md).", "",
              "Gesamtergebnis der harten Prüfungen: **" + ("BESTANDEN" if bericht["passed"] else "FEHLER") + "**.",
              "Rohwerte und Einzelabweichungen: [validation.json](validation.json)."]
    schreibe_markdown(ordner / "VALIDATION.md", textzeilen)
    return bericht
