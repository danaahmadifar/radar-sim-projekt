"""Transparenter Soll-Ist-Vergleich; Zuordnung gehört nicht zum Detektor."""

from dataclasses import dataclass
from .config import C, RadarConfig
from .detection import Candidate


@dataclass
class Match:
    target_index: int
    candidate_index: int
    range_error_m: float
    velocity_error_mps: float


def schaetztoleranzen(config: RadarConfig) -> tuple[float, float]:
    """FFT-Peak ohne Interpolation: Toleranzen in m und m/s.

    Je Achse höchstens ein halber Bin. Bei der korrigierten Entfernung kommt
    der Fehler der Dopplerfrequenz hinzu: ΔR/2 + c/(4*S*M*Tr).
    Die getrennte Zuordnung nutzt weiterhin ihr größeres Suchfenster.
    """
    if config.radar_mode == "passive":
        return config.range_bin_m/2, config.velocity_resolution/2
    return ((config.range_bin_m if config.radar_mode == "pulse_doppler" else config.range_resolution)/2 + C/(4*config.slope*config.chirps*config.repetition_s),
            config.velocity_resolution/2)


def match_targets(config: RadarConfig, candidates: list[Candidate]) -> list[Match]:
    """Vergleicht bekannte Ziele mit den erkannten möglichen Objekten.

    Zuerst nahe Paare suchen: Abstand höchstens 1,5 Auflösungszellen pro Achse.
    Dann das nächste noch freie Paar wählen. Jeder Sollwert und jede Erkennung
    dürfen nur einmal vorkommen. Das ist ein einfacher Vergleich, kein Tracking.
    Bei überlappenden Zielen kann die Zuordnung mehrdeutig sein.
    """
    moegliche_paare = []
    for ziel_nummer, ziel in enumerate(config.targets):
        for kandidat_nummer, kandidat in enumerate(candidates):
            entfernungsfehler = kandidat.range_m - ziel.range_m
            geschwindigkeitsfehler = kandidat.velocity_mps - ziel.velocity_mps
            if (abs(entfernungsfehler) <= 1.5 * config.range_resolution
                    and abs(geschwindigkeitsfehler) <= 1.5 * config.velocity_resolution):
                # Meter und m/s lassen sich nicht direkt addieren. Zuerst durch
                # die jeweilige Auflösung teilen: Dann vergleichen wir Zellabstände.
                abstand = ((entfernungsfehler / config.range_resolution)**2
                           + (geschwindigkeitsfehler / config.velocity_resolution)**2)
                moegliche_paare.append((abstand, ziel_nummer, kandidat_nummer,
                                       entfernungsfehler, geschwindigkeitsfehler))
    verwendete_ziele: set[int] = set()
    verwendete_kandidaten: set[int] = set()
    zuordnungen = []
    for _, ziel_nummer, kandidat_nummer, entfernungsfehler, geschwindigkeitsfehler in sorted(moegliche_paare):
        if ziel_nummer not in verwendete_ziele and kandidat_nummer not in verwendete_kandidaten:
            zuordnungen.append(Match(ziel_nummer, kandidat_nummer, entfernungsfehler, geschwindigkeitsfehler))
            verwendete_ziele.add(ziel_nummer)
            verwendete_kandidaten.add(kandidat_nummer)
    return sorted(zuordnungen, key=lambda paar: paar.target_index)
