# Lange Routen und komplexe Manöver

Die bisherige Obergrenze von 120 Sekunden ist entfernt. Flugdauer und Zeitschritt müssen endlich und positiv sein; der Zeitschritt muss weiterhin mindestens ein Radar-Messpaket umfassen. Eine Route wird mit `Dauer = Bogenlänge / Speed` vollständig abgeflogen. Längere Dauer erzeugt keine große Frame-Sammlung: Der Rechenkern berechnet jeden Frame einzeln.

## Route übernehmen, ohne Punkte zu verlieren

1. Bis zu 256 räumliche Stützpunkte anklicken und in XY, XZ oder YZ bearbeiten.
2. Speed oder Dauer einstellen. Die jeweils andere Eingabe folgt automatisch.
3. **Übernehmen** prüft zuerst den vollständigen Entwurf einschließlich Radarprofil.
4. Bei Erfolg übernimmt die GUI die Konfiguration und startet einen Frame. Bei einem Fehler bleibt der Editor mit allen Punkten offen. Die Meldung nennt die Ursache; Eingaben korrigieren und erneut übernehmen.

Während des Zeichnens wird die tatsächliche Entwurfsroute geprüft. Die bisher simulierte Route wird dabei nicht überschrieben. **Abbrechen** verwirft den Entwurf ausdrücklich. Bodenberührung, unmittelbar benachbarte identische Punkte und eine Umkehr mit verschwindender Tangente bleiben unzulässig: Bei konstantem Tempo wäre die dafür nötige Beschleunigung unendlich. Solche Entwürfe bleiben trotzdem sichtbar und bearbeitbar.

Für eine weiter entfernte Route passt die Automatik zusätzlich den ADC-Vorlauf an. Mit sicherer oberer Entfernung Rmax gilt:

```text
Nskip = ceil(1,05 · fs · 2Rmax/c)
Tchirp = (Nskip + N)/fs
Tr >= Tchirp
```

Damit kommt das Echo vor dem ADC-Start an, während die Anzahl N der aufgenommenen Samples unverändert bleibt. Die längere Rampe verändert ihre Steigung; Träger, Bandbreite und Chirpzahl werden bei Bedarf wie bisher angepasst und vollständig validiert. Diese Automatik ersetzt keine Leistungsbilanz eines realen Radars.

Bei langen Flügen kann der Zeitschritt beispielsweise auf 2 oder 10 Sekunden steigen. Er beschreibt Simulationszeit. Die Wiedergabe wartet höchstens eine reale Sekunde zwischen Frames; dadurch passen auch große Schritte in den Qt-Timer. Modell und Plotposition verwenden weiterhin die vollständige Simulationszeit.

## Lesbarer Code mit weniger Wiederholungen

- `route.py` berechnet die natürliche kubische Geometrie. Das dreidiagonale Gleichungssystem wird vorwärts eliminiert und rückwärts eingesetzt. Es benötigt keine volle Matrix. Seine Lösung wird im Test unabhängig mit `numpy.linalg.solve` verglichen.
- Die Geometrie wird nur nach den Stützpunkten zwischengespeichert. Eine andere Geschwindigkeit benötigt keine erneute Kurvenberechnung.
- `flugbahn.py` enthält die Bewegung und die gemeinsame Zeichenabtastung `flugbahn_punkte`. Komplexere Routen erhalten auch im Plot genügend Punkte.
- `routen_editor.py` hält den gemeinsamen XYZ-Entwurf. Ein einzelner Helfer wandelt die Punkte ins Routenformat um; die drei Projektionen benötigen keine getrennten Routen.
- `tempo_anpassung.py` bleibt GUI-unabhängig und berechnet ein gültiges Radarprofil.
- `gui.py` hat einen gemeinsamen Weg für Radarwerte aus JSON und Automatik. Einheitenumrechnungen stehen zentral; Daueranzeige und Übernahme verwenden gemeinsame Funktionen. Doppelte Rückgaben, tote Grenzfälle und unbenutzte Variablen wurden entfernt.

Die vorhandenen Kernfunktionen und JSON-Dateien bleiben kompatibel. Formeln und notwendige Modellprüfungen wurden beim Kürzen erhalten.

## Reproduzieren

[14_mehrfachschleife_3d.json](../examples/14_mehrfachschleife_3d.json) zeigt drei räumliche Schleifen mit 80 Punkten, 70 m/s und rund 246 Sekunden Flugdauer. Über **JSON öffnen** laden oder direkt starten:

```powershell
python -m radar_sim --config examples\14_mehrfachschleife_3d.json
python -m unittest discover -s tests -v
python -m radar_sim --validate
```

Gemessene Prüfungen und Einschränkungen: [routen_manoever.json](../reports/routen_manoever.json).
