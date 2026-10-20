"""Relative Sendeleistung und Energie, unabhängig von GUI und Empfangsmodell."""

from dataclasses import dataclass
import math
import numpy as np

from .config import RadarConfig


@dataclass(frozen=True)
class PowerBudget:
    """Rechteckige Leistungshüllkurve eines Chirps bzw. LFM-Pulses.

    peak: Ppeak/P0, duration_s: aktive Sendezeit, interval_s: PRI [s].
    Energie hat die Einheit P0·s; ohne absolutes P0 sind es keine Joule.
    ADC-Vorlauf verkürzt die Beobachtung, nicht die aktive Sendezeit.
    """

    peak: float
    duration_s: float
    interval_s: float
    repetitions: int

    def __post_init__(self) -> None:
        if (not all(math.isfinite(v) for v in (self.peak, self.duration_s, self.interval_s))
                or self.peak <= 0 or not 0 < self.duration_s <= self.interval_s
                or type(self.repetitions) is not int or self.repetitions < 1):
            raise ValueError("Sendeleistung: positive Werte, aktive Dauer ≤ PRI und ganze Wiederholungszahl erforderlich.")

    @property
    def duty_cycle(self) -> float:
        return self.duration_s/self.interval_s

    @property
    def average(self) -> float:
        return self.peak*self.duty_cycle

    @property
    def pulse_energy(self) -> float:
        return self.peak*self.duration_s

    @property
    def frame_energy(self) -> float:
        return self.repetitions*self.pulse_energy

    def waveform(self, intervals: int = 3) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Zeit [s], P/P0 und aufsummierte Energie [P0·s], jeweils Form [4K].

        Nur Flanken und Endpunkte speichern: vier Punkte je PRI genügen exakt
        für diese Hüllkurve. Keine RF- oder ADC-Abtastung für die Darstellung.
        K=min(intervals, Wiederholungszahl); höchstens 2048 Intervalle.
        """
        if type(intervals) is not int or not 1 <= intervals <= 2048:
            raise ValueError("1 bis 2048 Sendeintervalle darstellen.")
        k = np.arange(min(intervals, self.repetitions))[:, None]
        time_s = k*self.interval_s + np.array([0, self.duration_s, self.duration_s, self.interval_s])
        power = np.tile([self.peak, self.peak, 0., 0.], (len(k), 1))
        energy = (k + np.array([0., 1., 1., 1.]))*self.pulse_energy
        return time_s.ravel(), power.ravel(), energy.ravel()


def compare_power(config: RadarConfig, reference_duty: float = .1,
                  equal_average: bool = True) -> tuple[PowerBudget, PowerBudget]:
    """Aktueller Sender und hypothetische Referenz mit gleichem PRI und M.

    Bei Puls-Doppler ist die Referenz FMCW ohne Sendepause (D=1).
    Bei FMCW ist sie ein Pulssender mit frei gewähltem Referenz-Tastgrad.
    Bei gleichem Mittel: Pref_peak=Pactual_avg/Dref; sonst gleiche Spitzen.
    Die Referenz wird nicht in die Radarverarbeitung eingespeist. Ein anderer
    Puls-Tastgrad benötigt eventuell andere ADC-/Blindbereichseinstellungen.
    """
    if config.radar_mode not in ("fmcw", "pulse_doppler"):
        raise ValueError("Passivradar besitzt keinen eigenen Sender.")
    if not math.isfinite(reference_duty) or not 0 < reference_duty <= 1:
        raise ValueError("Der Referenz-Tastgrad muss zwischen 0 und 1 liegen.")
    actual = PowerBudget(config.tx_power, config.chirp_s, config.repetition_s, config.chirps)
    duty = 1. if config.radar_mode == "pulse_doppler" else reference_duty
    peak = actual.average/duty if equal_average else actual.peak
    reference = PowerBudget(peak, duty*config.repetition_s, config.repetition_s, config.chirps)
    return actual, reference
