"""Radarwerte für ein geändertes Flugtempo nachvollziehbar anpassen.

Nur die GUI ruft diese Hilfe nach einer Speed-Eingabe auf. Der Rechenkern
validiert Konfigurationen weiterhin strikt und ändert keine Eingaben selbst.
"""

from dataclasses import replace
import math

from .config import C, RadarConfig, validate_config
from .flugbahn import relative_bahngrenzen, pruefe_flugszene


def passe_radar_an_tempo(config: RadarConfig) -> RadarConfig:
    """Verhindert Doppler-Aliasing und zu viel Bewegung im Messpaket.

    Eingaben in SI-Einheiten. Geometrie, Samplezahl und Rauschen bleiben gleich.
    Für längere Laufzeiten wird das ADC-Fenster nach hinten verschoben und die
    aktive Rampe entsprechend verlängert: Nskip >= fs*2Rmax/c, T=(Nskip+N)/fs.
    Zuerst Pause und Chirpzahl verkürzen; falls nötig Träger und Bandbreite
    senken. Das verändert die Auflösung und wird in der GUI sichtbar gemacht.
    Die abschließende Kernprüfung bleibt maßgeblich, auch bei extremen Eingaben.
    """
    try:
        validate_config(config)
        return config
    except ValueError:
        pass
    c = config
    if c.radar_mode != "fmcw":
        # Kein stilles Verwandeln eines Pulsprofils in eine FMCW-Rampe.
        # Bei zu hohem Relativtempo PRI/Träger/Messpaket bewusst einstellen.
        validate_config(c)
        return c
    if c.flugszene is not None:
        pruefe_flugszene(c.flugszene)  # Keine ungültige Geometrie kaschieren.
        grenzen = [relative_bahngrenzen(b, c.flugszene) for b in c.flugszene.bahnen]
        tempo = max(g.tempo_max_mps for g in grenzen)
        entfernung = max(g.entfernung_max_m for g in grenzen)
        beschleunigung = max(g.radialbeschleunigung_max_mps2 for g in grenzen)
    else:
        tempo = max((abs(t.velocity_mps) for t in c.targets), default=0.)
        entfernung = max((t.range_m for t in c.targets), default=1.)
        beschleunigung = 0.
    if entfernung > c.timing_range_limit:
        vorlauf = math.ceil(1.05*2*entfernung*c.sample_rate_hz/C)
        chirp = (vorlauf+c.samples)/c.sample_rate_hz
        c = replace(c, adc_skip_samples=vorlauf, chirp_s=chirp,
                    repetition_s=max(c.repetition_s, chirp))
    if tempo <= 0:
        validate_config(c)
        return c
    # Tr darf nie kürzer als die aktive Rampe werden.
    intervall = max(c.chirp_s, min(c.repetition_s, C/(4*c.carrier_hz*1.3*tempo)))
    rand = c.training_doppler + c.guard_doppler
    minimum = max(32, 4*rand + 4)  # Platz für CFAR neben bewegten Targets.
    anzahl = max(minimum, c.chirps)
    # v*M*Tr <= ΔR/4; a*(M*Tr)^2 <= λ/8 (¼ Doppler-Bin).
    anzahl = min(anzahl, max(minimum, math.floor(.9*c.range_resolution/(4*tempo*intervall))))
    if beschleunigung > 0:
        anzahl = min(anzahl, max(minimum, math.floor(
            math.sqrt(.9*C/(8*c.carrier_hz*beschleunigung))/intervall)))
    dauer = anzahl * intervall
    # Auch die Trainings-/Schutzzellen müssen innerhalb der Doppler-FFT liegen.
    anteil = .9 * (1 - 2*(rand+2)/anzahl)
    traeger = min(c.carrier_hz, anteil*C/(4*intervall*tempo),
                  .1*C*c.sample_rate_hz/(4*tempo))
    if beschleunigung > 0:
        traeger = min(traeger, .9*C/(8*beschleunigung*dauer**2))
    # Schmalband, Range-Wanderung und |S*2R/c+2v*fc/c| < fs/2.
    bandbreite = min(c.bandwidth_hz, .099*traeger,
                    .9*C*c.chirp_s/(8*tempo*dauer*c.adc_duration_s),
                    (.9*C*c.sample_rate_hz/4 - traeger*tempo)*c.chirp_s/entfernung)
    angepasst = replace(c, repetition_s=intervall, chirps=anzahl,
                       carrier_hz=traeger, bandwidth_hz=bandbreite)
    validate_config(angepasst)
    return angepasst
