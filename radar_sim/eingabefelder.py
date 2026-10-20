"""Eingabefelder aufbauen; Radarberechnung und Ablauf stehen außerhalb dieser Klasse."""

from PyQt6.QtWidgets import QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox, QCheckBox, QScrollArea, QTableWidget, QHeaderView
from .antenne import Antenne, ANTENNENTYPEN
from .flugbahn import flugszenen
from .flughafen import flughafenszenen
from .parametergrenzen import ParameterBereich
from .regler import CompactDoubleSpinBox, ParameterRegler, feldwert, zahlenfeld
from .passiv_config import PassivSettings
from .fernradar import fernszene


class Eingabefelder(QTabWidget):
    """Enthält Eingabefelder für Flug, Radar, DSP, Targets und Antennen."""

    def __init__(self) -> None:
        super().__init__()
        self.tabBar().setObjectName("parameterTabs")
        self.controls = {}
        self.regler = {}
        self.ant_controls = {}
        self.passiv_controls = {}
        self._baue_flugfelder()
        self._baue_radar()
        self._baue_dsp()
        self._baue_targets()
        self._baue_antenne()
        self._baue_passiv()

    def _baue_flugfelder(self) -> None:
        """Flugbeispiel auswählen und dessen Startwerte bearbeiten."""
        box = QWidget()
        layout = QVBoxLayout(box)
        self.flug_auswahl = QComboBox()
        self.flug_auswahl.addItem("Feste Targets (ohne Flugroute)", None)
        from .passivradar import passiv_config
        for szene in (*flughafenszenen().values(), *flugszenen().values(), fernszene(), passiv_config().flugszene):
            self.flug_auswahl.addItem(szene.name, szene)
        layout.addWidget(QLabel("Flugbeispiel"))
        layout.addWidget(self.flug_auswahl)
        self.flug_auswahl.setToolTip("X und Y sind horizontal, Z ist die Höhe über Boden. Normalerweise steht das Radar im Ursprung. Air-to-Air zeigt zwei Flugzeuge: Ein Flugzeug trägt Sender und Empfänger, das andere ist das Echoziel. Gemessen werden relative Entfernung und radiale Relativgeschwindigkeit. Airport-Szenen laden passende Startwerte.")
        form = QFormLayout()
        self.flug_dauer = CompactDoubleSpinBox()
        self.flug_dauer.setDecimals(12)
        self.flug_dauer.setRange(1e-9, 1e12)
        self.flug_dauer.setToolTip("So lange dauert der Flug. Bei einer eigenen Route ändert eine längere Dauer das Tempo: Speed = Streckenlänge / Dauer. Änderst du stattdessen Speed, folgt die Dauer automatisch.")
        self.flug_schritt = CompactDoubleSpinBox()
        self.flug_schritt.setDecimals(12)
        self.flug_schritt.setRange(1e-9, 1e12)
        self.flug_schritt.setToolTip("Simulationszeit zwischen zwei Radarframes. Mindestens so lang wie ein Messpaket. Größere Schritte spielen lange Routen schneller ab; die Anzeige wartet höchstens eine Sekunde pro Frame.")
        self.dauer_regler = ParameterRegler(self.flug_dauer, ParameterBereich(0.1, 120))
        self.schritt_regler = ParameterRegler(self.flug_schritt, ParameterBereich(0.02, 1))
        form.addRow("Flugdauer / s", self.dauer_regler)
        form.addRow("Zeitschritt / s", self.schritt_regler)
        form.labelForField(self.dauer_regler).setToolTip(self.flug_dauer.toolTip())
        form.labelForField(self.schritt_regler).setToolTip(self.flug_schritt.toolTip())
        layout.addLayout(form)
        self.route_settings = QWidget()
        route_layout = QVBoxLayout(self.route_settings)
        route_layout.setContentsMargins(0, 0, 0, 0)
        self.routen_tempo = CompactDoubleSpinBox()
        self.routen_tempo.setRange(0.001, 1e6)
        self.routen_tempo.setDecimals(12)
        self.routen_tempo.setValue(70)
        self.routen_tempo.setToolTip("Maximales Flugtempo in Metern pro Sekunde. Die radiale Geschwindigkeit zum Radar kann kleiner sein. Bei Beispielbahnen bleibt die Strecke gleich und die Flugdauer folgt dem Tempo. Wenn nötig werden Radarwerte automatisch angepasst; die neue Auflösung steht oben.")
        self.tempo_regler = ParameterRegler(self.routen_tempo, ParameterBereich(.001, 1000))
        tempo_label = QLabel("Speed (max.) / m/s")
        tempo_label.setToolTip(self.routen_tempo.toolTip())
        route_layout.addWidget(tempo_label)
        route_layout.addWidget(self.tempo_regler)
        self.routen_staerke = CompactDoubleSpinBox()
        self.routen_staerke.setDecimals(15)
        self.routen_staerke.setRange(0.000001, 1e6)
        self.routen_staerke.setValue(1)
        self.routen_staerke.setToolTip("So stark strahlt das Objekt auf deiner Route zurück. Im didaktischen Modell ist das eine relative Leistung; im Radar-Modell der Radarquerschnitt in Quadratmetern.")
        self.routen_staerke_regler = ParameterRegler(self.routen_staerke, ParameterBereich(0.000001, 1e6), logarithmisch=True)
        staerke_label = QLabel("Route: Echostärke")
        staerke_label.setToolTip(self.routen_staerke.toolTip())
        route_layout.addWidget(staerke_label)
        route_layout.addWidget(self.routen_staerke_regler)
        self.staerke_label = staerke_label
        self.tempo_hinweis = QLabel()
        self.tempo_hinweis.setWordWrap(True)
        self.tempo_hinweis.setStyleSheet("color: #9cb0c8; font-size: 9pt;")
        route_layout.addWidget(self.tempo_hinweis)
        layout.addWidget(self.route_settings)
        knoepfe = QHBoxLayout()
        self.zeichnen_button = QPushButton("Route zeichnen")
        self.zeichnen_button.setCheckable(True)
        self.zeichnen_button.setToolTip("Öffnet Route 3D: Jeder Linksklick setzt einen Stützpunkt. Punkte fertig erlaubt das Verschieben. Rechtsklick auf die Linie fügt einen Punkt ein. Übernehmen verwendet den räumlichen Entwurf.")
        self.route_button = QPushButton("Übernehmen")
        self.route_button.setEnabled(False)
        self.abbrechen_button = QPushButton("Abbrechen")
        knoepfe.addWidget(self.zeichnen_button)
        knoepfe.addWidget(self.route_button)
        knoepfe.addWidget(self.abbrechen_button)
        layout.insertLayout(2, knoepfe)
        self.routen_hinweis = QLabel()
        self.routen_hinweis.setWordWrap(True)
        layout.addWidget(self.routen_hinweis)
        self.startwerte_label = QLabel("Startwerte · Doppelklick öffnet einen Regler")
        layout.addWidget(self.startwerte_label)
        self.flug_tabelle = QTableWidget(0, 8)
        self.flug_tabelle.setHorizontalHeaderLabels(["Start X / m", "Start Z / m", "vX / m/s", "vZ / m/s", "aZ / m/s²", "Stärke", "Start Y / m", "vY / m/s"])
        erklaerungen = ["Horizontaler Startort relativ zur Station.", "Starthöhe über der Station.",
                        "Horizontale Geschwindigkeit: + rechts, − links.", "Senkrechte Startgeschwindigkeit: + steigen, − sinken.",
                        "Senkrechte Beschleunigung. Negativ: nach unten offene Parabel.", "Relative Echoleistung oder Radarquerschnitt, je nach Amplitudenmodell.",
                        "Seitlicher Startort in der horizontalen Y-Richtung.", "Seitliche Geschwindigkeit entlang Y. Sie geht in Entfernung und radiale Geschwindigkeit ein."]
        for spalte, erklaerung in enumerate(erklaerungen):
            self.flug_tabelle.horizontalHeaderItem(spalte).setToolTip(erklaerung)
            self.flug_tabelle.setColumnWidth(spalte, 105)
        self.flug_tabelle.setMinimumHeight(140)
        self.flug_tabelle.setMaximumHeight(240)
        self.flug_tabelle.setToolTip("Startwerte per Doppelklick ändern. Eine Parabel beschreibt hier einen gesteuerten Flug, keine freie Wurfbewegung.")
        layout.addWidget(self.flug_tabelle)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        self.addTab(scroll, "Flug")

    def _neues_formular(self, name: str) -> QFormLayout:
        container = QWidget()
        form = QFormLayout(container)
        form.setContentsMargins(14, 18, 14, 18)
        form.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        self.addTab(scroll, name)
        return form

    def _zahlenregler(self, form: QFormLayout, key: str, label: str, minimum: float, maximum: float,
                decimals: int, tooltip: str, integer: bool = False) -> None:
        spin = zahlenfeld(minimum, maximum, tooltip, max(decimals, 9) if decimals else 0, integer)
        regler = ParameterRegler(spin, ParameterBereich(minimum, maximum, 1 if integer or key == "seed" else 0),
                                 logarithmisch=key in ("pfa", "reference_range_m", "reference_rcs_m2"))
        beschriftung = QLabel(label)
        beschriftung.setToolTip(tooltip)
        form.addRow(beschriftung, regler)
        self.controls[key] = spin
        self.regler[key] = regler

    def _baue_radar(self) -> None:
        form = self._neues_formular("Radar")
        self.radar_form = form
        modus = QComboBox()
        modus.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        modus.setMinimumContentsLength(12)
        modus.addItem("FMCW · kontinuierliche Chirps", "fmcw")
        modus.addItem("Puls-Doppler · LFM + Pulskompression", "pulse_doppler")
        modus.addItem("Passivradar · BETA", "passive")
        modus.setToolTip("Wählt ein offenes Startprofil. FMCW wertet Mischfrequenzen aus; Puls-Doppler misst verzögerte Pulse mit einem Matched Filter. Ein Moduswechsel setzt die Radarwerte zurück, behält Flugbahnen und Antenne. Nicht jede Nahbereichsszene passt in den Puls-Sendeblindbereich.")
        self.controls["radar_mode"] = modus
        form.addRow("Radarverfahren", modus)
        self.modus_hinweis = QLabel()
        self.modus_hinweis.setWordWrap(True)
        form.addRow(self.modus_hinweis)
        definitions = [
            ("carrier_hz", "Träger / GHz", .001, 300., 4, "Grundfrequenz der ausgesendeten Welle. Eine höhere Frequenz macht dieselbe Fluggeschwindigkeit als stärkere Phasenänderung sichtbar, verkleinert aber den eindeutigen Geschwindigkeitsbereich."),
            ("bandwidth_hz", "Bandbreite / MHz", .000001, 10000., 4, "Um diesen Betrag steigt die Frequenz im Chirp. Mehr Bandbreite trennt nahe Entfernungen besser. Dafür können längere Chirps oder eine höhere Abtastrate nötig werden."),
            ("chirp_s", "Aktiver Chirp / µs", 1., 10000., 4, "So lange dauert eine ausgesendete Frequenzrampe. Ein längerer Chirp verteilt dieselbe Bandbreite auf mehr Zeit und senkt die Mischfrequenz. Der Slider rastet auf ganzen Abtastpunkten."),
            ("repetition_s", "Wiederholintervall / µs", 1., 100000., 4, "Zeit vom Start eines Chirps zum nächsten, einschließlich Pause. Zu große Abstände machen hohe Geschwindigkeiten mehrdeutig. Muss mindestens die aktive Chirpdauer erreichen."),
            ("sample_rate_hz", "Abtastrate / MHz", 0.01, 100., 4, "So oft pro Sekunde liest der ADC das Mischsignal. Eine höhere Rate erfasst höhere Mischfrequenzen, braucht aber mehr Speicher. Der Slider sorgt für eine ganze Samplezahl pro Chirp."),
        ]
        for definition in definitions:
            self._zahlenregler(form, *definition)
        self._zahlenregler(form, "chirps", "Chirp-Anzahl", 16, 2048, 0, "So viele Rampen werden gemeinsam ausgewertet. Mehr Wiederholungen trennen ähnliche Geschwindigkeiten besser, dauern aber länger. Währenddessen darf das Flugobjekt nicht zu weit wandern.", True)
        self._zahlenregler(form, "adc_skip_samples", "ADC-Vorlauf / Samples", 0, 32768, 0,
                     "Diese Abtastschritte am Rampenanfang werden ausgelassen, bis das entfernteste Echo angekommen ist. Mehr Vorlauf erlaubt größere Laufzeiten, verkürzt aber das Messfenster und verschlechtert die Entfernungsauflösung. 0 verwendet das alte vereinfachte Nahbereichsmodell.", True)
        self._zahlenregler(form, "snr_db", "Referenz-SNR / dB", -80, 100, 1, "Verhältnis eines Echos mit Amplitude 1 zur Rauschleistung vor der FFT. Ein größerer Wert bedeutet weniger Rauschen; ein kleinerer Wert macht das Erkennen schwerer.")
        self._zahlenregler(form, "seed", "Noise-Seed", 0, 2**32 - 1, 0, "Bestimmt die Folge der Zufallszahlen. Gleicher Startwert und gleiche Frame-Nummer ergeben dasselbe Rauschen. So kannst du Versuche wiederholen.")
        noise = QCheckBox("AWGN addieren")
        noise.setToolTip("Fügt dem Mischsignal zufälliges Grundrauschen hinzu. Ausschalten entfernt dieses Rauschen, aber nicht die Nebenkeulen der FFT.")
        self.controls["noise_enabled"] = noise
        form.addRow(noise)

    def zeige_radarmodus(self, puls: bool) -> None:
        """Gemeinsame Felder erhalten die tatsächlich verwendete Bedeutung."""
        self.regler["chirp_s"].show()
        self.radar_form.labelForField(self.regler["chirp_s"]).show()
        self.radar_form.labelForField(self.regler["repetition_s"]).setText("Wiederholintervall / µs")
        for key, text in (("chirp_s", "Pulsdauer / µs" if puls else "Aktiver Chirp / µs"),
                          ("chirps", "Pulse pro Messpaket" if puls else "Chirp-Anzahl")):
            self.radar_form.labelForField(self.regler[key]).setText(text)
        self.regler["adc_skip_samples"].setVisible(not puls)
        self.radar_form.labelForField(self.regler["adc_skip_samples"]).setVisible(not puls)
        tipps = {
            "chirp_s": "Länge des LFM-Sendepulses. Währenddessen ist der Empfang gesperrt: Rmin=c·Tp/2. Längere Pulse tragen bei gleicher Spitzenamplitude mehr Energie, vergrößern aber den Blindbereich." if puls else "Dauer einer FMCW-Frequenzrampe; Steigung S=B/T. Längere Rampen senken die Mischfrequenz.",
            "bandwidth_hz": "Frequenzhub innerhalb des Pulses. Pulskompression erreicht nominal ΔR=c/(2B), auch bei längerem Puls. Der ADC muss die Bandbreite abtasten." if puls else "FMCW-Sendebandbreite; mit vollständig erfasster Rampe nominal ΔR=c/(2B).",
            "sample_rate_hz": "Komplexe Basisband-Abtastrate über das ganze PRI. fs>B plus Dopplerreserve. Entfernungsraster c/(2fs) ist nicht die Auflösung c/(2B)." if puls else "Abtastrate des dechirpten Mischsignals; dessen Frequenzen müssen innerhalb ±fs/2 liegen.",
            "repetition_s": "Zeit von Pulsstart zu Pulsstart, PRF=1/Tr. Größeres Tr erlaubt weiter entfernte Echos, senkt aber |v|max=λ/(4Tr)." if puls else "Zeit von Chirpstart zu Chirpstart, einschließlich Pause. Bestimmt die Doppler-Eindeutigkeit.",
            "chirps": "Anzahl kohärent ausgewerteter Pulse. Δv=λ/(2MTr). Mehr Pulse verbessern die Dopplerauflösung, verlängern aber das Messpaket." if puls else "Anzahl kohärent ausgewerteter FMCW-Chirps. Mehr Chirps verbessern die Dopplerauflösung.",
        }
        for name, tipp in tipps.items():
            self.controls[name].setToolTip(tipp)
            self.regler[name].setToolTip(tipp)
            self.radar_form.labelForField(self.regler[name]).setToolTip(tipp)
        self.modus_hinweis.setText("LFM-Pulse → Matched Filter → Doppler-FFT. Sendeblindbereich und PRI-/Geschwindigkeitsgrenzen; keine Mehr-PRF-Entfaltung. Hann gewichtet Filter und Pulsfolge, CFAR-Pfa ist nominell." if puls else "FMCW: Beat-Signal → Range-FFT → Doppler-FFT. ADC-, Laufzeit- und Geschwindigkeitsgrenzen; vereinfachtes kohärentes Modell.")

    def _baue_dsp(self) -> None:
        form = self._neues_formular("DSP / CFAR")
        window = QComboBox()
        window.addItem("Hann (periodisch)", "hann")
        window.addItem("Rechteck", "rect")
        window.setToolTip("Gewichtet die Signalränder vor beiden FFTs. Hann macht störende Nebenkeulen kleiner, verbreitert aber die Peaks. Rechteck behält alle Samples gleich stark.")
        self.controls["window"] = window
        form.addRow("Fenster", window)
        static = QCheckBox("Null-Doppler unterdrücken")
        static.setToolTip("Entfernt den Mittelwert über Chirps bzw. Pulse. Unterdrückt Ziele mit ungefähr null RADIALER RELATIVGESCHWINDIGKEIT. Bei bewegtem Radar ist ruhender Boden nicht automatisch Null-Doppler. Kein Bodenclutter-Modell und kein Plattform-Bewegungsausgleich.")
        self.controls["remove_static"] = static
        form.addRow(static)
        model = QComboBox()
        model.addItem("Didaktisch: relative Leistung", "didactic")
        model.addItem("Radar: relative σ/R⁴-Leistung", "radar")
        model.setToolTip("Didaktisch hängt die Echostärke nur von deiner Eingabe ab. Im Radar-Modell werden entfernte Ziele deutlich schwächer, entsprechend Leistung proportional zu Radarquerschnitt / Entfernung hoch vier. Es sind relative Werte, keine Watt.")
        self.controls["amplitude_model"] = model
        form.addRow("Amplitudenmodell", model)
        self._zahlenregler(form, "reference_range_m", "Radar-Referenz / m", 0.01, 10000000, 2, "Relative Entfernungsreferenz für die Echostärke, keine absolute Sendeleistung. Monostatisch A∝Rref²/R², bistatisch A∝Rref²/(Rt·Rr). Größere Referenzwerte erhöhen den normierten Pegel, nicht physikalisch belegte Reichweite.")
        self._zahlenregler(form, "reference_rcs_m2", "RCS-Referenz / m²", 0.001, 100000, 3, "Vergleichswert für den Radarquerschnitt, also wie stark ein Objekt zurückstrahlt. Bei gleicher Entfernung liefert ein größerer Radarquerschnitt mehr Echoleistung.")
        for key, label in (("training_range", "Training Range / Seite"), ("training_doppler", "Training Doppler / Seite"),
                           ("guard_range", "Schutz Range / Seite"), ("guard_doppler", "Schutz Doppler / Seite")):
            self._zahlenregler(form, key, label, 1 if key.startswith("training") else 0, 128, 0,
                         ("Wie viele Nachbarzellen pro Seite den Hintergrundpegel schätzen. Mehr Zellen glätten die Schätzung, brauchen aber mehr Platz im Bild. Am Rand fehlt dieser Platz."
                          if key.startswith("training") else
                          "Wie viele Zellen neben dem geprüften Peak ausgelassen werden. So wird sein eigenes Echo nicht als Rauschen mitgemittelt. Zu große Schutzbereiche verkleinern die auswertbare Bildfläche."), True)
        self._zahlenregler(form, "pfa", "Fehlalarm-Pfa", 1e-8, 0.1, 12,
                     "Erlaubte Fehlalarmwahrscheinlichkeit pro geprüfter Zelle im idealen Rauschmodell. Kleiner: weniger falsche Treffer, aber schwache Ziele können fehlen. Bei Hann ist die Rate nur näherungsweise so groß.")

    def _baue_targets(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        note = QLabel("v < 0: Annäherung · v > 0: Entfernung\nStärke: relative Leistung (didaktisch) oder RCS in m² (Radar). Phase: Beat-Startphase in rad.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.targets_table = QTableWidget(0, 4)
        self.targets_table.setHorizontalHeaderLabels(["R / m", "v / m/s", "Stärke / σ", "φ / rad"])
        self.targets_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.targets_table.setToolTip("Doppelklick zum Editieren; Dezimalpunkt oder Komma. Maximal 32 punktförmige Ziele.")
        for spalte, text in enumerate(("Direkte Entfernung zwischen Ziel und Radar in Metern.",
                                      "Geschwindigkeit entlang der Sichtlinie: negativ zur Station, positiv von ihr weg.",
                                      "Wie stark das Objekt zurückstrahlt: relative Leistung oder Radarquerschnitt, je nach Modell.",
                                      "Zusätzliche Startphase des Echos. Sie beeinflusst die Überlagerung mehrerer Echos.")):
            self.targets_table.horizontalHeaderItem(spalte).setToolTip(text)
        layout.addWidget(self.targets_table)
        row = QHBoxLayout()
        self.add_target_button = QPushButton("+ Target")
        self.remove_target_button = QPushButton("− Auswahl")
        row.addWidget(self.add_target_button)
        row.addWidget(self.remove_target_button)
        layout.addLayout(row)
        self.addTab(container, "Targets")

    def _baue_antenne(self) -> None:
        """Richtdiagramme als eigener, einfacher Parameterblock."""
        self.ant_form = self._neues_formular("Antenne")
        auswahl = QComboBox()
        auswahl.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        auswahl.setMinimumContentsLength(12)
        for typ, name in ANTENNENTYPEN.items():
            auswahl.addItem(name, typ)
        auswahl.setToolTip("Die Antenne gewichtet Flug-Echos nach ihrer bekannten Raumrichtung. Fächer und Parabol sind vereinfachte Gauß-Hauptkeulen; das Patch-Feld verwendet einen idealen Arrayfaktor mit Abstand λ/2. Alle Typen werden bei gleichem Achsenpegel verglichen, ohne absolute dBi oder Sendeleistung. Feste R/v-Targets ohne Raumposition gelten als auf der Achse.")
        self.ant_controls["typ"] = auswahl
        self.ant_form.addRow("Antennentyp", auswahl)
        self.ant_regler = {}
        definitionen = [
            ("azimut_grad", "Azimut / °", -180, 180, False, "Blickrichtung in der XY-Ebene: 0° ist +X, 90° ist +Y, 180° ist −X."),
            ("elevation_grad", "Elevation / °", -89, 89, False, "Neigung der Hauptachse über der horizontalen Ebene. 0° blickt waagerecht, positive Werte nach oben."),
            ("breite_az_grad", "Breite Azimut / °", .2, 120, False, "Volle Einweg-Halbwertsbreite der Fächerkeule. Am halben Winkel fällt die Sendeleistung auf die Hälfte, die monostatische Echoleistung auf ein Viertel."),
            ("breite_el_grad", "Breite Elevation / °", .2, 120, False, "Vertikale Halbwertsbreite der Fächerkeule. Große Werte ergeben einen hohen Fächer."),
            ("durchmesser_m", "Durchmesser / m", .05, 10, False, "Reflektordurchmesser. Die angenäherte Parabol-Halbwertsbreite ist 70·Wellenlänge/Durchmesser in Grad. Größer bedeutet schmaler."),
            ("elemente_horizontal", "Patch-Spalten", 2, 128, True, "Anzahl idealer Patch-Elemente horizontal, Abstand λ/2. Mehr Elemente machen die Hauptkeule schmaler und erzeugen ausgeprägte Nullstellen und Nebenkeulen."),
            ("elemente_vertikal", "Patch-Zeilen", 2, 128, True, "Anzahl idealer Patch-Elemente vertikal. Wir modellieren das normierte Fernfeld, kein kalibriertes Hardwarearray und keine Winkelschätzung."),
            ("zeichenlaenge_m", "Keulenlänge / m", 10, 10000000, False, "Nur die Zeichenlänge der Halbwertskeule. Sie begrenzt weder das Echo noch garantiert sie Erkennung. Die Empfindlichkeit folgt Richtdiagramm, Entfernung, RCS und Rauschen."),
        ]
        for key, label, unten, oben, ganz, tooltip in definitionen:
            spin = zahlenfeld(unten, oben, tooltip, 6, ganz)
            regler = ParameterRegler(spin, ParameterBereich(unten, oben, 1 if ganz else 0))
            self.ant_form.addRow(label, regler)
            self.ant_form.labelForField(regler).setToolTip(tooltip)
            self.ant_controls[key], self.ant_regler[key] = spin, regler

    def lese_antenne(self) -> Antenne:
        return Antenne(**{name: feldwert(feld) for name, feld in self.ant_controls.items()})

    def _baue_passiv(self) -> None:
        form = self._neues_formular("Passiv BETA")
        info = QLabel("Fester Fremdsender, Empfänger im Ursprung. Synthetisches Breitbandsignal und idealer Referenzkanal. Gemessen wird der zusätzliche Weg über das Flugzeug; keine eindeutige XYZ-Ortung.")
        info.setWordWrap(True)
        form.addRow(info)
        for key, label, unten, oben, tipp in (
            ("sender_x_m", "Sender X / m", -1e7, 1e7, "Weltposition des festen Fremdsenders. Der passive Empfänger steht bei (0,0,0)."),
            ("sender_y_m", "Sender Y / m", -1e7, 1e7, "Seitliche Weltposition des Fremdsenders; verändert die bistatische Geometrie und den Doppler."),
            ("sender_z_m", "Sender Z / m", 0, 1e6, "Bekannte Senderhöhe über Boden. Keine automatische Geländesichtprüfung."),
            ("maximaler_umweg_m", "Umweg-Suchbereich / m", 1000, 1e7, "Maximaler zusätzlicher Weg Tx→Target→Rx gegenüber Tx→Rx. Größerer Suchbereich braucht mehr Verzögerungszellen; das Rechenbudget bleibt begrenzt."),
            ("direktweg_db", "Direktweg / dB", -80, 60, "Leistung des direkten Senderanteils im Überwachungskanal relativ zu Aref²=1. Starker Direktweg kann schwache Echos verdecken.")):
            feld = zahlenfeld(unten, oben, tipp, 6)
            regler = ParameterRegler(feld, ParameterBereich(unten, oben), logarithmisch=key=="maximaler_umweg_m")
            form.addRow(label, regler)
            self.passiv_controls[key] = feld
        schalter = QCheckBox("Direktweg mit Referenzprojektion entfernen")
        schalter.setToolTip("Schätzt einen komplexen Direktweg-Koeffizienten aus Referenz und Überwachung. Keine vollständige Clutterunterdrückung; nahe Null-Doppler können auch Zielanteile verloren gehen.")
        form.addRow(schalter)
        self.passiv_controls["direktweg_entfernen"] = schalter

    def lese_passiv(self) -> PassivSettings:
        return PassivSettings(**{name: feldwert(feld) for name, feld in self.passiv_controls.items()})

    def zeige_passivmodus(self, aktiv: bool) -> None:
        """Der passive Pfad hat Referenzblöcke statt Sendepulse oder Rampen."""
        self.controls["remove_static"].setEnabled(not aktiv)
        self.controls["amplitude_model"].setItemText(1, "Radar: relative σ/(Rt²Rr²)-Leistung" if aktiv else "Radar: relative σ/R⁴-Leistung")
        if not aktiv:
            return
        for key in ("chirp_s", "adc_skip_samples"):
            self.regler[key].hide()
            self.radar_form.labelForField(self.regler[key]).hide()
        self.radar_form.labelForField(self.regler["chirps"]).setText("Dopplerbins")
        self.radar_form.labelForField(self.regler["repetition_s"]).setText("Doppler-Rasterzeit / µs")
        self.controls["repetition_s"].setToolTip("Bestimmt mit der Binanzahl die Integration T=M·Tr und den gewählten Doppler-Suchbereich ±1/(2Tr). Keine Puls-PRF des Fremdsenders; die CAF nutzt das ganze kontinuierliche Signal.")
        self.controls["bandwidth_hz"].setToolTip("Bandbreite des synthetischen Fremdsenders. Nominale Umwegauflösung c/B, kein Faktor 1/2. Der Empfänger bestimmt die reale Senderbandbreite nicht selbst.")
        self.controls["sample_rate_hz"].setToolTip("Abtastrate beider Basisbandkanäle. Umweg-Raster c/fs. Der Referenzkanal ist in dieser BETA ideal und rauschfrei.")
        self.controls["chirps"].setToolTip("Zahl der ausgewerteten Dopplerbins. Integration T=M·Tr; Wegänderungsraster λ/T. Die CAF wertet jeden Doppler über alle Samples aus.")
        for key in ("sample_rate_hz", "bandwidth_hz", "repetition_s", "chirps"):
            self.regler[key].setToolTip(self.controls[key].toolTip())
            self.radar_form.labelForField(self.regler[key]).setToolTip(self.controls[key].toolTip())
        self.modus_hinweis.setText("Passiv BETA: Referenz + Überwachung → Kreuzambiguität. ΔL=Rt+Rr−Basislinie, dΔL/dt=λf. Separater Fremdsender; keine monostatische Entfernungs- oder Geschwindigkeitsumrechnung.")

    def zeige_antennenfelder(self) -> None:
        typ = self.ant_controls["typ"].currentData()
        for key, widget in self.ant_regler.items():
            sichtbar = (key in ("breite_az_grad", "breite_el_grad") and typ == "faecher"
                         or key == "durchmesser_m" and typ == "parabol"
                         or key.startswith("elemente_") and typ == "patch_array"
                         or key in ("azimut_grad", "elevation_grad", "zeichenlaenge_m") and typ != "isotrop")
            self.ant_form.setRowVisible(widget, sichtbar)
