"""Abhängige Radar-Grenzen als reine Python-Rechnung, ohne GUI.

Jeder Bereich beschreibt EINE veränderliche Größe bei festgehaltenen übrigen
Eingaben. Gemeinsame Abhängigkeiten bleiben sichtbar. Die Gesamtprüfung in
validate_config entscheidet weiterhin, ob eine ganze Konfiguration gültig ist.
"""

from dataclasses import dataclass, replace
import math

from .config import C, MAX_CELLS, RadarConfig, Target, validate_config
from .flugbahn import relative_bahngrenzen


@dataclass(frozen=True)
class ParameterBereich:
    minimum: float
    maximum: float
    schritt: float = 0.0  # 0: kontinuierlich; sonst Raster mit Ursprung 0
    hinweis: str = ""
    null_erlaubt: bool = False  # optionaler alter Lehrmodus ohne ADC-Vorlauf

    @property
    def leer(self) -> bool:
        return self.minimum > self.maximum or not math.isfinite(self.minimum + self.maximum)

    def im_raster(self) -> "ParameterBereich":
        if self.leer or not self.schritt:
            return self
        unten = math.ceil(self.minimum / self.schritt - 1e-9)
        oben = math.floor(self.maximum / self.schritt + 1e-9)
        return ParameterBereich(unten * self.schritt, oben * self.schritt, self.schritt, self.hinweis, self.null_erlaubt)

    def begrenze_wert(self, wert: float) -> float:
        if self.null_erlaubt and wert == 0:
            return 0.0
        if self.leer:
            raise ValueError("Für diese Größe ist bei den übrigen Eingaben kein Wert möglich.")
        if self.schritt:
            wert = round(wert / self.schritt) * self.schritt
        return min(self.maximum, max(self.minimum, wert))

    def skaliert(self, faktor: float) -> "ParameterBereich":
        return ParameterBereich(self.minimum / faktor, self.maximum / faktor,
                                 self.schritt / faktor, self.hinweis, self.null_erlaubt)


GRUND_BEREICHE = {
    "carrier_hz": (1e6, 300e9), "bandwidth_hz": (1, 10e9),
    "chirp_s": (1e-6, 0.01), "repetition_s": (1e-6, 0.1),
    "sample_rate_hz": (1e4, 100e6), "chirps": (16, 2048),
    "snr_db": (-80, 100), "seed": (0, 2**32 - 1),
    "reference_range_m": (0.01, 10000000), "reference_rcs_m2": (0.001, 100000),
    "training_range": (1, 128), "training_doppler": (1, 128),
    "guard_range": (0, 128), "guard_doppler": (0, 128), "pfa": (1e-8, 0.1),
    "adc_skip_samples": (0, 32768),
}


def _strikt_unter(wert: float) -> float:
    return wert - max(abs(wert) * 1e-9, 1e-15)


def _strikt_ueber(wert: float) -> float:
    return wert + max(abs(wert) * 1e-9, 1e-15)


def _pulsbereiche(config: RadarConfig) -> dict[str, ParameterBereich]:
    """Gültiges Intervall um den aktuellen Puls- oder Passivwert.

    Die zentrale physikalische Prüfung entscheidet auch hier. Nur ein Feld
    ändern, an beiden Seiten halbieren, dann das Abtastraster berücksichtigen.
    Keine Arrays oder Frames werden dafür erzeugt. Eine ungültige Ausgangs-
    kombination muss zuerst korrigiert werden; dann gilt nur der Grundbereich.
    """
    c = config
    if min(c.sample_rate_hz, c.repetition_s) <= 0:
        raise ValueError("Abtastrate und Wiederholintervall müssen positiv sein.")
    try:
        validate_config(c)
        gueltig = True
    except ValueError:
        gueltig = False
    ergebnis = {}
    ganze = {"chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples"}
    for name, (unten, oben) in GRUND_BEREICHE.items():
        schritt = 1. if name in ganze else (1/c.sample_rate_hz if name == "repetition_s" else 1/c.repetition_s if name == "sample_rate_hz" else 0.)
        if name == "adc_skip_samples":
            hinweis = ("Passivempfang startet ohne ADC-Vorlauf." if c.radar_mode == "passive"
                       else "Pulsmodus erfasst ein ganzes PRI; Sendezeit wird gesperrt.")
            ergebnis[name] = ParameterBereich(0, 0, 1, hinweis)
            continue
        wert = getattr(c, name)
        def passt(x):
            x = round(x/schritt)*schritt if schritt else x
            x = round(x) if name in ganze else x
            try:
                validate_config(replace(c, **{name: x}))
                return True
            except ValueError:
                return False
        if gueltig:
            for seite, ende in enumerate((unten, oben)):
                if passt(ende):
                    grenze = ende
                else:
                    gut, schlecht = wert, ende
                    for _ in range(38):
                        mitte = (gut+schlecht)/2
                        if passt(mitte):
                            gut = mitte
                        else:
                            schlecht = mitte
                    grenze = gut
                if seite == 0:
                    unten = grenze
                else:
                    oben = grenze
        ergebnis[name] = ParameterBereich(unten, oben, schritt,
            "Gültiges Intervall bei übrigen festen Werten; Signalmodell, Laufzeit, Doppler, Sampling und Speicher.").im_raster()
    return ergebnis


def berechne_parameterbereiche(config: RadarConfig) -> dict[str, ParameterBereich]:
    """Grenzen aus Sampling, Timing, Doppler, Bewegung, Speicher und CFAR.

    S=B/T, |2SR/c + 2v*fc/c| < fs/2, |v| < c/(4fcTr),
    |v|MTr <= c/(8*S*Tadc), a(MTr)² <= c/(8fc), N=fs*T−Nskip ganzzahlig.
    Flugbahnen verwenden dieselben vorsichtigen Schranken wie die Kernprüfung.
    """
    c = config
    if c.radar_mode != "fmcw":
        return _pulsbereiche(c)
    grenzen = {name: list(werte) for name, werte in GRUND_BEREICHE.items()}
    erklaerung = {
        "carrier_hz": "Schmalbandmodell, Doppler und Beat-Abtastung",
        "bandwidth_hz": "Trägerfrequenz, Beat-Abtastung und Bewegung je Messpaket",
        "chirp_s": "Laufzeit, Abtastung, ganze Samples und Wiederholintervall",
        "repetition_s": "Aktiver Chirp, Doppler, Bewegung und Flug-Zeitschritt",
        "sample_rate_hz": "Beat-Abtastung, ganze Samples, CFAR-Breite und Speicher",
        "chirps": "Speicher, CFAR-Höhe, Bewegung und Flug-Zeitschritt",
    }

    def unten(name: str, wert: float) -> None:
        grenzen[name][0] = max(grenzen[name][0], wert)

    def oben(name: str, wert: float) -> None:
        grenzen[name][1] = min(grenzen[name][1], wert)

    def linear(name: str, faktor: float, versatz: float, betrag: float) -> None:
        # Löse |faktor*Parameter + versatz| < betrag nach dem Parameter auf.
        if faktor == 0:
            if abs(versatz) >= betrag:
                grenzen[name] = [1.0, 0.0]
            return
        a = (-betrag - versatz) / faktor
        b = (betrag - versatz) / faktor
        unten(name, _strikt_ueber(min(a, b)))
        oben(name, _strikt_unter(max(a, b)))

    if min(c.chirp_s, c.repetition_s, c.sample_rate_hz, c.carrier_hz, c.bandwidth_hz, c.chirps) <= 0:
        raise ValueError("Positive Radar-Größen nötig, um ihre Bereiche zu berechnen.")
    anzahl_samples = c.samples
    vorlauf = c.adc_skip_samples
    anteil = max(1e-15, c.adc_duration_s / c.chirp_s)
    kleinste_samplezahl = max(32, 2 * (c.training_range + c.guard_range) + 1)
    groesste_samplezahl = min(32768, MAX_CELLS // c.chirps)
    unten("chirp_s", (kleinste_samplezahl + vorlauf) / c.sample_rate_hz)
    oben("chirp_s", (groesste_samplezahl + vorlauf) / c.sample_rate_hz)
    oben("chirp_s", c.repetition_s)
    unten("repetition_s", c.chirp_s)
    unten("sample_rate_hz", (kleinste_samplezahl + vorlauf) / c.chirp_s)
    oben("sample_rate_hz", (groesste_samplezahl + vorlauf) / c.chirp_s)
    unten("adc_skip_samples", c.sample_rate_hz*c.chirp_s-groesste_samplezahl)
    oben("adc_skip_samples", c.sample_rate_hz*c.chirp_s-kleinste_samplezahl)
    unten("chirps", 2 * (c.training_doppler + c.guard_doppler) + 1)
    oben("chirps", MAX_CELLS // max(1, anzahl_samples))
    unten("carrier_hz", 10 * c.bandwidth_hz)
    oben("bandwidth_hz", 0.1 * c.carrier_hz)
    oben("training_range", (anzahl_samples - 1) // 2 - c.guard_range)
    oben("guard_range", (anzahl_samples - 1) // 2 - c.training_range)
    oben("training_doppler", (c.chirps - 1) // 2 - c.guard_doppler)
    oben("guard_doppler", (c.chirps - 1) // 2 - c.training_doppler)

    ziele = list(c.targets)
    beschleunigung = 0.0
    if c.flugszene is not None:
        for bahn in c.flugszene.bahnen:
            g = relative_bahngrenzen(bahn, c.flugszene)
            ziele.append(Target(g.entfernung_max_m, g.tempo_max_mps, bahn.staerke))
            beschleunigung = max(beschleunigung, g.radialbeschleunigung_max_mps2)
        oben("chirps", c.flugszene.zeitschritt_s / c.repetition_s)
        oben("repetition_s", c.flugszene.zeitschritt_s / c.chirps)
    for ziel in ziele:
        r, v = ziel.range_m, ziel.velocity_mps
        tempo = abs(v)
        if r <= 0:
            raise ValueError("Für die Bereiche werden positive Zielentfernungen benötigt.")
        unten("bandwidth_hz", _strikt_ueber(c.chirp_s * (-C * c.sample_rate_hz / 4 - v * c.carrier_hz) / r))
        # Die obere Beat-Grenze ist ebenfalls strikt.
        oben("bandwidth_hz", _strikt_unter(c.chirp_s * (C * c.sample_rate_hz / 4 - v * c.carrier_hz) / r))
        linear("carrier_hz", v, c.slope * r, C * c.sample_rate_hz / 4)
        unten("sample_rate_hz", _strikt_ueber(4 * abs(c.slope * r + v * c.carrier_hz) / C))
        if vorlauf:
            oben("sample_rate_hz", vorlauf*C/(2*r))
        else:
            unten("chirp_s", 80 * r / C)
        unten("adc_skip_samples", 2*r*c.sample_rate_hz/C)
        fd = 2 * v * c.carrier_hz / C
        if c.sample_rate_hz / 2 - fd <= 0:
            grenzen["chirp_s"] = [1.0, 0.0]
        else:
            unten("chirp_s", _strikt_ueber((2 * c.bandwidth_hz * r / C) / (c.sample_rate_hz / 2 - fd)))
        if -c.sample_rate_hz / 2 - fd > 0:
            oben("chirp_s", _strikt_unter((2 * c.bandwidth_hz * r / C) / (-c.sample_rate_hz / 2 - fd)))
        if tempo:
            oben("carrier_hz", _strikt_unter(C / (4 * tempo * c.repetition_s)))
            oben("repetition_s", _strikt_unter(C / (4 * tempo * c.carrier_hz)))
            oben("bandwidth_hz", _strikt_unter(C / (8 * anteil * tempo * c.chirps * c.repetition_s)))
            oben("chirps", _strikt_unter(C / (8 * anteil * c.bandwidth_hz * tempo * c.repetition_s)))
            oben("chirps", _strikt_unter(r / (tempo * c.repetition_s)))
            oben("repetition_s", _strikt_unter(C / (8 * anteil * c.bandwidth_hz * tempo * c.chirps)))
            oben("repetition_s", _strikt_unter(r / (tempo * c.chirps)))
            maximaler_anteil = C/(8*c.bandwidth_hz*tempo*c.chirps*c.repetition_s)
            if maximaler_anteil < 1:
                oben("chirp_s", (vorlauf/c.sample_rate_hz)/(1-maximaler_anteil))
                oben("sample_rate_hz", vorlauf/(c.chirp_s*(1-maximaler_anteil)))
                unten("adc_skip_samples", c.sample_rate_hz*c.chirp_s*(1-maximaler_anteil))
    if beschleunigung:
        oben("carrier_hz", _strikt_unter(C / (8 * beschleunigung * (c.chirps * c.repetition_s)**2)))
        messdauer_max = math.sqrt(C / (8 * c.carrier_hz * beschleunigung))
        oben("chirps", _strikt_unter(messdauer_max / c.repetition_s))
        oben("repetition_s", _strikt_unter(messdauer_max / c.chirps))

    ergebnis = {}
    ganze_zahlen = ("chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples")
    for name, (minimum, maximum) in grenzen.items():
        schritt = 1.0 if name in ganze_zahlen else 0.0
        if name == "chirp_s":
            schritt = 1 / c.sample_rate_hz
        elif name == "sample_rate_hz":
            schritt = 1 / c.chirp_s
        ergebnis[name] = ParameterBereich(minimum, maximum, schritt,
                                          erklaerung.get(name, "Einstellbereich dieser Größe")).im_raster()
    # Null ist ein separater, rückwärtskompatibler Nahbereichsmodus.
    try:
        validate_config(replace(c, adc_skip_samples=0))
        b = ergebnis["adc_skip_samples"]
        ergebnis["adc_skip_samples"] = (ParameterBereich(0, 0, 1, "Nur Nahmodell ohne ADC-Vorlauf möglich")
                                         if b.leer else replace(b, null_erlaubt=True))
    except ValueError:
        pass
    return ergebnis


def bereich_fuer_tabellenwert(config: RadarConfig, flug: bool, nummer: int, spalte: int) -> ParameterBereich:
    """Sicherer Einzelwert-Bereich einer Objekt- oder Flugtabellenzelle.

    Die Bahnparameter haben gemeinsam kompliziertere Grenzen. Statt diese ein
    zweites Mal herzuleiten, benutzen wir die Kernprüfung und suchen die beiden
    Grenzen des gültigen Intervalls durch Halbieren. Das geschieht nur beim
    Öffnen des Dialogs, niemals während einer FFT oder eines Radar-Frames.
    """
    if flug:
        namen = ("start_x_m", "start_hoehe_m", "geschwindigkeit_x_mps",
                 "geschwindigkeit_hoehe_mps", "beschleunigung_hoehe_mps2", "staerke", "start_y_m", "geschwindigkeit_y_mps")
        grundgrenzen = ((-1e7, 1e7), (0.01, 1e6), (-300, 300), (-100, 100), (-20, 20), (1e-6, 1e6), (-1e7, 1e7), (-300, 300))
        radarzeile = config.flugszene.radar_bahn is not None and nummer == len(config.flugszene.bahnen)
        original = config.flugszene.radar_bahn if radarzeile else config.flugszene.bahnen[nummer]
    else:
        namen = ("range_m", "velocity_mps", "strength", "phase_rad")
        grundgrenzen = ((0.01, 1e7), (-300, 300), (1e-6, 1e6), (-math.pi, math.pi))
        original = config.targets[nummer]
    unten, oben = grundgrenzen[spalte]
    aktuell = getattr(original, namen[spalte])
    unten, oben = min(unten, aktuell), max(oben, aktuell)

    def gueltig(wert: float) -> bool:
        objekt = replace(original, **{namen[spalte]: wert})
        if flug:
            if radarzeile:
                probe = replace(config, flugszene=replace(config.flugszene, radar_bahn=objekt))
            else:
                bahnen = list(config.flugszene.bahnen)
                bahnen[nummer] = objekt
                probe = replace(config, flugszene=replace(config.flugszene, bahnen=tuple(bahnen)))
        else:
            ziele = list(config.targets)
            ziele[nummer] = objekt
            probe = replace(config, targets=tuple(ziele))
        try:
            validate_config(probe)
            return True
        except ValueError:
            return False

    mitte = aktuell
    if not gueltig(mitte):
        moegliche = [unten + (oben - unten) * i / 128 for i in range(129)]
        passende = [wert for wert in moegliche if gueltig(wert)]
        if not passende:
            return ParameterBereich(1, 0, hinweis="Andere Eingaben zuerst korrigieren; keine passende Probe gefunden")
        mitte = min(passende, key=lambda wert: abs(wert - aktuell))
    if not gueltig(unten):
        falsch, richtig = unten, mitte
        for _ in range(42):
            probe = (falsch + richtig) / 2
            if gueltig(probe):
                richtig = probe
            else:
                falsch = probe
        unten = _strikt_ueber(richtig)
    if not gueltig(oben):
        richtig, falsch = mitte, oben
        for _ in range(42):
            probe = (richtig + falsch) / 2
            if gueltig(probe):
                richtig = probe
            else:
                falsch = probe
        oben = _strikt_unter(richtig)
    return ParameterBereich(unten, oben, hinweis="Gültiges Intervall für diese Zelle bei unveränderten übrigen Eingaben")
