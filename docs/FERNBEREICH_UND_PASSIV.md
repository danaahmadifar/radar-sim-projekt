# Fernbereich, Radarvergleich und Passivradar BETA

## Bedienung

**Route zeichnen** steht direkt unter **Flugbeispiel** und wechselt in den bekannten 3D-Routeneditor. Übernehmen und Abbrechen stehen daneben. Die vorhandene Punkt-für-Punkt-Bearbeitung bleibt erhalten.

Für große Abstände unter **Flug** das Beispiel **Fernbereich · Flugzeug bei 300 km** wählen. Die Startkoordinaten können über Tabelle oder Zell-Slider bis zu ±10.000 km eingestellt werden; feste Target-Entfernungen ebenfalls bis 10.000 km. Das sind Eingabebereiche, keine garantierten Radarreichweiten. Laufzeit, ADC, Doppler, Speicher und Bewegung müssen weiterhin zusammenpassen. Bei größeren Entfernungen deshalb unter anderem Wiederholintervall und ADC-Start anpassen. Zu große Geschwindigkeiten werden bei einem langen PRI begründet abgelehnt.

**Radar → Radarverfahren** wählt FMCW, Puls-Doppler oder **Passivradar · BETA**. Der passive Modus lädt bewusst eine eigene Demo mit festem Fremdsender, festem Empfänger und einem räumlichen Target; beim direkten Zurückwechseln wird das vorherige aktive Szenario wieder verwendet. Unter **Passiv BETA** sind Senderposition, Umweg-Suchfenster, Direktwegstärke und Direktweg-Projektion einstellbar. Das Lesen einer Passiv-JSON startet unmittelbar mit deren Geometrie. Aktive Beispielauswahl lädt passende aktive Profile.

Der rechte Tab **Radarvergleich** stellt Messgrößen, Auflösungen, Nah-/Fernbereich und die wesentlichen Vor-/Nachteile nebeneinander. Er zeigt auch die aktuellen nominalen Werte. Radar-, Antennen- und Exportfunktionen verwenden weiter ausschließlich NumPy, PyQt6 und pyqtgraph.

[Fernbereichsoberfläche](fern_puls_gui.png) · [Passiv-BETA mit Sender und Empfänger](passiv_beta_gui.png) · [Passive Einstellungen](passiv_parameter_gui.png)

## Fairer Fernbereichsvergleich

Beide 300-km-Profile verwenden:

| Größe | Wert |
|---|---:|
| Träger | 300 MHz |
| Sendebandbreite | 100 kHz |
| Abtastrate | 500 kSamples/s |
| Startabstand / PRI | 3 ms |
| Wiederholungen | 64 |
| Relative Leistungsreferenz | 100 km, 10 m² |
| Referenz-SNR pro aktivem ADC-Sample | 20 dB |

Das Pulsprofil sendet 50 µs lange LFM-Pulse. Seine nominale Auflösung ist `c/(2B)≈1498,96 m`; sein ADC-Raster beträgt `c/(2fs)≈299,79 m`. Der Puls darf bei dieser Konfiguration vollständig bis ungefähr 442,19 km empfangen werden. Der Sendeblindbereich reicht mindestens bis 7,49 km. Ein großes PRI hat damit einen Vorteil für die Laufzeit, aber einen Nachteil für die eindeutige radiale Geschwindigkeit: Hier gilt in beiden aktiven Profilen nur `|v|<83,28 m/s`. Der grundlegende [PRI-Zielkonflikt zwischen Entfernung und Geschwindigkeit](https://www.mathworks.com/help/fusion/ug/track-objects-with-wrapping-azimuth-angles-and-ambiguous-range-and-range-rate-measurements.html) wird nicht durch verborgene Mehr-PRF-Entfaltung umgangen.

FMCW sendet in diesem Vergleich eine 2,9-ms-Rampe. Das Echo aus rund 300 km braucht etwa 2 ms; der ADC beginnt deshalb erst bei 2,1 ms und erfasst die letzten 0,8 ms. Die beobachtete Bandbreite ist nur `100 kHz·0,8/2,9≈27,59 kHz`. Daraus folgen nominal `5433,74 m` Auflösung. Der passende ADC-Start erlaubt auch FMCW die große Entfernung. Der Unterschied entsteht aus dieser konkreten Konfiguration, nicht aus einem pauschalen FMCW-Reichweitenverbot.

Bei gleicher aktiver Echoamplitude enthalten die Verfahren hier unterschiedlich viele nutzbare Samples. Das FMCW-Fenster liefert mehr aktive Signalenergie und kann ein anderes Ausgangs-SNR besitzen. Gleiche Referenz-SNR pro Sample bedeutet **nicht gleiche mittlere Sendeleistung, gleiche Hardware, Rauschbandbreite oder Detektionswahrscheinlichkeit**. Längere Pulse liefern bei gleicher Spitzenleistung mehr Energie, vergrößern jedoch den Blindbereich. Die Auflösungsdemo mit zwei Targets bei 300 und 306 km wird mit ihren tatsächlichen Ergebnissen berichtet; sie ist keine allgemeine Garantie.

Beide aktiven Modelle behalten die Range-Doppler-Kopplung, Fensterverbreiterung und die CFAR-Randbehandlung bei. Die relative Leistung fällt monostatisch mit `σ/R⁴`. Eine Änderung der normierten Entfernungsreferenz erhöht keine physikalisch belegte Sendeleistung. Absolute Reichweite lässt sich ohne Sendeleistung, Gewinne, Verluste und Rauschzahl nicht behaupten. Die weitere [Puls-/FMCW-Herleitung](PULS_DOPPLER.md) gilt unverändert.

Die Szene verwendet eine **flache Welt mit freier Sicht**. Erdkrümmung, Gelände, Atmosphäre, Mehrwege und Funkhorizont sind nicht modelliert. Besonders bei Hunderten Kilometern darf die Darstellung deshalb nicht als Reichweitenvorhersage für eine reale Bodenstation gelesen werden.

## Passive BETA: richtige Messgrößen

Das passive System besitzt keinen eigenen Radarsender. Ein separater bekannter Fremdsender beleuchtet das Target; ein fester Empfänger im Ursprung erhält einen Referenz- und einen Überwachungskanal. Für Targetposition p und festen Senderort t gilt:

```text
Rt = |p−t|, Rr = |p|, L = |t|
b = Rt + Rr − L                         [m, zusätzlicher Weg]
τb = b/c                               [s, KEIN Faktor 2]
b_dot = ((p−t)/Rt + p/Rr) · v           [m/s]
fb = b_dot/λ                           [Hz]
```

Die [bistatische Wegdefinition](https://www.mathworks.com/help/radar/ug/non-cooperative-bistatic-radar-IQ-Simulation-and-Processing.html) unterscheidet sich von der monostatischen Entfernung. Positive b_dot bedeutet wachsender Umweg. In der Karte stehen deshalb **Bistatischer Umweg ΔL** und **Wegänderungsrate dΔL/dt**. `cτ/2` und `λf/2` wären hier falsch. Ein Umweg bestimmt eine Ellipsoidfläche, keine eindeutige Target-XYZ-Position. Bei zusammenfallenden Tx/Rx ergibt der mathematische Grenzfall b=2R und b_dot=2v_radial; die BETA selbst fordert getrennte Orte.

Die Weltflugzustände behalten ihren Abstand und ihre radiale Geschwindigkeit zum Rx-Ursprung. Die bistatischen Sollwerte stehen separat in den Frame-Targets. CSV-Detektionen verwenden die bisherigen generischen Felder `range_m` und `velocity_mps`; bei `radar_mode="passive"` bedeuten sie b und b_dot. Die beigefügte Konfigurationsdatei hält Verfahren und Geometrie fest. Die bekannte Flugposition ist weiterhin keine geschätzte 3D-Ortung.

## Fremdsender und zwei Kanäle

Die BETA erzeugt ein komplexes Zufallssignal mit flachem, begrenztem Spektralband als synthetische Fremdbeleuchtung. Der Seed ist reproduzierbar. Ein ausreichend langer Fourier-Signalabschnitt mit Vor-/Nachlauf erlaubt kontinuierliche Fractional Delays über `exp(−j2πfτb)`. Die ausgewerteten Abschnitte und Such-Lags überschreiten keine Periodengrenze. Es gibt kein ADC-Runden der Echoverzögerung und kein zyklisches Durchwickeln in der CAF.

Dies ist **kein demoduliertes FM-Radio, DVB-T, DAB oder realer OFDM-Sender**. Spektralform, Nutzdaten, Referenzrauschen, Oszillatorfehler und Synchronisationsprobleme solcher Systeme fehlen. Der Referenzkanal gilt ausdrücklich als ideal, rauschfrei und zeitlich synchron. Ein echter passiver Empfänger kann den Fremdsender nicht nach eigenem Wunsch auf eine andere Bandbreite umstellen; die Bandbreite im Simulator ist eine Szeneneingabe.

Das Überwachungssignal enthält alle Echos, einen einstellbaren Direktweg und AWGN. Für ein Echo gilt, bis auf eine konstante komplexe Phase:

```text
surv(t) = A · ref(t−τb) · exp(−j2πfb t) + Direktweg + Rauschen
```

Das didaktische Modell setzt `A=sqrt(Stärke·Grx)`. Im relativen Radargleichungsmodell gilt:

```text
Pr ∝ σb · Grx / (Rt² Rr²)
A = sqrt(σb/σref) · Rref²/(Rt Rr) · sqrt(Grx)
```

Der feste Fremdsender wird isotrop normiert. Nur die Empfangsantenne trägt die Richtwirkung bei; **sqrt(Grx)** als Amplitudenfaktor ist hier richtig. Der monostatische Faktor Grx für dieselbe Sende-/Empfangsantenne wäre falsch. σb ist eine frei vorgegebene konstante bistatische Punktziel-RCS, keine Umrechnung einer realen monostatischen Flugzeug-RCS. Direktweg-dB ist eine vorgegebene Störleistung nach Empfang relativ zu Aref²=1; keine aus absoluten Senderdaten hergeleitete HF-Bilanz.

Eine optionale komplexe Least-Squares-Projektion schätzt den Direktwegkoeffizienten `a=<ref,surv>/<ref,ref>` und zieht `a·ref` ab. Sie entfernt nur diesen einen signalgleichen Anteil. Sie ist kein ECA-/STAP-Clutterfilter. Zielanteile nahe Null-Doppler oder nahe dem Direktweg können mit entfernt werden. Ein nur aus Direktweg bestehendes Signal wird bis zur numerischen Präzision null; vollständig unter der relativen Rundungsgrenze liegende Residuen werden nicht als Echos ausgegeben.

## Exakte diskrete Kreuzambiguität

Die Verarbeitung wertet auf jedem Dopplerbin die vollständige Integration aus:

```text
CAF(f,k) = Σ[n=0…N−1] conj(surv[n+k]) ref[n] w[n]
                      · exp(−j2πf(n+k)/fs) / Σ |ref[n]|²w[n]
```

Die Karte ist `|CAF|²`. Jeder nichtnegative Lag nutzt dieselbe Zahl N von Integrationssamples. Eine mit Nullen aufgefüllte **lineare** FFT-Korrelation berechnet die Lags; der Mixterm enthält auch die schnelle Dopplerphase. Es gibt keine unkenntlich gemachte FMCW-FFT und keine nur unter kleiner Block-Dopplerphase gültige Blocknäherung. Die unabhängigen Tests vergleichen die FFT-Werte gegen die explizite Doppelsumme.

Die Oberfläche verwendet M Dopplerbins, die Rasterzeit Tr und `N=M·fs·Tr` Samples. Das ergibt:

```text
Integrationsdauer       T = M Tr
Dopplerraster           Δf = 1/T
Wegänderungsraster      Δb_dot = λ/T
Gewählter Suchbereich   |b_dot| < λ/(2Tr)
Nominale Umwegauflösung Δb ≈ c/B
Umweg-Abtastraster      c/fs
```

Tr ist **keine Puls-PRF des Fremdsenders**. Der Dopplerbereich ist ein gewähltes Suchraster, keine fundamentale passive Aliasinggrenze. Die echte ADC-Prüfung berücksichtigt nominelle Fremdsenderbandbreite plus bistatischen Doppler. Die Validierung begrenzt zusätzlich Umweg-Wanderung und Beschleunigung innerhalb der Integration. Hann verbreitert den Dopplerpeak. Auflösung und Genauigkeit hängen vom realen Fremdsendersignal und der bistatischen Geometrie ab; die nominalen c/B sind keine Garantie für beliebige Targets.

CA-CFAR arbeitet weiterhin mit linearen Leistungen und der tatsächlichen Trainingszellenzahl. Die Zellen sind nach CAF und Projektion korreliert, deshalb bleibt Pfa **nominell**. Direktweg, Signal-Ambiguität und Rauschen können zusätzliche Detektionen erzeugen. Der Messbericht zeigt tatsächliche Alarme und deren Stichprobenumfang statt eines kalibrierten Fehlalarmversprechens.

## Rechenbudget und BETA-Grenzen

16–128 Dopplerbins, 1024–131072 Integrationssamples, 20–2048 Suchverzögerungen und eine zusätzliche FFT-Arbeitsgrenze begrenzen CPU und Speicher. Die Signalauswertung läuft im bestehenden Worker; die GUI bleibt bedienbar. Die BETA kann langsamer als FMCW sein. Es gelten zunächst feste Tx/Rx und analytische Targetbahnen, keine freien Splinerouten oder bewegte Empfänger. Die sicheren Bahnprüfungen verwenden unter anderem b≤2Rr und |b_dot|≤2|v|; sie können konservativer als die tatsächliche Geometrie sein.

Keine Mehrwege, Clutterlandschaft, reale Rundfunkwellenform, Referenzrauschzahl, Hardware-Synchronisation, Target-Winkelschätzung oder Mehrsensor-Lokalisierung. Die BETA zeigt die Signalverarbeitung und ihre Grenzen, kein fertiges passives Überwachungssystem.

## Dateien und reproduzierbare Ergebnisse

`examples/18_fern_puls_300km.json`, `19_fern_fmcw_300km.json` und `20_passiv_beta.json` enthalten die neuen Startkonfigurationen. `fernradar.py` beschreibt die vergleichbaren aktiven Profile. `passivradar.py` enthält Geometrie, zwei I/Q-Kanäle, Direktweg-Projektion und CAF. Die zusätzlichen Einstellungen stehen in `passiv_config.py`; die bestehende Verarbeitungskette bleibt GUI-unabhängig.

`python -m unittest discover -s tests -q` prüft direkte CAF-Summen, Einweg-Antennenleistung, bistatische Geometrie und deren Ableitung, Seed, JSON, Speichergrenzen, 300-km-Profile und GUI-Wechsel. `python -m radar_sim --validate` erzeugt [FERN_UND_PASSIV.md](../reports/FERN_UND_PASSIV.md), Rohwerte, Spektrenvergleich und passive CAF. Die Auflösungsdemo und kleine Rauschstichprobe werden ausdrücklich mit ihren tatsächlichen Ergebnissen berichtet.
