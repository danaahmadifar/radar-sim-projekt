"""Messbericht für eine frei definierte Route und die gekoppelten Wertebereiche."""

from dataclasses import replace
import math
from pathlib import Path
from .io import schreibe_json, schreibe_markdown
import random
import numpy as np

from .config import RadarConfig, validate_config
from .evaluation import match_targets, schaetztoleranzen
from .flugbahn import erstelle_routenszene, berechne_flugzustand, flugszenen
from .parametergrenzen import berechne_parameterbereiche
from .pipeline import simulate_frame
from .route import GezeichneteRoute, berechne_routendaten


def beispielroute() -> RadarConfig:
    route = GezeichneteRoute(((-80., 35.), (0., 55.), (80., 35.)), 5)
    return RadarConfig(targets=(), flugszene=erstelle_routenszene(route))


def pruefe_route_und_regler() -> dict:
    config = beispielroute()
    szene = config.flugszene
    messwerte = []
    fehlende = 0
    fehlerhafte_frames = []
    r_toleranz, v_toleranz = schaetztoleranzen(config)
    for nummer in range(szene.letzter_frame + 1):
        ergebnis = simulate_frame(config, nummer)
        paare = match_targets(ergebnis.config, ergebnis.candidates)
        z = ergebnis.flugzustaende[0]
        dr = paare[0].range_error_m if paare else None
        dv = paare[0].velocity_error_mps if paare else None
        if not paare:
            fehlende += 1
        if not paare or abs(dr) > 1.01 * r_toleranz or abs(dv) > 1.01 * v_toleranz:
            fehlerhafte_frames.append(nummer)
        messwerte.append({"zeit_s": ergebnis.zeit_s, "x_m": z.x_m, "hoehe_m": z.hoehe_m,
                         "flugtempo_mps": math.hypot(z.geschwindigkeit_x_mps, z.geschwindigkeit_hoehe_mps),
                         "radialgeschwindigkeit_mps": z.radialgeschwindigkeit_mps,
                         "entfernungsfehler_m": dr, "geschwindigkeitsfehler_mps": dv})
    ableitungsfehler = []
    for zeit in np.linspace(0.01, szene.dauer_s - 0.01, 101):
        dt = 1e-4
        vorher = berechne_flugzustand(szene.bahnen[0], float(zeit - dt))
        jetzt = berechne_flugzustand(szene.bahnen[0], float(zeit))
        nachher = berechne_flugzustand(szene.bahnen[0], float(zeit + dt))
        ableitungsfehler.append(abs((nachher.entfernung_m - vorher.entfernung_m) / (2 * dt)
                                    - jetzt.radialgeschwindigkeit_mps))

    # Bereichsendpunkte unabhängig mit der Kernprüfung vergleichen.
    zufall = random.Random(42)
    c = RadarConfig(targets=(), flugszene=flugszenen()["07_gegenverkehr"])
    ganz = ("chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples")
    bereichsfehler = []
    anzahl_pruefungen = 0
    for durchlauf in range(80):
        bereiche = berechne_parameterbereiche(c)
        for name, b in bereiche.items():
            for wert in (b.minimum, b.maximum, (b.minimum + b.maximum) / 2):
                wert = b.begrenze_wert(wert)
                if name in ganz:
                    wert = int(round(wert))
                anzahl_pruefungen += 1
                try:
                    validate_config(replace(c, **{name: wert}))
                except ValueError as exc:
                    bereichsfehler.append({"durchlauf": durchlauf, "parameter": name, "wert": wert, "fehler": str(exc)})
        name = zufall.choice(list(bereiche))
        b = bereiche[name]
        wert = b.begrenze_wert(b.minimum + zufall.random() * (b.maximum - b.minimum))
        c = replace(c, **{name: int(round(wert)) if name in ganz else wert})

    tempo_fehler = max(abs(m["flugtempo_mps"] - 5) for m in messwerte)
    return {"bestanden": not fehlerhafte_frames and not bereichsfehler and tempo_fehler < 1e-9
                         and max(ableitungsfehler) < 1e-5,
            "laenge_m": berechne_routendaten(szene.bahnen[0].route).laenge_m, "dauer_s": szene.dauer_s,
            "frames": len(messwerte), "fehlende_zuordnungen": fehlende,
            "fehlerhafte_frames": fehlerhafte_frames, "max_tempoabweichung_mps": tempo_fehler,
            "max_fehler_radiale_ableitung_mps": max(ableitungsfehler),
            "bereichspruefungen": anzahl_pruefungen, "bereichsfehler": bereichsfehler,
            "messwerte": messwerte}


def schreibe_routenbericht(ordner: Path, bericht: dict) -> None:
    schreibe_json(ordner / "route_und_regler.json", bericht)
    text = ["# Gezeichnete Route und gekoppelte Regler", "",
            "Reproduzieren: `python -m radar_sim --validate`. Beispiel: `examples/09_gezeichnete_route.json`.", "",
            "Eine natürliche kubische Kurve verbindet (−80,35), (0,55) und (80,35) m. Das Flugtempo ist 5 m/s.", "",
            f"- Berechnete Länge: {bericht['laenge_m']:.9f} m; Flugdauer: {bericht['dauer_s']:.9f} s.",
            f"- {bericht['frames']} Radar-Messpakete, {bericht['fehlende_zuordnungen']} fehlende Zuordnungen, "
            f"{len(bericht['fehlerhafte_frames'])} Pakete außerhalb der üblichen FFT-Toleranzen.",
            f"- Größte Tempoabweichung: {bericht['max_tempoabweichung_mps']:.3g} m/s.",
            f"- Radiale Geschwindigkeit gegen zentrale numerische Ableitung der Entfernung: maximal "
            f"{bericht['max_fehler_radiale_ableitung_mps']:.3g} m/s Abweichung, Schritt 0,1 ms.",
            f"- {bericht['bereichspruefungen']} Minimum-/Maximum-/Mittelpunkt-Prüfungen nach 80 reproduzierbaren Parameteränderungen, "
            f"{len(bericht['bereichsfehler'])} Abweichungen von der Kernprüfung.", "",
            "Die Reglerbereiche gelten jeweils bei festgehaltenen übrigen Werten und enthalten einen kleinen numerischen Sicherheitsabstand an Modellgrenzen. "
            "Sie garantieren gültige Modellparameter, keine bestimmte Detektionswahrscheinlichkeit. "
            "Direkt eingetippte ungültige Werte werden angezeigt und erklärt. Andere Werte werden nicht automatisch verändert.", "",
            "Die Route wird nach Bogenlänge parametrisiert. Enge Umkehrpunkte und Bodenüberschwinger werden abgewiesen; "
            "die Beschleunigungsschranke verwendet die Krümmung der geglätteten Kurve. "
            "Die Animation endet am letzten Punkt; Start- und Bremsvorgänge werden nicht simuliert.", "",
            "![Flugtempo und radiale Geschwindigkeit](routen_tempo.png)", "",
            "Gesamtergebnis: **" + ("BESTANDEN" if bericht["bestanden"] else "FEHLER") + "**.",
            "Rohwerte: [route_und_regler.json](route_und_regler.json)."]
    schreibe_markdown(ordner / "ROUTE_UND_REGLER.md", text)
