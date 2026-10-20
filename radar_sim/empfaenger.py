"""Einfaches kohärentes Phasenrauschen und radialer Hüllkurvenbegrenzer.

Dies sind bewusst definierte Ersatzmodelle, keine Datenblatt-Nachbildung eines
PLL, LNA oder ADC. Alle Pegel beziehen sich auf dieselbe relative Aref²=1.
"""

import numpy as np


def phasen_bandreserve(config) -> float:
    """Konservative 6σ-Frequenzreserve für das nicht streng bandbegrenzte Modell.

    Sechs Spektralbreiten des glatten Phasenprozesses bzw. sechs RMS der
    momentanen Frequenzabweichung. Gaußausläufer sind mathematisch unbeschränkt;
    dies ist eine praktische ADC-Reserve, kein Beweis exakt null Aliasing.
    """
    e = config.effekte
    return 6*max(1., e.phase_rms_rad)/(2*np.pi*e.phase_zeit_s) if e.phasenrauschen and e.phase_rms_rad else 0.


class Phasenprozess:
    """Gemeinsame stationäre Gauß-Phase φ(t), in Radiant.

    Rφ(Δt)≈σ² exp(−Δt²/(2Tc²)). Ein gaußförmiger spektraler Tiefpass
    färbt weißes Gaußrauschen. Schritt Tc/8 und lineare Interpolation erlauben
    auch gebrochene Laufzeiten. 8Tc Rand auf jeder Seite vermeidet praktisch
    die periodische Kovarianz der FFT. Ensemble-RMS, kein nachträgliches
    Normieren jeder Realisierung. Kein universelles 1/f- oder PLL-Modell.
    """

    def __init__(self, config, frame_index: int, groesste_laufzeit_s: float):
        e = config.effekte
        self.rms = e.phase_rms_rad if e.phasenrauschen else 0.
        if not self.rms:
            return
        self.schritt = e.phase_zeit_s/8
        self.start = -groesste_laufzeit_s-8*e.phase_zeit_s
        dauer = config.chirps*config.repetition_s+groesste_laufzeit_s+16*e.phase_zeit_s
        anzahl = 1 << max(1, int(np.ceil(dauer/self.schritt))).bit_length()
        if anzahl > 262144:
            raise ValueError("Phasenprozess zu groß: Korrelationszeit erhöhen oder Messpaket verkürzen.")
        zufall = np.random.default_rng(np.random.SeedSequence([config.seed, frame_index, 911]))
        frequenz = np.fft.rfftfreq(anzahl, self.schritt)
        filterwerte = np.exp(-.25*(2*np.pi*frequenz*e.phase_zeit_s)**2)
        # Reelle FFT: innere positive Frequenzen repräsentieren jeweils ±f.
        energie = (filterwerte[0]**2+filterwerte[-1]**2+2*np.sum(filterwerte[1:-1]**2))/anzahl
        self.phase = np.fft.irfft(np.fft.rfft(zufall.normal(size=anzahl))*filterwerte, n=anzahl)*self.rms/np.sqrt(energie)
        self.zeiten = self.start+np.arange(anzahl)*self.schritt

    def werte(self, zeit_s: np.ndarray) -> np.ndarray:
        """φ(t) mit derselben Form wie zeit_s; kein Seed pro Echo."""
        if not self.rms:
            return np.zeros_like(zeit_s)
        if np.min(zeit_s) < self.zeiten[0] or np.max(zeit_s) > self.zeiten[-1]:
            raise ValueError("Zeit außerhalb des vorbereiteten Phasenprozesses.")
        return np.interp(zeit_s, self.zeiten, self.phase)

    def restphase(self, zeit_s: np.ndarray, laufzeit_s: float) -> np.ndarray:
        """φ(t)−φ(t−τ): gemeinsamer aktiver Sende-/Empfangsoszillator.

        Varianz≈2σ²(1−exp(−τ²/(2Tc²))). Für τ=0 exakt null.
        """
        return self.werte(zeit_s)-self.werte(zeit_s-laufzeit_s)


def begrenze_empfang(signal: np.ndarray, effekte) -> tuple[np.ndarray, float]:
    """Radialer harter Begrenzer y=x·min(1,Amax/|x|), Amax=10^(L/20).

    Form beliebig, komplexer Eingang. Rückgabe: neues Signal und Anteil
    begrenzter Samples. Erhält Phase, komprimiert Amplitude. Ein idealer
    Mischer mit Betrag 1 kommutiert damit. Keine AGC, Erholzeit oder Quantisierung.
    """
    if not effekte.saettigung:
        return signal, 0.
    grenze = 10**(effekte.saettigung_db/20)
    betrag = np.abs(signal)
    faktor = np.minimum(1., grenze/np.maximum(betrag, np.finfo(float).tiny))
    return signal*faktor, float(np.mean(betrag > grenze))
