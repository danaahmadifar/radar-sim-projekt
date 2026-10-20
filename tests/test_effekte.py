"""Analytische und statistische Referenzen für die vereinfachten Störmodelle."""

from dataclasses import replace
import math
import unittest
import numpy as np
from radar_sim.config import C, RadarConfig, Target, validate_config
from radar_sim.effekt_config import Stoereffekte
from radar_sim.empfaenger import Phasenprozess, begrenze_empfang
from radar_sim.ausbreitung import ERDRADIUS_M, erdkoordinaten, freie_sicht, monostatische_geometrie
from radar_sim.bodenclutter import bodenpunkte, aktive_bodenquellen
from radar_sim.model import generate_echo, target_amplitude
from radar_sim.pipeline import simulate_frame
from radar_sim.pulsradar import generate_pulsed_echo, process_pulses
from radar_sim.passivradar import passiv_config, erzeuge_passivempfang, kreuzambiguitaet
from radar_sim.effektbeispiele import effektbeispiele


class EffektTests(unittest.TestCase):
    def test_leakage_ist_verzoegerter_chirp_mit_richtigem_pegel(self):
        c = RadarConfig(targets=(), chirps=32, noise_enabled=False, window="rect")
        tau = 16/(c.samples*c.slope/c.sample_rate_hz)
        c = replace(c, effekte=Stoereffekte(leakage=True, leakage_db=20, leakage_delay_s=tau))
        f = simulate_frame(c)
        self.assertEqual(np.unravel_index(np.argmax(f.spectrum.power), f.spectrum.power.shape), (16, c.samples//2+16))
        self.assertAlmostEqual(float(f.spectrum.power.max()), 100, places=10)
        np.testing.assert_allclose(np.abs(f.echo.beat), 10, atol=1e-13)

    def test_puls_leakage_verschwindet_waehrend_senden(self):
        c = RadarConfig(radar_mode="pulse_doppler", carrier_hz=3e9, bandwidth_hz=2e6,
                        chirp_s=4e-6, repetition_s=200e-6, sample_rate_hz=5e6,
                        chirps=32, targets=(), noise_enabled=False,
                        effekte=Stoereffekte(leakage=True, leakage_delay_s=0))
        np.testing.assert_array_equal(generate_pulsed_echo(c).beat, 0)
        c = replace(c, effekte=replace(c.effekte, leakage_delay_s=1e-6))
        rx = generate_pulsed_echo(c).beat
        self.assertEqual(np.count_nonzero(abs(rx[0]) > 0), 5)
        self.assertTrue(np.all(rx[:, :c.pulse_samples] == 0))

    def test_saettigung_huelle_phase_und_zaehler(self):
        x = np.array([0, 1, -2j, 3+4j], complex)
        y, anteil = begrenze_empfang(x, Stoereffekte(saettigung=True, saettigung_db=0))
        np.testing.assert_allclose(y, [0, 1, -1j, .6+.8j], atol=1e-15)
        self.assertEqual(anteil, .5)
        # Der radiale Ersatzbegrenzer kommutiert mit einem idealen Mischer.
        rot = np.exp(1j*np.arange(4))
        yr, _ = begrenze_empfang(x*rot, Stoereffekte(saettigung=True, saettigung_db=0))
        np.testing.assert_allclose(yr, y*rot, atol=1e-15)

    def test_saettigung_liegt_vor_digitalem_abzug(self):
        c = RadarConfig(targets=(Target(40, -5, .001),), noise_enabled=False,
                        effekte=Stoereffekte(leakage=True, leakage_db=40, saettigung=True, saettigung_db=0))
        f = simulate_frame(c)
        self.assertEqual(f.echo.clipped_fraction, 1.)
        self.assertLessEqual(float(np.abs(f.echo.beat).max()), 1+1e-14)
        self.assertIsNotNone(f.vergleich)
        self.assertFalse(np.array_equal(f.spectrum.power, f.vergleich.power))

    def test_phasenrauschen_covarianz_und_laufzeitkorrelation(self):
        e = Stoereffekte(phasenrauschen=True, phase_rms_rad=.5, phase_zeit_s=10e-6)
        c = RadarConfig(effekte=e)
        t = np.arange(50, 5000)*e.phase_zeit_s/8
        phasen, kurz, lang = [], [], []
        for frame in range(12):
            p = Phasenprozess(c, frame, 100e-6)
            np.testing.assert_array_equal(p.restphase(t, 0), 0)
            phasen.extend(p.werte(t))
            kurz.extend(p.restphase(t, e.phase_zeit_s))
            lang.extend(p.restphase(t, 8*e.phase_zeit_s))
        # Reproduzierbare Stichprobe, rund 7000 Korrelationszeiten insgesamt.
        self.assertAlmostEqual(np.mean(np.square(phasen)), .25, delta=.025)
        erwartet = 2*.25*(1-math.exp(-.5))
        self.assertAlmostEqual(np.mean(np.square(kurz)), erwartet, delta=.02)
        self.assertAlmostEqual(np.mean(np.square(lang)), .5, delta=.05)
        self.assertLess(np.mean(np.square(kurz)), np.mean(np.square(lang)))

    def test_erdhorizont_gegen_tangentenwinkel(self):
        e = Stoereffekte(erdkruemmung=True)
        re = ERDRADIUS_M*e.erdradius_faktor
        h1, h2 = 20., 1000.
        grenze = re*(math.acos(re/(re+h1))+math.acos(re/(re+h2)))
        rx, _ = erdkoordinaten((0, 0, h1), (0, 0, 0), e)
        for faktor, sichtbar in ((.999, True), (1.001, False)):
            ziel, _ = erdkoordinaten((faktor*grenze, 0, h2), (0, 0, 0), e)
            self.assertEqual(freie_sicht(rx, ziel, e), sichtbar)
        # Bekannte Tangentenlänge sqrt(2Re h + h²), unabhängig vom Segmenttest.
        self.assertAlmostEqual(math.sqrt((re+h1)**2-re**2), math.sqrt(2*re*h1+h1*h1), delta=1e-6)

    def test_kugelgeschwindigkeit_und_doppler_gegen_ableitung(self):
        e = Stoereffekte(erdkruemmung=True)
        p, v = np.array([200000., 30000., 3000.]), np.array([-150., 20., -4.])
        dt = .01
        ort, tempo = erdkoordinaten(p, v, e)
        vor, _ = erdkoordinaten(p-v*dt, v, e)
        nach, _ = erdkoordinaten(p+v*dt, v, e)
        np.testing.assert_allclose(tempo, (nach-vor)/(2*dt), atol=1e-6)
        r, vr, _, _ = monostatische_geometrie(p, v, (0, 0, 20), (0, 0, 0), e)
        rm = monostatische_geometrie(p-v*dt, v, (0, 0, 20), (0, 0, 0), e)[0]
        rp = monostatische_geometrie(p+v*dt, v, (0, 0, 20), (0, 0, 0), e)[0]
        self.assertAlmostEqual(vr, (rp-rm)/(2*dt), delta=1e-6)
        self.assertGreater(r, 190000)

    def test_horizont_entfernt_echo_aber_nicht_sollwert(self):
        c = effektbeispiele()["Fernbereich · hinter dem Erdhorizont"][1]
        f = simulate_frame(c)
        self.assertEqual(len(f.config.targets), 1)
        self.assertEqual(f.config.targets[0].path_gain, 0)
        self.assertEqual(len(f.candidates), 0)
        self.assertEqual(float(f.spectrum.power.max()), 0)
        self.assertGreater(float(f.vergleich.power.max()), 0)

    def test_atmosphaere_zweiweg_leistung_und_amplitude(self):
        c = effektbeispiele()["Fernbereich · atmosphärische Dämpfung"][1]
        f = simulate_frame(c)
        ideal = simulate_frame(replace(c, effekte=replace(c.effekte, atmosphaere=False)))
        verlust = c.effekte.daempfung_db_km*2*f.config.targets[0].range_m/1000
        np.testing.assert_allclose(f.echo.beat, ideal.echo.beat*10**(-verlust/20), atol=1e-14)
        self.assertAlmostEqual(10*np.log10(f.spectrum.power.max()/ideal.spectrum.power.max()), -verlust, places=9)

    def test_passiv_atmosphaere_zaehlt_beide_wege(self):
        c = replace(passiv_config(), noise_enabled=False, effekte=Stoereffekte(atmosphaere=True, daempfung_db_km=.2))
        f = simulate_frame(c)
        z = f.flugzustaende[0]
        rt = np.linalg.norm(np.array(z.position_m)-c.passiv.senderort)
        rr = np.linalg.norm(z.position_m)
        erwartet = -.2*(rt+rr)/1000
        self.assertAlmostEqual(10*np.log10(f.spectrum.power.max()/f.vergleich.power.max()), erwartet, places=9)

    def test_teilpuls_energie_und_matched_filter_analytisch(self):
        # Ganzzahlige Verzögerung 30 Samples, langer Puls 60 Samples.
        c = replace(effektbeispiele()["Puls · unvollständiges Nah-Echo"][1], targets=(Target(C*30/(2*5e6)),))
        rx = generate_pulsed_echo(c)
        self.assertEqual(np.count_nonzero(abs(rx.beat[0]) > 0), 30)
        spektrum = process_pulses(rx.beat, c)
        self.assertAlmostEqual(float(spektrum.power.max()), .25, places=10)
        kurz = replace(c, chirp_s=4e-6)
        self.assertAlmostEqual(float(process_pulses(generate_pulsed_echo(kurz).beat, kurz).power.max()), 1., places=10)

    def test_bodenstatistik_flaeche_und_feste_streuer(self):
        e = Stoereffekte(bodenclutter=True, clutter_innen_m=20, clutter_aussen_m=80, sigma0_db=-20)
        c = RadarConfig(effekte=e, targets=())
        p1, p2 = bodenpunkte(c), bodenpunkte(c)
        np.testing.assert_array_equal(np.array([q[0] for q in p1]), np.array([q[0] for q in p2]))
        self.assertEqual([q[1:] for q in p1], [q[1:] for q in p2])
        werte = [sum(q[1] for q in bodenpunkte(replace(c, seed=seed))) for seed in range(200)]
        erwartet = .01*np.pi*(80**2-20**2)
        self.assertAlmostEqual(np.mean(werte), erwartet, delta=.04*erwartet)

    def test_clutter_geht_auch_didaktisch_nach_radargleichung(self):
        e = Stoereffekte(bodenclutter=True, clutter_innen_m=20, clutter_aussen_m=80, clutter_ringe=2, clutter_sektoren=8)
        c = RadarConfig(effekte=e, targets=())
        radar = replace(c, amplitude_model="radar")
        a = [target_amplitude(c, q) for q in aktive_bodenquellen(c, c)]
        b = [target_amplitude(radar, q) for q in aktive_bodenquellen(radar, radar)]
        np.testing.assert_allclose(a, b, rtol=1e-14)
        self.assertTrue(all(q.velocity_mps == 0 for q in aktive_bodenquellen(c, c)))

    def test_bewegtes_radar_erzeugt_boden_doppler(self):
        from radar_sim.flugbahn import Flugzustand
        e = Stoereffekte(bodenclutter=True, clutter_innen_m=20, clutter_aussen_m=80, clutter_ringe=1, clutter_sektoren=8)
        c = RadarConfig(carrier_hz=3e9, chirps=32, targets=(), effekte=e)
        radar = Flugzustand(0, 30, 100, 0, 30, 0)
        quellen = aktive_bodenquellen(c, c, radar)
        self.assertTrue(any(q.velocity_mps > 0 for q in quellen))
        self.assertTrue(any(q.velocity_mps < 0 for q in quellen))
        for (ort, _, _), q in zip(bodenpunkte(c), quellen):
            erwartet = -100*ort[0]/np.linalg.norm(ort-np.array([0, 0, 30]))
            self.assertAlmostEqual(q.velocity_mps, erwartet, places=12)

    def test_passiver_gemeinsamer_lo_und_begrenzer(self):
        c = replace(passiv_config(), noise_enabled=False, effekte=Stoereffekte(phasenrauschen=True, phase_zeit_s=100e-6))
        kanal = erzeuge_passivempfang(c, [], 0)
        self.assertEqual(float(kreuzambiguitaet(kanal, c).power.max()), 0)
        c = replace(c, effekte=replace(c.effekte, saettigung=True, saettigung_db=0))
        kanal = erzeuge_passivempfang(c, [], 0)
        self.assertGreater(kanal.clipped_fraction, .9)
        self.assertGreater(kanal.reference_clipped_fraction, 0)
        self.assertLessEqual(float(np.abs(kanal.ueberwachung).max()), 1+1e-14)

    def test_json_seed_und_ungueltige_effekte(self):
        c = effektbeispiele()["FMCW · Empfänger übersteuert"][1]
        self.assertEqual(RadarConfig.from_dict(c.to_dict()), c)
        np.testing.assert_array_equal(generate_echo(c).beat, generate_echo(c).beat)
        for e in (replace(c.effekte, saettigung=1), replace(c.effekte, phase_rms_rad=float("nan")),
                  replace(c.effekte, clutter_ringe=2.5), replace(c.effekte, clutter_aussen_m=1)):
            with self.assertRaises(ValueError):
                validate_config(replace(c, effekte=e))
        with self.assertRaises(ValueError):
            validate_config(replace(passiv_config(), effekte=Stoereffekte(leakage=True)))
        with self.assertRaises(ValueError):
            validate_config(replace(c, effekte=Stoereffekte(erdkruemmung=True)))

    def test_parametergrenzen_mit_stoerungen_und_adc_nullmodell(self):
        from radar_sim.parametergrenzen import berechne_parameterbereiche
        ganze = {"chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples"}
        for name, (_, c) in effektbeispiele().items():
            for feld, b in berechne_parameterbereiche(c).items():
                if b.leer:
                    continue
                for wert in (b.minimum, b.maximum, b.begrenze_wert((b.minimum+b.maximum)/2)):
                    x = int(round(wert)) if feld in ganze else wert
                    with self.subTest(demo=name, feld=feld, wert=x):
                        validate_config(replace(c, **{feld: x}))
        c = effektbeispiele()["FMCW · Leakage und Phasenrauschen"][1]
        b = berechne_parameterbereiche(c)["adc_skip_samples"]
        self.assertTrue(b.null_erlaubt)
        self.assertGreaterEqual(b.minimum, 2)
        validate_config(replace(c, adc_skip_samples=0))
        with self.assertRaises(ValueError):
            validate_config(replace(c, adc_skip_samples=1))


if __name__ == "__main__":
    unittest.main()
