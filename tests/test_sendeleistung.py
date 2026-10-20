"""Energieflächen, TX-Skalierung, feste Rauschreferenz und GUI-Vergleich."""

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np

from radar_sim import RadarConfig, Target, simulate_frame, validate_config
from radar_sim.effekt_config import Stoereffekte
from radar_sim.io import load_config, save_config
from radar_sim.model import generate_echo
from radar_sim.passivradar import passiv_config
from radar_sim.pulsradar import puls_config, pulsform
from radar_sim.sendeleistung import PowerBudget, compare_power


class PowerTests(unittest.TestCase):
    def test_energy_is_exact_area_including_pauses(self):
        budget = PowerBudget(10., 10e-6, 100e-6, 64)
        self.assertAlmostEqual(budget.average, 1.)
        self.assertAlmostEqual(budget.pulse_energy, 100e-6)
        self.assertAlmostEqual(budget.frame_energy, .0064)
        for duty in (.001, .1, 1.):
            b = replace(budget, duration_s=duty*budget.interval_s)
            t, p, e = b.waveform(64)
            area = np.sum(np.diff(t)*(p[1:]+p[:-1])/2)
            self.assertAlmostEqual(area, b.frame_energy, places=14)
            self.assertAlmostEqual(e[-1], area, places=14)
            self.assertTrue(np.all(np.diff(e) >= -1e-14))
        with self.assertRaises(ValueError):
            budget.waveform(1000000)
        with self.assertRaises(ValueError):
            PowerBudget(1, .2, .1, 16)

    def test_comparison_has_equal_energy_or_equal_peaks(self):
        for c in (RadarConfig(), puls_config(RadarConfig())):
            actual, reference = compare_power(c)
            self.assertAlmostEqual(actual.frame_energy, reference.frame_energy)
            self.assertEqual(actual.duration_s, c.chirp_s)
            self.assertEqual(actual.peak, c.tx_power)
            actual, reference = compare_power(c, equal_average=False)
            self.assertEqual(actual.peak, reference.peak)
            self.assertNotEqual(actual.frame_energy, reference.frame_energy)
        pulse, fmcw = compare_power(replace(puls_config(RadarConfig()), chirp_s=20e-6))
        self.assertAlmostEqual(pulse.peak/fmcw.peak, 10.)
        # ADC-Vorlauf beeinflusst nicht die abgestrahlte Sendeenergie.
        self.assertEqual(compare_power(RadarConfig())[0], compare_power(replace(RadarConfig(), adc_skip_samples=50))[0])

    def test_tx_scales_echo_and_spectrum_but_not_receiver_noise(self):
        for mode in ('fmcw', 'pulse_doppler'):
            c = RadarConfig(targets=(Target(40, 0),), noise_enabled=False)
            if mode == 'pulse_doppler':
                c = replace(puls_config(c), targets=(Target(1000, 0),))
            a, b = simulate_frame(c), simulate_frame(replace(c, tx_peak_db=10))
            np.testing.assert_allclose(b.echo.beat, np.sqrt(10)*a.echo.beat, atol=1e-12)
            np.testing.assert_allclose(b.spectrum.power, 10*a.spectrum.power, atol=1e-12)
            self.assertAlmostEqual(b.echo.expected_signal_power, 10*a.echo.expected_signal_power)
            noise = replace(c, targets=(), noise_enabled=True)
            np.testing.assert_array_equal(generate_echo(noise).beat, generate_echo(replace(noise, tx_peak_db=10)).beat)
            self.assertEqual(generate_echo(noise).noise_power, generate_echo(replace(noise, tx_peak_db=10)).noise_power)

    def test_tx_scales_leakage_before_saturation(self):
        c = RadarConfig(targets=(), noise_enabled=False,
                        effekte=Stoereffekte(leakage=True, leakage_db=0))
        a, b = generate_echo(c), generate_echo(replace(c, tx_peak_db=20))
        self.assertAlmostEqual(b.leakage_power, 100*a.leakage_power)
        np.testing.assert_allclose(b.beat, 10*a.beat)
        saturated = generate_echo(replace(c, tx_peak_db=20,
                                  effekte=replace(c.effekte, saettigung=True, saettigung_db=0)))
        np.testing.assert_allclose(np.abs(saturated.beat), 1.)
        self.assertEqual(saturated.clipped_fraction, 1.)

    def test_json_defaults_bounds_and_passive(self):
        old = RadarConfig().to_dict()
        old['schema_version'] = 7
        old.pop('tx_peak_db')
        self.assertEqual(RadarConfig.from_dict(old).tx_peak_db, 0.)
        c = replace(RadarConfig(), tx_peak_db=12)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'power.json'
            save_config(path, c)
            self.assertEqual(load_config(path), c)
        for bad in (-61, 61, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                validate_config(replace(c, tx_peak_db=bad))
        with self.assertRaises(ValueError):
            validate_config(replace(passiv_config(), tx_peak_db=1))
        with self.assertRaises(ValueError):
            compare_power(passiv_config())

    def test_compression_trace_matches_direct_correlation(self):
        c = replace(puls_config(RadarConfig()), targets=(Target(1000, 0),),
                    window='rect', noise_enabled=False)
        result = simulate_frame(c)
        template = pulsform(np.arange(c.pulse_samples)/c.sample_rate_hz, c)
        # Unabhängige Summen, nicht der FFT-Code des Matched Filters.
        direct = np.array([np.sum(result.echo.beat[0, k:k+c.pulse_samples]*template.conj())/c.pulse_samples
                           for k in range(c.pulse_samples, c.samples-c.pulse_samples+1)])
        np.testing.assert_allclose(result.spectrum.compressed_first, direct, atol=1e-14)


class PowerGuiTests(unittest.TestCase):
    def test_controls_passive_return_and_exports(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PyQt6.QtWidgets import QApplication
        from radar_sim.gui import MainWindow
        from radar_sim.report_plots import export_plot
        app = QApplication.instance() or QApplication([])
        c = replace(puls_config(RadarConfig()), targets=(Target(1000, 0),))
        window = MainWindow(c)
        def wait():
            end = time.monotonic()+20
            while window.busy or window.result is None:
                app.processEvents()
                if time.monotonic() > end:
                    self.fail('GUI-Frame nicht fertig')
                time.sleep(.002)
            app.processEvents()
        try:
            window.resize(1920, 1080)
            window.show()
            wait()
            view = window.views.leistungsansicht
            window.views.zeige_ansicht(view)
            self.assertIn('Vergleichsreferenz', view.summary.text())
            self.assertGreater(len(view.compressed_curve.getData()[0]), 0)
            curves = view.pulse_curve, view.fmcw_curve
            view.normalization.setCurrentIndex(1)
            self.assertEqual(max(curves[0].getData()[1]), max(curves[1].getData()[1]))
            window.tabs.controls['tx_peak_db'].setValue(10)
            window.start_frame()
            wait()
            self.assertEqual(window.result.config.tx_peak_db, 10)
            self.assertEqual(max(view.pulse_curve.getData()[1]), 10)
            self.assertIs(view.pulse_curve, curves[0])
            with tempfile.TemporaryDirectory() as folder:
                for name, plot in view.diagramme():
                    path = Path(folder)/(name+'.png')
                    export_plot(plot, path)
                    self.assertGreater(path.stat().st_size, 1000)
            window.tabs.controls['radar_mode'].setCurrentIndex(2)
            window.start_frame()
            wait()
            self.assertIn('sendet nicht', view.summary.text())
            self.assertIsNone(view.pulse_curve.getData()[0])
            self.assertFalse(window.tabs.regler['tx_peak_db'].isVisible())
            window.tabs.controls['radar_mode'].setCurrentIndex(1)
            window.start_frame()
            wait()
            self.assertEqual(window.result.config.tx_peak_db, 10)
            self.assertIs(view.pulse_curve, curves[0])
            window.tabs.controls['radar_mode'].setCurrentIndex(0)
            window.start_frame()
            wait()
            self.assertTrue(view.reference_duty.isVisible())
            view.normalization.setCurrentIndex(0)
            view.reference_duty.setValue(20)
            actual, ref = compare_power(window.result.config, .2)
            self.assertAlmostEqual(max(view.pulse_curve.getData()[1]), ref.peak)
            self.assertAlmostEqual(max(view.fmcw_curve.getData()[1]), actual.peak)
        finally:
            window.close()
            app.processEvents()
