"""Analytische FFT-Referenz und Regression gegen Kreise auf Spektralflanken."""

from dataclasses import replace
import unittest
import numpy as np

from radar_sim import RadarConfig, Target, simulate_frame
from radar_sim.config import C
from radar_sim.detection import CFARResult, ca_cfar, group_candidates, lokale_maxima
from radar_sim.evaluation import match_targets
from radar_sim.flugbahn import flugszenen
from radar_sim.processing import Spectrum


def analytische_fensterantwort(frequenzabstand: np.ndarray, anzahl: int, fenster: str) -> np.ndarray:
    """Geschlossene Formel der DFT eines einzelnen Tons, ohne FFT-Aufruf.

    u ist der Frequenzabstand in Zyklen pro Sample.
    Rechteck: D(u)=exp(jπu(N−1))*sin(πNu)/sin(πu).
    Hann: 0.5D(u)−0.25D(u+1/N)−0.25D(u−1/N).
    sinc schreibt den Quotienten ohne Division durch null bei u=0.
    """
    def rechteck(u: np.ndarray) -> np.ndarray:
        u = (u + 0.5) % 1 - 0.5
        return anzahl * np.exp(1j * np.pi * u * (anzahl - 1)) * np.sinc(anzahl * u) / np.sinc(u)

    if fenster == "rect":
        return rechteck(frequenzabstand) / anzahl
    return (0.5 * rechteck(frequenzabstand)
            - 0.25 * rechteck(frequenzabstand + 1 / anzahl)
            - 0.25 * rechteck(frequenzabstand - 1 / anzahl)) / (anzahl / 2)


class DetektionsTheorieTests(unittest.TestCase):
    def test_fft_entspricht_analytischer_fensterantwort_auch_zwischen_bins(self) -> None:
        for fenster in ("rect", "hann"):
            config = RadarConfig(noise_enabled=False, window=fenster, targets=(Target(40.37, -4.31, 0.7),))
            result = simulate_frame(config)
            fd = 2 * -4.31 / config.wavelength
            fb = 2 * config.slope * 40.37 / C + fd
            fast = analytische_fensterantwort((fb - result.spectrum.beat_hz) / config.sample_rate_hz,
                                             config.samples, fenster)
            slow = analytische_fensterantwort((fd - result.spectrum.doppler_hz) * config.repetition_s,
                                             config.chirps, fenster)
            erwartet = 0.7 * np.abs(slow[:, None] * fast[None, :])**2
            np.testing.assert_allclose(result.spectrum.power, erwartet, rtol=1e-5, atol=1e-18)

    def test_cfartreffer_auf_flanke_ist_kein_objekt(self) -> None:
        config = RadarConfig(chirps=32)
        leistung = np.zeros((32, 40))
        leistung[16, 20] = 5
        leistung[16, 21] = 10  # Größerer Nachbar, der selbst zunächst NICHT CFAR-qualifiziert ist.
        maske = np.zeros_like(leistung, dtype=bool)
        maske[16, 20] = True
        cfar = CFARResult(maske, np.ones_like(leistung), np.ones_like(maske), 1, 1)
        spektrum = Spectrum(leistung, leistung.mean(0), np.arange(40) * 25000.,
                            np.zeros(32), np.arange(40) * config.range_resolution, np.zeros(32))
        self.assertEqual(group_candidates(spektrum, cfar, config), [])
        maske[16, 21] = True
        kandidaten = group_candidates(spektrum, cfar, config)
        self.assertEqual(len(kandidaten), 1)
        self.assertEqual(kandidaten[0].range_bin, 21)

    def test_peak_pruefung_sieht_diagonale_nachbarn_und_gleiche_spitzen(self) -> None:
        bild = np.zeros((8, 8))
        bild[3, 3] = 5
        bild[4, 4] = 6
        peaks = lokale_maxima(bild)
        self.assertFalse(peaks[3, 3])
        self.assertTrue(peaks[4, 4])
        bild[3, 3] = 6
        self.assertTrue(lokale_maxima(bild)[3, 3])
        self.assertFalse(lokale_maxima(np.zeros((8, 8))).any())
        self.assertFalse(lokale_maxima(np.ones((8, 8))).any())

    def test_alle_drei_fluege_ohne_awgn_haben_keine_zusaetzlichen_kreise_mit_hann(self) -> None:
        for name, szene in flugszenen().items():
            config = RadarConfig(targets=(), flugszene=szene, noise_enabled=False, window="hann")
            for nummer in range(szene.letzter_frame + 1):
                with self.subTest(szene=name, frame=nummer):
                    ergebnis = simulate_frame(config, nummer)
                    self.assertEqual(len(ergebnis.candidates), len(szene.bahnen))
                    self.assertEqual(len(match_targets(ergebnis.config, ergebnis.candidates)), len(szene.bahnen))

    def test_leere_szene_ohne_awgn_ergibt_keine_treffer(self) -> None:
        for fenster in ("hann", "rect"):
            ergebnis = simulate_frame(RadarConfig(targets=(), noise_enabled=False, window=fenster))
            self.assertFalse(ergebnis.cfar.mask.any())
            self.assertEqual(ergebnis.candidates, [])

    def test_schwaches_ziel_wird_nicht_durch_globalen_anzeigepegel_versteckt(self) -> None:
        basis = RadarConfig(noise_enabled=False)
        fd = 8 / (basis.chirps * basis.repetition_s)
        v = fd * basis.wavelength / 2
        entfernung = C * (100 / basis.chirp_s - fd) / (2 * basis.slope)
        config = replace(basis, targets=(Target(40 * basis.range_resolution), Target(entfernung, v, 1e-8)))
        result = simulate_frame(config)
        self.assertEqual(len(match_targets(config, result.candidates)), 2)

    def test_rechteck_nebenkeulen_koennen_echte_lokale_fehlpeaks_sein(self) -> None:
        # Bewusster Gegenbeleg zu einer pauschalen Behauptung "AWGN aus => nie Fehlalarme".
        config = RadarConfig(targets=(), flugszene=flugszenen()["07_gegenverkehr"],
                             noise_enabled=False, window="rect")
        result = simulate_frame(config, 66)
        self.assertGreater(len(result.candidates), 2)
        self.assertEqual(len(match_targets(result.config, result.candidates)), 2)
        peaks = lokale_maxima(result.spectrum.power)
        for kandidat in result.candidates:
            self.assertTrue(peaks[kandidat.doppler_bin, kandidat.range_bin])

    def test_cfar_ist_unabhaengig_von_gemeinsamer_leistungsskalierung(self) -> None:
        config = RadarConfig()
        leistung = np.random.default_rng(7).exponential(1, (64, 80))
        a = ca_cfar(leistung, config)
        b = ca_cfar(leistung * 1e-8, config)
        np.testing.assert_array_equal(a.mask, b.mask)
        np.testing.assert_allclose(b.threshold[a.valid], 1e-8 * a.threshold[a.valid], rtol=1e-11)


if __name__ == "__main__":
    unittest.main()
