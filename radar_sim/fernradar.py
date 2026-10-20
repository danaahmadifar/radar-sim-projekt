"""Fernbereich ohne Reichweitenversprechen: gleiche fc/B/fs/PRI für den Vergleich."""

from dataclasses import replace
from .config import RadarConfig
from .flugbahn import Flugbahn, Flugszene
from .antenne import Antenne


def fernszene() -> Flugszene:
    return Flugszene("Fernbereich · Flugzeug bei 300 km", (Flugbahn(-300000, 10000, 50, staerke=10),), 60, 1.)


def fern_config(modus: str = "pulse_doppler") -> RadarConfig:
    """300 MHz, 100 kHz Hub, 500 kSamples/s, PRI 3 ms, 64 Wiederholungen.

    Puls: Tp=50 µs, gesamte B nutzbar. FMCW: T=2,9 ms, ADC-Start 2,1 ms,
    nur die letzten 0,8 ms beobachtet. Beide können 300 km messen; FMCW verliert
    hier beobachtete Bandbreite. Das beweist keine universelle Puls-Überlegenheit.
    Relative Amplitude beider Profile hat dieselbe 100-km-/10-m²-Referenz.
    """
    c = RadarConfig(carrier_hz=300e6, bandwidth_hz=100e3, sample_rate_hz=500e3,
                    chirp_s=50e-6, repetition_s=.003, chirps=64, targets=(),
                    flugszene=fernszene(), radar_mode="pulse_doppler", snr_db=20,
                    amplitude_model="radar", reference_range_m=100000, reference_rcs_m2=10,
                    pfa=1e-6, antenne=Antenne(typ="faecher", elevation_grad=2,
                                            breite_az_grad=12, breite_el_grad=12, zeichenlaenge_m=300000))
    return replace(c, radar_mode="fmcw", chirp_s=.0029, adc_skip_samples=1050) if modus == "fmcw" else c
