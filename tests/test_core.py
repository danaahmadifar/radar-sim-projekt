"""Physikalische Referenzen und unabhängige CFAR-Kontrollrechnung, Standard-unittest."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from radar_sim.config import C, MAX_CELLS, RadarConfig, Target, validate_config
from radar_sim.detection import ca_cfar
from radar_sim.evaluation import match_targets
from radar_sim.io import export_candidates, load_config, save_config
from radar_sim.model import dechirp, generate_echo, target_amplitude
from radar_sim.pipeline import simulate_frame
from radar_sim.processing import process_beat
from radar_sim.scenarios import scenarios
from radar_sim.validation import noise_experiment


class PhysicsTests(unittest.TestCase):
    def test_delayed_echo_dechirp_identity(self) -> None:
        c = replace(RadarConfig(), noise_enabled=False, targets=(Target(40, -5, 0.7),))
        t = np.arange(c.samples) / c.sample_rate_hz
        target = c.targets[0]
        tau = 2 * target.range_m / C
        fd = 2 * target.velocity_mps / c.wavelength
        tx = np.exp(1j * np.pi * c.slope * t**2)
        for m in (0, 17, c.chirps - 1):
            # Unabhängig aus verzögertem RX-Chirp aufbauen; φ=0.
            rx = np.sqrt(target.strength) * np.exp(1j * (np.pi * c.slope * (t - tau)**2
                  - 2 * np.pi * c.carrier_hz * tau - 2 * np.pi * fd * (m * c.repetition_s + t)))
            np.testing.assert_allclose(dechirp(tx, rx), generate_echo(c).beat[m], atol=2e-10)

    def test_scenario_estimates_and_signs(self) -> None:
        for name, config in scenarios().items():
            if name in ("near_resolution", "noise_only"):
                continue
            with self.subTest(name=name):
                result = simulate_frame(config)
                matches = match_targets(config, result.candidates)
                self.assertEqual(len(matches), len(config.targets))
                tolerance = config.range_resolution / 2 + C / (4 * config.slope * config.chirps * config.repetition_s)
                for match in matches:
                    self.assertLessEqual(abs(match.range_error_m), tolerance * 1.01)
                    self.assertLessEqual(abs(match.velocity_error_mps), config.velocity_resolution * 0.501)

    def test_negative_beat_near_origin_is_preserved(self) -> None:
        c = replace(RadarConfig(), targets=(Target(0.1, -10),), window="rect", noise_enabled=False)
        r = simulate_frame(c)
        d, n = np.unravel_index(np.argmax(r.spectrum.power), r.spectrum.power.shape)
        # |fd| < 1/(2Tr) <= 1/(2T): negativer Nahbereichston liegt hier
        # innerhalb eines halben Range-Bins um DC. Phasensteigung prüft das Vorzeichen.
        phase_step = np.angle(r.echo.beat[0, 1:] * r.echo.beat[0, :-1].conj()).mean()
        self.assertLess(phase_step, 0)
        self.assertLess(r.spectrum.beat_hz[0], 0)
        self.assertLess(r.spectrum.velocity_mps[d], 0)

    def test_doppler_range_coupling_correction(self) -> None:
        base = RadarConfig(chirp_s=80e-6, repetition_s=100e-6, sample_rate_hz=5e6, noise_enabled=False)
        fd = 20 / (base.chirps * base.repetition_s)
        r = C * (40 / base.chirp_s - fd) / (2 * base.slope)
        c = replace(base, targets=(Target(r, fd * base.wavelength / 2),))
        result = simulate_frame(c)
        match = match_targets(c, result.candidates)[0]
        candidate = result.candidates[match.candidate_index]
        self.assertAlmostEqual(candidate.range_m, r, places=9)
        self.assertGreater(abs(candidate.apparent_range_m - r), 0.1)

    def test_amplitude_power_not_field(self) -> None:
        c = RadarConfig(amplitude_model="radar")
        a = target_amplitude(c, Target(40, 0, 1))
        self.assertEqual(a, 1)
        self.assertAlmostEqual(target_amplitude(c, Target(80, 0, 1))**2, a**2 / 16)
        self.assertAlmostEqual(target_amplitude(c, Target(40, 0, 4)), 2 * a)
        self.assertEqual(target_amplitude(replace(c, amplitude_model="didactic"), Target(100, 0, 4)), 2)

    def test_noise_reference_reproducibility_and_variance(self) -> None:
        c = replace(RadarConfig(), targets=(), snr_db=10)
        a, b = generate_echo(c, 3), generate_echo(c, 3)
        np.testing.assert_array_equal(a.beat, b.beat)
        self.assertFalse(np.array_equal(a.beat, generate_echo(c, 4).beat))
        self.assertAlmostEqual(float(np.mean(np.abs(a.beat)**2)), 0.1, delta=0.002)
        self.assertAlmostEqual(float(a.beat.real.var()), 0.05, delta=0.001)
        self.assertEqual(generate_echo(replace(c, targets=(Target(20),))).noise_power, a.noise_power)

    def test_coherent_gain_and_static_filter(self) -> None:
        for window in ("rect", "hann"):
            c = replace(RadarConfig(), window=window, noise_enabled=False,
                        targets=(Target(40 * RadarConfig().range_resolution),))
            beat = generate_echo(c).beat
            s = process_beat(beat, c)
            self.assertAlmostEqual(float(s.power.max()), 1, places=10)
            suppressed = process_beat(beat, replace(c, remove_static=True))
            self.assertLess(float(suppressed.power.max()), 1e-25)


class CFARTests(unittest.TestCase):
    def test_integral_image_against_nested_reference(self) -> None:
        c = replace(RadarConfig(), training_range=3, training_doppler=2, guard_range=1, guard_doppler=1, pfa=0.01)
        p = np.random.default_rng(17).exponential(2.0, (20, 24))
        result = ca_cfar(p, c)
        hd, hr = 3, 4
        for d in range(hd, p.shape[0] - hd):
            for r in range(hr, p.shape[1] - hr):
                training = [p[d + dd, r + rr] for dd in range(-hd, hd + 1) for rr in range(-hr, hr + 1)
                            if not (abs(dd) <= 1 and abs(rr) <= 1)]
                self.assertEqual(len(training), result.training_cells)
                alpha = len(training) * (c.pfa**(-1 / len(training)) - 1)
                self.assertAlmostEqual(result.threshold[d, r], alpha * np.mean(training), places=10)
        self.assertFalse(result.valid[:hd].any())
        self.assertTrue(np.isnan(result.threshold[:, :hr]).all())

    def test_rectangular_noise_false_alarm_rate(self) -> None:
        result = noise_experiment("rect", 48)
        self.assertTrue(result["check"], result)


class ConfigTests(unittest.TestCase):
    def test_invalid_parameters_explained_before_allocation(self) -> None:
        base = RadarConfig()
        bad = [replace(base, repetition_s=1e-6), replace(base, sample_rate_hz=10_000_001),
               replace(base, chirps=2048, sample_rate_hz=100e6), replace(base, pfa=0),
               replace(base, carrier_hz=float("nan")), replace(base, targets=(Target(40, 100),)),
               replace(base, targets=(Target(300),)), replace(base, targets=(Target(-1),)),
               replace(base, targets=(Target(40, 0, 0),)), replace(base, training_range=1000),
               replace(base, chirps=128.0), replace(base, window="invalid"), replace(base, seed=-1),
               replace(base, chirp_s=0.01, repetition_s=0.01, sample_rate_hz=40000, targets=(Target(40, 1),))]
        for config in bad:
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    validate_config(config)

    def test_json_csv_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            c = scenarios()["01_stationary"]
            save_config(path / "config.json", c)
            self.assertEqual(load_config(path / "config.json"), c)
            result = simulate_frame(c)
            export_candidates(path / "detections.csv", result.candidates)
            content = (path / "detections.csv").read_text(encoding="utf-8-sig")
            self.assertIn("velocity_mps", content)
            self.assertEqual(len(content.splitlines()), len(result.candidates) + 1)
            data = c.to_dict()
            data["surprise"] = 42
            with self.assertRaises(ValueError):
                RadarConfig.from_dict(data)


if __name__ == "__main__":
    unittest.main()
