"""SI-Konfiguration und Grenzen des verwendeten Schmalbandmodells."""

from dataclasses import asdict, dataclass, field, replace
import math
from typing import Any
from .flugbahn import Flugszene, Flugbahn, relative_bahngrenzen, pruefe_flugszene, kleinster_abstand
from .route import GezeichneteRoute
from .antenne import Antenne, pruefe_antenne
from .passiv_config import PassivSettings

C = 299_792_458.0
MAX_CELLS = 1_048_576  # begrenzt Arbeitsarrays; keine Garantie für gesamten Qt-Prozessspeicher


@dataclass(frozen=True)
class Target:
    """Radar-Ziel zu einem Zeitpunkt.

    range_m: direkte Entfernung [m], velocity_mps: radiale Geschwindigkeit [m/s].
    Positiv bedeutet Entfernung von der Station, negativ Annäherung.
    Passiv-BETA-Ergebnis: range_m ist der bistatische Umweg, velocity_mps
    dessen Änderungsrate. Diese Werte sind keine monostatische Rx-Entfernung.
    strength: relative Echoleistung oder Radarquerschnitt [m²], je nach Modell.
    phase_rad: zusätzliche Startphase des Mischsignals [rad].
    """

    range_m: float = 40.0
    velocity_mps: float = 0.0
    strength: float = 1.0
    phase_rad: float = 0.0
    antenna_gain: float = 1.0  # normierter EINWEG-Leistungsgewinn; Echoamplitude mal G


@dataclass(frozen=True)
class RadarConfig:
    """Die Namen enthalten ihre Einheit: hz=Hertz, s=Sekunden, m=Meter.

    carrier: Träger, bandwidth: Bandbreite, chirp: Frequenzrampe,
    repetition: Wiederholung, sample_rate: Abtastrate, chirps: Anzahl Rampen.
    targets sind feste Radar-Ziele; flugszene beschreibt alternativ bewegte Objekte.
    """
    carrier_hz: float = 77e9
    bandwidth_hz: float = 150e6
    chirp_s: float = 40e-6
    repetition_s: float = 60e-6
    sample_rate_hz: float = 10e6
    chirps: int = 128
    snr_db: float = 0.0
    noise_enabled: bool = True
    seed: int = 42
    window: str = "hann"
    remove_static: bool = False
    amplitude_model: str = "didactic"
    reference_range_m: float = 40.0
    reference_rcs_m2: float = 1.0
    training_range: int = 8
    training_doppler: int = 6
    guard_range: int = 2
    guard_doppler: int = 2
    pfa: float = 1e-4
    targets: tuple[Target, ...] = field(default_factory=lambda: (
        Target(40.0, -5.0, 1.0), Target(72.0, 7.0, 0.65), Target(105.0, 0.0, 0.45)))
    flugszene: Flugszene | None = None
    adc_skip_samples: int = 0
    antenne: Antenne = field(default_factory=Antenne)
    radar_mode: str = "fmcw"  # pulse_doppler: chirp_s ist die LFM-Pulsdauer.
    passiv: PassivSettings = field(default_factory=PassivSettings)

    @property
    def samples(self) -> int:
        """Nur ganzzahlige Abtastfenster zulässig; keine versteckte Daueränderung."""
        dauer = self.repetition_s if self.radar_mode != "fmcw" else self.chirp_s
        return round(self.sample_rate_hz * dauer) - self.adc_skip_samples

    @property
    def pulse_samples(self) -> int:
        return math.ceil(self.sample_rate_hz*self.chirp_s - 1e-9)

    @property
    def range_bins(self) -> int:
        if self.radar_mode == "passive":
            return math.floor(self.passiv.maximaler_umweg_m*self.sample_rate_hz/C)+1
        return self.samples - 2*self.pulse_samples + 1 if self.radar_mode == "pulse_doppler" else self.samples

    @property
    def range_bin_m(self) -> float:
        if self.radar_mode == "passive":
            return C/self.sample_rate_hz
        return C/(2*self.sample_rate_hz) if self.radar_mode == "pulse_doppler" else self.range_resolution

    @property
    def minimum_range_m(self) -> float:
        return C*self.chirp_s/2 if self.radar_mode == "pulse_doppler" else 0.

    @property
    def adc_start_s(self) -> float:
        return self.adc_skip_samples / self.sample_rate_hz

    @property
    def adc_duration_s(self) -> float:
        return self.repetition_s if self.radar_mode != "fmcw" else self.chirp_s - self.adc_start_s

    @property
    def timing_range_limit(self) -> float:
        """Mit Vorlauf: Echo stammt aus derselben Rampe. Sonst alte Randnäherung."""
        if self.radar_mode == "passive":
            return (self.range_bins-1)*self.range_bin_m
        if self.radar_mode == "pulse_doppler":
            return C*(self.repetition_s-self.chirp_s)/2
        return C/2 * (self.adc_start_s if self.adc_skip_samples else .025*self.chirp_s)

    @property
    def slope(self) -> float:
        """Chirp-Steigung S=B/T in Hertz pro Sekunde."""
        return self.bandwidth_hz / self.chirp_s

    @property
    def wavelength(self) -> float:
        """Wellenlänge λ=c/fc in Metern."""
        return C / self.carrier_hz

    @property
    def range_resolution(self) -> float:
        """c/(2*S*Tadc) [m]; ohne Vorlauf c/(2B), ohne Fensterverbreiterung."""
        if self.radar_mode == "passive":
            return C/self.bandwidth_hz
        return C/(2*self.bandwidth_hz) if self.radar_mode == "pulse_doppler" else C / (2 * self.slope * self.adc_duration_s)

    @property
    def velocity_resolution(self) -> float:
        """Nominale Geschwindigkeitsauflösung λ/(2MTr) in Metern pro Sekunde."""
        return self.wavelength / ((1 if self.radar_mode == "passive" else 2) * self.chirps * self.repetition_s)

    @property
    def max_velocity(self) -> float:
        """Geschwindigkeiten ab diesem Betrag sind wegen Doppler-Aliasing mehrdeutig."""
        return self.wavelength / ((2 if self.radar_mode == "passive" else 4) * self.repetition_s)

    @property
    def apparent_range_limit(self) -> float:
        """ADC-Grenze der Scheinentfernung c*fs/(4S) in Metern."""
        if self.radar_mode == "passive":
            return self.timing_range_limit
        return C*self.repetition_s/2 if self.radar_mode == "pulse_doppler" else C * self.sample_rate_hz / (4 * self.slope)

    @property
    def training_cells(self) -> int:
        return ((2 * (self.training_range + self.guard_range) + 1)
                * (2 * (self.training_doppler + self.guard_doppler) + 1)
                - (2 * self.guard_range + 1) * (2 * self.guard_doppler + 1))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 6, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RadarConfig":
        """Striktes Schema: unbekannte Felder und Versionen sind Fehler."""
        values = dict(data)
        if values.pop("schema_version", 1) not in (1, 2, 3, 4, 5, 6):
            raise ValueError("Unbekannte JSON-Schemaversion.")
        try:
            if "antenne" in values:
                values["antenne"] = Antenne(**values["antenne"])
            if "passiv" in values:
                values["passiv"] = PassivSettings(**values["passiv"])
            values["targets"] = tuple(Target(**t) for t in values.get("targets", []))
            if values.get("flugszene") is not None:
                szene = dict(values["flugszene"])
                bahnen = []
                for eintrag in szene["bahnen"]:
                    bahn = dict(eintrag)
                    if bahn.get("route") is not None:
                        route = dict(bahn["route"])
                        route["punkte"] = tuple(tuple(punkt) for punkt in route["punkte"])
                        bahn["route"] = GezeichneteRoute(**route)
                    bahnen.append(Flugbahn(**bahn))
                szene["bahnen"] = tuple(bahnen)
                if szene.get("radar_bahn") is not None:
                    szene["radar_bahn"] = Flugbahn(**szene["radar_bahn"])
                values["flugszene"] = Flugszene(**szene)
            config = cls(**values)
            validate_config(config)
            return config
        except (TypeError, KeyError) as exc:
            raise ValueError(f"Ungültiges Konfigurationsschema: {exc}") from exc


def validate_config(config: RadarConfig) -> list[str]:
    """Prüft VOR Array-Allokation; Fehler verhindern Aliasing und ungültige Näherungen.

    Rückgabe: verständliche Warnungen. Modellgrenzen: B/fc <= 0.1,
    Laufzeit <= ADC-Start (ohne Vorlauf: Laufzeit/T <= 0.025),
    Wanderung im Frame <= 0.25 nominelle Range-Zellen.
    Das sind konservative didaktische Grenzen, keine universellen Naturkonstanten.
    """
    c = config
    if c.radar_mode not in ("fmcw", "pulse_doppler", "passive"):
        raise ValueError("Unbekanntes Radarverfahren.")
    numeric = ("carrier_hz", "bandwidth_hz", "chirp_s", "repetition_s", "sample_rate_hz",
               "snr_db", "reference_range_m", "reference_rcs_m2", "pfa")
    for name in numeric:
        value = getattr(c, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name}: endliche Zahl erforderlich.")
    for name in ("chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples"):
        if type(getattr(c, name)) is not int:
            raise ValueError(f"{name}: ganze Zahl erforderlich.")
    if type(c.noise_enabled) is not bool or type(c.remove_static) is not bool:
        raise ValueError("Rausch- und Clutterschalter müssen boolesch sein.")
    if min(c.carrier_hz, c.bandwidth_hz, c.chirp_s, c.sample_rate_hz,
           c.reference_range_m, c.reference_rcs_m2) <= 0:
        raise ValueError("Frequenzen, Dauer und Amplitudenreferenzen müssen positiv sein.")
    if c.radar_mode != "passive" and c.repetition_s < c.chirp_s:
        raise ValueError("Das Wiederholintervall muss mindestens so lang wie der aktive Chirp sein.")
    if c.radar_mode == "pulse_doppler":
        if c.adc_skip_samples != 0:
            raise ValueError("Puls-Doppler: ADC-Vorlauf auf 0 setzen; der ADC erfasst ein ganzes Pulsintervall.")
        if c.pulse_samples < 8 or c.bandwidth_hz*c.chirp_s < 4:
            raise ValueError("LFM-Puls: mindestens 8 Abtastwerte und Zeit-Bandbreite-Produkt B·Tp ≥ 4 erforderlich.")
        if c.bandwidth_hz >= c.sample_rate_hz:
            raise ValueError("LFM-Puls: fs muss größer als die Basisband-Bandbreite B sein (plus Dopplerreserve).")
    pruefe_antenne(c.antenne)
    if not 0 <= c.adc_skip_samples <= 32768:
        raise ValueError("Der ADC-Vorlauf muss 0–32768 Samples betragen.")
    if c.bandwidth_hz / c.carrier_hz > 0.1:
        raise ValueError("B/fc > 10 %: Die Schmalband-Dopplernäherung ist hier nicht freigegeben.")
    count = c.sample_rate_hz * (c.repetition_s if c.radar_mode != "fmcw" else c.chirp_s) - c.adc_skip_samples
    if (not math.isfinite(count) or abs(count - round(count)) > 1e-6
            or not 32 <= round(count) <= 32768):
        raise ValueError("fs · Tr muss 32–32768 ganze ADC-Samples je Pulsintervall ergeben." if c.radar_mode == "pulse_doppler" else "fs · T minus ADC-Vorlauf muss 32–32768 ganze Samples ergeben.")
    if not 16 <= c.chirps <= 2048 or c.chirps * c.samples > MAX_CELLS:
        raise ValueError("16–2048 Chirps und höchstens 1.048.576 Samplezellen pro Frame erlaubt.")
    if not 0 <= c.seed < 2**32 or not -80 <= c.snr_db <= 100:
        raise ValueError("Seed muss in [0, 2³²) und SNR zwischen −80 und 100 dB liegen.")
    if c.window not in ("rect", "hann") or c.amplitude_model not in ("didactic", "radar"):
        raise ValueError("Unbekanntes Fenster oder Amplitudenmodell.")
    if min(c.training_range, c.training_doppler) < 1 or min(c.guard_range, c.guard_doppler) < 0:
        raise ValueError("CFAR: mindestens eine Trainingszelle pro Richtung, Schutzzellen ≥ 0.")
    if 2 * (c.training_range + c.guard_range) + 1 > c.range_bins or 2 * (c.training_doppler + c.guard_doppler) + 1 > c.chirps:
        raise ValueError("Das CFAR-Fenster passt nicht in die Range-Doppler-Map.")
    if not 1e-8 <= c.pfa <= 0.1:
        raise ValueError("Die nominelle CFAR-Pfa muss zwischen 10⁻⁸ und 0,1 liegen.")
    if len(c.targets) > 32:
        raise ValueError("Höchstens 32 punktförmige Ziele pro Szene erlaubt.")
    if c.radar_mode == "passive":
        from .passivradar import validate_passive
        return validate_passive(c)
    if c.flugszene is not None:
        if not isinstance(c.flugszene, Flugszene):
            raise ValueError("Die Flugbeschreibung muss eine Flugszene sein.")
        pruefe_flugszene(c.flugszene)
        if c.targets:
            raise ValueError("Entweder Flugbahnen oder feste Radar-Ziele verwenden; nicht beide gleichzeitig.")
        if c.flugszene.zeitschritt_s < c.chirps * c.repetition_s:
            raise ValueError("Der Flug-Zeitschritt muss mindestens der Dauer eines Radar-Messpakets entsprechen.")
        pruefe_fluggrenzen(c)
    warnings: list[str] = []
    for index, t in enumerate(c.targets, 1):
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
               for x in (t.range_m, t.velocity_mps, t.strength, t.phase_rad, t.antenna_gain)):
            raise ValueError(f"Ziel {index}: nur endliche Zahlen erlaubt.")
        if not 0 < t.range_m or not 0 < t.strength <= 1e6:
            raise ValueError(f"Ziel {index}: Entfernung > 0 und Stärke in (0, 10⁶] erforderlich.")
        if not 0 <= t.antenna_gain <= 1:
            raise ValueError("Der relative Einweg-Antennengewinn muss zwischen 0 und 1 liegen.")
        tau = 2 * t.range_m / C
        fd = 2 * t.velocity_mps / c.wavelength
        if abs(t.velocity_mps) >= c.max_velocity:
            raise ValueError(f"Ziel {index}: Doppler-Aliasing; |v| muss < {c.max_velocity:.3f} m/s sein.")
        if c.radar_mode == "pulse_doppler":
            if t.range_m < c.minimum_range_m:
                raise ValueError(f"Ziel {index}: Sende-Blindbereich; R muss ≥ c·Tp/2 = {c.minimum_range_m:.2f} m sein.")
            if c.bandwidth_hz/2 + abs(fd) >= c.sample_rate_hz/2:
                raise ValueError(f"Ziel {index}: Pulsbandbreite plus Doppler überschreitet ADC-Nyquist.")
        elif abs(c.slope * tau + fd) >= c.sample_rate_hz / 2:
            raise ValueError(f"Ziel {index}: Beat-Frequenz außerhalb ±fs/2 (Range-Doppler-Kopplung berücksichtigt).")
        if t.range_m > c.timing_range_limit * (1+1e-12):
            if c.radar_mode == "pulse_doppler":
                raise ValueError(f"Ziel {index}: Echo endet nach dem nächsten Puls; R muss ≤ c·(Tr−Tp)/2 sein. Keine Mehr-PRF-Entfaltung implementiert.")
            if c.adc_skip_samples:
                raise ValueError(f"Ziel {index}: Echo erreicht den ADC erst nach dem Aufnahmebeginn. ADC-Vorlauf erhöhen oder fs senken.")
            raise ValueError(f"Ziel {index}: Laufzeit > 2,5 % der Chirpdauer. Für größere Entfernungen ADC-Vorlauf einstellen.")
        migration = abs(t.velocity_mps) * c.chirps * c.repetition_s
        if migration > 0.25 * c.range_resolution:
            raise ValueError(f"Ziel {index}: Bewegung im Frame > ¼ Range-Zelle; eingefrorene Entfernung ungeeignet.")
        if t.range_m - migration <= 0:
            raise ValueError(f"Ziel {index}: Bewegung führt zu einer nicht positiven Entfernung.")
        if c.radar_mode == "fmcw" and abs(c.slope * tau + fd) > 0.95 * c.sample_rate_hz / 2:
            warnings.append(f"Ziel {index} liegt nahe der ADC-Nyquist-Grenze.")
    if c.remove_static:
        warnings.append("Mittelwertabzug unterdrückt stationäre und schwächt langsame Ziele; Rauschbins werden korreliert.")
    if c.window == "hann":
        warnings.append("Hann verbreitert Hauptkeulen (erste Nullstelle ca. 2 Bins); CFAR-Pfa ist wegen Korrelation nominell.")
    if c.radar_mode == "pulse_doppler":
        warnings.append("Puls-Doppler: LFM-Pulskompression, Empfang während Senden gesperrt. Entfernungszellen nach Filterung korreliert; CFAR-Pfa auch bei Rechteck nur nominell. Auflösung ≠ ADC-Binabstand.")
    if c.flugszene is not None and c.flugszene.radar_bahn is not None:
        warnings.append("Bewegtes monostatisches Radar: R und v sind relativ zur Plattform. Antennenausrichtung bleibt im Weltkoordinatensystem fest; kein Lage-/Cluttermodell.")
    if not c.noise_enabled:
        warnings.append("Ohne AWGN hat die CFAR-Pfa keine statistische Aussage; Fenster-Nebenkeulen bleiben im Spektrum vorhanden.")
    warnings.append("CFAR-Ränder werden nicht ausgewertet; Ziele dort können undetektiert bleiben.")
    return warnings


def pruefe_fluggrenzen(config: RadarConfig) -> None:
    """Prüft vorsichtige Grenzen für die GANZE Flugzeit statt nur einen Frame.

    Ein kurzes Radar-Messpaket verwendet weiterhin konstante Entfernung und
    radiale Geschwindigkeit. Diese Näherung darf auch beim Überflug nicht
    durch zu schnelle Bewegung oder zu starke Beschleunigung ungültig werden.
    """
    szene = config.flugszene
    if szene is None:
        return
    messdauer_s = config.chirps * config.repetition_s
    for nummer, bahn in enumerate(szene.bahnen, 1):
        grenzen = relative_bahngrenzen(bahn, szene)
        tempo_grenze = grenzen.tempo_max_mps
        entfernung_grenze = grenzen.entfernung_max_m
        # |v_radial| <= Flugtempo. Für die Entfernung verwenden wir ebenfalls
        # eine sichere obere Grenze, auch wenn x und Höhe ihr Maximum zu anderen Zeiten haben.
        pruefziel = Target(entfernung_grenze, tempo_grenze, bahn.staerke)
        if config.radar_mode == "pulse_doppler":
            if kleinster_abstand(bahn, szene) < config.minimum_range_m:
                raise ValueError("Die relative Flugbahn erreicht den Puls-Sendeblindbereich.")
        try:
            validate_config(replace(config, flugszene=None, targets=(pruefziel,)))
        except ValueError as exc:
            raise ValueError(f"Flugobjekt {nummer}, sichere Grenze der gesamten Bahn: {exc}") from exc
        # d(v_radial)/dt = (|v|² + Ort·Beschleunigung − v_radial²)/R.
        # R >= kleinste Höhe liefert eine konservative, leicht prüfbare Schranke.
        beschleunigung_grenze = grenzen.radialbeschleunigung_max_mps2
        if beschleunigung_grenze * messdauer_s > 0.25 * config.velocity_resolution:
            raise ValueError(f"Flugobjekt {nummer}: Die Geschwindigkeit ändert sich während eines Messpakets zu stark. "
                             "Weniger Chirps oder ein kürzeres Wiederholintervall wählen.")
