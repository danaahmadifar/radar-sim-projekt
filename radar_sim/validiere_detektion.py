"""Zusätzliche Kreise nachvollziehen: CFAR-Zelle ist nicht gleich Objekt-Peak."""

from pathlib import Path
from .io import schreibe_json, schreibe_markdown

from .config import RadarConfig
from .evaluation import match_targets
from .flugbahn import flugszenen
from .pipeline import simulate_frame


def pruefe_detektionskandidaten() -> dict:
    """Alle drei Hann-Flüge ohne AWGN prüfen, einschließlich zusätzlicher Kandidaten.

    Die Sollwerte werden ausschließlich zur Bewertung benutzt. Die Detektion
    selbst kennt weder Zielanzahl noch Sollentfernungen oder Sollgeschwindigkeiten.
    """
    szenen = []
    for name, szene in flugszenen().items():
        config = RadarConfig(targets=(), flugszene=szene, noise_enabled=False, window="hann")
        roh_treffer = 0
        kandidaten = 0
        zugeordnet = 0
        zusaetzlich = 0
        fehlend = 0
        fehlerhafte_frames = []
        for nummer in range(szene.letzter_frame + 1):
            ergebnis = simulate_frame(config, nummer)
            paare = match_targets(ergebnis.config, ergebnis.candidates)
            anzahl_soll = len(szene.bahnen)
            roh_treffer += int(ergebnis.cfar.mask.sum())
            kandidaten += len(ergebnis.candidates)
            zugeordnet += len(paare)
            zusaetzlich += len(ergebnis.candidates) - len(paare)
            fehlend += anzahl_soll - len(paare)
            if len(paare) != anzahl_soll or len(ergebnis.candidates) != anzahl_soll:
                fehlerhafte_frames.append(nummer)
        szenen.append({"szene": name, "frames": szene.letzter_frame + 1,
                       "cfar_zellen_gesamt": roh_treffer, "peak_kandidaten_gesamt": kandidaten,
                       "zugeordnet": zugeordnet, "zusaetzlich": zusaetzlich, "fehlend": fehlend,
                       "fehlerhafte_frames": fehlerhafte_frames})
    # Rechteck ist ein absichtlicher Gegenbeleg zu "ohne AWGN gibt es nie Fehlpeaks".
    rechteck = RadarConfig(targets=(), flugszene=flugszenen()["07_gegenverkehr"],
                           noise_enabled=False, window="rect")
    beispiel = simulate_frame(rechteck, 66)
    paare = match_targets(beispiel.config, beispiel.candidates)
    return {"bestanden": all(not szene["fehlerhafte_frames"] for szene in szenen),
            "hann_ohne_awgn": szenen,
            "rechteck_gegenbeispiel": {"frame": 66, "zeit_s": beispiel.zeit_s,
                                       "soll": 2, "kandidaten": len(beispiel.candidates),
                                       "zugeordnet": len(paare),
                                       "zusaetzlich": len(beispiel.candidates) - len(paare)}}


def schreibe_detektionsbericht(ordner: Path, bericht: dict) -> None:
    schreibe_json(ordner / "detektion.json", bericht)
    text = ["# Prüfung zusätzlicher Radar-Kreise", "",
            "Reproduzieren: `python -m radar_sim --validate`.", "",
            "## Gefundener Fehler und Korrektur", "",
            "Die frühere Gruppierung machte aus jeder zusammenhängenden CFAR-Trefferfläche einen Kreis, auch wenn dort kein lokales Maximum lag. "
            "Im ersten Überflug ohne AWGN entstanden dadurch fünf Kreise: ein Ziel und vier Flankenkandidaten bei etwa −105 bis −121 dB relativ zur Einheitsleistung.", "",
            "Jetzt muss ein Kandidat die CFAR-Schwelle überschreiten UND ein lokales Maximum gegenüber allen acht Nachbarn im vollständigen Leistungsbild sein. "
            "Die Nachbarn müssen selbst keine CFAR-Treffer sein. Zusammenhängende Bereiche ohne qualifizierten Peak erhalten keinen Kreis. "
            "Die reine CFAR-Maske bleibt unverändert zugänglich; keine Sollwerte oder vorgegebene Zielanzahl steuern die Auswahl.", "",
            "## Gemessene Flüge ohne AWGN, Hann-Fenster", "",
            "| Szene | Messpakete | Rohe CFAR-Zellen gesamt | Peak-Kandidaten gesamt | Zugeordnet | Zusätzliche | Fehlende |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for szene in bericht["hann_ohne_awgn"]:
        text.append(f"| {szene['szene']} | {szene['frames']} | {szene['cfar_zellen_gesamt']} | "
                    f"{szene['peak_kandidaten_gesamt']} | {szene['zugeordnet']} | {szene['zusaetzlich']} | {szene['fehlend']} |")
    rechteck = bericht["rechteck_gegenbeispiel"]
    text += ["", "Diese Prüfung ist eine Regression für die drei konkreten Szenen, keine allgemeine Null-Fehlalarm-Garantie.", "",
             "## Warum AWGN ausschalten allein nicht genügt", "",
             "Eine endliche Beobachtungsdauer verteilt einen nicht genau auf der FFT-Zelle liegenden Ton auf benachbarte Zellen. "
             "Die Fensterantwort hat Haupt- und Nebenkeulen. Diese verschwinden beim Ausschalten des Rauschens nicht. "
             "CA-CFAR schätzt einen Hintergrundpegel, hat aber kein Wissen über die Zahl realer Objekte. "
             "Die Pfa-Formel setzt unabhängige exponentielle Rauschleistungen voraus; im rein deterministischen, rauschfreien Spektrum gilt diese statistische Interpretation nicht.", "",
             f"Rechteck-Gegenbeispiel: Gegenverkehr, Frame {rechteck['frame']} bei {rechteck['zeit_s']:.1f} s. "
             f"{rechteck['kandidaten']} lokale Peak-Kandidaten bei 2 Sollobjekten, davon {rechteck['zusaetzlich']} zusätzlich. "
             "Hier bilden die stärkeren Rechteck-Nebenkeulen selbst lokale Maxima. Die Peak-Prüfung allein kann solche signalbedingten Geisterpeaks nicht grundsätzlich ausschließen.", "",
             "Mit AWGN gibt es zusätzlich statistische Fehlalarme. Pfa bezieht sich auf eine geprüfte Zelle, nicht auf den ganzen Frame "
             "und nicht auf die Kandidaten nach Gruppierung. Die Fehlalarmmessung in VALIDATION.md zählt weiterhin die rohe CFAR-Maske.", "",
             "![Spektralflanke und CFAR-Schwelle](detektion_schnitt.png)", "",
             "Die Grafik zeigt einen Dopplerschnitt durch den stärksten Entfernungsbin des ersten rauschfreien Überflugs. "
             "Punkte kennzeichnen rohe Schwellenüberschreitungen; ein Kreis verlangt zusätzlich ein lokales Maximum im gesamten 2D-Bild. "
             "Die Leistung und die Schwelle sind auf Aref²=1 bezogen. Zur Darstellung unter −160 dB abgeschnitten.", "",
             "## Abgleich mit der Theorie", "",
             "- Die Tests vergleichen das 2D-Spektrum eines Tons zwischen den FFT-Bins mit der geschlossenen Formel der endlichen geometrischen Reihe, für Rechteck und periodisches Hann. Kein FFT-Aufruf wird zur Referenzberechnung verwendet.",
             "- Der verzögerte Empfangschirp stimmt mit dem äquivalenten Beat-Modell überein; Laufzeit, Mischreihenfolge, Dopplervorzeichen und Kopplung bleiben unverändert.",
             "- Die CFAR-Schwelle wird gegen eine direkte Trainingsring-Summe geprüft. Die statistische Fehlalarmprüfung bleibt von der Peak-Gruppierung getrennt.",
             "- Ein 80 dB schwächeres, isoliertes Testziel bleibt detektierbar. Es wurde keine globale Anzeige-Pegelgrenze eingeführt, um schwache Kreise zu verstecken.", "",
             "Primärquellen: [MathWorks: CFAR-Annahmen](https://www.mathworks.com/help/phased/ug/constant-false-alarm-rate-cfar-detectors.html), "
             "[TI: Radar Hardware Accelerator User's Guide, Abschnitt 2.3.2](https://www.ti.com/lit/ug/swru526b/swru526b.pdf), "
             "[MathWorks: FFT und spektrale Leakage](https://www.mathworks.com/help/signal/ug/time-frequency-analysis-using-fft.html). "
             "TI beschreibt die Nachbarprüfung für 1D; hier wird sie ausdrücklich auf alle acht Nachbarn des 2D-Leistungsbildes angewendet.", "",
             "Gesamtergebnis der Hann-Regression: **" + ("BESTANDEN" if bericht["bestanden"] else "FEHLER") + "**."]
    schreibe_markdown(ordner / "DETEKTION.md", text)
