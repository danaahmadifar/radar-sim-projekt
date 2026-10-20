"""Prüft Fluggeometrie, Vorzeichen, Zeitablauf und gespeicherte Flugbahnen."""

from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest
import numpy as np

from radar_sim import RadarConfig, Target, simulate_frame, validate_config
from radar_sim.flugbahn import Flugbahn, Flugszene, berechne_flugzustand, flugszenen
from radar_sim.io import load_config, save_config


class FlugbahnTests(unittest.TestCase):
    def test_gerader_ueberflug_mit_hoehe_und_radialem_vorzeichen(self) -> None:
        bahn = Flugbahn()
        anfang = berechne_flugzustand(bahn, 0)
        mitte = berechne_flugzustand(bahn, 10)
        ende = berechne_flugzustand(bahn, 20)
        self.assertAlmostEqual(anfang.entfernung_m, math.sqrt(100**2 + 35**2))
        self.assertAlmostEqual(anfang.radialgeschwindigkeit_mps, -1000 / anfang.entfernung_m)
        self.assertEqual(mitte.x_m, 0)
        self.assertEqual(mitte.entfernung_m, 35)
        self.assertEqual(mitte.radialgeschwindigkeit_mps, 0)
        self.assertEqual(mitte.geschwindigkeit_x_mps, 10)  # Das Objekt fliegt trotzdem weiter.
        self.assertAlmostEqual(ende.radialgeschwindigkeit_mps, -anfang.radialgeschwindigkeit_mps)

    def test_zwei_flugrichtungen_sind_nicht_zwei_radialvorzeichen(self) -> None:
        szene = flugszenen()["07_gegenverkehr"]
        a, b = [berechne_flugzustand(bahn, 0) for bahn in szene.bahnen]
        self.assertGreater(a.geschwindigkeit_x_mps, 0)
        self.assertLess(b.geschwindigkeit_x_mps, 0)
        # Zu Beginn fliegen beide von gegenüberliegenden Seiten zur Station hin.
        self.assertLess(a.radialgeschwindigkeit_mps, 0)
        self.assertLess(b.radialgeschwindigkeit_mps, 0)
        self.assertNotEqual(a.hoehe_m, b.hoehe_m)

    def test_parabel_und_numerische_ableitung_der_entfernung(self) -> None:
        bahn = flugszenen()["08_parabel"].bahnen[0]
        for zeit in np.linspace(0.1, 19.9, 41):
            zustand = berechne_flugzustand(bahn, float(zeit))
            self.assertAlmostEqual(zustand.hoehe_m, 45 - 0.002 * zustand.x_m**2)
            delta = 1e-4
            vorher = berechne_flugzustand(bahn, zeit - delta).entfernung_m
            nachher = berechne_flugzustand(bahn, zeit + delta).entfernung_m
            self.assertAlmostEqual((nachher - vorher) / (2 * delta), zustand.radialgeschwindigkeit_mps, places=6)
        self.assertEqual(berechne_flugzustand(bahn, 10).hoehe_m, 45)

    def test_frames_bewegen_sich_und_lassen_sich_wiederholen(self) -> None:
        szene = flugszenen()["06_ueberflug"]
        config = RadarConfig(targets=(), flugszene=szene)
        a, b, c = [simulate_frame(config, index) for index in (0, 100, 200)]
        self.assertEqual(a.input_config, config)
        self.assertIsNone(a.config.flugszene)
        self.assertEqual(b.zeit_s, 10)
        self.assertEqual(b.config.targets[0].range_m, 35)
        self.assertEqual(c.zeit_s, 20)
        np.testing.assert_array_equal(a.echo.beat, simulate_frame(config, 0).echo.beat)
        self.assertFalse(np.array_equal(a.echo.beat, b.echo.beat))
        with self.assertRaisesRegex(ValueError, "beendet"):
            simulate_frame(config, 201)
        with self.assertRaises(ValueError):
            simulate_frame(config, -1)

    def test_ungueltige_flugbahnen_werden_frueh_erkannt(self) -> None:
        basis = flugszenen()["06_ueberflug"]
        ungueltige_szenen = [
            replace(basis, dauer_s=float("nan")), replace(basis, bahnen=()),
            replace(basis, zeitschritt_s=0), replace(basis, bahnen=(Flugbahn(start_hoehe_m=-1),)),
            replace(basis, bahnen=(Flugbahn(geschwindigkeit_x_mps=100),)),
            replace(basis, bahnen=(Flugbahn(start_x_m=1000),)),
            # Höhe fällt zwischen den positiven Endpunkten unter null: Scheitel prüfen!
            replace(basis, bahnen=(Flugbahn(-100, 35, 10, -10, 1),)),
        ]
        for szene in ungueltige_szenen:
            with self.subTest(szene=szene):
                with self.assertRaises(ValueError):
                    validate_config(RadarConfig(targets=(), flugszene=szene))
        with self.assertRaisesRegex(ValueError, "nicht beide"):
            validate_config(RadarConfig(targets=(Target(),), flugszene=basis))
        with self.assertRaisesRegex(ValueError, "ändert"):
            validate_config(RadarConfig(targets=(), flugszene=basis, chirps=256))

    def test_json_neues_und_altes_format(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            datei = Path(ordner) / "flug.json"
            for szene in flugszenen().values():
                config = RadarConfig(targets=(), flugszene=szene)
                save_config(datei, config)
                self.assertEqual(load_config(datei), config)
            alt = RadarConfig().to_dict()
            alt.pop("flugszene")
            alt["schema_version"] = 1
            self.assertEqual(RadarConfig.from_dict(alt), RadarConfig())


if __name__ == "__main__":
    unittest.main()
