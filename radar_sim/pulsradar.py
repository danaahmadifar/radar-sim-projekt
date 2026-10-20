"""Kohärente LFM-Pulse: Empfangssignal, Pulskompression und Doppler-FFT.

    rx[m,n] = A s(t[n]−τ) exp(−j2πfcτ) exp(−j2πfd(t[n]+mTr))

τ=2R/c, fd=2v/λ, v>0 entfernt sich. Wir speichern conj(rx), damit positive
Geschwindigkeiten wie bei tx*conj(rx) im FMCW-Modell positive Dopplerbins haben.
Es gibt kein FMCW-Dechirping: s ist ein zeitlich begrenzter Basisband-LFM-Puls.
R und v bleiben je kurzem Messpaket eingefroren; Doppler wird einmal eingesetzt.
"""

import numpy as np
from .config import C, RadarConfig
from .model import EchoFrame, target_amplitude
from .processing import Spectrum, window_values, unterdruecke_null_doppler


def pulsform(zeit_s: np.ndarray, config: RadarConfig) -> np.ndarray:
    """Konjugierter Up-Chirp mit Trägeroffset −B/2…+B/2 und Rechteck-Hüllkurve.

    Arrayform entspricht der Eingangszeit. Außerhalb 0≤t<Tp ist der Puls null.
    Amplitudenreferenz ist 1 während des Sendepulses, nicht im PRI-Mittel.
    """
    aktiv = (zeit_s >= -1e-15) & (zeit_s < config.chirp_s-1e-15)
    return aktiv * np.exp(-1j*np.pi*config.slope*(zeit_s-config.chirp_s/2)**2)


def generate_pulsed_echo(config: RadarConfig, frame_index: int = 0, bodenquellen: tuple = ()) -> EchoFrame:
    """Empfang [M Pulse,N ADC-Werte je PRI], konjugiert, noch ungefiltert.

    Monostatische Sende-/Empfangsumschaltung: t<Tp ist inklusive Rauschen
    gesperrt. Keine Umschalt-Erholzeit, Mehrwege oder Echos früherer PRIs.
    Ungültige Laufzeiten und Doppler-Aliasing werden vorab abgelehnt.
    """
    t = np.arange(config.samples)/config.sample_rate_hz
    starts = np.arange(config.chirps)*config.repetition_s
    signal = np.zeros((config.chirps, config.samples), complex)
    leistung = 0.
    from .empfaenger import Phasenprozess, begrenze_empfang
    tau_max = max((2*z.range_m/C for z in (*config.targets, *bodenquellen)), default=0.)
    phase = Phasenprozess(config, frame_index, max(tau_max, config.effekte.leakage_delay_s if config.effekte.leakage else 0.))
    zeiten = starts[:, None]+t[None, :] if phase.rms else None
    for ziel in (*config.targets, *bodenquellen):
        tau = 2*ziel.range_m/C
        fd = 2*ziel.velocity_mps/config.wavelength
        amplitude = target_amplitude(config, ziel)
        schnell = pulsform(t-tau, config) * np.exp(2j*np.pi*(fd*t+(config.carrier_hz*tau)%1))
        langsam = np.exp(2j*np.pi*fd*starts + 1j*ziel.phase_rad)
        echo = amplitude*langsam[:, None]*schnell[None, :]
        if phase.rms:
            echo *= np.exp(1j*phase.restphase(zeiten, tau))
        signal += echo
        leistung += amplitude**2
    leakage_power = 0.
    if config.effekte.leakage:
        tau = config.effekte.leakage_delay_s
        leakage_power = config.tx_power * 10**(config.effekte.leakage_db/10)
        leak = np.sqrt(leakage_power)*pulsform(t-tau, config)[None, :]*np.exp(2j*np.pi*((config.carrier_hz*tau)%1))
        if phase.rms:
            leak = leak*np.exp(1j*phase.restphase(zeiten, tau))
        signal += leak
    noise_power = 10**(-config.snr_db/10) if config.noise_enabled else 0.
    if noise_power:
        zufall = np.random.default_rng(np.random.SeedSequence([config.seed, frame_index]))
        sigma = np.sqrt(noise_power/2)
        signal.real += zufall.normal(0, sigma, signal.shape)
        signal.imag += zufall.normal(0, sigma, signal.shape)
    signal[:, t < config.chirp_s-1e-15] = 0
    signal, anteil = begrenze_empfang(signal, config.effekte)
    clutter_power = sum(target_amplitude(config, z)**2 for z in bodenquellen)
    return EchoFrame(signal, t, starts, noise_power, leistung-clutter_power, anteil, leakage_power, clutter_power)


def komprimiere_pulse(empfang: np.ndarray, config: RadarConfig) -> np.ndarray:
    """Lineare Korrelation, KEINE zyklische Faltung.

    r[k] = Σ_n empfang[k+n] conj(referenz[n]) w[n] / Σ_n w[n].
    L=ceil(Tp fs). Rechteck ist der Matched Filter, Hann eine bewusste
    Gewichtung zur Nebenkeulenminderung mit Verlust und breiterem Hauptmaximum.
    FFT-Nullauffüllen dient hier ausschließlich der linearen Faltung.
    Standard: Ausgang [M,N−2L+1], Tp≤Verzögerung≤Tr−Tp.
    Mit Teilpulsen: [M,N−L+1], Verzögerung ab 0; Empfang während Senden
    bleibt null. Der kleinere überlappende Echoanteil senkt den Peak automatisch.
    """
    l = config.pulse_samples
    referenz = pulsform(np.arange(l)/config.sample_rate_hz, config)
    gewicht = window_values(l, config.window)
    filterwerte = np.conjugate(referenz[::-1])*gewicht[::-1]
    fft_laenge = 1 << (config.samples+l-2).bit_length()
    ausgang = np.fft.ifft(np.fft.fft(empfang, n=fft_laenge, axis=1)
                         * np.fft.fft(filterwerte, n=fft_laenge)[None, :], axis=1)
    start = l-1 if config.effekte.teilpulse else 2*l-1
    return ausgang[:, start:config.samples] / gewicht.sum()


def process_pulses(empfang: np.ndarray, config: RadarConfig) -> Spectrum:
    """Matched Filter entlang Fast Time, danach kohärente FFT entlang der Pulse.

    Verzögerungsraster ΔRbin=c/(2fs), nominelle Auflösung c/(2B).
    Der Doppler verschiebt das LFM-Maximum näherungsweise um fd/S; wie bei
    FMCW wird Rapp = R + c fd/(2S) in der Detektion korrigiert.
    """
    if empfang.shape != (config.chirps, config.samples):
        raise ValueError("Puls-Empfang benötigt [Pulse pro Paket, ADC-Samples je PRI].")
    signal = empfang
    if config.remove_static:
        signal = unterdruecke_null_doppler(empfang)
    komprimiert = komprimiere_pulse(signal, config)
    fenster = window_values(config.chirps, config.window)
    spektrum = np.fft.fftshift(np.fft.fft(komprimiert*fenster[:, None], axis=0), axes=0)/fenster.sum()
    fd = np.fft.fftshift(np.fft.fftfreq(config.chirps, d=config.repetition_s))
    start = 0 if config.effekte.teilpulse else config.pulse_samples
    delays = np.arange(start, config.samples-config.pulse_samples+1)/config.sample_rate_hz
    return Spectrum(np.abs(spektrum)**2, np.mean(np.abs(komprimiert)**2, axis=0),
                    None, fd, C*delays/2, config.wavelength*fd/2,
                    compressed_first=komprimiert[0].copy())


def puls_config(config: RadarConfig) -> RadarConfig:
    """Offenes Lehrprofil, keine behaupteten Betriebsdaten eines realen Gerätes."""
    from dataclasses import replace
    return replace(config, radar_mode="pulse_doppler", carrier_hz=3e9, bandwidth_hz=2e6,
                   chirp_s=4e-6, repetition_s=200e-6, sample_rate_hz=5e6, chirps=64,
                   adc_skip_samples=0)
