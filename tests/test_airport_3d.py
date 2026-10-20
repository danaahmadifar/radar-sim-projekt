"""Unabhängige Raumgeometrie, spätes ADC-Fenster und relative Antennenwirkung."""

from dataclasses import replace
import math
import tempfile
from pathlib import Path
import unittest
import numpy as np

from radar_sim import RadarConfig, Target, simulate_frame, validate_config
from radar_sim.antenne import Antenne, antennenbasis, antennengewinn, keulenrand
from radar_sim.flughafen import flughafen_config, flughafenszenen
from radar_sim.flugbahn import Flugbahn, berechne_flugzustand, erstelle_routenszene
from radar_sim.route import GezeichneteRoute, berechne_routendaten, routen_position_3d
from radar_sim.parametergrenzen import berechne_parameterbereiche
from radar_sim.model import dechirp, generate_echo, target_amplitude
from radar_sim.evaluation import match_targets
from radar_sim.io import save_config, load_config


class AirportTests(unittest.TestCase):
    def test_adc_ueberlappung_und_entfernungsaufloesung(self):
        c = replace(flughafen_config(), flugszene=None, targets=(Target(5000),), noise_enabled=False,
                    amplitude_model="didactic")
        validate_config(c)
        self.assertEqual(c.samples, 400)
        self.assertAlmostEqual(c.adc_start_s, 40e-6)
        self.assertAlmostEqual(c.range_resolution, 29.9792458)
        echo = generate_echo(c)
        t = echo.fast_time_s
        tau = 10000/299792458
        self.assertTrue(np.all(t >= tau))
        self.assertTrue(np.all(t < c.chirp_s))
        tx = np.exp(1j*np.pi*c.slope*t**2)
        rx = np.exp(1j*(np.pi*c.slope*(t-tau)**2-2*np.pi*c.carrier_hz*tau))
        np.testing.assert_allclose(echo.beat[0], dechirp(tx, rx), atol=2e-9)
        with self.assertRaises(ValueError):
            validate_config(replace(c, adc_skip_samples=300))

    def test_airport_anflug_und_gegenverkehr_jeder_zeitpunkt(self):
        for name in ("10_flughafen_anflug", "11_flughafen_gegenverkehr"):
            c = flughafen_config(name)
            for nummer in range(c.flugszene.letzter_frame+1):
                f = simulate_frame(c, nummer)
                paare = match_targets(f.config, f.candidates)
                self.assertEqual(len(paare), len(c.flugszene.bahnen), (name, nummer))
                for p in paare:
                    # FFT-Maximum ohne Interpolation: etwa halber Bin plus Kopplung.
                    self.assertLessEqual(abs(p.range_error_m), c.range_resolution*.55)
                    self.assertLessEqual(abs(p.velocity_error_mps), c.velocity_resolution*.55)

    def test_bereiche_mit_adc_vorlauf_und_drei_koordinaten(self):
        for name in flughafenszenen():
            c = flughafen_config(name)
            for key, b in berechne_parameterbereiche(c).items():
                self.assertFalse(b.leer, (name, key))
                for wert in (b.minimum, b.maximum, (b.minimum+b.maximum)/2):
                    wert = b.begrenze_wert(wert)
                    if key in ("chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples"):
                        wert = round(wert)
                    with self.subTest(name=name, key=key, wert=wert):
                        validate_config(replace(c, **{key: wert}))


class RaumTests(unittest.TestCase):
    def test_radiale_projektion_und_raumtempo(self):
        bahn = Flugbahn(-3000, 500, 70, -3, start_y_m=600, geschwindigkeit_y_mps=-15)
        for t in (0., 8., 20.):
            z = berechne_flugzustand(bahn, t)
            ort = np.array([-3000+70*t, 600-15*t, 500-3*t])
            self.assertAlmostEqual(z.entfernung_m, np.linalg.norm(ort))
            self.assertAlmostEqual(z.radialgeschwindigkeit_mps, ort@np.array([70,-15,-3])/np.linalg.norm(ort))

    def test_3d_route_konstantes_tempo_und_numerische_ableitungen(self):
        route = GezeichneteRoute(((-4000., -500., 400.), (-3000., 0., 600.),
                                 (-1800., 600., 500.), (-700., 900., 350.)), 70)
        szene = erstelle_routenszene(route, .5, 10)
        c = replace(flughafen_config(), flugszene=szene)
        validate_config(c)
        for t in np.linspace(.01, szene.dauer_s-.01, 51):
            z = berechne_flugzustand(szene.bahnen[0], float(t))
            v = np.array([z.geschwindigkeit_x_mps, z.geschwindigkeit_y_mps, z.geschwindigkeit_hoehe_mps])
            self.assertAlmostEqual(np.linalg.norm(v), 70, places=9)
            dt = 1e-4
            vorher = berechne_flugzustand(szene.bahnen[0], t-dt)
            nachher = berechne_flugzustand(szene.bahnen[0], t+dt)
            np.testing.assert_allclose((np.array(nachher.position_m)-vorher.position_m)/(2*dt), v, atol=2e-5)
            self.assertAlmostEqual((nachher.entfernung_m-vorher.entfernung_m)/(2*dt), z.radialgeschwindigkeit_mps, places=5)
        with tempfile.TemporaryDirectory() as ordner:
            p = Path(ordner)/"3d.json"
            save_config(p, c)
            self.assertEqual(c, load_config(p))


class AntennenTests(unittest.TestCase):
    def test_gauss_halbwert_und_zweiweg_leistung(self):
        a = Antenne(typ="faecher", azimut_grad=0, elevation_grad=0, breite_az_grad=12, breite_el_grad=40)
        self.assertAlmostEqual(float(antennengewinn(a, [1,0,0], 9.3e9)), 1)
        p = [math.cos(math.radians(6)), math.sin(math.radians(6)), 0]
        g = float(antennengewinn(a, p, 9.3e9))
        self.assertAlmostEqual(g, .5)
        c = RadarConfig(amplitude_model="didactic")
        self.assertAlmostEqual(target_amplitude(c, Target(40, antenna_gain=g))**2, .25)
        self.assertEqual(float(antennengewinn(a, [-1,0,0], 9.3e9)), 0)

    def test_patch_array_nullstelle_und_parabol_breite(self):
        a = Antenne(typ="patch_array", azimut_grad=0, elevation_grad=0, elemente_horizontal=16)
        self.assertAlmostEqual(float(antennengewinn(a, [1,0,0], 9.3e9)), 1)
        self.assertLess(float(antennengewinn(a, [math.sqrt(1-(2/16)**2), 2/16, 0], 9.3e9)), 1e-28)
        a = replace(a, typ="parabol", durchmesser_m=.6)
        winkel = math.radians(70*(299792458/9.3e9)/.6/2)
        self.assertAlmostEqual(float(antennengewinn(a, [math.cos(winkel),math.sin(winkel),0], 9.3e9)), .5)

    def test_keulenrand_ist_halbwertsgrenze_in_drei_dimensionen(self):
        for typ in ("patch_array", "parabol", "faecher"):
            a = Antenne(typ=typ, azimut_grad=140, elevation_grad=13)
            rand = keulenrand(a, 9.3e9)
            np.testing.assert_allclose(np.linalg.norm(rand, axis=1), a.zeichenlaenge_m, atol=1e-9)
            np.testing.assert_allclose(antennengewinn(a, rand, 9.3e9), .5, atol=2e-7)

    def test_antenne_wirkt_im_echo_zeichenlaenge_nicht(self):
        c = replace(flughafen_config(), noise_enabled=False)
        f = simulate_frame(c)
        andere_laenge = simulate_frame(replace(c, antenne=replace(c.antenne, zeichenlaenge_m=1000)))
        np.testing.assert_array_equal(f.echo.beat, andere_laenge.echo.beat)
        abgewandt = simulate_frame(replace(c, antenne=replace(c.antenne, azimut_grad=0)))
        np.testing.assert_array_equal(abgewandt.echo.beat, np.zeros_like(f.echo.beat))
        self.assertEqual(len(abgewandt.candidates), 0)


if __name__ == "__main__":
    unittest.main()
