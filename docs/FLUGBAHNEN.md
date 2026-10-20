# Flugbahnen einfach erklärt

Diese Einführung erklärt die kleinen ursprünglichen Lehrbeispiele in der Ebene Y=0. Das Programm startet inzwischen mit einer Flughafen-Szene und unterstützt räumliche Routen: [Flughafen, 3D und Antennen](AIRPORT_3D_ANTENNEN.md). Im Raum gilt entsprechend R=√(X²+Y²+Z²) und v_radial=(XvX+YvY+ZvZ)/R.

## 1. Mit dieser Datei anfangen

Öffne zuerst [flugbahn.py](../radar_sim/flugbahn.py). `Flugbahn` speichert Startwerte, `berechne_flugzustand` rechnet sie in aktuelle Position und Geschwindigkeit um. Es werden gewöhnliche Formeln verwendet, kein Simulationsframework.

Die Station steht am Boden bei x=0 und h=0. Ein Objekt befindet sich bei horizontalem Ort x und Höhe h. Alle Zahlen stehen in Metern und Sekunden.

```text
Höhe h
  ^                Objekt (x,h)
  |                   o
  |                  /  R = direkte Entfernung zur Station
  |                 /
  +---------------▲--------------------> x
               Radar (0,0)
```

Die Höhe ist Teil des vorgegebenen Beispiels. Unser Radar schätzt weiterhin nur Entfernung und radiale Geschwindigkeit, keine Höhe oder Winkel.

## 2. Wie bewegt sich ein Objekt?

Die horizontale Bewegung ist gleichmäßig:

```text
x(t) = Startort + horizontale Geschwindigkeit * t
```

Für die Höhe darf eine konstante senkrechte Beschleunigung hinzukommen:

```text
h(t)  = Starthöhe + senkrechte Startgeschwindigkeit * t + Beschleunigung * t²/2
vh(t) = senkrechte Startgeschwindigkeit + Beschleunigung * t
```

Null Beschleunigung und null senkrechte Geschwindigkeit ergeben einen geraden Überflug in gleicher Höhe. Negative Beschleunigung ergibt eine nach unten offene Parabel. Die Beispielparabel verwendet −0,4 m/s². Ein gesteuertes Flugobjekt kann einer solchen Bahn folgen. Für eine freie Wurfbewegung wäre unter Vernachlässigung des Luftwiderstands −9,81 m/s² zu verwenden; das ist hier nicht das gewählte Beispiel.

## 3. Was davon sieht das Radar?

Die direkte Entfernung ergibt sich aus dem Satz des Pythagoras:

```text
R = sqrt(x² + h²)
```

Das Radar sieht, wie schnell sich **diese Entfernung** ändert:

```text
v_radial = dR/dt = (x * vx + h * vh) / R
```

Beispiel: x=−100 m, h=35 m, vx=+10 m/s und vh=0. Die Entfernung ist etwa 105,948 m; die radiale Geschwindigkeit etwa −9,439 m/s. Das Minus heißt Annäherung. Nach zehn Sekunden steht das Objekt genau über der Station: x=0, h=35 m. Seine horizontale Geschwindigkeit ist weiterhin 10 m/s, aber seine radiale Geschwindigkeit in diesem Moment null. Danach nimmt die Entfernung wieder zu.

Zwei entgegengesetzt fliegende Objekte können beide gleichzeitig auf die Station zufliegen. Die Flugrichtung links/rechts und das radiale Vorzeichen sind unterschiedliche Dinge.

## 4. Die vorgegebenen Fälle

| Datei | Werte | Kontrolle |
|---|---|---|
| `06_ueberflug.json` | x0=−100 m, h0=35 m, vx=10 m/s, vh=0, a=0 | Nach 10 s: R=35 m und v_radial=0 |
| `07_gegenverkehr.json` | Objekt 1 wie oben; Objekt 2: x0=80 m, h0=60 m, vx=−10 m/s | Verschiedene Höhen; Objekt 2 erreicht x=0 nach 8 s |
| `08_parabel.json` | x0=−100 m, h0=25 m, vx=10 m/s, vh0=4 m/s, a=−0,4 m/s² | h=45−0,002x²; nach 10 s: x=0, h=45 m; nach 20 s wieder h=25 m |

Die Beispiele entsprechen eher kleinen langsamen Flugobjekten als Verkehrsflugzeugen. 10 m/s sind 36 km/h. Die Höhen sind für dieses vereinfachte Lehrmodell gewählt; es wird keine reale Flugfreigabe oder Antennenabdeckung modelliert.

## 5. Wie entstehen die Radar-Signale während des Flugs?

[pipeline.py](../radar_sim/pipeline.py) führt diese Schritte aus:

1. Aus der Frame-Nummer und dem Zeitschritt die Flugzeit berechnen: t = Nummer * Zeitschritt.
2. Für jedes Flugobjekt aktuelle Entfernung und radiale Geschwindigkeit bestimmen.
3. Diese Werte als Radar-Ziele an [model.py](../radar_sim/model.py) übergeben.
4. Echo, Entfernungsspektrum, Geschwindigkeitskarte und Erkennung wie bisher berechnen.

Ein Radar-Messpaket dauert mit den Standardwerten 7,68 ms. Der nächste angezeigte Zeitpunkt liegt 0,1 s später. Die kurzen Pakete überlappen sich nicht. Innerhalb eines Pakets werden Entfernung und radiale Geschwindigkeit angenähert konstant gehalten; die Dopplerphase beschreibt die Bewegung. Zwischen den Paketen ändern sie sich entsprechend der Flugbahn. Es wird keine zweite zusätzliche Dopplerphase aus der Flugzeit addiert.

Die Eingabeprüfung begrenzt über die **gesamte** Flugbahn Entfernung, Tempo und Beschleunigung. Bei den sicheren Obergrenzen kann auch eine tatsächlich noch auswertbare Bahn abgewiesen werden; die Meldung sagt das ausdrücklich. Die Änderung der radialen Geschwindigkeit innerhalb eines Pakets darf höchstens ein Viertel der nominalen Geschwindigkeitsauflösung betragen. Für die Bahn werden außerdem Endpunkte und Höhenscheitel geprüft, damit kein Objekt unbemerkt zwischen zwei Bildern unter den Boden fällt.

`result.input_config` enthält die vollständige ursprüngliche Flugbahn. `result.config` enthält nur die aktuellen Radar-Ziele. Die Exporte verwenden die vollständige Flugbahn zusammen mit Frame-Nummer und Zeit, damit der berechnete Zustand reproduzierbar bleibt.

## 6. Warum flackert die Anzeige nicht mehr durch den Frame-Wechsel?

Die Eingaben bleiben während der ganzen Wiedergabe gesperrt. Sie werden nicht mehr bei jedem Frame aus- und eingeschaltet. Plots, Farbskala und Tabellenzellen werden wiederverwendet. Achsenbereiche und der schematische Chirp werden nur bei geänderten Radarparametern neu eingestellt. Der Zoom bleibt erhalten. Die Skalen von Signalamplitude und Spektrum passen zur ganzen Szene und springen nicht mit jedem Zufallswert. Neue Daten werden gemeinsam eingesetzt, bevor Qt das nächste Bild zeichnet.

Der GUI-Test prüft bei einer vollständigen kurzen Wiedergabe genau zwei Änderungen der Bedienbarkeit: einmal sperren und einmal am Ende freigeben. Er prüft außerdem unveränderten Zoom, wiederverwendete Tabellenzellen, automatisches Anhalten, Rücksetzen und die fünf PNG-Exporte. Ein Rauschsignal selbst ändert natürlich weiterhin seine Form; das gehört zur Simulation.

## 7. In welcher Reihenfolge den restlichen Code lesen?

1. `flugbahn.py`: Position, Höhe und radiale Geschwindigkeit.
2. `pipeline.py`: Reihenfolge der Berechnung.
3. `model.py`: Laufzeit, Mischfrequenz, Phasen und Rauschen.
4. `processing.py`: Fenster, zwei FFT-Richtungen und beschriftete Achsen.
5. `detection.py`: Umgebungsmittelwert, Erkennungsschwelle und zusammengehörige Treffer.
6. `gui.py`: Bedienung und Übergabe der Ergebnisse an die Diagramme.

Die Formeln stehen direkt bei den betreffenden Rechenschritten. Array-Formen werden als Tabellen erklärt. Die bisherigen englischen Namen der öffentlichen Radar-Schnittstelle bleiben erhalten, um vorhandene Beispiele und JSON-Dateien weiter verwenden zu können. Eine unnötige zweite API mit deutschen Aliasnamen wird vermieden.

Messwerte für alle 603 Pakete: [Flugbericht](../reports/FLUEGE.md). Für die ausführliche Signalherleitung: [TECHNIK.md](TECHNIK.md).

Zusätzliche Prüfung der Kreise ohne AWGN: [Detektionsbericht](../reports/DETEKTION.md). Wichtig: Ein Kreis benötigt jetzt sowohl eine Schwellenüberschreitung als auch ein lokales Maximum gegenüber seinen acht Nachbarn. Ein Peak-Kandidat ist weiterhin keine Bestätigung eines realen Objekts; Rauschen und Fenster-Nebenkeulen können Fehlpeaks erzeugen.

Eigene Routen sind ebenfalls möglich: Im Flug-Reiter **Route zeichnen** wählen, im Flugfeld ziehen, Tempo einstellen und **Übernehmen** drücken. Der Code glättet die Mauslinie und ordnet die Zeit nach der Weglänge zu. Dadurch bleibt das Tempo entlang der Route gleich. Die gleiche Sichtlinienformel berechnet weiterhin die radiale Geschwindigkeit. Vollständige Anleitung: [REGLER_UND_ROUTEN.md](REGLER_UND_ROUTEN.md).
