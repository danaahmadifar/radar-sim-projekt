# Technische Dokumentation

Fernbereichsprofile, der Vergleich der Verfahren und die zusätzliche passive BETA mit korrekter bistatischer Weg-/Dopplerdefinition stehen in [FERNBEREICH_UND_PASSIV.md](FERNBEREICH_UND_PASSIV.md). Die BETA nutzt eine CAF aus zwei Basisbandkanälen und hat keinen FMCW-Beat oder monostatischen Faktor 1/2. Die bekannten Weltpositionen bleiben Simulationseingaben.

Die folgenden Abschnitte beschreiben den FMCW-Pfad. Der zusätzliche kohärente LFM-Puls-Doppler-Pfad, die bewegte monostatische Radarplattform, Vergleich und Grenzen stehen in [PULS_DOPPLER.md](PULS_DOPPLER.md). Die gemessenen Ergebnisse stehen im [Puls-/Plattformbericht](../reports/PULS_UND_PLATTFORM.md). Bei bewegtem Radar sind R und v stets relativ zur Plattform, Weltposition und Höhe bleiben bekannte Eingaben.

## 1. Geltungsbereich und Konventionen

Dies ist eine Signalverarbeitungssimulation eines monostatischen FMCW-Radars mit isotropen Punktzielen und vereinfachter Ausbreitung. Ein Frame besteht aus M identischen Aufwärtschirps mit Startabstand Tr, aktiver Dauer T und positiver Steigung S=B/T. Alle Rechengrößen sind SI-Werte. `fc` bezeichnet die Start-/Referenzfrequenz des Chirps; die konstante Wellenlänge λ=c/fc ist eine Schmalbandnäherung.

| Symbol | Bedeutung / Einheit |
|---|---|
| c | 299 792 458 m/s |
| R | Abstand zu Framebeginn / m |
| v | radiale Geschwindigkeit / m/s, positiv entfernt sich das Ziel |
| τ=2R/c | Zweiweglaufzeit / s |
| fd=2v/λ | Doppler im **Beat**, positiv für Entfernung / Hz |
| m=0…M−1 | Chirpindex (Slow Time) |
| t=(Nskip+n)/fs, n=0…N−1 | lokale Fast Time / s; ADC-Vorlauf Nskip überspringt Rampenanfang |
| N=fs T−Nskip | ganzzahlige Zahl erfasster Samples; Tadc=T−Nskip/fs |

Der physikalische Empfangs-Doppler ist bei Annäherung positiv. Der verwendete Mischer `tx · conj(rx)` kehrt das Empfangsvorzeichen um: Ein sich entfernendes Objekt hat positiven Beat-Doppler. `rx · conj(tx)` würde alle Beat-Phasen und beide Frequenzachsen umkehren.

## 2. Empfangschirp und Dechirping

Ein idealer komplexer Sendechirp ohne direkt abgetasteten RF-Träger lautet

```text
q(t) = exp(j π S t²)
```

Der folgende Empfangsausdruck wird in der Schmalband-/Frozen-Envelope-Näherung benutzt:

```text
rx_bb[m,t] = A · exp(j π S (t−τ)²)
              · exp(−j 2π fc τ)
              · exp(−j 2π fd (m Tr+t)) · exp(−j φ)
```

Der Mischer ergibt algebraisch:

```text
z[m,n] = q(t) · conj(rx_bb[m,t])
       = A exp(j 2π [(Sτ+fd)t + fd m Tr + fcτ − ½Sτ²] + jφ)
fb     = Sτ + fd
```

[generate_echo](../radar_sim/model.py) berechnet direkt diesen äquivalenten Beat-Ausdruck, statt zwei hochfrequente Signale numerisch zu mischen. `dechirp` zeigt die Mischoperation separat. Ein Test konstruiert unabhängig einen verzögerten Basisbandempfangschirp und prüft die Identität für mehrere Chirps, einschließlich Fast-Time-Doppler. Es werden nur Arrays mit Form `[M,N]` abgetastet, keine 77-GHz-Welle und kein Chirp mit 150 MHz digital rekonstruiert. Die Referenztest-Identität ist algebraisch; sie ist keine Behauptung einer bandbegrenzten RF-Abtastung bei der ADC-Rate.

`φ` ist eine frei wählbare **Beat**-Startphase. Im RX-Ausdruck hat sie deshalb negatives Vorzeichen. Mehrere Ziele addieren sich kohärent als komplexe Felder, nicht als Leistungen. Destruktive Interferenz bei identischen R/v/Phasen bleibt möglich.

## 3. Bewegungsnäherung ohne doppelte Dopplerzählung

Aus R(t_global)=R0+v·t_global folgt Δτ=2v·t_global/c. Der dominante Trägerphasenanteil wird zu `−2π fc τ0 − 2π fd t_global`. Die Chirphüllkurve verwendet weiterhin τ0. Genau daraus folgt obiges Modell mit Doppler in Fast und Slow Time. Es ist eine Näherung erster Ordnung mit eingefrorener Hüllkurvenlaufzeit, verwandt mit Stop-and-Hop. Striktes Stop-and-Hop ohne Fast-Time-Doppler würde `fd·t` weglassen; das geschieht hier ausdrücklich nicht.

Insbesondere wird **nicht** zugleich `fc·τ[m]` und ein zusätzlicher `fd·mTr`-Term eingesetzt. Das würde dieselbe Bewegung zweimal zählen. Innerhalb eines kurzen Frames bleiben R und A konstant. Im Modus „Feste Targets (ohne Flugroute)“ ändert Play nur den Rauschindex. In den drei Flugbeispielen werden dagegen R(t), radiale Geschwindigkeit und gegebenenfalls die relative Amplitude vor jedem neuen Frame aus der Flugbahn berechnet. Die vollständigen Formeln und Beispielwerte stehen in [FLUGBAHNEN.md](FLUGBAHNEN.md).

Ein Messpaket hat M·Tr Beobachtungsdauer; die Flugzeit zwischen angezeigten Paketen ist gesondert einstellbar und darf nicht kürzer als das Paket sein. Pro Frame wird mit seinem momentanen R(t) eine neue Startphase `fc·τ(t)−Sτ(t)²/2` berechnet. Der Doppleranteil beschreibt nur die lokale Bewegung während dieses Pakets. Es wird kein zusätzlicher globaler `fd·t`-Term addiert. Die Auswertung kombiniert keine FFTs verschiedener Frames.

Vernachlässigt werden die bewegungsabhängige Verschiebung der Chirphüllkurve, Range-Migration, frequenzabhängiger Doppler über B und Amplitudenänderung im Frame. Deshalb erzwingt die Konfiguration konservative Lehrmodellgrenzen:

- B/fc ≤ 10 % für konstanten Schmalband-Doppler.
- Mit ADC-Vorlauf: Zweiweglaufzeit τ ≤ Nskip/fs, damit die gesamte Aufnahme im überlappenden Inneren derselben Rampe liegt. Ohne Vorlauf gilt für alte Nahbereichsversuche weiterhin τ ≤ 2,5 % T mit idealisierten Rändern. Ein-/Ausschalttransienten werden nicht simuliert. Der spätere ADC-Start erlaubt die neuen Kilometerszenen ohne diese Randnäherung.
- `|v| M Tr ≤ ΔR/4`: nur kleine Range-Wanderung. Auch darunter bleibt die reale Hüllkurvenphase angenähert; an der Grenze kann der vernachlässigte Phasenanteil größenordnungsmäßig bis π/2 wachsen. Diese Grenze garantiert keine hardwaregetreue Phasengenauigkeit.
- Entfernung muss auch unter konservativ angenommener Frame-Wanderung positiv bleiben.
- Bei Flugbahnen zusätzlich: konservative Schranke für die Änderung der radialen Geschwindigkeit im Paket ≤ Δv/4. Mit kleinster Höhe hmin und größtem Flugtempo vmax genügt `(|vmax|²/hmin + |a_h|) M Tr ≤ Δv/4`. Diese Schranke berücksichtigt auch die sich ändernde Sichtlinie beim geraden Überflug. Die sichere maximale Entfernung, das Flugtempo und die Höhenextrema werden über die gesamte Szene geprüft. Sie können eine Bahn konservativ ablehnen, auch wenn die tatsächlichen radialen Werte etwas kleiner wären.

Die Grenzwerte sind offengelegte Engineering-Entscheidungen für diese Version. Verletzte Modellgrenzen werden nicht als valide simulierte Messung ausgegeben.

## 4. Amplitude, relative Radargleichung und Rauschen

Die folgenden Formeln gelten zunächst auf der Antennenachse. Für räumliche Flugobjekte kommt der normierte Einweg-Leistungsgewinn G hinzu: `A=A0·G`, damit die monostatische Empfangsleistung `A0²·G²` entsteht. Alle Antennentypen werden bei gleichem Achsenpegel verglichen. Richtdiagramme, 3D-Koordinaten und die Bedeutung der projizierten Halbwertskeule stehen in [Flughafen, 3D und Antennen](AIRPORT_3D_ANTENNEN.md).

Das didaktische Modell verwendet eine relative Ziel-**Leistung** g>0:

```text
A = sqrt(g),     relative Leistung = A² = g
```

Im relativen Radargleichungsmodell wird bei festem System und unveränderter Frequenz `Pr ∝ σ/R⁴` benutzt:

```text
A = sqrt(σ/σref) (Rref/R)²
Pr / Pref = (σ/σref) (Rref/R)⁴
```

Die Standardreferenz ist Rref=40 m, σref=1 m², Pref=Aref²=1. Doppelte Entfernung erzeugt ein Viertel der **Amplitude** und ein Sechzehntel der **Leistung**. Vierfache RCS verdoppelt die Amplitude. Ohne Sendeleistung, Gewinne, Systemverluste und Rauschzahl gibt es keine absolute Watt- oder dBm-Aussage. Die Frequenzabhängigkeit eines vollständigen Linkbudgets wird nicht simuliert; Vergleiche über fc sind relativ zur jeweils normierten Systemreferenz.

Das eingestellte Referenz-SNR gilt am Ausgang des idealen Mischers vor Clutterfilter, Fenster und FFT:

```text
SNRref = 10 log10(Aref² / Pn), Aref² = 1
Pn = 10^(−SNRref/10)
w = sqrt(Pn/2) (x + j y), x,y unabhängig N(0,1)
```

Rauschen bleibt bei Zieländerungen und leeren Szenen gleich definiert. Ein Einzelziel hat `SNRtarget = SNRref + 10log10(A²)`. Bei kohärent überlagerten Zielen ist die tatsächlich gemittelte Szenenleistung wegen Kreuztermen nicht immer ΣA²; `expected_signal_power` bezeichnet diese inkohärente Referenzsumme, nicht die gemessene Summenleistung. Es wird kein SNR auf Basis des aktuellen Szenenmaximums nachgeregelt.

`SeedSequence([seed, frame_index])` und NumPy `default_rng` erzeugen reproduzierbare Frames. Gleiche Konfiguration, gleicher Seed, gleicher Frameindex und gleiche NumPy-Version ergeben dieselben Werte. Rauschen ausschalten ist ein eigener Schalter; kein unendlicher SNR-Sonderwert.

## 5. Fenster, FFTs und Achsen

Arraykonvention durchgängig `[Chirp m, Sample n]`, anschließend `[Doppler-Bin d, Range-Bin r]`:

```text
optional zc[m,n] = z[m,n] − mean_m(z[m,n])
X[m,r] = fftshift(fft_n(zc[m,n] wr[n])) / sum(wr)
Y[d,r] = fftshift(fft_m(X[m,r] wd[m])) / sum(wd)
P[d,r] = |Y[d,r]|²
```

Rechteck `w=1` und periodisches Hann `w[n]=½−½cos(2πn/N)` stehen für beide Dimensionen zur Verfügung. Die Fenstersummennormierung erhält die kohärente Tonamplitude: Ein binzentriertes Ziel A=1 liefert Ppeak=1. Sie ist keine Rauschleistungsdichte-Normierung. Für weißes Rauschen gilt nach beiden FFTs `E[Pbin]=Pn·sum(wr²)/sum(wr)²·sum(wd²)/sum(wd)²`.

Das Entfernungsspektrum ist `mean_m(|X|²)` vor Dopplerfenster. Es hat deshalb einen höheren Rauschboden als die 2D-Map; beide verwenden dieselbe Einheitsleistungsreferenz. Die Darstellung ist `10log10(P/1)`, numerisch unten auf −160 dB begrenzt. Es findet keine Normalisierung auf den jeweils stärksten Peak statt.

Frequenzen aus `fftshift(fftfreq(...))`:

```text
fb[r]          = signierte Fast-Time-Frequenz
fd[d]          = signierte Slow-Time-Frequenz
Rapp[r]        = c fb[r]/(2S)
v[d]           = λ fd[d]/2
Rhat[d,r]      = c (fb[r]−fd[d])/(2S)
Rapp − R       = c fd/(2S) = fc v/S
```

Die Heatmap bleibt ein unverzerrtes rechteckiges FFT-Raster und heißt deshalb Scheinentfernung. Sollkreuze und Kandidatenkreise liegen in genau diesem Koordinatensystem. Eine Tabelle zeigt Rhat. Signierte Fast-Time-Bins bleiben erhalten, weil sehr nahe sich nähernde Ziele auch negative Beat-Frequenzen haben können. Negative Scheinentfernung ist nicht automatisch negative physikalische Entfernung. Bei sehr kleinen R unter einem halben Range-Bin kann Quantisierung trotzdem zu einem verworfenen Rhat≤0 führen; keine Sub-Bin-Interpolation.

Mittelwertabzug entfernt den exakt stationären Anteil, verändert langsame Ziele und korreliert das Rauschen zusätzlich. Mit Hann-Dopplerfenster ist die Filterwirkung nach Fensterung nicht auf nur eine ausgeblendete Map-Zeile beschränkt. Ein verschwundenes stationäres Ziel ist in diesem Modus erwartetes Verhalten.

## 6. Auflösung, Eindeutigkeit und zulässige Bereiche

Nominelle rechteckige Auflösungsmaßstäbe:

```text
ΔR = c/(2*S*Tadc), bei Nskip=0 also c/(2B)
Δfd = 1/(M Tr)
Δv = λ/(2 M Tr)
```

Weil N=fs·Tadc und ohne Zero-Padding gearbeitet wird, stimmt der Range-Binabstand numerisch mit c/(2·S·Tadc) überein. Bei späterem ADC-Start wird nur S·Tadc der TX-Bandbreite beobachtet. Das bedeutet nicht, dass ein beliebiges Zielpaar im Abstand eines Bins stets getrennt wird. Hanns erste Nullstelle liegt ungefähr doppelt so weit vom Maximum entfernt wie beim Rechteck; Zielphasen, SNR, Dynamikunterschied und Gruppierung beeinflussen die Trennung. Zusätzliche FFT-Punkte würden nur das Spektrum interpolieren, keine neue physikalische Auflösung schaffen.

Der nominelle Doppler-Nyquistbereich ist `−λ/(4Tr) ≤ v < λ/(4Tr)`. Die Validierung verwendet konservativ `|v| < λ/(4Tr)` und weist beide Grenzfälle ab. Bei geradem M liegt die höchste positive Binmitte um Δv unter der positiven Nyquistgrenze; negative Nyquist-Binmitte ist vorhanden. Der CFAR-Rand verkleinert die **detektierbare** Fläche zusätzlich.

ADC-Bedingung einschließlich Kopplung:

```text
|2 S R/c + 2v/λ| < fs/2
−c fs/(4S) − fc v/S < R < c fs/(4S) − fc v/S
```

Zusätzlich gelten R>0, Laufzeit- und Migrationsgrenzen. Der messbare Bereich ist also kein beliebiges Rechteck aus maximaler Entfernung und Geschwindigkeit. Eine für **alle** nominell eindeutigen v sichere obere Entfernung ist `c fs/(4S) − fc vmax/S`, weiter begrenzt durch `c·Nskip/(2fs)` bei Vorlauf bzw. das alte 2,5-%-Timing ohne Vorlauf. Die GUI zeigt diesen konservativen Grenzwert, den Nyquist-Geschwindigkeitsbereich und die zusätzliche Migrationsgrenze `|v| ≤ ΔR/(4MTr)`.

Ursprüngliche Kern-/Lehrwerte: fc=77 GHz, B=150 MHz, T=40 µs, Tr=60 µs, fs=10 MHz, N=400, M=128. Daraus folgen ΔR≈0,999308 m, Δv≈0,253477 m/s, |v|<16,2225 m/s, Rapp-Nyquistbetrag≈199,862 m. Das alte Timingmodell begrenzt R auf ca. 149,896 m. Der neue GUI-Standard verwendet das [Flughafenprofil](AIRPORT_3D_ANTENNEN.md) mit 9,3 GHz, 96 Chirps und spätem ADC-Fenster. CFAR wertet mit derselben Trainings-/Schutzumgebung keine Zellen in den äußeren 10 Range- und 8 Doppler-Bins aus. Eine saubere FFT-Schätzung ist dort grundsätzlich möglich, eine CFAR-Detektion wird jedoch absichtlich nicht behauptet.

## 7. Zweidimensionale CA-CFAR

`training_range`, `training_doppler`, `guard_range`, `guard_doppler` sind Halbbreiten pro Seite in FFT-Zellen. Mit tr,td,gr,gd gilt:

```text
hr = tr+gr, hd = td+gd
Ntrain = (2hr+1)(2hd+1) − (2gr+1)(2gd+1)
Pnoise = sum(äußeres Rechteck ohne inneres Schutzrechteck) / Ntrain
alpha = Ntrain [Pfa^(−1/Ntrain) − 1]
Detektion <=> Pcut > alpha Pnoise
```

Ein Integralbild berechnet Rechtecksummen in O(MN), statt pro CUT den Ring erneut zu durchlaufen. `expm1` verbessert die numerische Berechnung von alpha. Der Ring schließt Schutzrechteck und CUT aus; die Standardkonfiguration hat Ntrain=332. Ein sehr kleiner Leistungsboden von `max(Pmax·10⁻¹⁴, tiny)` verhindert künstliche Schwellen unterhalb der Rundungsgrenze bei exakt rauschfreien Spektren. Dieser Boden ist ein numerischer Sonderfall und kein zusätzlicher Signalpegelregler.

**Randbehandlung:** Nur vollständig im Bild liegende Ringe werden geprüft. Andere Schwellen sind NaN und deren Masken false. Kein Wrapping, keine Spiegelung und keine variable Trainingszellenzahl am Rand. Deshalb gilt pro ausgewerteter CUT dieselbe tatsächliche Zellenzahl. Eine Umgehung mit Teilfenstern würde eine neu berechnete Anzahl und Schwelle erfordern.

Die Skalierung folgt aus unabhängigen exponentiellen Leistungen, wie sie bei weißem komplexem Gaußrauschen und rechteckig gefensterter DFT entstehen. Für N Trainingsleistungen mit Mittel μ hat der normalisierte Trainingsmittelwert eine Gamma-Verteilung; daraus folgt `P(Pcut > alpha·mean_train)=(1+alpha/N)^(−N)`. Die Lösung ergibt die implementierte Formel.

Das ist eine Pfa **pro CUT unter Nullhypothese**, keine Wahrscheinlichkeit für mindestens einen Fehlalarm im Frame und keine garantierte Falschkandidatenrate nach Gruppierung. Überlappende Ringe machen Entscheidungen abhängig. Hann-Fenster, Clutterfilter, Mehrzielkontamination, Nebenkeulen und ungleichförmiger Hintergrund verletzen zusätzliche Annahmen. Insbesondere bei rauschfreien Zielsignalen kann CFAR Nebenkeulen als weitere Kandidaten melden. Der Bericht zählt diese zusätzlichen Kandidaten und kalibriert Hann nicht heimlich nach.

8-fach benachbarte detektierte Zellen werden zu Komponenten verbunden. Ein Kandidat muss zusätzlich ein **lokales Maximum im vollständigen Leistungsbild** sein: nicht kleiner als alle acht Nachbarn und größer als mindestens einer. Dadurch sind gleiche Nachbarspitzen eines Tons zwischen FFT-Zellen erlaubt; ein flaches Feld ist kein Peak. Die Nachbarprüfung darf nicht nur CFAR-qualifizierte Nachbarn betrachten. Pro Komponente bleibt das stärkste qualifizierte Maximum; Komponenten ohne Peak erzeugen keinen Kreis. Keine Interpolation, keine Sollwertkenntnis, kein Tracking. Eng verbundene Ziele können verschmelzen. Kandidaten mit Rhat≤0 werden als unphysikalisch verworfen; höchstens 256 stärkste Kandidaten gelangen in Tabelle/CSV. Roh-CFAR-Maske und gültige CUTs bleiben im Rechenkern vollständig verfügbar.

Die frühere Implementierung wählte einfach die stärkste Zelle je CFAR-Komponente, auch auf monotonen Flanken. Das war ein Fehler der Kandidatenbildung. Ohne AWGN meldete der erste Überflug vier zusätzliche Kandidaten bei etwa −105 bis −121 dB, obwohl diese kein Maximum des Spektrums waren. Die Nachbarprüfung korrigiert diesen Fall. Die 603 Messpakete der drei Hann-Flüge ohne AWGN enthalten jetzt genau 804 passende Kandidaten, ohne zusätzliche oder fehlende Zuordnungen. Rechteck-Nebenkeulen können weiterhin selbst lokale Maxima und zusätzliche Kandidaten erzeugen; ein Gegenbeispiel wird ausdrücklich geprüft. Details, Messzahlen und Schwellenplot: [DETEKTION.md](../reports/DETEKTION.md).

Die Peak-Prüfung ändert nicht die CA-CFAR-Skalierung oder die statistisch untersuchte Rohmaske. Sie ist eine zusätzliche Stufe zur Kandidatenbildung. Im GUI steht deshalb „Peak-Kandidat“ statt einer Bestätigung eines realen Objekts. Die Tabelle zeigt `10log10(P/Schwelle)`, um knapp über der Schwelle liegende Treffer einordnen zu können. Es wurde keine zusätzliche globale dB-Grenze eingeführt.

## 8. Validierung und tatsächliche Ergebnisse

[Der automatisch generierte Bericht](../reports/VALIDATION.md) enthält Einzelabweichungen, SNR-Versuch, Rauschstatistik und PNGs. Die Rohdaten sind JSON, alle Szenen JSON-Dateien unter `examples/`. Die Generatoren stehen in `scenarios.py`; Bericht und Tests verwenden feste Seeds.

Unabhängige Referenzen in den Tests: analytisch verzögerter Empfangschirp versus Beat-Äquivalent, kohärente Einheitsverstärkung, relative R⁻⁴-Leistung, Rauschvarianz und eine verschachtelte CFAR-Ringberechnung als Kontrolle des Integralbildes. Eine zusätzliche geschlossene DFT-Referenz prüft die Fensterantwort eines Tons zwischen den Bins: `D_N(u)=exp(jπu(N−1))·sin(πNu)/sin(πu)`; für periodisches Hann gilt `W_N(u)=½D_N(u)−¼D_N(u+1/N)−¼D_N(u−1/N)`. Das 2D-Spektrum ist das Produkt der Fast- und Slow-Time-Antworten, jeweils durch die Fenstersumme normiert. Die Referenz verwendet keine FFT und prüft auch die Nebenkeulen. Die Peak-Regression umfasst alle drei Flüge ohne AWGN, eine leere Szene, einen höheren nicht CFAR-qualifizierten Nachbarn und ein 80 dB schwächeres isoliertes Ziel.

Zusätzlich werden ungültige Konfigurationen, signierte Nahbereichsbeats, statische Unterdrückung und JSON/CSV geprüft. Die Flugtests prüfen den Pythagoras-Abstand, den bekannten Parabelscheitel und die radiale Geschwindigkeit gegen eine numerische Ableitung von R(t). GUI-Tests verarbeiten Ergebnisse über Qt-Signale, prüfen Bedienzustände und erhaltenen Zoom während der Wiedergabe und exportieren alle fünf Diagramme offscreen.

Ein diskreter FFT-Maximalschätzer ohne Sub-Bin-Interpolation wird mit auflösungsbezogenen Grenzen bewertet:

```text
|vhat−v| ≤ Δv/2
|Rhat−R| ≤ ΔR/2 + c Δfd/(4S)
```

Ein Prozent numerischer Spielraum wird zusätzlich verwendet. Diese Grenzen gelten für ausreichend isolierte, dominierende Peaks; kein universeller Fehlerbound unter beliebigem Rauschen. Der Soll-Ist-Vergleich sortiert mögliche Paare nach quadratischem Abstand in ΔR-/Δv-Einheiten und ordnet greedy 1:1 zu. Gate: jeweils 1,5 nominelle Zellen. Zusätzliche Kandidaten werden separat ausgewiesen. Nahe interferierende Ziele sind kein Test, der garantiert beide Sollwerte treffen muss.

Gemessener Referenzlauf auf Windows: Standard-Szene maximal |ΔR|=0,195543 m und |Δv|=0,097359 m/s. Reines Rauschen: 96 unabhängige Frames je Fenster, je 1.751.040 geprüfte CUTs. Rechteck 1.726 Fehlalarme, Pfa=0,0009857; Hann 2.118, Pfa=0,0012096. Nominell 0,001. 95-%-Intervalle werden aus der Streuung der **Frame-Raten** gebildet; kein falsches Binomialintervall mit unabhängig angenommenen benachbarten CUTs. Ein harter Rechteck-Sanity-Check erlaubt max(4 Standardfehler, 15 % Pfa) Abweichung; Hann wird nur gemessen.

Die Auflösungsdemo mit 1,2 ΔR Abstand und Hann ordnet nur eines der zwei Ziele zu. Das ist als Demo gekennzeichnet und kein bestandener Zweizieltest. Im SNR-Sweep werden bei Referenz-SNR −40/−30/−20/0/15 dB jeweils 0/31/32/32/32 von 32 Sollzielen zugeordnet. Wegen kleiner Stichprobe und Zuordnungsgates ist das eine Illustration der Verarbeitung, keine statistisch belastbare Radar-Pd-Spezifikation. Berichtszahlen können bei Änderungen des Modells oder NumPy geringfügig abweichen; maßgeblich ist der neu ausgeführte Lauf.

Der [Flugbericht](../reports/FLUEGE.md) ergänzt alle 201 Zeitpunkte je Flugszene. Insgesamt 603 Frames und 804 Soll-Zielwerte werden mit denselben FFT-Toleranzen geprüft. Im Referenzlauf fehlen keine Zuordnungen; maximaler Fehler über alle Flüge: ca. 0,504 m und 0,127 m/s. Die Rohdatei enthält alle Einzelwerte und RMSE. Höhe und horizontaler Ort sind bekannte Simulationsdaten und werden nicht als vom Radar gemessen ausgegeben. Die parabelförmige Szene ist eine vorgegebene Bahn mit −0,4 m/s² senkrechter Beschleunigung, keine ballistische Freiflugrechnung.

## 9. Architektur, Ressourcen und Reproduzierbarkeit

Die Pipeline `simulate_frame` validiert vor Array-Allokation. M×N≤1.048.576, N zwischen 32 und 32768, M zwischen 16 und 2048 und höchstens 32 Ziele. Getrennte Fast-/Slow-Time-Phasen vermeiden pro Ziel ein zusätzliches volles Phasenarray. CFAR nutzt Integralbilder. Qt hält höchstens einen aktiven Berechnungsjob, keine Frame-Warteschlange. Während des nächsten Jobs kann der letzte Frame noch in der GUI liegen: Spitzenbedarf enthält also beide Ergebnisse und temporäre Arrays. Die Grenze begrenzt den Bedarf, ist aber keine exakte MiB-Garantie; Qt, FFT und Python benötigen zusätzlichen Speicher.

Konfigurationen werden als JSON-Version 3 mit optionaler `flugszene` und gezeichneter `route` gespeichert. Die Versionen 1 und 2 bleiben lesbar. Die maximale Dateigröße ist 1 MB, unbekannte Felder und nicht endliche Zahlen werden abgewiesen. CSV enthält SI-Einheiten in Spaltennamen, Semikolon und UTF-8-BOM für Windows. `power` und `threshold` sind relative lineare Leistungen; `apparent_range_m` ist der unkorrigierte Wert. Vollständige Eingabekonfiguration, Frameindex und Flugzeit begleiten den GUI-CSV-Export. Bekannte Flugzustände stehen in einer getrennten `.flug.csv`; diese sind keine Schätzwerte. PNG-Exporte enthalten die beschrifteten Achsen; der Heatmapexport der GUI enthält die Farbskala. Berichtsgrafiken nennen die feste Farbspanne im Titel.

Es wurden keine Zugangsdaten, externen Radar-Bibliotheken, Netzdaten oder zusätzlichen Testframeworks in den Simulator eingebunden. GitHub-Referenzcode war beim Aufbau nicht erreichbar; Details siehe README. Der Code behauptet deshalb keine übernommene Repository-Struktur.

## 10. Gekoppelte Regler und gezeichnete Routen

`parametergrenzen.py` löst die beschriebenen Sampling-, Timing-, Doppler-, Speicher-, Bewegungs- und CFAR-Bedingungen jeweils nach einer veränderlichen Größe auf. Die anderen Eingaben bleiben dabei fest. Chirpdauer und ADC-Rate werden auf ein Raster ganzzahliger Samplezahlen gesetzt. An strikten Modellgrenzen wird ein kleiner numerischer Sicherheitsabstand verwendet. Die Kernprüfung akzeptiert Sampleprodukte innerhalb 10⁻⁶ einer ganzen Zahl und prüft die Grenzen 32…32768 an dieser gerundeten Zahl, damit beispielsweise 31,999999999999996 wegen binärer Fließkommadarstellung nicht als weniger als 32 Samples abgewiesen wird.

Die GUI zeigt Zahlenfeld, Slider und Bereich nebeneinander im selben Parameterblock. Direkte ungültige Eingaben bleiben sichtbar und sperren die Simulation; andere Parameter werden nicht heimlich geändert. Die Bereiche sichern das Rechenmodell, keine Detektionsgarantie. Die Tests vergleichen Minima, Maxima und Mittelpunkte mit `validate_config`, auch nach 80 reproduzierbaren Änderungen (3.600 Bereichsprüfungen).

Eine gezeichnete Route ist eine natürliche kubische Kurve durch höchstens 64 nach Weglänge verteilte Mauspunkte. `route.py` löst das kleine lineare System für die zweiten Ableitungen. Die Zeitzuordnung erfolgt durch die integrierte Bogenlänge `s=v*t`. Acht Gaußpunkte je Teilintervall und 64 Teilintervalle pro Kurvenabschnitt bestimmen die Längentabelle; drei Newton-Korrekturen invertieren sie. Der Geschwindigkeitsvektor ist `v*p'/abs(p')`. Damit stimmen die Norm des Flugtempos und die zeitliche Positionsableitung überein, auch bei ungleichen Abständen der Stützpunkte.

Die Kurve ist an den Knoten glatt bis zur zweiten Ableitung. Höhenextrema werden über die Polynomableitung geprüft. Verschwindende Tangenten (spitze Umkehr) sind verboten. Die Krümmung wird konservativ durch `max(abs(p''))/min(abs(p'))²` beschränkt; das Minimum des Tangentenbetrags wird über die stationären Punkte des zugehörigen quartischen Polynoms bestimmt. Die radiale Beschleunigung ist höchstens `v²*(1/h_min + Krümmungsgrenze)`. Derselbe Wert geht in Kernvalidierung und Reglergrenzen ein. Eine Animation endet am letzten Routenpunkt, ohne Start- oder Bremsdynamik zu modellieren.

Die Beispielroute (−80,35) → (0,55) → (80,35) m hat 165,848095609 m Länge. Bei 5 m/s dauert sie 33,169619122 s. Alle 333 Messpakete wurden geprüft: keine fehlende Zuordnung und keine Überschreitung der dokumentierten FFT-Toleranzen. Die radiale Geschwindigkeit stimmt mit einer zentralen numerischen Ableitung von R(t) bis auf etwa 1,39·10⁻¹⁰ m/s überein. Details: [Routen- und Reglerbericht](../reports/ROUTE_UND_REGLER.md), [Bedienung und Formeln](REGLER_UND_ROUTEN.md).

## 11. Primärquellen und Einordnung

- [Texas Instruments: Programming Chirp Parameters in TI Radar Devices, SWRA553A](https://www.ti.com/lit/an/swra553a/swra553a.pdf): Hintergrund zu Bandbreite, Chirptiming, Entfernung und Dopplergrenzen. Das vorliegende Modell verwendet eigene offengelegte Näherungen und keine gerätespezifischen TI-ADC-Modi.
- [NumPy: Discrete Fourier Transform](https://numpy.org/doc/stable/reference/routines.fft.html): FFT-Vorzeichen, Frequenzordnung und `fftshift`.
- [pyqtgraph: ImageItem](https://pyqtgraph.readthedocs.io/en/latest/api_reference/graphicsItems/imageitem.html): Bildachsen und Koordinatenabbildung. Im Projekt explizit `axisOrder="row-major"`.
- [MathWorks: Constant False-Alarm Rate Detectors](https://www.mathworks.com/help/phased/ug/constant-false-alarm-rate-cfar-detectors.html): Verteilungsannahmen, Trainingszellen und Interpretation der Fehlalarmwahrscheinlichkeit.
- [Texas Instruments: Radar Hardware Accelerator User's Guide, SWRU526B, Abschnitt 2.3.2](https://www.ti.com/lit/ug/swru526b/swru526b.pdf): CFAR und zusätzliche Peak-Nachbarprüfung. TI beschreibt die 1D-Prüfung; der Simulator prüft ausdrücklich acht Nachbarn in 2D.

Die zentrale Beat-Gleichung und CA-CFAR-Skalierung werden oben hergeleitet, damit Berechnungen ohne eine versteckende Radar-Bibliothek überprüfbar bleiben.
