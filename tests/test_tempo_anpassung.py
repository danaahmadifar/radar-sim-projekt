"""Hohe Geschwindigkeiten müssen gültige Radarframes statt Aliasing ergeben."""

from dataclasses import replace
import unittest

from radar_sim.config import RadarConfig, Target, validate_config
from radar_sim.flughafen import flughafen_config
from radar_sim.flugbahn import berechne_flugzustand
from radar_sim.evaluation import match_targets
from radar_sim.pipeline import simulate_frame
from radar_sim.tempo_anpassung import passe_radar_an_tempo


class TempoTests(unittest.TestCase):
    def test_gegenverkehr_100_bis_1500_mps_mit_analytischer_referenz(self):
        original = replace(flughafen_config("11_flughafen_gegenverkehr"), noise_enabled=False)
        szene = original.flugszene
        for tempo in (100, 250, 500, 1000, 1500):
            faktor = tempo/70
            bahnen = tuple(replace(b, geschwindigkeit_x_mps=b.geschwindigkeit_x_mps*faktor)
                           for b in szene.bahnen)
            c = passe_radar_an_tempo(replace(original, flugszene=replace(
                szene, bahnen=bahnen, dauer_s=szene.dauer_s/faktor)))
            validate_config(c)
            self.assertGreater(c.max_velocity, tempo)
            for index in (0, c.flugszene.letzter_frame//2, c.flugszene.letzter_frame):
                with self.subTest(tempo=tempo, frame=index):
                    frame = simulate_frame(c, index)
                    matches = match_targets(frame.config, frame.candidates)
                    self.assertEqual(len(matches), 2)
                    for m in matches:
                        # FFT-Peak ohne Interpolation: bis ½ Doppler-Bin.
                        self.assertLessEqual(abs(m.velocity_error_mps), c.velocity_resolution/2+1e-9)
                        # Range-Korrektur übernimmt zusätzlich den Doppler-Binfehler.
                        toleranz = c.range_resolution/2+c.carrier_hz/c.slope*c.velocity_resolution/2
                        self.assertLessEqual(abs(m.range_error_m), toleranz+1e-9)
                    for alt, neu in zip(szene.bahnen, bahnen):
                        self.assertEqual(berechne_flugzustand(alt, szene.dauer_s).position_m,
                                         berechne_flugzustand(neu, c.flugszene.dauer_s).position_m)

    def test_gueltige_eingaben_bleiben_und_ungueltige_geometrie_wird_abgelehnt(self):
        c = flughafen_config()
        self.assertIs(passe_radar_an_tempo(c), c)
        bodenkontakt = replace(c.flugszene.bahnen[0], start_hoehe_m=-1)
        with self.assertRaisesRegex(ValueError, "über dem Boden"):
            passe_radar_an_tempo(replace(c, flugszene=replace(c.flugszene, bahnen=(bodenkontakt,))))
        fest = passe_radar_an_tempo(RadarConfig(targets=(Target(100, -700),), noise_enabled=False))
        frame = simulate_frame(fest)
        self.assertGreater(fest.max_velocity, 700)
        self.assertEqual(len(match_targets(frame.config, frame.candidates)), 1)
