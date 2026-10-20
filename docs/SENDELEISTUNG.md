# Sendeleistung, Tastgrad und Pulsenergie

Die Ansicht **Signale → Power / Energy** zeigt die Leistungshüllkurven von FMCW und Puls-Doppler auf derselben Zeit- und Leistungsskala. Die ausgefüllte Fläche unter der Kurve ist die Sendeenergie. Bei LFM verändert sich die Frequenz innerhalb des Pulses; seine ideale Leistung bleibt dabei konstant. Der Frequenzverlauf bleibt unter **Signale → Empfang & FFT** verfügbar.

## Normierung und Einheiten

Unter **Radar → TX Peak / dB** wird die relative Sende-Spitzenleistung eingestellt:

```text
q = Ppeak/P0 = 10^(TX_Peak_dB/10)
D = Taktiv/Tr                         Tastgrad
Pmittel/P0 = q · D
Epuls/P0 = q · Taktiv                 Einheit s
Eframe/P0 = M · q · Taktiv            Einheit s
```

P0 ist eine feste, relative Sendeleistungsreferenz. Ohne einen Zahlenwert für P0 in Watt sind die Energien keine Joule. Die Oberfläche gibt sie zur besseren Lesbarkeit in **P0·µs** an. Für FMCW bezeichnet Epuls die Energie je aktivem Chirp. Auch FMCW kann eine konfigurierte Sendepause haben. Der ADC-Vorlauf verkürzt nur das Empfangsfenster, nicht die Sendezeit und nicht die abgestrahlte Energie.

Die Beziehungen zwischen Spitzenleistung, mittlerer Leistung, Pulsdauer und Tastgrad sind in der [MathWorks-Dokumentation zum Tastgrad](https://au.mathworks.com/help/signal/ref/dutycycle.html) beschrieben.

## Fairer Vergleich

Der eingestellte Sender ist mit **simulierter Sender** gekennzeichnet. Der andere Verlauf heißt **Vergleichsreferenz** und ist ein hypothetischer Sender mit demselben PRI und derselben Wiederholungszahl. Er fließt nicht in die Echo- oder Detektionsberechnung ein:

- **Gleiche mittlere Leistung:** Die Spitzenleistung der Referenz wird an ihren Tastgrad angepasst. Die Frame-Energien sind bei gleicher Frame-Dauer gleich.
- **Gleiche Spitzenleistung:** Die Referenz erhält dieselbe Spitze. Der Sender mit dem höheren Tastgrad sendet mehr Energie pro Frame.

Im Puls-Doppler-Modus ist die Referenz ein FMCW-Sender ohne Sendepause. Im FMCW-Modus ist die Referenz ein Pulssender mit einstellbarem Tastgrad, standardmäßig 10 %. Das ist ein Vergleich des Sendebudgets. Er behauptet keine gültige zweite Empfangskonfiguration, gleiche Rauschbandbreite, gleiche Auflösung oder eine bestimmte Detektionsreichweite.

Beispiel: Pulsdauer 10 µs, PRI 100 µs, Peak 10·P0. Der Tastgrad beträgt 10 %, die mittlere Leistung P0 und die Energie je PRI 100·P0·µs. Durchgehendes FMCW mit Peak P0 sendet über dieselben 100 µs ebenfalls 100·P0·µs. Der Puls ist zehnmal höher, enthält über das gemeinsame Zeitfenster aber keine zusätzliche Energie.

Die Energiekurve zeigt die ersten drei PRI, die Tabelle die vollständige Frame-Energie. Kurvenflanken und Energie werden analytisch berechnet; für die Darstellung wird kein GHz-Träger und kein zusätzlicher ADC-Datenblock erzeugt.

## Wirkung auf die tatsächliche Simulation

TX Peak beeinflusst aktive FMCW- und Puls-Doppler-Signale gleichermaßen:

```text
Echoamplitude_neu = sqrt(q) · Echoamplitude_bei_0_dB
Echoleistung_neu = q · Echoleistung_bei_0_dB
aktive_Leakageleistung_neu = q · Leakageleistung_bei_0_dB
Pn = 10^(−Referenz_SNR/10)            unveränderte Empfängerrauschleistung
```

Das gilt auch für aktive Bodenechos. Antennengewinn, RCS- und Entfernungsfaktoren bleiben erhalten. Leakage/dB beschreibt den Kopplungsweg bei TX Peak 0 dB. Sättigung wird anschließend auf der gesamten Empfangssumme berechnet; ein höherer TX-Pegel kann deshalb auch Übersteuerung verstärken. Die Referenz-SNR bleibt auf Echoamplitude 1 bei TX Peak 0 dB bezogen. Bei sonst gleichen Bedingungen verbessert +10 dB TX Peak die Eingangssignal-SNR um 10 dB, solange keine Sättigung vorliegt. Der tatsächliche SNR eines Targets enthält außerdem dessen Echo- und Ausbreitungsfaktoren.

Der FMCW-Mischer verwendet weiterhin einen normierten LO; die TX-Skalierung geht einmal in die Echoamplitude ein. Sie wird nicht nochmals als unnormierte LO-Verstärkung multipliziert. Pulsreferenz und Matched Filter bleiben auf Einheitsamplitude normiert. Der Default ist 0 dB: bisherige Szenarien und Rechenergebnisse behalten ihre Normierung.

Passivradar hat keinen eigenen Sender. Dort wird TX Peak ausgeblendet, muss in der Konfiguration 0 dB sein und der Vergleich bleibt leer. Die separate Modellierung des Fremdsenders bleibt erhalten. Das JSON-Schema ist Version 8; Dateien der bisherigen Versionen 1–7 bleiben mit TX Peak 0 dB lesbar.

## Empfang und Pulskompression

Rechts unten erscheinen im Puls-Doppler-Modus die tatsächliche Leistung des ersten RX-Blocks und die erste komprimierte Pulsantwort aus derselben Verarbeitung wie die Range-Doppler-Map. Die Zeitachse der Filterantwort entspricht der getesteten Echoverzögerung. Der Empfänger bleibt während des Sendens gesperrt. Bei aktiviertem Null-Doppler-Abzug arbeitet der Filter auf dem bereinigten Signal, während RX die Samples davor zeigt.

Beide Kurven beziehen sich auf Aref²=1. Der Matched Filter ist durch die Summe seiner Gewichte normiert; seine Spitze wird nicht künstlich angehoben. Seine Ausgangsfläche ist **keine Sendeenergie**. Pulskompression erzeugt keine zusätzliche Energie, sondern ermöglicht die Entfernungsauflösung eines breitbandigen LFM-Pulses bei längerer Sendezeit. Fensterung, Doppler und teilweise empfangene Pulse beeinflussen das Ergebnis weiterhin.

## Implementierung und Prüfung

- `radar_sim/sendeleistung.py`: Formeln und kleine analytische Hüllkurven, ohne GUI.
- `radar_sim/leistungsansicht.py`: Vergleich, Tabelle und Empfangsdiagramm.
- `model.py` und `pulsradar.py`: TX-Skalierung in den tatsächlichen Signalen.
- `tests/test_sendeleistung.py`: exaktes Flächenintegral einschließlich Pausen, beide Vergleichsnormierungen, Echo-/FFT-Skalierung, konstantes Rauschen, Leakage vor Sättigung, JSON-Kompatibilität und Filterantwort gegen direkte Summen. GUI-Prüfung einschließlich Moduswechsel, TX-Regler, erhaltener Kurven und vier PNG-Exporte.

Die vier neuen Diagramme werden über den bestehenden **PNG**-Button zusammen mit den bisherigen Diagrammen exportiert.
