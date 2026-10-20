# Gekoppelte Regler und eigene Flugrouten

## Die Regler bedienen

Jede numerische Einstellung besitzt ein Zahlenfeld und einen Slider. Auch Werte in den Objekt- und Flugtabellen öffnen bei Doppelklick einen Slider-Dialog. Auswahlmöglichkeiten wie Hann/Rechteck bleiben Auswahllisten, Schalter wie AWGN bleiben Schalter.

Unter jedem Radar-Slider steht der berechnete Bereich. Bewege die Maus über Beschriftung, Zahlenfeld oder Slider: Ein Tooltip erklärt die Aufgabe der Größe in einfachen Worten. Der Slider zeigt außerdem die genaueren Bereichsgrenzen an. Die kurze Anzeige darunter ist zur besseren Lesbarkeit gerundet.

Die Grenzen werden nach 60 ms Eingabepause neu berechnet. Grundlage sind die aktuellen übrigen Größen und die gesamte Flugbahn, nicht nur die aktuelle Objektposition. Die Berechnung benötigt keine FFT und keine großen Signalarrays. Die bestehende Kernprüfung bleibt die letzte Instanz vor jeder Simulation.

Die Slider-Dialoge der Tabellen berechnen ebenfalls einen gekoppelten Einzelwertbereich. Dafür wird die unveränderte Kernprüfung benutzt und die gültige Intervallgrenze durch wiederholtes Halbieren gesucht. So werden bei einem Flug beispielsweise die zulässige Höhe und horizontale Geschwindigkeit unter Berücksichtigung der gesamten Bahn eingegrenzt. Die Suche läuft nur beim Öffnen eines Dialogs. Bei bereits widersprüchlichen anderen Eingaben wird ein nicht verfügbarer Bereich erklärt; direkte Korrekturen im Zahlenfeld bleiben möglich.

Ein Slider kann nur Werte aus seinem Bereich wählen. Für aktiven Chirp und Abtastrate gilt zusätzlich ein Raster, damit `Samples = Abtastrate × Chirpdauer − ADC-Vorlauf` eine ganze Zahl bleibt. Direkt eingetippte Werte werden nicht stillschweigend zusammen mit anderen Größen verändert: Unpassende Kombinationen bleiben sichtbar, werden erklärt und sperren die Berechnung. Innerhalb des angezeigten Rasters werden Chirp-/Abtastrateneingaben beim Abschließen auf ganze Samples gerastet. Der ADC-Vorlauf kennt außerdem den gesonderten Wert 0 für das vereinfachte alte Nahbereichsmodell, falls dieses zu den übrigen Eingaben passt. Die [neue Beschreibung](AIRPORT_3D_ANTENNEN.md) erklärt dessen Unterschied zum späten ADC-Fenster.

Wenn mehrere Größen gleichzeitig unpassend sind, müssen sie gegebenenfalls nacheinander angepasst werden. Ein leerer Bereich ist ausdrücklich gekennzeichnet. Die Bereiche beschreiben jeweils eine veränderliche Größe bei festgehaltenen anderen Werten. Sie sind keine Behauptung, dass jede beliebige Kombination aus allen Bereichsgrenzen gemeinsam gültig wäre.

Beispiel beim ersten Überflug und sonst unveränderten Standardwerten:

| Einstellung | Bei 150 MHz Bandbreite | Bei 250 MHz Bandbreite |
|---|---:|---:|
| Kleinste aktive Chirpdauer | 28,3 µs | 35,4 µs |
| Kleinste ADC-Abtastrate | 5,325 MHz | 8,85 MHz |
| Kleinste Trägerfrequenz im Schmalbandmodell | 1,5 GHz | 2,5 GHz |

Die genaue letzte Ziffer an einer strikten Grenze enthält einen kleinen Sicherheitsabstand gegen Rundungsfehler. Die Zahlen gelten für den ersten Überflug mit 35 m Höhe, 10 m/s und den bisherigen Timingwerten. Bei anderen Objekten ändern sie sich.

## Woher kommen die Bereiche?

Die zentralen Gleichungen stehen in [parametergrenzen.py](../radar_sim/parametergrenzen.py):

| Bedingung | Welche Einstellungen sie koppelt |
|---|---|
| S = B/T | Bandbreite und aktive Chirpdauer |
| abs(2SR/c + 2v·fc/c) < fs/2 | Entfernung, radiale Geschwindigkeit, Träger, Bandbreite, Chirpdauer und ADC |
| abs(v) < c/(4fcTr) | Flugtempo, Träger und Wiederholintervall |
| abs(v)MTr ≤ c/(8B) | Bewegung während des Messpakets, Bandbreite, Chirpzahl und Wiederholintervall |
| a(MTr)² ≤ c/(8fc) | Radiale Beschleunigung, Träger und Beobachtungsdauer |
| N = fsT ganzzahlig | ADC und Chirpdauer |
| M·N ≤ 1.048.576 | Chirpzahl, ADC, Chirpdauer und Speicher |
| CFAR-Fenster passt in N×M | Trainings-/Schutzzellen, ADC, Chirpdauer und Chirpzahl |

Die vorher dokumentierten Schmalband- und Laufzeitgrenzen gelten weiter. Bei Flügen werden dieselben sicheren Schranken wie in `validate_config` verwendet. Beispielsweise ist die radiale Geschwindigkeit niemals größer als das gesamte Flugtempo. Konservative Grenzen dürfen eine nur mit genauerer Analyse noch auswertbare Kombination ablehnen. Sie garantieren gültige Modellparameter, keine Trennung beliebig naher Ziele und keine Detektionsgarantie.

## Speed ohne bisherigen Radar-Deckel

`tempo_anpassung.py` berechnet bei Speed-Eingaben ein gültiges Profil. Die ursprünglichen Radarwerte bilden die Ausgangsbasis; bei niedrigerem Tempo werden sie wieder benutzt, soweit sie gültig sind. Eine manuelle Radareingabe setzt die Basis neu. Im Rechenkern muss diese Anpassung ausdrücklich aufgerufen werden; `simulate_frame` und `validate_config` verändern selbst keine Parameter.

Bei geraden und parabelförmigen Beispielbahnen gilt für den Tempofaktor k: `v_neu=k*v`, `a_neu=k²*a`, `T_neu=T/k`. Somit sind Positionen bei gleichen relativen Flugzeiten unverändert. Beim Gegenverkehr bleibt jede Richtung erhalten. Speed ist das Maximum des Flugtempos, nicht dessen radialer Anteil. Individuell bearbeitete Tabellengeschwindigkeiten verändern dagegen die Bahn bei festgehaltener Dauer.

Falls das bisherige Profil nicht mehr passt, verkürzt die Automatik zuerst eine vorhandene Chirppause und die Chirpfolge. Das Intervall bleibt mindestens so lang wie der aktive Chirp. Chirpzahl und CFAR-Fenster behalten genügend Platz für Training und Schutz. Danach werden nötigenfalls Träger und Bandbreite gesenkt, sodass `|v| < c/(4fcTr)`, `v*MTr ≤ ΔR/4`, `a*(MTr)² ≤ λ/8`, `B/fc ≤ 0,1` und die Beat-Abtastgrenze eingehalten werden. Für größere Entfernungen verschiebt die Automatik den ADC-Start und verlängert den Chirp; Samplezahl und räumliche Geometrie bleiben erhalten. Sicherheitsabstände fangen Rundung ab. Die abschließende Kernprüfung entscheidet weiterhin über die Zulässigkeit.

Das kann die Entfernungs- oder Geschwindigkeitsauflösung verschlechtern. Zwei nahe Targets können dann verschmelzen. Die automatische Anpassung ist keine Fähigkeit eines unverändert betriebenen realen Airport-Radars; insbesondere kann ein anderes Frequenzband nötig werden. Neue Werte stehen unter Radar und als Auto-Radar-Hinweis. Eine starre Flugdauergrenze gibt es nicht mehr. Positive Zeiten, gültige Geometrie und Speicherbegrenzung werden weiterhin geprüft. Bei einem Fehler bleiben die Punkte im Editor erhalten.

Range-Doppler zeigt einen zur gesamten Szene passenden Geschwindigkeitsausschnitt mit Reserve. Bei Flugbahnen dient das maximale Flugtempo als sichere Schranke für den radialen Anteil. Mindestens einige Doppler-Bins bleiben sichtbar. Die FFT-Achse selbst ist unverändert `λ/(2MTr)` pro Bin. Die Achse wird beim Eingabewechsel gesetzt und springt nicht zwischen Frames.

## Eine Route zeichnen

1. Im Reiter Flug **Route zeichnen** wählen. Die Ansicht wechselt zu **Route 3D** mit XY, XZ und YZ. Die Radarstation bleibt in allen Ansichten sichtbar.
2. Jeden Stützpunkt mit einem einzelnen Linksklick setzen. Mausziehen fügt keine Punkte hinzu. **Punkte fertig** wechselt zum Verschieben der rosa Griffe; deren unsichtbare dritte Koordinate bleibt gleich. **Punkte setzen** hängt weitere Punkte an. **Neue Route** leert den Entwurf.
3. Rechtsklick auf die glatte Fluglinie fügt gezielt einen zusätzlichen Stützpunkt ein. Dessen dritte Koordinate stammt aus der 3D-Kurve. Bodenberührung oder eine spitze Umkehr werden verständlich gemeldet. Insgesamt sind höchstens 256 Punkte möglich.
4. **Flugdauer** oder **Speed (max.)** einstellen und **Übernehmen** wählen. Beide Eingaben sind gekoppelt: Dauer = räumliche Streckenlänge / Tempo. Lange Routen werden mit ihrer tatsächlichen Dauer übernommen; die frühere Grenze von 120 s entfällt. Ein gültiger Wert lässt sich direkt eingeben; nach Übernehmen folgt bei Bedarf die automatische Radar-Anpassung.
5. **Play** startet die Bewegung. **Reset** setzt Zeit und Rauschen zurück. Am Ziel wird die Wiedergabe beendet. Start- und Bremsvorgänge sind kein Bestandteil dieses Modells.

Während des Zeichnens sind Berechnen und Abspielen gesperrt; eine unfertige Linie verändert das laufende Radarmodell nicht. **Abbrechen** verwirft die Zeichnung. Außerhalb des Zeichenmodus bleiben Zoomen und Verschieben normal erhalten.

## Wie wird aus Stützpunkten eine Flugbewegung?

Eine natürliche kubische Kurve verbindet die einzeln geklickten Stützpunkte. Es werden keine weiteren Bearbeitungspunkte verteilt. Die erste und zweite Ableitung passen an den Übergängen zusammen. Dadurch entstehen im Unterschied zu einem einfachen Linienzug keine sprunghaften Richtungswechsel bei gleichbleibendem Tempo. Die glatte Kurve zwischen den Punkten ist die Vorschau der tatsächlich geflogenen Strecke.

Pro Abschnitt gilt mit einer lokalen Kurvenkoordinate u von 0 bis 1:

```text
p(u)   = a + b*u + c*u² + d*u³          # Position (x, Höhe)
p'(u)  = b + 2c*u + 3d*u²              # Tangente
p''(u) = 2c + 6d*u                     # zweite Ableitung
```

Die Koeffizienten entstehen aus einem dreidiagonalen Gleichungssystem mit NumPy-Vektoren und einfachem Vorwärts-/Rückwärtseinsetzen. Es gibt kein verstecktes Routen- oder Spline-Framework. Der Start und das Ende haben die natürlichen Randbedingungen, also zweite Ableitung null.

Der Flug folgt der **Strecke**, nicht der Reihenfolge gleich großer Zeitabschnitte zwischen Mauspunkten:

```text
Weglänge s = eingestelltes Tempo * Flugzeit
Weglänge bis u = Integral von |p'(u)|
Geschwindigkeit = Tempo * p'(u) / |p'(u)|
Flugdauer = gesamte Kurvenlänge / Tempo
```

Die Bogenlänge wird mit acht Gauß-Integrationspunkten auf jeweils 64 Teilstücken pro Kurvenabschnitt berechnet. Drei Newton-Schritte korrigieren die Umkehrung von Weglänge zu Kurvenposition. Das Tempo ist damit unabhängig von der Mausgeschwindigkeit und den Abständen der Stützpunkte.

Wie bei den bisherigen Flügen gilt weiterhin:

```text
R = sqrt(x² + h²)
v_radial = (x*vx + h*vh) / R
```

Deshalb kann ein Objekt auf deiner Route mit 5 m/s fliegen und trotzdem momentan eine radiale Geschwindigkeit von null haben.

## Kurvengrenzen und Dateien

Die Kurvenhöhe wird an den echten Polynomextrema geprüft, nicht nur an gezeichneten Punkten. Spitzkehren mit verschwindender Tangente sind unzulässig. Für die Beschleunigung gilt bei konstantem Tempo `a = Tempo²·Krümmung`. Der Simulator verwendet die sichere Schranke `Krümmung ≤ max|p''|/min|p'|²` und berücksichtigt zusätzlich die sich ändernde Sichtlinie zum Radar. Zu hohes Tempo kann deshalb weniger Chirps, ein kürzeres Wiederholintervall oder eine flachere Kurve erfordern.

Die Route wird mit Punkten und Tempo im JSON-Format Version 3 gespeichert. Alte Dateien der Versionen 1 und 2 bleiben lesbar. Eine geladene Route wird neu aus denselben Punkten berechnet. Die Kurvendaten werden zwischengespeichert, damit sie nicht für jedes Radar-Messpaket erneut vorbereitet werden müssen. Die Höhe und der horizontale Ort sind weiterhin bekannte Simulationsdaten und keine Radar-Winkelschätzung.

Beispiel: [09_gezeichnete_route.json](../examples/09_gezeichnete_route.json). Gemessene Ergebnisse: [route_und_regler.json](../reports/route_und_regler.json). Automatische Tests: `test_route.py`, `test_parametergrenzen.py` und der Maus-/Slider-Test in `test_gui.py`.
