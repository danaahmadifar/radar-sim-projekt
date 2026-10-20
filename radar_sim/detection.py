"""2D-CA-CFAR in linearer Leistung; keine Radar-Blackbox."""

from dataclasses import dataclass
import math
import numpy as np
from numpy.typing import NDArray

from .config import C, RadarConfig
from .processing import Spectrum


@dataclass
class CFARResult:
    """mask: erkannte Zellen; threshold: lineare Schwelle; valid: geprüfte Zellen."""
    mask: NDArray[np.bool_]
    threshold: NDArray[np.float64]  # NaN außerhalb vollständig trainierbarer CUTs
    valid: NDArray[np.bool_]
    training_cells: int
    alpha: float


@dataclass
class Candidate:
    """Mögliches Objekt: korrigierte Entfernung, radiale Geschwindigkeit,
    Scheinentfernung, lineare Leistung und Schwelle sowie Lage und Größe der Zellgruppe.
    """
    range_m: float
    velocity_mps: float
    apparent_range_m: float
    power: float
    threshold: float
    doppler_bin: int
    range_bin: int
    cells: int


def _rechteck_summen(leistung: NDArray[np.float64], halbe_hoehe: int, halbe_breite: int) -> NDArray[np.float64]:
    """Summiert alle vollständig im Bild liegenden Rechtecke ohne langsame Zellschleife.

    Ein Summenbild enthält an jeder Stelle die Summe links oberhalb dieser Stelle.
    Vier seiner Werte reichen deshalb für die Summe eines beliebigen Rechtecks:
    rechts unten − links unten − rechts oben + links oben.
    Eine zusätzliche Nullzeile und Nullspalte vereinfachen die Bildränder.
    """
    summenbild = np.pad(leistung, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    hoehe = 2 * halbe_hoehe + 1
    breite = 2 * halbe_breite + 1
    return (summenbild[hoehe:, breite:] - summenbild[:-hoehe, breite:]
            - summenbild[hoehe:, :-breite] + summenbild[:-hoehe, :-breite])


def ca_cfar(power: NDArray[np.float64], config: RadarConfig) -> CFARResult:
    """Erkennt helle Zellen, die deutlich über ihrer Umgebung liegen.

    Eingang power: Leistungstabelle [Geschwindigkeitszellen, Entfernungszellen].
    Die direkte Umgebung ist ein Schutzbereich. Ein größerer Ring schätzt den
    Rauschpegel. Schwelle = Ringmittelwert * alpha.
    alpha = N * (Pfa**(-1/N) - 1), N = tatsächliche Zahl der Ringzellen.
    Nur LINEARE Leistungen einsetzen, niemals die dB-Darstellung!

    Die Formel setzt unabhängige Rauschleistungen voraus. Mit Hann oder
    statischer Unterdrückung sind Nachbarzellen abhängig; Pfa ist dann nur ein
    Richtwert. Am Rand wird ohne vollständigen Ring gar nicht geprüft.
    """
    halbe_hoehe = config.training_doppler + config.guard_doppler
    halbe_breite = config.training_range + config.guard_range
    if power.ndim != 2 or min(power.shape[0] - 2 * halbe_hoehe, power.shape[1] - 2 * halbe_breite) <= 0:
        raise ValueError("Das Leistungsbild ist zu klein für den gewählten CFAR-Ring.")
    if not np.all(np.isfinite(power)) or np.any(power < 0):
        raise ValueError("CFAR benötigt endliche, nichtnegative lineare Leistungen.")
    aussen_summe = _rechteck_summen(power, halbe_hoehe, halbe_breite)
    schutz_summe = _rechteck_summen(power, config.guard_doppler, config.guard_range)
    # Beide Summen müssen dieselben Mittelpunkte beschreiben. Der kleinere
    # Schutzbereich passt häufiger ins Bild; seine zusätzlichen Ränder abschneiden.
    schutz_summe = schutz_summe[config.training_doppler:schutz_summe.shape[0] - config.training_doppler,
                               config.training_range:schutz_summe.shape[1] - config.training_range]
    anzahl_ringzellen = config.training_cells
    alpha = anzahl_ringzellen * math.expm1(-math.log(config.pfa) / anzahl_ringzellen)
    # expm1(x) berechnet exp(x)-1 genauer, wenn x klein ist.
    schwelle = np.full(power.shape, np.nan)
    gueltig = np.zeros(power.shape, dtype=bool)
    innenbereich = (slice(halbe_hoehe, power.shape[0] - halbe_hoehe),
                    slice(halbe_breite, power.shape[1] - halbe_breite))
    rauschmittel = (aussen_summe - schutz_summe) / anzahl_ringzellen
    # Ohne Rauschen dürfen Rundungsreste keine praktisch unendlich kleine Schwelle erzeugen.
    kleinste_leistung = max(float(power.max()) * 1e-14, np.finfo(float).tiny)
    schwelle[innenbereich] = alpha * np.maximum(rauschmittel, kleinste_leistung)
    gueltig[innenbereich] = True
    erkannt = (power > schwelle) & gueltig
    return CFARResult(erkannt, schwelle, gueltig, anzahl_ringzellen, alpha)


def lokale_maxima(leistung: NDArray[np.float64]) -> NDArray[np.bool_]:
    """Prüft jede Zelle gegen ALLE acht Nachbarn im vollständigen Leistungsbild.

    CFAR allein sagt nur: größer als die geschätzte Hintergrundschwelle.
    Auch eine Flanke kann diese Schwelle überschreiten, ohne ein Peak zu sein.
    Deshalb dürfen wir Nachbarn nicht auf die CFAR-Treffermaske beschränken.
    Ein gleich hohes Nachbarfeld ist erlaubt (Peak genau zwischen FFT-Zellen).
    Ein vollständig flaches Feld ist kein Maximum. Bildränder werden nicht
    umgefaltet; CFAR wertet sie ohnehin nicht als vollständige Trainingsfenster aus.
    """
    if leistung.ndim != 2 or 0 in leistung.shape:
        raise ValueError("Die Peak-Prüfung braucht eine zweidimensionale Leistungstabelle.")
    hoehe, breite = leistung.shape
    # Randwerte fortsetzen: Ein vollkommen flaches positives Bild darf auch
    # an der Bildkante nicht künstlich zum Maximum werden.
    randbild = np.pad(leistung, 1, mode="edge")
    nicht_kleiner = np.ones(leistung.shape, dtype=bool)
    mindestens_ein_kleinerer_nachbar = np.zeros(leistung.shape, dtype=bool)
    for zeilenabstand in (-1, 0, 1):
        for spaltenabstand in (-1, 0, 1):
            if zeilenabstand == 0 and spaltenabstand == 0:
                continue
            nachbar = randbild[1 + zeilenabstand:1 + zeilenabstand + hoehe,
                               1 + spaltenabstand:1 + spaltenabstand + breite]
            nicht_kleiner &= leistung >= nachbar
            mindestens_ein_kleinerer_nachbar |= leistung > nachbar
    return nicht_kleiner & mindestens_ein_kleinerer_nachbar & (leistung > 0)


def group_candidates(spectrum: Spectrum, cfar: CFARResult, config: RadarConfig) -> list[Candidate]:
    """Fasst zusammenhängende Treffer zu möglichen Objekten zusammen.

    Nachbarn dürfen seitlich, ober-/unterhalb oder diagonal liegen (8 Nachbarn).
    Pro Gruppe bleibt das stärkste echte lokale Maximum des Leistungsbildes.
    Gruppen ohne lokales Maximum werden verworfen. Ein bloßer CFAR-Treffer auf
    einer Spektralflanke ist noch kein Objekt. Das Verfahren kennt keine Sollwerte.
    Die Entfernung wird korrigiert: R = c*(Mischfrequenz−Dopplerfrequenz)/(2S).
    Beim LFM-Puls ist stattdessen Rapp die gemessene Laufzeitentfernung;
    die näherungsweise Kompressionsverschiebung c*fd/(2S) wird abgezogen.
    Eng benachbarte Objekte können in derselben Gruppe landen.
    """
    peak_zellen = lokale_maxima(spectrum.power) & cfar.mask
    offene_zellen = {(int(zeile), int(spalte)) for zeile, spalte in np.argwhere(cfar.mask)}
    kandidaten: list[Candidate] = []
    while offene_zellen:
        startzelle = offene_zellen.pop()
        noch_zu_pruefen = [startzelle]
        staerkste_zelle = None
        anzahl = 0
        while noch_zu_pruefen:
            zeile, spalte = noch_zu_pruefen.pop()
            anzahl += 1
            if peak_zellen[zeile, spalte] and (staerkste_zelle is None
                    or spectrum.power[zeile, spalte] > spectrum.power[staerkste_zelle]):
                staerkste_zelle = (zeile, spalte)
            for zeilenabstand in (-1, 0, 1):
                for spaltenabstand in (-1, 0, 1):
                    nachbar = (zeile + zeilenabstand, spalte + spaltenabstand)
                    if nachbar in offene_zellen:
                        offene_zellen.remove(nachbar)
                        noch_zu_pruefen.append(nachbar)
        if staerkste_zelle is None:
            continue
        zeile, spalte = staerkste_zelle
        if config.radar_mode == "passive":
            entfernung = spectrum.apparent_range_m[spalte]
        elif config.radar_mode == "pulse_doppler":
            entfernung = spectrum.apparent_range_m[spalte] - C*spectrum.doppler_hz[zeile]/(2*config.slope)
        else:
            entfernung = C * (spectrum.beat_hz[spalte] - spectrum.doppler_hz[zeile]) / (2 * config.slope)
        if entfernung > 0:
            kandidaten.append(Candidate(float(entfernung), float(spectrum.velocity_mps[zeile]),
                                        float(spectrum.apparent_range_m[spalte]), float(spectrum.power[zeile, spalte]),
                                        float(cfar.threshold[zeile, spalte]), zeile, spalte, anzahl))
    # Begrenzung betrifft nur Tabelle/CSV. Die vollständige Trefferkarte bleibt erhalten.
    return sorted(kandidaten, key=lambda k: (-k.power, k.doppler_bin, k.range_bin))[:256]
