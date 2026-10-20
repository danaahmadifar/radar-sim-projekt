"""Die angezeigten Bereiche müssen zur vorhandenen Kernprüfung passen."""

from dataclasses import replace
import random
import unittest

from radar_sim import RadarConfig, Target, validate_config
from radar_sim.flugbahn import flugszenen, erstelle_routenszene
from radar_sim.parametergrenzen import berechne_parameterbereiche, bereich_fuer_tabellenwert, ParameterBereich
from radar_sim.route import GezeichneteRoute

GANZ = ("chirps", "seed", "training_range", "training_doppler", "guard_range", "guard_doppler", "adc_skip_samples")


class ParameterGrenzenTests(unittest.TestCase):
    def test_minimum_maximum_und_mitte_sind_gueltig(self) -> None:
        configs = [RadarConfig(), RadarConfig(targets=(Target(40, -5),)), RadarConfig(targets=())]
        configs += [RadarConfig(targets=(), flugszene=s) for s in flugszenen().values()]
        route = GezeichneteRoute(((-80., 35.), (0., 55.), (80., 35.)))
        configs.append(RadarConfig(targets=(), flugszene=erstelle_routenszene(route)))
        for config in configs:
            for name, bereich in berechne_parameterbereiche(config).items():
                self.assertFalse(bereich.leer, name)
                for wert in (bereich.minimum, bereich.maximum, (bereich.minimum + bereich.maximum) / 2):
                    wert = bereich.begrenze_wert(wert)
                    if name in GANZ:
                        wert = int(round(wert))
                    with self.subTest(name=name, wert=wert):
                        validate_config(replace(config, **{name: wert}))

    def test_3600_bereichspruefungen_nach_reproduzierbaren_aenderungen(self) -> None:
        config = RadarConfig(targets=(), flugszene=flugszenen()["07_gegenverkehr"])
        zufall = random.Random(42)
        for durchlauf in range(80):
            bereiche = berechne_parameterbereiche(config)
            for name, b in bereiche.items():
                for wert in (b.minimum, b.maximum, (b.minimum + b.maximum) / 2):
                    wert = b.begrenze_wert(wert)
                    if name in GANZ:
                        wert = int(round(wert))
                    with self.subTest(durchlauf=durchlauf, name=name, wert=wert):
                        validate_config(replace(config, **{name: wert}))
            name = zufall.choice(list(bereiche))
            b = bereiche[name]
            wert = b.begrenze_wert(b.minimum + zufall.random() * (b.maximum - b.minimum))
            if name in GANZ:
                wert = int(round(wert))
            config = replace(config, **{name: wert})
            validate_config(config)

    def test_bandbreite_aendert_sampling_und_timingbereiche(self) -> None:
        config = RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"])
        a = berechne_parameterbereiche(config)
        b = berechne_parameterbereiche(replace(config, bandwidth_hz=250e6))
        self.assertGreater(b["chirp_s"].minimum, a["chirp_s"].minimum)
        self.assertGreater(b["sample_rate_hz"].minimum, a["sample_rate_hz"].minimum)
        self.assertGreater(b["carrier_hz"].minimum, a["carrier_hz"].minimum)
        self.assertAlmostEqual(b["chirp_s"].schritt, 1 / config.sample_rate_hz)
        self.assertAlmostEqual(b["sample_rate_hz"].schritt, 1 / config.chirp_s)

    def test_leere_bereiche_werden_explizit_gemeldet(self) -> None:
        config = RadarConfig(bandwidth_hz=5e9)
        self.assertTrue(berechne_parameterbereiche(config)["chirp_s"].leer)
        with self.assertRaises(ValueError):
            ParameterBereich(2, 1).begrenze_wert(1.5)

    def test_tabellenregler_fuer_flug_und_radar_ziele(self) -> None:
        for flug in (False, True):
            config = RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"]) if flug else RadarConfig()
            namen = (("start_x_m", "start_hoehe_m", "geschwindigkeit_x_mps", "geschwindigkeit_hoehe_mps",
                      "beschleunigung_hoehe_mps2", "staerke") if flug else
                     ("range_m", "velocity_mps", "strength", "phase_rad"))
            for spalte, name in enumerate(namen):
                b = bereich_fuer_tabellenwert(config, flug, 0, spalte)
                self.assertFalse(b.leer)
                for anteil in (0, 0.25, 0.5, 0.75, 1):
                    wert = b.minimum + anteil * (b.maximum - b.minimum)
                    if flug:
                        bahn = replace(config.flugszene.bahnen[0], **{name: wert})
                        probe = replace(config, flugszene=replace(config.flugszene, bahnen=(bahn,)))
                    else:
                        ziele = (replace(config.targets[0], **{name: wert}),) + config.targets[1:]
                        probe = replace(config, targets=ziele)
                    with self.subTest(flug=flug, name=name, anteil=anteil):
                        validate_config(probe)


if __name__ == "__main__":
    unittest.main()
