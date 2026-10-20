"""Aus Radar-Zielen ein komplexes Mischsignal berechnen.

Die öffentlichen Namen bleiben englisch, damit vorhandene Beispiele weiter
funktionieren. Kommentare und Rechenschritte verwenden einfache deutsche Wörter.
"""

from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray

from .config import C, RadarConfig, Target


@dataclass
class EchoFrame:
    """Ein Messpaket: beat=Mischsignal, fast_time_s=Samplezeiten,
    slow_time_s=Chirp-Startzeiten, noise_power=Rauschleistung.
    expected_signal_power ist die Summe der Einzelziel-Leistungen;
    durch Überlagerung kann die tatsächlich gemessene Summenleistung abweichen.
    Bei Pulsen gilt diese Referenz während eines aktiven Echos, nicht im PRI-Mittel.
    """
    beat: NDArray[np.complex128]  # [chirp m, ADC-Sample n]
    fast_time_s: NDArray[np.float64]
    slow_time_s: NDArray[np.float64]
    noise_power: float
    expected_signal_power: float
    clipped_fraction: float = 0.0  # Anteil der Samples oberhalb des Amplitude-Limits
    leakage_power: float = 0.0     # Eingangsleistung während aktivem Leakage-Signal
    clutter_power: float = 0.0     # Summe der einzelnen Clutterleistungen vor Begrenzung


def target_amplitude(config: RadarConfig, target: Target) -> float:
    """Berechnet die Signalhöhe, also die Amplitude eines Echos.

    Die Eingabestärke ist eine Leistung. Deshalb brauchen wir die Wurzel.
    Im Radar-Modus gilt zusätzlich A = sqrt(σ/σref) * (Rref/R)².
    Das Quadrat der Amplitude ist dann proportional zu σ/R⁴.
    TX Peak skaliert die Echoamplitude mit sqrt(Ppeak/P0). Die Rauschreferenz
    bleibt fest. Wir berechnen relative Werte, keine Empfangsleistung in Watt.
    """
    if config.amplitude_model == "didactic":
        return float(np.sqrt(config.tx_power * target.strength) * target.antenna_gain * target.path_gain)
    return float(np.sqrt(config.tx_power * target.strength / config.reference_rcs_m2)
                 * (config.reference_range_m / target.range_m) ** 2 * target.antenna_gain * target.path_gain)


def dechirp(tx: NDArray[np.complex128], rx: NDArray[np.complex128]) -> NDArray[np.complex128]:
    """Mischer tx · conj(rx). Umgekehrte Reihenfolge kehrt ALLE Phasenvorzeichen um."""
    return tx * np.conjugate(rx)


def generate_echo(config: RadarConfig, frame_index: int = 0, bodenquellen: tuple[Target, ...] = ()) -> EchoFrame:
    """Berechnet das Mischsignal für ein kurzes Radar-Messpaket (einen Frame).

    Pro Ziel: z[m,n] = A * exp(j*2π*((Sτ+fd)*t[n] + fd*m*Tr
                                      + fc*τ − S*τ²/2) + j*φ).
    τ=2R/c ist die Hin- und Rücklaufzeit [s], fd=2v/λ der Doppleranteil [Hz].
    Das Ergebnis ist eine Tabelle mit Form [Anzahl Chirps, Samples pro Chirp].
    Jede Zahl enthält Real- und Imaginärteil (NumPy-Typ complex128).

    Innerhalb dieses kurzen Messpakets bleiben Entfernung und Geschwindigkeit
    näherungsweise konstant. Bei einem Flug liefert pipeline.py für jedes neue
    Paket neue Zielwerte. Bewegung nicht zusätzlich in die Laufzeit dieses
    Pakets einsetzen: Sie steckt bereits in der Dopplerphase.
    Rauschleistung vor Fenster/FFT: Pn=10^(-SNR/10), bezogen auf Amplitude 1.
    """
    if config.radar_mode == "pulse_doppler":
        from .pulsradar import generate_pulsed_echo
        return generate_pulsed_echo(config, frame_index, bodenquellen)
    # 1. Zwei Zeitachsen: Samples innerhalb eines Chirps und Startzeiten der Chirps.
    # Vorlauf überspringt den Rampenanfang, bis alle modellierten Echos da sind.
    sample_zeiten = (np.arange(config.samples, dtype=float) + config.adc_skip_samples) / config.sample_rate_hz
    chirp_zeiten = np.arange(config.chirps, dtype=float) * config.repetition_s
    mischsignal = np.zeros((config.chirps, config.samples), dtype=np.complex128)
    summe_einzelleistungen = 0.0
    from .empfaenger import Phasenprozess, begrenze_empfang
    groesste_laufzeit = max((2*z.range_m/C for z in (*config.targets, *bodenquellen)), default=0.)
    groesste_laufzeit = max(groesste_laufzeit, config.effekte.leakage_delay_s if config.effekte.leakage else 0.)
    phase = Phasenprozess(config, frame_index, groesste_laufzeit)
    zeiten = chirp_zeiten[:, None]+sample_zeiten[None, :] if phase.rms else None

    # 2. Alle Ziele liefern ein Echo. Wir addieren die komplexen Signale.
    for ziel in (*config.targets, *bodenquellen):
        laufzeit_s = 2 * ziel.range_m / C
        doppler_hz = 2 * ziel.velocity_mps / config.wavelength
        mischfrequenz_hz = config.slope * laufzeit_s + doppler_hz
        amplitude = target_amplitude(config, ziel)
        startphase = config.carrier_hz * laufzeit_s - 0.5 * config.slope * laufzeit_s**2
        # Eine volle Umdrehung ändert die Phase nicht. Modulo 1 hält Zahlen klein.
        sample_phase = 2 * np.pi * (mischfrequenz_hz * sample_zeiten + startphase % 1)
        chirp_phase = 2 * np.pi * doppler_hz * chirp_zeiten + ziel.phase_rad
        # [:, None] macht aus einem Vektor eine Spalte; [None, :] eine Zeile.
        # NumPy kombiniert beides zu unserer Tabelle [Chirps, Samples].
        echo = amplitude * np.exp(1j * chirp_phase[:, None]) * np.exp(1j * sample_phase[None, :])
        if phase.rms:
            echo *= np.exp(1j*phase.restphase(zeiten, laufzeit_s))
        mischsignal += echo
        summe_einzelleistungen += amplitude**2

    leakage_power = 0.
    if config.effekte.leakage:
        tau = config.effekte.leakage_delay_s
        leakage_power = config.tx_power * 10**(config.effekte.leakage_db/10)
        start = (config.carrier_hz*tau-.5*config.slope*tau*tau)%1
        leak = np.sqrt(leakage_power)*np.exp(2j*np.pi*(config.slope*tau*sample_zeiten+start))[None, :]
        if phase.rms:
            leak = leak*np.exp(1j*phase.restphase(zeiten, tau))
        mischsignal += leak

    # 3. Rauschen mit festem Startwert: wiederholbare Zufallszahlen statt Zufall je Start.
    rauschleistung = 10 ** (-config.snr_db / 10) if config.noise_enabled else 0.0
    if rauschleistung:
        zufall = np.random.default_rng(np.random.SeedSequence([config.seed, frame_index]))
        # Real- und Imaginärteil tragen jeweils die Hälfte der Rauschleistung.
        standardabweichung = np.sqrt(rauschleistung / 2)
        mischsignal.real += zufall.normal(0, standardabweichung, mischsignal.shape)
        mischsignal.imag += zufall.normal(0, standardabweichung, mischsignal.shape)
    mischsignal, anteil = begrenze_empfang(mischsignal, config.effekte)
    clutter_power = sum(target_amplitude(config, z)**2 for z in bodenquellen)
    return EchoFrame(mischsignal, sample_zeiten, chirp_zeiten, rauschleistung,
                     summe_einzelleistungen-clutter_power, anteil, leakage_power, clutter_power)
