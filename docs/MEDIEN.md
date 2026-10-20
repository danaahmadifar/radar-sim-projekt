# Demobilder und Videos

Die Medien wurden am 20.10.2026 aus der Anwendung erzeugt. Die PNGs zeigen berechnete Zustände der GUI, keine gezeichneten Mockups. Für die Videos werden eigene Fensterinhalte mit `QWidget.grab()` erfasst und mit Qt Multimedia als H.264-MP4 codiert. Desktop, andere Programme und Mikrofon werden nicht aufgenommen.

Die Bewegung ist teilweise als Zeitraffer dargestellt. Die Bildunterschrift nennt Zeitraffer beziehungsweise Standbild. Die Videobildrate ist eine Präsentationseinstellung und kein gemessener Echtzeitdurchsatz des Radarsimulators. Die Radarberechnungen und Detektionen werden für die Aufnahmen unverändert ausgeführt. Einzelne Diagramme sind wie beim manuellen Zoomen auf einen passenden Ausschnitt eingestellt.

Die aktuelle Oberfläche verwendet je vier Haupttabs links und rechts. Zusammengehörige Ergebnisansichten werden über **Ansicht** ausgewählt. Die Results-Tabelle ist in der Simulation einblendbar; **Effekt-Demos** steht links unter **Effekte**.

## Dateien

Alle acht PNGs haben 1920 × 1080 Pixel:

| Bild | Inhalt |
|---|---|
| [01_fmcw_gegenverkehr.png](media/01_fmcw_gegenverkehr.png) | Zwei Flugrichtungen; 20 s Simulationszeit, zwei Sollwerte und zwei CFAR-Peaks |
| [02_puls_doppler.png](media/02_puls_doppler.png) | Puls-Doppler mit bewegtem Radar: Sendepulse, RX* und Pulskompression |
| [03_route_3d.png](media/03_route_3d.png) | Überflug mit leichter Sinusbewegung: XY, XZ, YZ; 600 m Höhe, 70 m/s, seitlich ±100 m |
| [04_antenna_pattern.png](media/04_antenna_pattern.png) | Klassisches Polardiagramm eines idealisierten Patch-Felds mit 12 × 6 Elementen |
| [05_passivradar.png](media/05_passivradar.png) | Fremdsender, Empfänger und bistatische Messgrößen des Passivradars |
| [06_effektvergleich.png](media/06_effektvergleich.png) | Schwaches Target mit und ohne Leakage/Phasenrauschen |
| [07_bodenclutter.png](media/07_bodenclutter.png) | Bewegtes Radar und Doppler der festen Bodenstreuer |
| [08_power_energy.png](media/08_power_energy.png) | Ausgefüllte Sendeleistungskurven, gleiche mittlere Leistung, Energie und echte Pulskompression; Empfangsausschnitt um den Filterpeak vergrößert |

Die Videos haben ebenfalls 1920 × 1080 Pixel, 12 Bilder/s und keine Tonspur:

| Video | Dauer | Videoframes | Dateigröße |
|---|---:|---:|---:|
| [01_gegenverkehr.mp4](media/01_gegenverkehr.mp4) | 20,167 s | 242 | ca. 7,1 MiB |
| [02_verfahren_und_effekte.mp4](media/02_verfahren_und_effekte.mp4) | 32,000 s | 384 | ca. 4,1 MiB |

Das erste Video zeigt 60 s simulierten Gegenverkehr mit nominell dreifachem Abspieltempo. Das zweite Video enthält:

| Beginn | Abschnitt |
|---|---|
| 0:00 | Puls-Doppler mit bewegter Plattform, ungefähr doppeltes Tempo |
| 0:05,5 | Empfangssignal und Pulskompression, Standbild |
| 0:08,5 | Power / Energy: hohe Puls-Spitzen bei gleicher Frame-Energie, Standbild |
| 0:12,5 | Räumliche Route in drei Projektionen, Standbild |
| 0:15,5 | Klassisches Antennen-Polardiagramm, Standbild |
| 0:18,5 | Passivradar mit Fremdsender, Standbild |
| 0:22,5 | Leakage und Phasenrauschen, Standbild |
| 0:27,5 | Bewegtes Radar mit Bodenclutter, ungefähr Originaltempo |

## Erzeugen und prüfen

Im Projektordner mit den installierten Projektabhängigkeiten ausführen:

```powershell
# Acht Bilder und beide Videos neu erzeugen
python tools/demo_medien.py

# Alternativ nur die Bilder erzeugen
python tools/demo_medien.py --images-only

# Erzeugte Dateien und Videowiedergabe prüfen
python tools/pruefe_medien.py
```

Die Skripte schreiben nach `docs/media/` und überschreiben dort gleichnamige Ausgaben. `--output anderer_ordner` ist für die Erzeugung möglich; das Prüfsystem prüft die im Projekt mitgelieferten Dateien unter `docs/media/`. `medien.json` enthält Dateinamen, Auflösung, Simulationszeitpunkte, Peakzahlen und Video-Kapitel des letzten Erzeugungslaufs. Bei `--images-only` enthält dieses Manifest nur die neu erzeugten Bilder.

Die Videoerstellung benötigt zusätzlich zu den ohnehin verwendeten PyQt6-Modulen ein Qt ab Version 6.8 mit verfügbarem H.264-Encoder. Getestet wurde Qt Multimedia aus der vorhandenen PyQt6-Installation unter Windows. Es wurden keine weiteren Python-Pakete und kein separates ffmpeg-Programm installiert. Der normale Simulator benötigt diese optionale Videoerstellung nicht. Die verwendete [Qt-Schnittstelle QVideoFrameInput](https://doc.qt.io/qt-6/qvideoframeinput.html) nimmt die GUI-Bilder entgegen; Codec und Container übernimmt QMediaRecorder.

## Tatsächliche Medienprüfung

`tools/pruefe_medien.py` wurde erfolgreich ausgeführt:

- Alle acht PNG-Dateien konnten mit 1920 × 1080 Pixeln gelesen werden.
- MP4-Container geprüft: H.264 (`avc1`), 1920 × 1080, jeweils genau eine Videospur und keine Tonspur.
- Samplezahlen stimmen mit dem Erzeugungsmanifest überein: 242 und 384 Frames.
- Beide Videos wurden mit Qt vollständig bis zum Ende abgespielt und dekodiert. Tatsächlich empfangen: alle 626 Videoframes.
- Anfang, Mitte und Ende jedes Videos wurden als PNG gespeichert und auf nichtleeren Bildinhalt geprüft. Die Demobilder und dekodierte Kontrollbilder wurden zusätzlich visuell geprüft.

Die konkreten Ergebnisse stehen in [media/pruefung.json](media/pruefung.json); die dekodierten Kontrollbilder liegen unter `media/pruefung/`. Diese Medienprüfung ergänzt die wissenschaftlichen Modellprüfungen und ersetzt sie nicht.

## Orientierung an den vorhandenen Projekten

Für die neue README wurden die tatsächlichen öffentlichen READMEs dieser Projekte über die GitHub-API gelesen:

- [ESP32 WLAN Signal-Tester](https://github.com/danaahmadifar/wifi-signal-tester-mit-esp32-support): kurzer Überblick, Bilder, nummerierte Funktionsbereiche, Projektstruktur und Einrichtung.
- [Acoustic Doppler Simulator](https://github.com/danaahmadifar/acoustic-doppler-simulator): Demo am Anfang, übersichtliche Funktionen und Startanleitung.
- [Patch-Antenne 2,45 GHz](https://github.com/danaahmadifar/patch-antenna-2.45ghz): sachliche technische Beschreibung und getrennte Darstellung der Ergebnisse.

Zusätzlich wurden `python_gui/requirements.txt`, die Imports von `python_gui/main.py` und `python_gui/ui/views/analyzer_ansicht.py` des WLAN-Projekts geprüft. NumPy, PyQt6 und pyqtgraph werden dort tatsächlich verwendet. Die zusätzliche serielle Schnittstelle dieses Hardwareprojekts benötigt der Radarsimulator nicht. Es fand kein vollständiger Codeaudit dieser Repositories statt; übernommen wurde ihre verständliche Dokumentationsstruktur.
