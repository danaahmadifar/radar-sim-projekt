"""Explizite NumPy-FFTs: Achse 1 = Entfernung, Achse 0 = Doppler."""

from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray

from .config import C, RadarConfig


@dataclass
class Spectrum:
    """FFT-Ergebnisse: power=Leistung, beat_hz=Mischfrequenzen,
    doppler_hz=Dopplerfrequenzen, apparent_range_m=Scheinentfernung,
    velocity_mps=radiale Geschwindigkeit. Frequenz- und Ortsachsen sind 1D-Vektoren.
    Passiv BETA: apparent_range_m ist ΔL, velocity_mps ist dΔL/dt;
    beat_hz ist wie beim Pulsradar None. Die CAF hat keine Beat-Frequenzachse.
    """
    power: NDArray[np.float64]  # [Doppler-Bin, Range-Bin], |FFT|², Aref²=1
    range_power: NDArray[np.float64]  # Mittel über Chirps, vor Doppler-Fenster
    beat_hz: NDArray[np.float64] | None  # Pulsradar hat keine FMCW-Beat-Frequenzachse.
    doppler_hz: NDArray[np.float64]
    apparent_range_m: NDArray[np.float64]
    velocity_mps: NDArray[np.float64]


def window_values(size: int, kind: str) -> NDArray[np.float64]:
    """Fenster schwächen die Ränder des Signals ab und verringern Nebenkeulen.

    Rechteck: jeder Wert ist 1. Hann: w[n]=0.5−0.5cos(2πn/N).
    """
    if kind == "rect":
        return np.ones(size)
    if kind == "hann":
        sample_nummern = np.arange(size)
        return 0.5 - 0.5 * np.cos(2 * np.pi * sample_nummern / size)
    raise ValueError("Als Fenster sind nur Rechteck und Hann erlaubt.")


def power_db(power: NDArray[np.float64]) -> NDArray[np.float64]:
    """10log10(P/1), mindestens −160 dB. Referenz: Einheitsamplitude binzentriert."""
    return 10 * np.log10(np.maximum(power, 1e-16))


def unterdruecke_null_doppler(signal: NDArray[np.complex128]) -> NDArray[np.complex128]:
    """Mittelwert über Achse 0 entfernen, konstante Echos exakt auslöschen.

    Erst die erste Zeile abziehen, dann den Mittelwert der Differenzen.
    Mathematisch identisch zu signal−mean(signal); ein identisches Echo über
    alle Chirps/Pulse erzeugt so keine winzigen Rundungsreste und Scheintreffer.
    """
    differenz = signal-signal[:1]
    return differenz-differenz.mean(axis=0, keepdims=True)


def process_beat(beat: NDArray[np.complex128], config: RadarConfig) -> Spectrum:
    """Aus dem Mischsignal Entfernung und Geschwindigkeit sichtbar machen.

    Eingang: [Chirps, Samples]. Ausgangsleistung: [Geschwindigkeitszellen,
    Entfernungszellen]. axis=1 bedeutet zeilenweise, axis=0 spaltenweise.
    Pulsmodus delegiert an den Laufzeit-/Matched-Filter-Pfad in pulsradar.py.
    Die FMCW-FFT wird durch die Fenstersumme geteilt. Ein genau auf einer FFT-Zelle
    liegendes Signal mit Amplitude 1 behält dadurch die Spitzenleistung 1.
    """
    if config.radar_mode == "pulse_doppler":
        from .pulsradar import process_pulses
        return process_pulses(beat, config)
    if beat.shape != (config.chirps, config.samples):
        raise ValueError("Das Mischsignal braucht die Form [Anzahl Chirps, Samples pro Chirp].")

    # 1. Ein unveränderliches Echo optional entfernen: Mittelwert je Sample abziehen.
    signal = beat
    if config.remove_static:
        signal = unterdruecke_null_doppler(beat)

    # 2. FFT innerhalb jedes Chirps: Frequenz -> Entfernung.
    sample_fenster = window_values(config.samples, config.window)
    gefenstertes_signal = signal * sample_fenster[None, :]
    entfernungs_fft = np.fft.fft(gefenstertes_signal, axis=1)
    entfernungs_fft = np.fft.fftshift(entfernungs_fft, axes=1) / sample_fenster.sum()
    entfernungs_leistung = np.mean(np.abs(entfernungs_fft)**2, axis=0)

    # 3. FFT über die Chirps: Phasenänderung von Chirp zu Chirp -> Geschwindigkeit.
    chirp_fenster = window_values(config.chirps, config.window)
    gefensterte_chirps = entfernungs_fft * chirp_fenster[:, None]
    doppler_fft = np.fft.fft(gefensterte_chirps, axis=0)
    doppler_fft = np.fft.fftshift(doppler_fft, axes=0) / chirp_fenster.sum()
    leistung = np.abs(doppler_fft)**2

    # 4. Zu jeder Zelle die richtige Frequenz in Hz und die physikalische Achse berechnen.
    # fftshift ordnet negative Frequenzen links/unten und positive rechts/oben an.
    mischfrequenzen = np.fft.fftshift(np.fft.fftfreq(config.samples, d=1 / config.sample_rate_hz))
    dopplerfrequenzen = np.fft.fftshift(np.fft.fftfreq(config.chirps, d=config.repetition_s))
    scheinentfernung = C * mischfrequenzen / (2 * config.slope)
    geschwindigkeit = config.wavelength * dopplerfrequenzen / 2
    return Spectrum(leistung, entfernungs_leistung, mischfrequenzen, dopplerfrequenzen,
                    scheinentfernung, geschwindigkeit)
