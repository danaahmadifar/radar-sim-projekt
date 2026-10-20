# Fünf einzeln prüfbare Lernschritte

Ausführen: `python -m radar_sim --steps`. Jeder Schritt zeigt analytische fb/fd, Sollwerte und tatsächlich geschätzte R/v. Alle Szenen verwenden Seed 42 und Frameindex 0. Die JSON-Dateien können direkt in der GUI geöffnet werden.

| Schritt | Szene | Analytische Erwartung | Quellcode zum Lesen |
|---|---|---|---|
| 1: Echo und Entfernung | `01_stationary.json` | R=40ΔR=39,972328 m; v=0; fb=1 MHz | `model.py`: τ, Phase, tx·conj(rx); `processing.py`: Range-FFT |
| 2: Geschwindigkeit | `02_approach_recede.json` | v=−18Δv=−4,562588 und +24Δv=+6,083451 m/s; fb≈997656,25 und 1878125 Hz | `processing.py`: Doppler-FFT, `fftfreq`, λ/2; Kopplungskorrektur in `detection.py` |
| 3: Überlagerung | `03_same_range_two_velocities.json` | beide R=60ΔR=59,958492 m; v=−16Δv und +20Δv | komplexe Summe in `model.py`; Doppler trennt gleiche Entfernung |
| 4: Rauschen und CFAR | `04_cfar_noise.json` | R=45ΔR und 90ΔR; v=−12Δv und +18Δv; Referenz-SNR −15 dB | AWGN-Varianz, Trainingsring, lineare Schwelle, Integralbild |
| 5: GUI und Vergleich | `05_dashboard.json` | (40 m, −5 m/s), (72 m, +7 m/s), (105 m, 0 m/s) | `pipeline.py`, `evaluation.py`, `gui.py`, `io.py` |

Im Standardfall sind ΔR=0,999308193 m und Δv≈0,253477119 m/s. Die Dopplerwerte der ersten Lernbeispiele liegen absichtlich auf Bins; die Beat-Frequenz bewegter Ziele liegt wegen der Kopplung trotzdem nicht immer auf einem Range-Bin. Deshalb ist ein kleiner Entfernungsfehler trotz Korrektur erwartbar. Im vollständigen Bericht stehen die gemessenen Abweichungen, keine bloß angenommenen Erfolge.

Zusätzliche Versuche: `03_two_ranges.json` für zwei stationäre Entfernungen, `near_resolution.json` für 1,2ΔR Abstand und `noise_only.json` für reines Rauschen. In der letzten Szene bei Rechteck gilt die nominelle CFAR-Statistik am besten. Für eine belastbarere Prüfung den Monte-Carlo-Bericht statt nur einen Frame betrachten.

Nach jedem Schritt können gezielt Parameter variiert werden: Bandbreite verdoppeln (ΔR halbiert sich), Chirpzahl verdoppeln (Δv halbiert sich, Modellwanderung beachten), Tr verlängern (kleinerer eindeutiger Geschwindigkeitsbereich), Hann und Rechteck vergleichen (Nebenkeulen gegen Hauptkeulenbreite), statische Unterdrückung aktivieren (stationäres Ziel verschwindet). Ungültige Kombinationen werden erklärt, anstatt unbemerkt aliasierte Sollwerte als richtige Schätzung auszugeben.

## Danach: Die drei bewegten Flüge

Die Anwendung startet mit einem Flughafenanflug. Unter **Flug** gibt es dazu Gegenverkehr, Höhenbogen und eine räumliche Route sowie die bisherigen kleinen Lehrbeispiele. Die fünf Lernschritte verwenden weiterhin ihre ursprünglichen Parameter über „Feste Targets (ohne Flugroute)“ oder ihre JSON-Dateien. **Overview** zeigt Flugfeld und Radarbild, **Signals** die Zwischensignale und **Results** die Schätzfehler. **Route 3D** enthält die gekoppelten XY-, XZ- und YZ-Ansichten. Die neuen Standardwerte und Antennenmodelle erklärt [Flughafen und 3D](AIRPORT_3D_ANTENNEN.md).

Für den Einstieg in den deutschen Bewegungscode siehe [FLUGBAHNEN.md](FLUGBAHNEN.md). Dort werden Höhe, Flugrichtung, Entfernung und radiale Geschwindigkeit an konkreten Zahlen erklärt. Alle Zeitpunkte der drei Beispiele werden zusätzlich mit `--validate` berechnet und im [Flugbericht](../reports/fluege.json) gespeichert.
