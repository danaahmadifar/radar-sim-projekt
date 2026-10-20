"""Routenlänge, konstantes Tempo, radiale Projektion und JSON-Rückweg."""

from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np

from radar_sim import RadarConfig, simulate_frame, validate_config
from radar_sim.flugbahn import erstelle_routenszene, berechne_flugzustand
from radar_sim.route import GezeichneteRoute, berechne_routendaten, routen_position, punkt_auf_route
from radar_sim.io import save_config, load_config


class RoutenTests(unittest.TestCase):
    def test_dreidiagonale_loesung_entspricht_unabhaengiger_matrix(self) -> None:
        zufall = np.random.default_rng(20261019)
        punkte = np.column_stack((np.cumsum(zufall.uniform(10, 100, 37)),
                                  zufall.uniform(-80, 80, 37), zufall.uniform(500, 800, 37)))
        route = GezeichneteRoute(tuple(map(tuple, punkte)), 5)
        daten = berechne_routendaten(route)
        abstand = np.linalg.norm(np.diff(punkte, axis=0), axis=1)
        matrix = np.eye(len(punkte))
        rechts = np.zeros_like(punkte)
        for i in range(1, len(punkte)-1):
            a, b = abstand[i-1:i+1]
            matrix[i, i-1:i+2] = [a, 2*(a+b), b]
            rechts[i] = 6*((punkte[i+1]-punkte[i])/b-(punkte[i]-punkte[i-1])/a)
        referenz = np.linalg.solve(matrix, rechts)
        berechnet = 2*daten.koeffizienten[:, 2]/abstand[:, None]**2
        np.testing.assert_allclose(berechnet, referenz[:-1], rtol=1e-11, atol=1e-12)
        self.assertIs(daten, berechne_routendaten(replace(route, geschwindigkeit_mps=50)))

    def test_256_punkte_und_lange_flugdauer_brauchen_keine_frame_sammlung(self) -> None:
        winkel = np.linspace(0, 8*np.pi, 256)
        punkte = tuple((float(60*np.cos(a)), float(60*np.sin(a)), 60.) for a in winkel)
        route = GezeichneteRoute(punkte, .05)
        szene = erstelle_routenszene(route, 30.)
        self.assertGreater(szene.dauer_s, 120)
        config = RadarConfig(targets=(), flugszene=szene, noise_enabled=False)
        validate_config(config)
        for index in (0, szene.letzter_frame//2, szene.letzter_frame):
            frame = simulate_frame(config, index)
            self.assertEqual(frame.echo.beat.shape, (config.chirps, config.samples))
            z = frame.flugzustaende[0]
            self.assertAlmostEqual(math.hypot(z.geschwindigkeit_x_mps, z.geschwindigkeit_y_mps,
                                             z.geschwindigkeit_hoehe_mps), .05)
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner)/"lange_route.json"
            save_config(datei, config)
            self.assertEqual(load_config(datei), config)

    def test_kurvenpunkt_bei_rechtsklick_bewahrt_die_dritte_koordinate(self) -> None:
        route = GezeichneteRoute(((0., 10., 20.), (100., 30., 60.)), 5)
        for achsen in ((0,1), (0,2), (1,2)):
            erwarteter_punkt = np.array([40.,18.,36.])
            abschnitt, punkt, abstand = punkt_auf_route(route, achsen, erwarteter_punkt[list(achsen)], (2., 3.))
            self.assertEqual(abschnitt, 0)
            np.testing.assert_allclose(punkt, erwarteter_punkt, atol=1e-10)
            self.assertAlmostEqual(abstand, 0, places=10)

    def test_gerade_strecke_hat_analytische_zeitzuordnung(self) -> None:
        route = GezeichneteRoute(((-60., 35.), (60., 35.)), 5)
        daten = berechne_routendaten(route)
        self.assertAlmostEqual(daten.laenge_m, 120, places=10)
        self.assertAlmostEqual(daten.kruemmungsgrenze_pro_m, 0, places=12)
        self.assertEqual(routen_position(route, 8), (-20., 35., 5., 0.))
        self.assertAlmostEqual(erstelle_routenszene(route).dauer_s, 24)

    def test_kurven_tempo_und_ableitung_auch_bei_ungleichen_punktabstaenden(self) -> None:
        route = GezeichneteRoute(((-80., 35.), (-65., 45.), (0., 65.), (70., 30.)), 5)
        szene = erstelle_routenszene(route)
        bahn = szene.bahnen[0]
        for zeit in np.linspace(0.01, szene.dauer_s - 0.01, 61):
            z = berechne_flugzustand(bahn, float(zeit))
            self.assertAlmostEqual(math.hypot(z.geschwindigkeit_x_mps, z.geschwindigkeit_hoehe_mps), 5, places=10)
            dt = 1e-4
            a = berechne_flugzustand(bahn, zeit - dt)
            b = berechne_flugzustand(bahn, zeit + dt)
            self.assertAlmostEqual((b.x_m - a.x_m) / (2 * dt), z.geschwindigkeit_x_mps, places=5)
            self.assertAlmostEqual((b.hoehe_m - a.hoehe_m) / (2 * dt), z.geschwindigkeit_hoehe_mps, places=5)
            self.assertAlmostEqual((b.entfernung_m - a.entfernung_m) / (2 * dt), z.radialgeschwindigkeit_mps, places=5)
        self.assertAlmostEqual(berechne_flugzustand(bahn, 0).x_m, -80)
        self.assertAlmostEqual(berechne_flugzustand(bahn, szene.dauer_s).x_m, 70)

    def test_schneller_fliegen_halbiert_dauer_und_verdoppelt_tempo(self) -> None:
        a = GezeichneteRoute(((-80., 35.), (0., 55.), (80., 35.)), 4)
        b = replace(a, geschwindigkeit_mps=8)
        sa, sb = erstelle_routenszene(a), erstelle_routenszene(b)
        self.assertAlmostEqual(sa.dauer_s, 2 * sb.dauer_s)
        za = berechne_flugzustand(sa.bahnen[0], 10)
        zb = berechne_flugzustand(sb.bahnen[0], 5)
        self.assertAlmostEqual(za.x_m, zb.x_m)
        self.assertAlmostEqual(za.hoehe_m, zb.hoehe_m)
        self.assertAlmostEqual(zb.radialgeschwindigkeit_mps, 2 * za.radialgeschwindigkeit_mps)

    def test_route_mit_radar_und_export_reproduzierbar(self) -> None:
        route = GezeichneteRoute(((-80., 35.), (0., 55.), (80., 35.)), 5)
        config = RadarConfig(targets=(), flugszene=erstelle_routenszene(route))
        validate_config(config)
        a = simulate_frame(config, 30)
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner) / "route.json"
            save_config(datei, config)
            geladen = load_config(datei)
            self.assertEqual(geladen, config)
            b = simulate_frame(geladen, 30)
            np.testing.assert_array_equal(a.echo.beat, b.echo.beat)
        letzter = simulate_frame(config, config.flugszene.letzter_frame)
        self.assertAlmostEqual(letzter.flugzustaende[0].x_m, 80, places=8)

    def test_boden_doppelte_punkte_und_spitzkehren_werden_abgewiesen(self) -> None:
        schlechte_punkte = [
            ((0., 0.), (10., 20.)), ((0., 30.), (0., 30.)),
            ((-20., 30.), (0., 30.), (-20., 30.)),
            ((-90., 0.1), (-80., 0.1), (0., 100.), (80., 0.1), (90., 0.1)),
        ]
        for punkte in schlechte_punkte:
            with self.subTest(punkte=punkte), self.assertRaises(ValueError):
                berechne_routendaten(GezeichneteRoute(punkte))
        with self.assertRaises(ValueError):
            berechne_routendaten(GezeichneteRoute(((-10., 30.), (10., 30.)), 0))

    def test_beschleunigungsgrenze_gilt_auch_fuer_enge_routen(self) -> None:
        route = GezeichneteRoute(((-30., 35.), (0., 65.), (30., 35.)), 15)
        with self.assertRaises(ValueError):
            validate_config(RadarConfig(targets=(), flugszene=erstelle_routenszene(route)))


if __name__ == "__main__":
    unittest.main()
