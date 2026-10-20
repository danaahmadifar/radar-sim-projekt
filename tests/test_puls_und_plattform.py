"""Unabhängige Signalreferenzen für Puls-Doppler und bewegtes monostatisches Radar."""

from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
import numpy as np
from radar_sim.config import C, RadarConfig, Target, validate_config
from radar_sim.flugbahn import Flugbahn, Flugszene, relativer_zustand, relative_bahngrenzen, kleinster_abstand
from radar_sim.flughafen import flughafen_config
from radar_sim.pulsradar import puls_config, komprimiere_pulse
from radar_sim.model import generate_echo
from radar_sim.pipeline import simulate_frame
from radar_sim.evaluation import match_targets, schaetztoleranzen
from radar_sim.parametergrenzen import berechne_parameterbereiche, bereich_fuer_tabellenwert
from radar_sim.io import save_config, load_config


class PulsUndPlattformTests(unittest.TestCase):
    def setUp(self):
        self.c = replace(puls_config(RadarConfig()), targets=(Target(5000, 0),), noise_enabled=False)

    def test_puls_echo_gegen_verzoegerten_basisbandempfang(self):
        c = replace(self.c, targets=(Target(4100, -30),))
        echo = generate_echo(c)
        t = np.arange(c.samples)/c.sample_rate_hz
        tau = 8200/C
        fd = -60/c.wavelength
        erwartet = np.zeros_like(echo.beat)
        for m in range(c.chirps):
            # Reales RX-Vorzeichen vor der abschließenden Konjugation.
            aktiv = (t-tau >= 0) & (t-tau < c.chirp_s) & (t >= c.chirp_s)
            phase = np.pi*c.slope*(t-tau-c.chirp_s/2)**2 - 2*np.pi*c.carrier_hz*tau - 2*np.pi*fd*(t+m*c.repetition_s)
            erwartet[m, aktiv] = np.exp(-1j*phase[aktiv])
        np.testing.assert_allclose(echo.beat, erwartet, atol=2e-9)
        np.testing.assert_array_equal(echo.beat[:, :c.pulse_samples], 0)

    def test_matched_filter_gegen_direkte_lineare_korrelation(self):
        c = replace(self.c, window="rect")
        zufall = np.random.default_rng(819)
        empfang = zufall.normal(size=(c.chirps, c.samples))+1j*zufall.normal(size=(c.chirps, c.samples))
        t = np.arange(c.pulse_samples)/c.sample_rate_hz
        referenz = np.exp(-1j*np.pi*c.slope*(t-c.chirp_s/2)**2)
        erwartet = np.array([np.correlate(zeile, referenz, "valid")[c.pulse_samples:]/c.pulse_samples for zeile in empfang])
        np.testing.assert_allclose(komprimiere_pulse(empfang, c), erwartet, atol=1e-14)

    def test_puls_entfernung_vorzeichen_kopplung_und_mehrere_ziele(self):
        for window in ("rect", "hann"):
            for ziele in ((Target(5000, 0),), (Target(4100, -40), Target(8100, 30)),
                          (Target(6000, -40), Target(6000, 40))):
                c = replace(self.c, targets=ziele, window=window)
                f = simulate_frame(c)
                paare = match_targets(c, f.candidates)
                self.assertEqual(len(paare), len(ziele), (window, ziele, f.candidates))
                rtol, vtol = schaetztoleranzen(c)
                for p in paare:
                    self.assertLessEqual(abs(p.range_error_m), rtol*1.01)
                    self.assertLessEqual(abs(p.velocity_error_mps), vtol*1.01)
                self.assertEqual(f.spectrum.power.shape, (c.chirps, c.range_bins))
                self.assertAlmostEqual(float(np.diff(f.spectrum.apparent_range_m)[0]), C/(2*c.sample_rate_hz))
        self.assertNotEqual(self.c.range_resolution, self.c.range_bin_m)

    def test_blindbereich_mehrdeutigkeit_sampling_und_speicher(self):
        for fehlerhaft in (replace(self.c, targets=(Target(self.c.minimum_range_m-1),)),
                           replace(self.c, targets=(Target(self.c.timing_range_limit+1),)),
                           replace(self.c, targets=(Target(5000, self.c.max_velocity),)),
                           replace(self.c, sample_rate_hz=1e6), replace(self.c, adc_skip_samples=1),
                           replace(self.c, chirps=2048), replace(self.c, repetition_s=200.11e-6)):
            with self.subTest(config=fehlerhaft):
                with self.assertRaises(ValueError):
                    validate_config(fehlerhaft)

    def test_lfm_dopplerkopplung_ist_messbar_und_korrektur_hat_richtiges_vorzeichen(self):
        # Feiner ADC-Raster und langer Puls machen den LFM-Bias sichtbar.
        # Ein isoliertes Ziel braucht für diesen Formeltest keine CFAR-Schwelle.
        for v in (-78., 78.):
            c = replace(self.c, chirp_s=40e-6, bandwidth_hz=1e6, sample_rate_hz=20e6,
                        window="rect", targets=(Target(12000, v),))
            f = simulate_frame(c)
            i, j = np.unravel_index(np.argmax(f.spectrum.power), f.spectrum.power.shape)
            rapp = f.spectrum.apparent_range_m[j]
            korrigiert = rapp-C*f.spectrum.doppler_hz[i]/(2*c.slope)
            self.assertGreater((rapp-12000)*np.sign(v), c.range_bin_m/2)
            self.assertLessEqual(abs(korrigiert-12000), schaetztoleranzen(c)[0]*1.01)

    def test_rauschen_reproduzierbar_und_leere_szene(self):
        c = replace(self.c, targets=(), noise_enabled=True)
        a, b = generate_echo(c, 3), generate_echo(c, 3)
        np.testing.assert_array_equal(a.beat, b.beat)
        self.assertFalse(np.array_equal(a.beat, generate_echo(c, 4).beat))
        np.testing.assert_array_equal(a.beat[:, :c.pulse_samples], 0)
        self.assertEqual(len(simulate_frame(replace(c, noise_enabled=False)).candidates), 0)
        f = simulate_frame(replace(self.c, remove_static=True))
        self.assertEqual(len(f.candidates), 0)
        np.testing.assert_array_equal(f.spectrum.power, 0)
        f = simulate_frame(RadarConfig(targets=(Target(40),), noise_enabled=False, remove_static=True))
        self.assertEqual(len(f.candidates), 0)
        np.testing.assert_array_equal(f.spectrum.power, 0)

    def test_relative_geometrie_ableitung_und_gemeinsames_tempo(self):
        radar = Flugbahn(500, 1800, 160, start_y_m=40, geschwindigkeit_y_mps=2)
        ziel = Flugbahn(-4500, 2100, 200, start_y_m=340, geschwindigkeit_y_mps=5)
        szene = Flugszene("Test", (ziel,), 40, .5, radar)
        for t in (0., 10., 40.):
            zustand = relativer_zustand(ziel, radar, t)
            p = np.array([-5000+40*t, 300+3*t, 300])
            self.assertAlmostEqual(zustand.entfernung_m, np.linalg.norm(p))
            self.assertAlmostEqual(zustand.radialgeschwindigkeit_mps, p@np.array([40, 3, 0])/np.linalg.norm(p))
            if t > 0:
                dt = 1e-4
                self.assertAlmostEqual((relativer_zustand(ziel, radar, t+dt).entfernung_m-relativer_zustand(ziel, radar, t-dt).entfernung_m)/(2*dt), zustand.radialgeschwindigkeit_mps, places=6)
        gleich = replace(ziel, geschwindigkeit_x_mps=160, geschwindigkeit_y_mps=2)
        self.assertEqual(relativer_zustand(gleich, radar, 12).radialgeschwindigkeit_mps, 0)
        self.assertAlmostEqual(kleinster_abstand(ziel, szene), np.linalg.norm([-3400, 420, 300]))
        self.assertGreaterEqual(relative_bahngrenzen(ziel, szene).tempo_max_mps, np.linalg.norm([40,3,0]))

    def test_beide_moden_flugradar_und_json(self):
        for c in (flughafen_config("15_zwei_flugzeuge_radar"), puls_config(flughafen_config("15_zwei_flugzeuge_radar"))):
            for nummer in (0, 40, 80):
                f = simulate_frame(c, nummer)
                self.assertEqual(len(f.config.targets), 1)
                self.assertIsNotNone(f.radar_zustand)
                self.assertEqual(len(match_targets(f.config, f.candidates)), 1)
            with tempfile.TemporaryDirectory() as ordner:
                p = Path(ordner)/"radar.json"
                save_config(p, c)
                self.assertEqual(load_config(p), c)
            self.assertFalse(bereich_fuer_tabellenwert(c, True, 1, 0).leer)

    def test_gemeinsame_bewegung_beider_flugzeuge_aendert_echo_nicht(self):
        c = flughafen_config("15_zwei_flugzeuge_radar")
        szene = c.flugszene
        radar = replace(szene.radar_bahn, geschwindigkeit_x_mps=szene.radar_bahn.geschwindigkeit_x_mps+100,
                        geschwindigkeit_y_mps=20)
        ziel = replace(szene.bahnen[0], geschwindigkeit_x_mps=szene.bahnen[0].geschwindigkeit_x_mps+100,
                       geschwindigkeit_y_mps=20)
        andere_szene = replace(szene, radar_bahn=radar, bahnen=(ziel,))
        for basis in (c, puls_config(c)):
            a = simulate_frame(basis, 20)
            b = simulate_frame(replace(basis, flugszene=andere_szene), 20)
            np.testing.assert_array_equal(a.echo.beat, b.echo.beat)

    def test_zusammentreffen_zwischen_frames_wird_abgelehnt(self):
        radar = Flugbahn(0, 1800, 0)
        ziel = Flugbahn(-10, 1800, 20)
        szene = Flugszene("Kollision", (ziel,), 1, 1, radar)
        with self.assertRaisesRegex(ValueError, "Abstand"):
            validate_config(replace(self.c, targets=(), flugszene=szene))
        for ungueltig in (replace(szene, radar_bahn="kein Flugzeug"),
                          replace(szene, bahnen=(replace(ziel, start_x_m=float('inf')),))):
            with self.assertRaises(ValueError):
                validate_config(replace(self.c, targets=(), flugszene=ungueltig))

    def test_puls_slidergrenzen_auch_mit_bewegtem_radar(self):
        for c in (self.c, puls_config(flughafen_config("15_zwei_flugzeuge_radar"))):
            for name, grenze in berechne_parameterbereiche(c).items():
                self.assertFalse(grenze.leer, name)
                for wert in (grenze.minimum, grenze.maximum, (grenze.minimum+grenze.maximum)/2):
                    wert = grenze.begrenze_wert(wert)
                    if name in ("chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples"):
                        wert = round(wert)
                    with self.subTest(name=name, wert=wert):
                        validate_config(replace(c, **{name: wert}))


if __name__ == "__main__":
    unittest.main()
