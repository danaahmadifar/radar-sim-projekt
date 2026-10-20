# Aufbau verstehen

Das Projekt hat einen Rechenkern und eine Desktop-Oberfläche. Die GUI sammelt Eingaben und zeigt Ergebnisse. Die Mathematik steht in normalen Python-Funktionen, die auch ohne Fenster aufrufbar sind. Es gibt keine fertige Radar-Bibliothek und kein zusätzliches Anwendungsframework.

## Mit dem Rechenkern anfangen

1. `config.py`: `RadarConfig` enthält die Radarparameter, `Target` die Sollobjekte. Intern gelten Meter, Sekunden und Hertz. `validate_config` prüft, ob die Eingaben zum Modell passen.
2. `model.py`: Die komplexen Echos werden addiert und mit dem Sendesignal gemischt. Das ergibt ein Beat-Signal mit der Form `[Chirp, Sample]`. Rauschen kommt mit einem festen Seed hinzu.
3. `processing.py`: Erst wird entlang der Samples die Entfernung ausgewertet, dann entlang der Chirps die Geschwindigkeit. Beide Schritte verwenden NumPy-FFTs. Leistung ist der Betragsquadratswert des komplexen Spektrums.
4. `detection.py`: CA-CFAR vergleicht jede auswertbare Zelle mit ihrem geschätzten Hintergrund. Lokale Maxima werden zu Targets zusammengefasst. Ein Target kann auch ein Fehlalarm sein.
5. `pipeline.py`: `simulate_frame` führt diese Schritte zusammen. `evaluation.py` vergleicht danach die Schätzung mit den bekannten Sollwerten. Die Sollwerte beeinflussen den Detektor nicht.

`python -m radar_sim --steps` führt fünf kleine Beispiele mit erwarteten Ergebnissen aus. Die genaue Herleitung und die Modellgrenzen stehen in [TECHNIK.md](TECHNIK.md).

## Die Bewegung ergänzen

`flugbahn.py` berechnet Ort und Geschwindigkeit zu einem Zeitpunkt. Die radiale Geschwindigkeit ist nur der Anteil entlang der Verbindung zwischen Target und Radar. Über der Station kann sie null sein, obwohl das Objekt weiterfliegt. Innerhalb eines kurzen Radarframes wird die Bewegung näherungsweise eingefroren; zwischen Frames wird die Flugbahn weitergerechnet.

`route.py` ist eine zusätzliche Funktion für selbst gezeichnete Routen. Eine glatte Kurve verhindert sprunghafte Richtungswechsel. Die zurückgelegte Strecke bestimmt die Position bei vorgegebenem Speed. Diese Berechnung ist anspruchsvoller als die geraden Beispielbahnen und wird in [REGLER_UND_ROUTEN.md](REGLER_UND_ROUTEN.md) getrennt erklärt.

Seit der Flughafen-Erweiterung sind die Orte und Geschwindigkeiten räumlich: X, Y, Z und vX, vY, vZ. `flughafen.py` liefert die neuen GUI-Startwerte. `antenne.py` berechnet den relativen Einweg-Leistungsgewinn aus der bekannten Richtung; dieser wirkt als Amplitudenfaktor im monostatischen Echo. Der späte ADC-Start in `config.py` und `model.py` erlaubt die Kilometerszenen mit einem gültigen überlappenden Rampenfenster.

## Die Oberfläche lesen

Die Oberfläche besteht aus drei gewöhnlichen Qt-Klassen. Jede hat eine klar abgegrenzte Aufgabe:

| Klasse / Datei | Aufgabe |
|---|---|
| `MainWindow` in `gui.py` | Eingaben prüfen, Hintergrundberechnung, Wiedergabe, Routenübernahme und Exporte steuern |
| `Eingabefelder` in `eingabefelder.py` | Die fünf Parameterreiter mit Zahlenfeldern, Tabellen, Auswahl und Tooltips aufbauen |
| `Ergebnisansichten` in `ergebnisansichten.py` | Overview, Signals, Results, Routeneditor und Antenna Pattern halten; Diagramme gemeinsam aktualisieren |

`MainWindow.start_frame` startet die Berechnung im Qt-Threadpool. `show_result` übergibt den fertigen Frame an `Ergebnisansichten.zeige_ergebnis` und steuert den nächsten Wiedergabeschritt. Die Ansichten behalten ihre Plotelemente und den Zoom. Eingabefelder berechnen keine Radarframes.

Im Quellcode findet man die Eingaben unter `fenster.tabs` und die Diagramme unter `fenster.views`, etwa `fenster.tabs.controls["chirps"]` oder `fenster.views.rd_plot`. Die öffentlichen Funktionen des Rechenkerns bleiben unverändert.

Die Zusatzdateien haben jeweils eine kleine Aufgabe: `regler.py` verbindet Zahlenfeld und Slider und liest/schreibt Qt-Feldwerte. `parametergrenzen.py` berechnet deren zulässige Bereiche und `routen_zeichnen.py` verarbeitet Mausbewegungen. `io.py` übernimmt JSON, CSV und das einheitliche Schreiben der Berichte. Weiße Pfeile und das Qt-Stylesheet `style.qss` liegen unter `radar_sim/assets/`.

`routen_editor.py` hält einen gemeinsamen Satz räumlicher Stützpunkte für XY, XZ und YZ. Die Ansichten sind nur verschiedene Projektionen dieser Daten. Die Radarverarbeitung bleibt dieselbe Range-/Doppler-Kette; bekannte Raumkoordinaten sind keine gemessenen Winkel. Details: [Flughafen, 3D und Antennen](AIRPORT_3D_ANTENNEN.md).

`flugansicht.py` zeichnet neben Range-Doppler eine drehbare XYZ-Ansicht. `projiziere` rechnet räumliche Punkte `[N,3]` in Bildschirmpositionen `[N,2]` um. Originalkoordinaten bleiben gespeichert, damit jeder neue Blickwinkel dieselben Daten verwendet. Achsen und Bodenraster werden nur bei einer neuen Flugbahn oder geänderter Antenne aufgebaut. Pro Frame bewegen sich nur die Target-Punkte. Die Darstellung benötigt NumPy und pyqtgraph, kein OpenGL und keine zusätzliche Bibliothek.

`tempo_anpassung.py` passt ein Radarprofil nach einer Speed-Eingabe an. Die Datei enthält eine normale Funktion mit dokumentierten Grenzen für Doppler, Bewegung, Beschleunigung und Beat-Abtastung. Die GUI übernimmt diese Werte sichtbar. Im Rechenkern bleiben die Prüfungen strikt; es findet keine versteckte Anpassung in `simulate_frame` statt. Das Szenario-Dropdown verwendet den Namen als stabilen Schlüssel, statt Qt nach Dataclass-Objekten suchen zu lassen.

Die Anwendung startet im Vollbild. F11 wechselt zwischen Vollbild und Fenster, Esc verlässt das Vollbild. Die Ansicht bleibt während der Framefolge bestehen: Es werden nur Daten aktualisiert und keine Fenster neu aufgebaut. Erklärungen stehen in Tooltips, ausführliche Formeln in der Dokumentation.

## Was das Projekt vorzeigbar macht

Zusätzlich zu FMCW ist kohärentes LFM-Puls-Doppler auswählbar: `pulsradar.py` berechnet echte verzögerte Basisbandpulse und lineare Pulskompression, danach die Doppler-FFT. `processing.py` wählt den Pfad. `Flugszene.radar_bahn` beschreibt optional die bewegte Sende-/Empfangsplattform; `flugbahn.py` berechnet R und v aus relativer Lage und Geschwindigkeit. Die Weltpositionen bleiben die bekannte Darstellung, keine Winkelschätzung. Das Pulsprofil wird bei Speed-Eingaben bewusst nicht automatisch umgebaut. Physik, Moduswechsel und Modellgrenzen: [Puls-Doppler](PULS_DOPPLER.md).

Die Physik ist hergeleitet, der Rechenkern lässt sich unabhängig benutzen und die Ergebnisse werden mit analytischen Referenzen verglichen. Tests und Messberichte machen die Grenzen sichtbar. Die Beschränkung auf Entfernung und radiale Geschwindigkeit hält den Umfang überschaubar. Das ideale Array-Richtdiagramm gewichtet bekannte Flugrichtungen; empfangene Arraykanäle, Winkelmessung und Tracking sind keine Bestandteile dieser Version.

`antennendiagramm.py` bereitet lokale Winkelschnitte und die Winkelkarte ohne Qt auf. `antennenansicht.py` zeichnet diese Werte im eigenen Tab; die Formeln bleiben in `antenne.py`. `antennen_validierung.py` vergleicht sie gegen direkte Element-Summen und analytische Halbwerte. Details: [Antennendiagramme](ANTENNENDIAGRAMME.md).

Die gemeinsame Radar-Eingabe steht in `_set_radar_inputs`, die Einheitenumrechnung in `RADAR_SKALEN`. `_route_uebernehmen` prüft zuerst und schließt den Editor erst nach Erfolg. Die Geometrie wird unabhängig vom Speed gecacht; Details der Kürzung und der langen Routen: [ROUTEN_UND_CODE.md](ROUTEN_UND_CODE.md).
