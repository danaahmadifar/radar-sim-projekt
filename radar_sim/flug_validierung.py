"""Alle Zeitpunkte der drei Flüge prüfen und einen lesbaren Bericht schreiben."""

from pathlib import Path
from .io import schreibe_json, schreibe_markdown
import numpy as np

from .config import RadarConfig
from .evaluation import match_targets, schaetztoleranzen
from .flugbahn import flugszenen
from .pipeline import simulate_frame


def pruefe_fluege() -> dict:
    """Prüft jeden dargestellten Frame, nicht nur Start und Ende der Flugbahn.

    Die Sollwerte sind die bekannte Geometrie. FFT-Schätzwerte dürfen um einen
    halben Bin abweichen; bei Entfernung kommt der Doppler-Korrekturfehler hinzu.
    Eine zweite, unabhängige Geometrieprüfung mit Zahlenwerten und numerischer
    Ableitung steht in tests/test_flugbahn.py.
    """
    ergebnisse = []
    for dateiname, szene in flugszenen().items():
        config = RadarConfig(targets=(), flugszene=szene)
        entfernungstoleranz, geschwindigkeitstoleranz = schaetztoleranzen(config)
        messwerte = []
        entfernungsfehler = []
        geschwindigkeitsfehler = []
        fehlerhafte_frames = []
        fehlende_objekte = 0
        for frame_nummer in range(szene.letzter_frame + 1):
            ergebnis = simulate_frame(config, frame_nummer)
            zuordnungen = match_targets(ergebnis.config, ergebnis.candidates)
            nach_objekt = {paar.target_index: paar for paar in zuordnungen}
            frame_in_ordnung = len(zuordnungen) == len(szene.bahnen)
            for nummer, zustand in enumerate(ergebnis.flugzustaende):
                zuordnung = nach_objekt.get(nummer)
                zeile = {"objekt": nummer + 1, "zeit_s": ergebnis.zeit_s,
                         "x_m": zustand.x_m, "hoehe_m": zustand.hoehe_m,
                         "entfernung_soll_m": zustand.entfernung_m,
                         "geschwindigkeit_soll_mps": zustand.radialgeschwindigkeit_mps,
                         "entfernung_geschaetzt_m": None, "geschwindigkeit_geschaetzt_mps": None}
                if zuordnung is None:
                    fehlende_objekte += 1
                else:
                    kandidat = ergebnis.candidates[zuordnung.candidate_index]
                    zeile["entfernung_geschaetzt_m"] = kandidat.range_m
                    zeile["geschwindigkeit_geschaetzt_mps"] = kandidat.velocity_mps
                    entfernungsfehler.append(zuordnung.range_error_m)
                    geschwindigkeitsfehler.append(zuordnung.velocity_error_mps)
                    if (abs(zuordnung.range_error_m) > 1.01 * entfernungstoleranz
                            or abs(zuordnung.velocity_error_mps) > 1.01 * geschwindigkeitstoleranz):
                        frame_in_ordnung = False
                messwerte.append(zeile)
            if not frame_in_ordnung:
                fehlerhafte_frames.append(frame_nummer)
        ergebnisse.append({
            "dateiname": dateiname, "name": szene.name,
            "frames": szene.letzter_frame + 1, "soll_objekte_gesamt": len(messwerte),
            "fehlende_zuordnungen": fehlende_objekte, "fehlerhafte_frames": fehlerhafte_frames,
            "max_entfernungsfehler_m": max(map(abs, entfernungsfehler), default=None),
            "max_geschwindigkeitsfehler_mps": max(map(abs, geschwindigkeitsfehler), default=None),
            "rmse_entfernung_m": float(np.sqrt(np.mean(np.square(entfernungsfehler)))) if entfernungsfehler else None,
            "rmse_geschwindigkeit_mps": float(np.sqrt(np.mean(np.square(geschwindigkeitsfehler)))) if geschwindigkeitsfehler else None,
            "entfernungstoleranz_m": entfernungstoleranz,
            "geschwindigkeitstoleranz_mps": geschwindigkeitstoleranz,
            "bestanden": not fehlerhafte_frames, "messwerte": messwerte,
        })
    return {"bestanden": all(e["bestanden"] for e in ergebnisse), "szenen": ergebnisse}


def schreibe_flugbericht(ordner: Path, bericht: dict) -> None:
    """Speichert tatsächliche Messwerte; kein Teststatus wird vorweggenommen."""
    schreibe_json(ordner / "fluege.json", bericht)
    text = ["# Validierung der drei Flugbeispiele", "",
            "Reproduzieren: `python -m radar_sim --validate`. Seed 42, Referenz-SNR 0 dB.",
            "Je Szene 20 s Flugzeit, 0,1 s Zeitschritt, 201 berechnete Radar-Messpakete.", "",
            "| Flug | Messpakete | Sollobjekte über alle Zeiten | Fehlende Zuordnungen | max. Entfernungsfehler / m | max. Geschwindigkeitsfehler / m/s | Ergebnis |",
            "|---|---:|---:|---:|---:|---:|---|"]
    for szene in bericht["szenen"]:
        status = "BESTANDEN" if szene["bestanden"] else "FEHLER"
        entfernung = szene["max_entfernungsfehler_m"]
        geschwindigkeit = szene["max_geschwindigkeitsfehler_mps"]
        entfernung_text = "—" if entfernung is None else f"{entfernung:.6f}"
        geschwindigkeit_text = "—" if geschwindigkeit is None else f"{geschwindigkeit:.6f}"
        text.append(f"| {szene['name']} | {szene['frames']} | {szene['soll_objekte_gesamt']} | "
                    f"{szene['fehlende_zuordnungen']} | {entfernung_text} | {geschwindigkeit_text} | {status} |")
    text += ["", "Die Grenzwerte sind ΔR/2 + c·Δfd/(4S) und Δv/2, jeweils mit 1 % Rechenspielraum.",
             "Geprüft werden die Schätzfehler aller zugeordneten Ziele und das Fehlen von Zuordnungen.",
             "Zusätzliche Erkennungen durch Rauschen sind weiterhin möglich; siehe die allgemeine CFAR-Validierung.",
             "RMSE (Wurzel des mittleren quadratischen Fehlers), Einzelmessungen und fehlerhafte Frame-Nummern stehen in [fluege.json](fluege.json).", "",
             "Die Flugbahn ist bekannt. Höhe und horizontaler Ort sind keine Radar-Schätzwerte.",
             "Bei Gegenverkehr können beide Objekte gleichzeitig auf die Station zufliegen: entgegengesetzte Flugrichtung bedeutet nicht automatisch entgegengesetzte radiale Geschwindigkeit.",
             "Die Parabel ist eine vorgegebene Bahn eines gesteuerten Flugobjekts mit −0,4 m/s² senkrechter Beschleunigung, keine freie Wurfbewegung.", "",
             "Einzelüberflug und Objekt 1 des Gegenverkehrs haben dieselbe Bahn; ihre Kurven liegen in den Diagrammen übereinander.", "",
             "![Flugbahnen](flugbahnen.png)", "![Entfernung über der Flugzeit](flug_entfernung.png)",
             "![Radiale Geschwindigkeit über der Flugzeit](flug_geschwindigkeit.png)"]
    schreibe_markdown(ordner / "FLUEGE.md", text)
