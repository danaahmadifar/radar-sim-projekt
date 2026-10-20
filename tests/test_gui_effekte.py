"""Bedienbare Effekt-Demos, Referenzkurven, Grenzen und Konfigurationsexport."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import unittest
from dataclasses import replace
from PyQt6.QtWidgets import QApplication
from radar_sim.gui import MainWindow
from radar_sim.effektbeispiele import effektbeispiele
from radar_sim.config import RadarConfig


class EffektGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def warte(self, window):
        ende = time.monotonic()+25
        while window.busy or window.result is None:
            self.app.processEvents()
            if time.monotonic() > ende:
                self.fail("Effekt-Worker nicht fertig")
            time.sleep(.005)
        self.app.processEvents()

    def test_demos_stoerungen_referenzkurven_und_roundtrip(self):
        c = effektbeispiele()["FMCW · Empfänger übersteuert"][1]
        window = MainWindow(c)
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte(window)
            self.assertIsNotNone(window.result.vergleich)
            self.assertEqual(window.result.echo.clipped_fraction, 1.)
            self.assertIn("100.00 %", window.views.effektansicht.info.text())
            self.assertGreater(len(window.views.effektansicht.kurven[0][0].getData()[0]), 0)
            kurve = window.views.effektansicht.kurven[0][1]
            config = window.get_config()
            self.assertTrue(config.effekte.leakage)
            self.assertTrue(config.effekte.saettigung)
            self.assertEqual(RadarConfig.from_dict(config.to_dict()), config)
            name = "Fernbereich · hinter dem Erdhorizont"
            window.tabs.effektfelder.demo_laden.emit(name)
            self.warte(window)
            self.assertTrue(window.views.effektansicht.isVisible())
            self.assertEqual(window.result.config.targets[0].path_gain, 0.)
            self.assertIs(kurve, window.views.effektansicht.kurven[0][1])
            window.tabs.effektfelder.demo_laden.emit("Passivradar · Direktweg und Übersteuerung")
            self.warte(window)
            self.assertEqual(window.result.config.radar_mode, "passive")
            self.assertFalse(window.tabs.effektfelder.controls["leakage"].isEnabled())
            self.assertGreater(window.result.passiv_empfang.clipped_fraction, .9)
            window.tabs.setCurrentWidget(window.tabs.effektfelder)
            self.app.processEvents()
            self.assertEqual(window.tabs.effektfelder.horizontalScrollBar().maximum(), 0)
            bar = window.tabs.tabBar()
            self.assertLess(bar.tabRect(window.tabs.count()-1).right(), bar.width())
        finally:
            window.close()

    def test_alle_demos_start_mitte_ende_und_fehler_erkennbar(self):
        # Rechenkern ohne Fenster: Kein spät auftretender Laufzeitfehler in den Demos.
        from radar_sim.pipeline import simulate_frame
        for name, (_, c) in effektbeispiele().items():
            nummern = (0, c.flugszene.letzter_frame//2, c.flugszene.letzter_frame) if c.flugszene else (0,)
            for n in nummern:
                with self.subTest(szene=name, frame=n):
                    f = simulate_frame(c, n)
                    self.assertTrue(f.spectrum.power.size > 0)
        window = MainWindow()
        try:
            self.warte(window)
            window.tabs.effektfelder.controls["phase_rms_rad"].setValue(3)
            window.tabs.effektfelder.controls["phase_zeit_s"].setValue(.001)
            window.tabs.effektfelder.controls["phasenrauschen"].setChecked(True)
            window._aktualisiere_grenzen()
            self.assertFalse(window._eingaben_gueltig)
            self.assertFalse(window.run_button.isEnabled())
            self.assertIn("Phasen", window.grenzen_hinweis.text())
        finally:
            window.close()

    def test_teilpuls_achsen_und_leakage_pegel_sind_sichtbar(self):
        import numpy as np
        c = effektbeispiele()["FMCW · Leakage und Phasenrauschen"][1]
        window = MainWindow(c)
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte(window)
            grenze = window.views.beat_plot.viewRange()[1][1]
            self.assertGreater(grenze, float(np.abs(window.result.echo.beat).max()))
            self.assertGreaterEqual(window.views.colorbar.levels()[1], 50)
            c = effektbeispiele()["Puls · kurzer Puls zum Vergleich"][1]
            window.set_config(c)
            window.start_frame()
            self.warte(window)
            self.assertAlmostEqual(window.views.rd_plot.viewRange()[0][0], 0, places=8)
            window.tabs.effektfelder.controls["teilpulse"].setChecked(False)
            window._aktualisiere_grenzen()
            window.start_frame()
            self.warte(window)
            self.assertAlmostEqual(window.views.rd_plot.viewRange()[0][0], c.minimum_range_m, places=8)
            self.assertGreater(window.result.spectrum.apparent_range_m[0], 500)
        finally:
            window.close()
