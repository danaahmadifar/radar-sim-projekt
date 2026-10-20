"""GUI ohne sichtbares Fenster prüfen: Wiedergabe, ruhige Anzeige und fünf PNGs."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import time
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QStyle, QStyleOptionSpinBox, QLabel

from radar_sim.gui import MainWindow
from radar_sim.report_plots import export_plot
from radar_sim.scenarios import scenarios
from radar_sim import RadarConfig
from radar_sim.flugbahn import flugszenen
from radar_sim.io import load_config
from radar_sim.regler import ParameterRegler
from radar_sim.flughafen import flughafen_config
from radar_sim.flugansicht import projiziere
from radar_sim.flugbahn import berechne_flugzustand
from radar_sim.flugbahn import erstelle_routenszene
from radar_sim.route import GezeichneteRoute, berechne_routendaten
from radar_sim.routen_editor import PROJEKTIONEN


class ZustandsBeobachter(QObject):
    """Zählt echte Änderungen der Bedienbarkeit während der Wiedergabe."""

    def __init__(self):
        super().__init__()
        self.zustaende = []

    def eventFilter(self, objekt, ereignis):
        if ereignis.type() == QEvent.Type.EnabledChange:
            self.zustaende.append(objekt.isEnabled())
        return False


class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_funktionsgruppen_alle_ansichten_und_eingaben_erreichbar(self) -> None:
        window = MainWindow()
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte_bis(lambda: window.result is not None and not window.busy)
            self.assertEqual([window.tabs.tabText(i) for i in range(window.tabs.count())],
                             ["Szene", "Radar", "Antenne", "Effekte"])
            self.assertEqual([window.views.tabText(i) for i in range(window.views.count())],
                             ["Simulation", "Signale", "Antenne", "Vergleich"])
            config = window.get_config()
            for ansicht in (window.views.overview, window.views.route_editor, window.views.signal_graphs,
                            window.views.leistungsansicht, window.views.antennenansicht,
                            window.views.effektansicht, window.views.vergleich, window.views.results_table):
                window.views.zeige_ansicht(ansicht)
                self.app.processEvents()
                self.assertTrue(ansicht.isVisible())
            window.views.results_toggle.setChecked(False)
            self.assertFalse(window.views.results_table.isVisible())
            for name in ("Flug", "Radar", "DSP / CFAR", "Antenne", "Effekte"):
                window.tabs.zeige_bereich(name)
                self.app.processEvents()
                self.assertEqual(window.tabs.currentWidget().horizontalScrollBar().maximum(), 0)
            self.assertEqual(window.get_config(), config)
            labels = [label.text() for label in window.tabs.effektfelder.findChildren(QLabel)]
            self.assertIn("Effekt-Demos", labels)
            self.assertNotIn("Nachteile nachvollziehen", labels)
            # Targets sind bei festen R/v-Werten editierbar; passive Felder bei Passivradar.
            window.set_config(RadarConfig())
            window.tabs.zeige_bereich("Targets")
            self.app.processEvents()
            self.assertTrue(window.tabs.targets_table.isVisible())
            self.assertTrue(window.tabs.targets_table.isEnabled())
            self.assertEqual(window.tabs.currentWidget().horizontalScrollBar().maximum(), 0)
            window.tabs.controls["radar_mode"].setCurrentIndex(2)
            window.tabs.zeige_bereich("Passivradar")
            self.app.processEvents()
            self.assertTrue(window.tabs.bereiche["Passivradar"].isVisible())
            self.assertEqual(window.tabs.currentWidget().horizontalScrollBar().maximum(), 0)
        finally:
            window.close()
            self.app.processEvents()

    def test_route_direkt_unter_beispielen_fernprofil_und_passivbeta(self) -> None:
        from radar_sim.fernradar import fern_config
        window=MainWindow(fern_config())
        try:
            window.resize(1920,1080)
            window.show()
            self.warte_bis(lambda: window.result is not None and not window.busy)
            # Der Button liegt unmittelbar unter der Auswahl, vor der Dauer.
            button=window.tabs.zeichnen_button
            combo=window.tabs.flug_auswahl
            self.assertGreater(button.y(),combo.y())
            self.assertLess(button.y(),window.tabs.flug_dauer.parentWidget().y())
            self.assertIn("5433",window.views.vergleich.toPlainText())
            self.assertGreater(window.result.config.targets[0].range_m,300000)
            window.tabs.controls["radar_mode"].setCurrentIndex(2)
            self.app.processEvents()
            self.assertEqual(window.get_config().radar_mode,"passive")
            self.assertTrue(window._eingaben_gueltig,window.grenzen_hinweis.text())
            window.start_frame()
            self.warte_bis(lambda: not window.busy and window.result.config.radar_mode=="passive")
            self.assertIsNotNone(window.result.passiv_empfang)
            self.assertIn("ΔL",window.views.results_table.horizontalHeaderItem(1).text())
            self.assertEqual(len(window.result.candidates),1)
            self.assertTrue(window.views.sender_marker.isVisible())
            self.assertFalse(window.tabs.regler["chirp_s"].isVisible())
            window.views.setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(len(window.views.chirp_curve.getData()[0]),1000)
            window.tabs.controls["radar_mode"].setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(window.get_config().flugszene.name,fern_config().flugszene.name)
            window.start_frame()
            self.warte_bis(lambda: not window.busy and window.result.config.radar_mode=="pulse_doppler")
            self.assertIn("R Soll",window.views.results_table.horizontalHeaderItem(1).text())
            self.assertFalse(window.views.sender_marker.isVisible())
        finally:
            window.close()

    def test_bewegtes_radar_und_wechsel_zu_puls_doppler(self) -> None:
        from radar_sim.antenne import keulenlinien
        window = MainWindow(flughafen_config("15_zwei_flugzeuge_radar"))
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None and not window.busy)
            self.assertEqual(window.tabs.flug_tabelle.rowCount(), 2)
            self.assertEqual(len(window.result.config.targets), 1)
            anzahl = window.tabs.flug_auswahl.count()
            window.tabs.controls["radar_mode"].setCurrentIndex(1)
            self.app.processEvents()
            self.assertEqual(window.get_config().radar_mode, "pulse_doppler")
            self.assertEqual(window.tabs.flug_auswahl.count(), anzahl)
            self.assertIn("Pulsdauer", window.tabs.radar_form.labelForField(window.tabs.regler["chirp_s"]).text())
            self.assertTrue(window._eingaben_gueltig, window.grenzen_hinweis.text())
            window.start_frame()
            self.warte_bis(lambda: not window.busy and window.result.config.radar_mode == "pulse_doppler")
            self.assertEqual(window.result.spectrum.power.shape[1], window.result.config.range_bins)
            self.assertEqual(len(window.views.real_curve.getData()[0]), window.result.config.samples)
            for index in (0, 10):
                if index:
                    window.frame_index = index
                    window.start_frame()
                    self.warte_bis(lambda: not window.busy and window.result.frame_index == index)
                radarort = np.array(window.result.radar_zustand.position_m)
                np.testing.assert_allclose(window.views.flug_plot.geometrie[window.views.radar_marker][0], radarort)
                lokal = keulenlinien(window.result.config.antenne, window.result.config.carrier_hz,
                                     ringe=(.25,.5,.75,1.), mantellinien=8)
                np.testing.assert_allclose(window.views.flug_plot.geometrie[window.views.sichtkeule], lokal+radarort)
                self.assertEqual(len(window.result.candidates), 1)
            window.tabs.controls["radar_mode"].setCurrentIndex(0)
            self.app.processEvents()
            self.assertEqual(window.get_config().radar_mode, "fmcw")
            self.assertTrue(window._eingaben_gueltig, window.grenzen_hinweis.text())
        finally:
            window.close()

    def test_antennen_vorschau_reagiert_ohne_neuen_radarframe(self) -> None:
        from radar_sim.antenne import Antenne
        config = replace(flughafen_config(), antenne=Antenne(typ="parabol"))
        window = MainWindow(config)
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None and not window.busy)
            ansicht = window.views.antennenansicht
            window.views.zeige_ansicht(ansicht)
            self.app.processEvents()
            self.assertEqual(ansicht.ansichten.currentIndex(), 0)
            self.assertEqual(len(ansicht.polarplot.legend.items), 2)
            ansicht.zweiweg.setChecked(True)
            self.assertTrue(all(k[1].isVisible() for k in ansicht.polarplot.kurven))
            self.assertEqual(len(ansicht.polarplot.legend.items), 4)
            ansicht.zweiweg.setChecked(False)
            self.assertEqual(len(ansicht.polarplot.legend.items), 2)
            daten = tuple(k[0].getData()[1].copy() for k in ansicht.polarplot.kurven)
            ansicht.db_grenze.setCurrentIndex(0)
            self.assertEqual(ansicht.polarplot.untergrenze_db, -15)
            self.assertTrue(any(not np.array_equal(vorher, k[0].getData()[1])
                                for vorher, k in zip(daten, ansicht.polarplot.kurven)))
            frame = window.result
            breite = ansicht.daten.breite_az
            window.tabs.ant_controls["durchmesser_m"].setValue(1.2)
            self.warte_bis(lambda: ansicht.daten.breite_az < breite*.6)
            self.assertIs(window.result, frame)
            self.assertAlmostEqual(ansicht.daten.breite_az, breite/2, places=9)
            ansicht.ganze_schnitte.setChecked(True)
            ansicht.ansichten.setCurrentIndex(1)
            self.assertEqual(ansicht.schnitte[0].viewRange()[0], [-180., 180.])
            self.assertEqual(ansicht.schnitte[1].viewRange()[0], [-90., 90.])
            with tempfile.TemporaryDirectory() as ordner:
                for name, plot in ansicht.diagramme():
                    pfad = Path(ordner)/f"{name}.png"
                    export_plot(plot, pfad)
                    self.assertGreater(pfad.stat().st_size, 1000)
            # Ein isotropes Diagramm darf keine fiktive Halbwertsbreite erhalten.
            window.tabs.ant_controls["typ"].setCurrentIndex(0)
            self.warte_bis(lambda: ansicht.daten.breite_az is None)
            np.testing.assert_array_equal(ansicht.daten.karte, 1)
            for kurve, _ in ansicht.polarplot.kurven:
                x, y = kurve.getData()
                np.testing.assert_allclose(x*x+y*y, 1, atol=1e-14)
            self.assertIn("nicht definiert", ansicht.info.text())
        finally:
            window.close()

    def test_worker_render_edit_and_five_png_exports(self) -> None:
        config = scenarios()["05_dashboard"]
        window = MainWindow(config)
        errors = []
        window.fail = errors.append
        window.show()
        deadline = time.monotonic() + 20
        while window.result is None and not errors and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(errors, [])
        self.assertIsNotNone(window.result)
        self.assertEqual(window.result.config.targets, config.targets)
        self.assertFalse(window.busy)
        self.assertGreaterEqual(window.views.results_table.rowCount(), len(config.targets))
        window.add_target()
        self.assertEqual(len(window.get_config().targets), 4)
        window.tabs.targets_table.selectRow(3)
        window.remove_target()
        self.assertEqual(len(window.get_config().targets), 3)
        with tempfile.TemporaryDirectory() as directory:
            for index, plot in enumerate((window.views.rd_plot, window.views.chirp_plot, window.views.beat_plot, window.views.range_plot, window.views.flug_plot)):
                path = Path(directory) / f"plot{index}.png"
                export_plot(plot, path)
                self.assertGreater(path.stat().st_size, 1000)
            screenshot = Path(directory) / "window.png"
            self.assertTrue(window.grab().save(str(screenshot)))
        window.close()
        self.app.processEvents()

    def warte_bis(self, bedingung, timeout_s=10) -> None:
        ende = time.monotonic() + timeout_s
        while not bedingung() and time.monotonic() < ende:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(bedingung(), "Die GUI lieferte nicht rechtzeitig ein Ergebnis.")

    def test_xyz_projektion_und_maussteuerung_bleiben_beim_frame_erhalten(self) -> None:
        # Kamera von +X: Y liegt waagrecht, Z senkrecht, X in Blickrichtung.
        np.testing.assert_allclose(projiziere(np.eye(3), 0, 0),
                                   [[0, 0], [1, 0], [0, 1]], atol=1e-14)
        # Die Projektion darf Längen nicht vergrößern (keine künstliche Z-Skalierung).
        matrix = projiziere(np.eye(3), -45, 25)
        np.testing.assert_allclose(matrix.T @ matrix, np.eye(2), atol=1e-14)
        window = MainWindow(flughafen_config("13_flughafen_route3d"))
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte_bis(lambda: window.result is not None)
            plot = window.views.flug_plot
            kurve = window.views.flug_kurven[0]
            punkt = window.views.flug_punkte[0]
            xyz = plot.geometrie[kurve].copy()
            # Die neue Überflugroute schwingt seitlich zwischen -100 und +100 m.
            self.assertAlmostEqual(np.ptp(xyz[:, 1]), 200, delta=1)
            np.testing.assert_allclose(plot.geometrie[punkt][0], window.result.flugzustaende[0].position_m)
            texte = [t.toPlainText() for t in plot.achsen_texte]
            self.assertTrue(all(name in texte for name in ("X [m]", "Y [m]", "Z · Höhe [m]")))
            # Letzter Keulenring besteht aus genau den physikalisch berechneten XYZ.
            from radar_sim.antenne import keulenrand
            np.testing.assert_allclose(plot.geometrie[window.views.sichtkeule][294:391],
                                       keulenrand(window.result.config.antenne, window.result.config.carrier_hz))
            vorher = np.array(kurve.getData())
            keule_vorher = np.array(window.views.sichtkeule.getData())
            mitte = window.views.graphs.mapFromScene(plot.vb.sceneBoundingRect().center())
            QTest.mousePress(window.views.graphs.viewport(), Qt.MouseButton.LeftButton, pos=mitte)
            QTest.mouseMove(window.views.graphs.viewport(), mitte+QPointF(60, 35).toPoint(), delay=30)
            QTest.mouseRelease(window.views.graphs.viewport(), Qt.MouseButton.LeftButton, pos=mitte+QPointF(60, 35).toPoint())
            self.app.processEvents()
            self.assertNotEqual(plot.azimut, -45)
            self.assertFalse(np.allclose(vorher, np.array(kurve.getData())))
            self.assertFalse(np.allclose(keule_vorher, np.array(window.views.sichtkeule.getData()), equal_nan=True))
            kamera = plot.azimut, plot.elevation
            plot.vb.scaleBy((.8, .8))
            zoom = plot.viewRange()
            frame = window.result.frame_index
            window.run_button.click()
            self.warte_bis(lambda: window.result.frame_index > frame)
            self.assertIs(window.views.flug_kurven[0], kurve)
            self.assertEqual((plot.azimut, plot.elevation), kamera)
            np.testing.assert_allclose(plot.viewRange(), zoom)
            np.testing.assert_array_equal(plot.geometrie[kurve], xyz)
            np.testing.assert_allclose(plot.geometrie[punkt][0], window.result.flugzustaende[0].position_m)
            QTest.mouseDClick(window.views.graphs.viewport(), Qt.MouseButton.LeftButton, pos=mitte)
            self.app.processEvents()
            self.assertEqual((plot.azimut, plot.elevation), (-45, 25))
            with tempfile.TemporaryDirectory() as ordner:
                pfad = Path(ordner)/"xyz.png"
                export_plot(plot, pfad)
                self.assertGreater(pfad.stat().st_size, 10000)
        finally:
            window.close()
            self.app.processEvents()

    def test_szenariowechsel_und_import_erzeugen_keine_doppelten_eintraege(self) -> None:
        window = MainWindow()
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            anzahl = window.tabs.flug_auswahl.count()
            namen = [window.tabs.flug_auswahl.itemText(i) for i in range(1, anzahl)]
            for _ in range(2):
                for name in namen:
                    window.tabs.flug_auswahl.setCurrentIndex(window.tabs.flug_auswahl.findText(name))
                    self.warte_bis(lambda: not window.busy and window.result.input_config.flugszene.name == name)
                    self.assertEqual(window.tabs.flug_auswahl.count(), anzahl)
            # Neu erzeugte Dataclasses mit gleichem Namen müssen denselben Eintrag ersetzen.
            config = window.get_config()
            for _ in range(3):
                kopie = RadarConfig.from_dict(config.to_dict())
                window.set_config(kopie)
                self.assertEqual(window.tabs.flug_auswahl.count(), anzahl)
                self.assertEqual(window.get_config(), kopie)
            texte = [window.tabs.flug_auswahl.itemText(i) for i in range(anzahl)]
            self.assertEqual(len(texte), len(set(texte)))
        finally:
            window.close()
            self.app.processEvents()

    def test_freies_tempo_und_range_doppler_fuer_gegenverkehr_und_route(self) -> None:
        window = MainWindow(flughafen_config("11_flughafen_gegenverkehr"))
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte_bis(lambda: window.result is not None)
            vorher = window.get_config()
            window.tabs.routen_tempo.setValue(500)
            # Sofortiger Klick muss funktionieren, auch vor Ablauf des Debounce-Timers.
            window.run_button.click()
            self.warte_bis(lambda: not window.busy and window.result.input_config != vorher)
            config = window.result.input_config
            self.assertTrue(window._eingaben_gueltig, window.grenzen_hinweis.text())
            self.assertAlmostEqual(window.tabs.routen_tempo.value(), 500)
            self.assertGreater(config.max_velocity, 500)
            self.assertNotEqual(config.carrier_hz, vorher.carrier_hz)
            self.assertTrue(window.tabs.tempo_hinweis.text())
            for alt, neu in zip(vorher.flugszene.bahnen, config.flugszene.bahnen):
                np.testing.assert_allclose(berechne_flugzustand(alt, vorher.flugszene.dauer_s).position_m,
                                           berechne_flugzustand(neu, config.flugszene.dauer_s).position_m, atol=1e-6)
            self.assertLess(window.result.flugzustaende[0].radialgeschwindigkeit_mps, 0)
            self.assertGreater(window.result.flugzustaende[1].radialgeschwindigkeit_mps, 0)
            self.assertEqual(len(window.result.candidates), 2)
            self.assertLess(window.views.rd_plot.viewRange()[1][0], -500)
            self.assertGreater(window.views.rd_plot.viewRange()[1][1], 500)
            window.tabs.routen_tempo.setValue(70)
            window.start_frame()
            self.warte_bis(lambda: not window.busy and window.result.input_config == vorher)
            self.assertEqual(window.result.input_config.carrier_hz, vorher.carrier_hz)
            self.assertLess(window.views.rd_plot.viewRange()[1][1], 100)
            window.set_config(flughafen_config("13_flughafen_route3d"))
            window.tabs.routen_tempo.setValue(1500)  # Auch der frühere feste 1000er-Deckel entfällt.
            window.start_frame()
            self.warte_bis(lambda: not window.busy and window.result.input_config.flugszene.bahnen[0].route is not None)
            self.assertAlmostEqual(window.result.input_config.flugszene.bahnen[0].route.geschwindigkeit_mps, 1500)
            self.assertGreater(window.views.rd_plot.viewRange()[1][1], 1500)
        finally:
            window.close()
            self.app.processEvents()

    def test_ueberflug_zoomt_auf_60_prozent_trotz_grosser_keule(self) -> None:
        from radar_sim.antenne import Antenne
        config = RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"],
                             antenne=Antenne(typ="faecher", zeichenlaenge_m=6000))
        window = MainWindow(config)
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte_bis(lambda: window.result is not None)
            for _ in range(5):
                self.app.processEvents()
            plot = window.views.flug_plot
            x, y = window.views.flug_kurven[0].getData()
            bereiche = np.array(plot.viewRange())
            anteil = max(np.ptp(x)/np.ptp(bereiche[0]), np.ptp(y)/np.ptp(bereiche[1]))
            self.assertAlmostEqual(anteil, .6, delta=.025)
            zoom = plot.viewRange()
            window.run_button.click()
            self.warte_bis(lambda: not window.busy and window.result.frame_index == 1)
            np.testing.assert_allclose(plot.viewRange(), zoom)
        finally:
            window.close()
            self.app.processEvents()

    def test_grosse_ansichten_und_vollbild_mit_tastatur(self) -> None:
        """Die Diagramme erhalten bei Full HD Platz; F11 und Esc bleiben erreichbar."""
        window = MainWindow()
        try:
            window.resize(1920, 1080)
            window.show()
            window.activateWindow()
            self.warte_bis(lambda: window.result is not None)
            self.assertFalse(window.grenzen_hinweis.isVisible())
            unterkante = window.views.mapTo(window.centralWidget(), window.views.rect().bottomLeft()).y()
            self.assertLess(window.centralWidget().height() - unterkante, 20)
            self.assertGreater(window.views.flug_plot.vb.height(), 650)
            self.assertGreater(window.views.rd_plot.vb.height(), 650)
            window.views.setCurrentIndex(1)
            self.app.processEvents()
            for plot in (window.views.chirp_plot, window.views.beat_plot, window.views.range_plot):
                self.assertGreater(plot.vb.height(), 300)
            window.views.zeige_ansicht(window.views.results_table)
            self.app.processEvents()
            self.assertTrue(window.views.results_table.isVisible())
            self.assertTrue(window.views.results_table.item(0, 0).text().startswith("Target"))
            QTest.keyClick(window, Qt.Key.Key_F11)
            self.app.processEvents()
            self.assertTrue(window.isFullScreen())
            QTest.keyClick(window, Qt.Key.Key_Escape)
            self.app.processEvents()
            self.assertFalse(window.isFullScreen())
            window.fullscreen_button.click()
            self.assertTrue(window.isFullScreen())
            window.fullscreen_button.click()
            self.assertFalse(window.isFullScreen())
        finally:
            window.close()

    def test_weisse_pfeile_sichtbar_und_anklickbar(self) -> None:
        """Gerenderte Pixel und echte Klicks prüfen, für Ganzzahl und Dezimalzahl."""
        window = MainWindow()
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            window.tabs.setCurrentIndex(1)
            self.app.processEvents()
            for key in ("bandwidth_hz", "chirps"):
                spin = window.tabs.controls[key]
                window.tabs.currentWidget().ensureWidgetVisible(spin)
                self.app.processEvents()
                vorher = spin.value()
                option = QStyleOptionSpinBox()
                spin.initStyleOption(option)
                for richtung in (QStyle.SubControl.SC_SpinBoxUp, QStyle.SubControl.SC_SpinBoxDown):
                    rect = spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, richtung, spin)
                    bild = spin.grab().toImage()
                    faktor = bild.devicePixelRatio()
                    weisse_pixel = 0
                    for y in range(round(rect.top() * faktor), round((rect.bottom() + 1) * faktor)):
                        for x in range(round(rect.left() * faktor), round((rect.right() + 1) * faktor)):
                            farbe = bild.pixelColor(x, y)
                            if min(farbe.red(), farbe.green(), farbe.blue()) > 230:
                                weisse_pixel += 1
                    self.assertGreater(weisse_pixel, 8, f"Kein weißer Pfeil sichtbar: {key}, {richtung}")
                    QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=rect.center())
                    erwartet = vorher + spin.singleStep() if richtung == QStyle.SubControl.SC_SpinBoxUp else vorher
                    self.assertAlmostEqual(spin.value(), erwartet)
        finally:
            window.close()

    def test_flug_abspielen_ohne_zustandsflackern_und_zoomverlust(self) -> None:
        szene = replace(flugszenen()["06_ueberflug"], dauer_s=0.1, zeitschritt_s=0.02)
        config = RadarConfig(targets=(), flugszene=szene)
        window = MainWindow(config)
        fehler = []
        window.fail = fehler.append
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None or bool(fehler))
            self.assertEqual(fehler, [])
            erstes_signal = window.result.echo.beat.copy()
            erste_zelle = window.views.results_table.item(0, 0)
            bild = window.views.image
            window.views.rd_plot.setRange(xRange=(20, 140), yRange=(-12, 12), padding=0)
            zoom = window.views.rd_plot.viewRange()
            beobachter = ZustandsBeobachter()
            window.tabs.installEventFilter(beobachter)
            window.play_button.click()
            self.warte_bis(lambda: window.result.frame_index == szene.letzter_frame or bool(fehler))
            self.assertEqual(fehler, [])
            self.assertFalse(window.play_button.isChecked())
            self.assertFalse(window.timer.isActive())
            self.assertTrue(window.tabs.isEnabled())
            self.assertEqual(beobachter.zustaende, [False, True])
            self.assertEqual(window.views.rd_plot.viewRange(), zoom)
            self.assertIs(window.views.image, bild)
            self.assertIs(window.views.results_table.item(0, 0), erste_zelle)
            self.assertAlmostEqual(window.result.flugzustaende[0].x_m, -99)
            with tempfile.TemporaryDirectory() as ordner:
                pfad = Path(ordner)
                with patch("radar_sim.gui.QFileDialog.getSaveFileName", return_value=(str(pfad / "ziele.csv"), "CSV")):
                    window.save_csv()
                gespeichert = load_config(pfad / "ziele.config.json")
                self.assertEqual(gespeichert, window.result.input_config)
                self.assertEqual(gespeichert.flugszene, config.flugszene)
                self.assertIn("zeit_s=0.1", (pfad / "ziele.frame.txt").read_text())
                self.assertTrue((pfad / "ziele.flug.csv").is_file())
                with patch("radar_sim.gui.QFileDialog.getExistingDirectory", return_value=ordner):
                    window.save_png()
                self.assertEqual(len(list(pfad.glob("*.png"))), len(window.views.diagramme()))
            window.reset_seed()
            self.warte_bis(lambda: window.result.frame_index == 0 and not window.busy)
            np.testing.assert_array_equal(window.result.echo.beat, erstes_signal)
        finally:
            window.close()
            self.app.processEvents()

    def test_slider_passen_sich_an_ohne_andere_werte_zu_verstellen(self) -> None:
        window = MainWindow(RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"]))
        fehler = []
        window.fail = fehler.append
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            alt = window.tabs.regler["chirp_s"].bereich.minimum
            andere_werte = [window.tabs.controls[k].value() for k in ("chirp_s", "repetition_s", "sample_rate_hz")]
            window.tabs.controls["bandwidth_hz"].setValue(250)
            window._aktualisiere_grenzen()
            self.assertGreater(window.tabs.regler["chirp_s"].bereich.minimum, alt)
            self.assertEqual(andere_werte, [window.tabs.controls[k].value() for k in ("chirp_s", "repetition_s", "sample_rate_hz")])
            self.assertTrue(window._eingaben_gueltig)
            for name in ("chirps", "chirp_s", "sample_rate_hz"):
                window.tabs.regler[name].slider.setValue(1000 if name != "chirp_s" else 0)
                window._aktualisiere_grenzen()
                self.assertTrue(window._eingaben_gueltig, window.grenzen_hinweis.text())
                window.get_config()
            for regler in window.tabs.regler.values():
                self.assertTrue(regler.spin.toolTip())
                self.assertTrue(regler.slider.toolTip())
            window.tabs.controls["bandwidth_hz"].setValue(10000)
            window._aktualisiere_grenzen()
            self.assertFalse(window._eingaben_gueltig)
            self.assertFalse(window.run_button.isEnabled())
            self.assertFalse(window.play_button.isEnabled())
            self.assertIn("Bitte anpassen", window.grenzen_hinweis.text())
            self.assertEqual(fehler, [])
        finally:
            window.close()

    def test_tabellenwert_oeffnet_gekoppelten_slider_dialog(self) -> None:
        window = MainWindow(scenarios()["01_stationary"])
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            gefunden = []
            def bearbeite(dialog):
                regler = dialog.findChildren(ParameterRegler)
                gefunden.extend(regler)
                self.assertEqual(len(regler), 1)
                regler[0].spin.setValue(45)
                return QDialog.DialogCode.Accepted
            with patch("radar_sim.gui.QDialog.exec", bearbeite):
                window._tabellenwert_bearbeiten(window.tabs.targets_table, 0, 0)
            self.assertTrue(gefunden)
            self.assertEqual(window.get_config().targets[0].range_m, 45)
        finally:
            window.close()

    def test_route_mit_echten_mausereignissen_zeichnen_und_abfliegen(self) -> None:
        window = MainWindow(RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"]))
        fehler = []
        window.fail = fehler.append
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            self.assertTrue(window.tabs.route_settings.isVisible())  # Speed jetzt auch für Beispielbahnen.
            window.views.setCurrentIndex(1)
            window.tabs.zeichnen_button.click()
            QTest.qWait(50)
            self.assertTrue(window.views.route_editor.isVisible())
            self.assertTrue(window.tabs.route_settings.isVisible())
            self.assertFalse(window.play_button.isEnabled())
            orte = [(-90., 30.), (-45., 50.), (0., 60.), (45., 50.), (90., 30.)]
            editor = window.views.route_editor
            pixel = [editor.graphs.mapFromScene(editor.ansichten["XZ"].mapViewToScene(QPointF(*ort))) for ort in orte]
            viewport = editor.graphs.viewport()
            QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=pixel[0])
            QTest.mouseMove(viewport, pixel[-1], delay=20)
            QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=pixel[-1])
            self.app.processEvents()
            self.assertEqual(len(editor.punkte), 0, "Freihandziehen darf keine Punkte erzeugen.")
            for nummer, ort in enumerate(pixel, 1):
                QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=ort)
                self.app.processEvents()
                self.assertEqual(len(editor.punkte), nummer)
            editor.linie_button.click()  # Punkte fertig: Griffe dürfen verschoben werden.

            self.assertIsNotNone(window._routen_entwurf, window.tabs.routen_hinweis.text())
            self.assertTrue(window.tabs.route_button.isEnabled())
            window.tabs.route_button.click()
            self.warte_bis(lambda: window.result.input_config.flugszene.bahnen[0].route is not None or bool(fehler))
            self.assertEqual(fehler, [])
            self.assertTrue(window._eingaben_gueltig, window.grenzen_hinweis.text())
            config = window.get_config()
            self.assertAlmostEqual(config.flugszene.bahnen[0].route.geschwindigkeit_mps, 10)
            self.assertTrue(window.tabs.dauer_regler.isEnabled())
            dauer = config.flugszene.dauer_s
            window.tabs.routen_tempo.setValue(4)
            window._aktualisiere_grenzen()
            self.assertAlmostEqual(window.get_config().flugszene.dauer_s, dauer * 10 / 4)
            window.frame_index = 30
            window._last_input_config = window.get_config()
            window.start_frame()
            self.warte_bis(lambda: window.result.frame_index == 30)
            self.assertNotEqual(window.result.flugzustaende[0].x_m, config.flugszene.bahnen[0].route.punkte[0][0])
            with tempfile.TemporaryDirectory() as ordner:
                datei = Path(ordner) / "route.json"
                with patch("radar_sim.gui.QFileDialog.getSaveFileName", return_value=(str(datei), "JSON")):
                    window.save_json()
                self.assertEqual(load_config(datei), window.get_config())
        finally:
            window.close()
            self.app.processEvents()

    def test_eigene_route_ueber_120_sekunden_startet_ohne_verwerfen(self) -> None:
        window = MainWindow(RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"]))
        fehler = []
        window.fail = fehler.append
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            window.tabs.zeichnen_button.click()
            editor = window.views.route_editor
            for ort in ((-60., 35.), (60., 35.)):
                pixel = editor.graphs.mapFromScene(editor.ansichten["XZ"].mapViewToScene(QPointF(*ort)))
                QTest.mouseClick(editor.graphs.viewport(), Qt.MouseButton.LeftButton, pos=pixel)
            self.app.processEvents()
            window.tabs.routen_tempo.setValue(.5)
            self.assertGreater(window.tabs.flug_dauer.value(), 120)
            window.tabs.route_button.click()
            self.warte_bis(lambda: not window.busy and window.result.input_config.flugszene.bahnen[0].route is not None)
            self.assertTrue(window.tabs.dauer_regler.isEnabled())
            self.assertGreater(window.tabs.flug_dauer.value(), 120)  # Kein Klemmen auf 120 s.
            self.assertTrue(window.run_button.isEnabled(), window.grenzen_hinweis.text())
            self.assertFalse(editor.aktiv)
            self.assertGreater(window.result.input_config.flugszene.dauer_s, 120)
            laenge = window.tabs.flug_dauer.value() * window.tabs.routen_tempo.value()
            window.tabs.flug_dauer.setValue(.1)
            window._aktualisiere_grenzen()
            self.assertTrue(window.run_button.isEnabled(), window.grenzen_hinweis.text())  # Auch hohes Tempo wird durch Auto-Radar möglich.
            window.tabs.flug_dauer.setValue(60)
            window._aktualisiere_grenzen()
            self.assertAlmostEqual(window.tabs.routen_tempo.value(), laenge/60, places=8)
            self.assertTrue(window.run_button.isEnabled(), window.grenzen_hinweis.text())
            window.run_button.click()
            self.warte_bis(lambda: not window.busy and window.result.input_config.flugszene.bahnen[0].route is not None)
            self.assertAlmostEqual(window.result.input_config.flugszene.dauer_s, 60, places=8)
            window.play_button.click()
            self.warte_bis(lambda: window.result.frame_index >= 2 or bool(fehler))
            window.play_button.click()
            self.warte_bis(lambda: not window.busy)
            self.assertEqual(fehler, [])
        finally:
            window.close()
            self.app.processEvents()

    def test_komplexer_entwurf_bleibt_bei_fehler_und_laesst_sich_uebernehmen(self) -> None:
        window = MainWindow(RadarConfig(targets=(), flugszene=flugszenen()["06_ueberflug"]))
        try:
            window.show()
            self.warte_bis(lambda: window.result is not None)
            bisher = window.result
            window.tabs.zeichnen_button.click()
            editor = window.views.route_editor
            winkel = np.linspace(0, 6*np.pi, 80)
            punkte = np.column_stack((-2000+1000*np.cos(winkel), 800*np.sin(winkel), 500+100*np.sin(2*winkel)))
            editor.punkte = punkte.copy()
            editor._zeige_punkte(True)
            window.tabs.routen_tempo.setValue(70)
            # Ein absichtlich zu großes CFAR-Fenster darf keinen Punkt verlieren.
            window.tabs.controls["training_range"].setValue(128)
            window.tabs.controls["guard_range"].setValue(128)
            window.tabs.route_button.click()
            self.assertTrue(editor.aktiv)
            self.assertIs(window.result, bisher)
            np.testing.assert_array_equal(editor.punkte, punkte)
            self.assertIn("Route bleibt im Editor", window.tabs.routen_hinweis.text())
            self.assertTrue(window.tabs.route_button.isEnabled())
            window.tabs.controls["training_range"].setValue(8)
            window.tabs.controls["guard_range"].setValue(2)
            window.tabs.flug_schritt.setValue(2)
            window.tabs.route_button.click()
            self.warte_bis(lambda: not window.busy and window.result is not bisher)
            config = window.result.input_config
            self.assertFalse(editor.aktiv)
            self.assertGreater(config.flugszene.dauer_s, 120)
            self.assertEqual(config.flugszene.bahnen[0].route.punkte, tuple(map(tuple, punkte)))
            self.assertGreater(config.adc_skip_samples, 0)
            self.assertEqual(config.samples, bisher.config.samples)
            self.assertTrue(window._eingaben_gueltig, window.grenzen_hinweis.text())
            # Nach der Übernahme wieder öffnen: alle 80 Punkte sind noch editierbar.
            window.tabs.zeichnen_button.click()
            np.testing.assert_array_equal(editor.punkte, punkte)
        finally:
            window.close()
            self.app.processEvents()

    def test_rechtsklick_fuegt_einen_punkt_in_jeder_projektion_ein(self) -> None:
        # Eigene Testgeometrie mit eindeutigem YZ-Verlauf. Beim ebenen
        # Sinus-Überflug liegen in YZ mehrere Strecken übereinander.
        route = GezeichneteRoute(((-4000., -500., 400.), (-3000., 0., 600.),
                                 (-1800., 600., 500.), (-700., 900., 350.)), 70)
        config = replace(flughafen_config(), flugszene=erstelle_routenszene(route, .5, 10))
        window = MainWindow(config)
        try:
            window.resize(1920,1080)
            window.show()
            self.warte_bis(lambda: window.result is not None)
            window.tabs.zeichnen_button.click()
            editor = window.views.route_editor
            self.app.processEvents()
            for name, (a,b) in PROJEKTIONEN.items():
                route = GezeichneteRoute(tuple(tuple(p) for p in editor.punkte), 1.)
                daten = berechne_routendaten(route)
                view = editor.ansichten[name]
                orte = [view.mapViewToScene(QPointF(float(p[a]),float(p[b]))) for p in editor.punkte]
                laengen = [np.hypot((q-p).x(),(q-p).y()) for p,q in zip(orte,orte[1:])]
                index = int(np.argmax(laengen))
                punkt = np.polynomial.polynomial.polyval(.5, daten.koeffizienten[index])
                pixel = editor.graphs.mapFromScene(view.mapViewToScene(QPointF(float(punkt[a]),float(punkt[b]))))
                vorher = len(editor.punkte)
                QTest.mouseClick(editor.graphs.viewport(), Qt.MouseButton.RightButton, pos=pixel)
                self.app.processEvents()
                self.assertEqual(len(editor.punkte), vorher+1, editor.hinweis.text())
                self.assertGreater(editor.punkte[index+1,2], 250)
                self.assertLess(editor.punkte[index+1,0], -500)
                for projektion, (i,j) in PROJEKTIONEN.items():
                    x,y=editor.griffe[projektion].getData()
                    np.testing.assert_array_equal(x,editor.punkte[:,i])
                    np.testing.assert_array_equal(y,editor.punkte[:,j])
            # Ein Rechtsklick auf einen vorhandenen Griff erzeugt kein Duplikat.
            p=editor.punkte[1]
            pixel=editor.graphs.mapFromScene(editor.ansichten["XZ"].mapViewToScene(QPointF(float(p[0]),float(p[2]))))
            vorher=len(editor.punkte)
            QTest.mouseClick(editor.graphs.viewport(),Qt.MouseButton.RightButton,pos=pixel)
            self.app.processEvents()
            self.assertEqual(len(editor.punkte),vorher)
            # Abseits der Fluglinie ebenfalls keinen Punkt hinzufügen.
            ort=editor.ansichten["XZ"].sceneBoundingRect().topLeft()+QPointF(25,25)
            QTest.mouseClick(editor.graphs.viewport(),Qt.MouseButton.RightButton,pos=editor.graphs.mapFromScene(ort))
            self.app.processEvents()
            self.assertEqual(len(editor.punkte),vorher)
        finally:
            window.close()
            self.app.processEvents()

    def test_raumroute_in_alle_drei_ansichten_mit_der_maus_bearbeiten(self) -> None:
        route = GezeichneteRoute(((-4000., -500., 400.), (-3000., 0., 600.),
                                 (-1800., 600., 500.), (-700., 900., 350.)), 70)
        config = replace(flughafen_config(), flugszene=erstelle_routenszene(route, .5, 10))
        window = MainWindow(config)
        fehler = []
        window.fail = fehler.append
        try:
            window.resize(1920, 1080)
            window.show()
            self.warte_bis(lambda: window.result is not None or bool(fehler))
            self.assertEqual(fehler, [])
            window.tabs.zeichnen_button.click()
            editor = window.views.route_editor
            QTest.qWait(50)
            self.assertTrue(editor.isVisible())
            for name, (a, b) in PROJEKTIONEN.items():
                vorher = editor.punkte[1].copy()
                anfang = QPointF(float(vorher[a]), float(vorher[b]))
                # Deutlich über Qt-Drag-Schwelle, auch bei Kilometer-Achsen.
                ende = QPointF(float(vorher[a]+200), float(vorher[b]+200))
                pixel_a = editor.graphs.mapFromScene(editor.ansichten[name].mapViewToScene(anfang))
                pixel_b = editor.graphs.mapFromScene(editor.ansichten[name].mapViewToScene(ende))
                viewport = editor.graphs.viewport()
                QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=pixel_a)
                QTest.mouseMove(viewport, pixel_b, delay=30)
                QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=pixel_b)
                self.app.processEvents()
                unsichtbar = ({0,1,2}-{a,b}).pop()
                self.assertEqual(editor.punkte[1, unsichtbar], vorher[unsichtbar])
                self.assertGreater(np.linalg.norm(editor.punkte[1]-vorher), 10, name)
                for projektion, (i,j) in PROJEKTIONEN.items():
                    x,y = editor.griffe[projektion].getData()
                    self.assertAlmostEqual(x[1], editor.punkte[1,i])
                    self.assertAlmostEqual(y[1], editor.punkte[1,j])
            self.assertIsNotNone(window._routen_entwurf)
            neue_punkte = tuple(tuple(float(v) for v in p) for p in editor.punkte)
            window.tabs.route_button.click()
            self.warte_bis(lambda: not window.busy)
            self.assertEqual(fehler, [])
            self.assertEqual(window.get_config().flugszene.bahnen[0].route.punkte, neue_punkte)
            window.tabs.ant_controls["typ"].setCurrentIndex(window.tabs.ant_controls["typ"].findData("parabol"))
            window._aktualisiere_grenzen()
            self.assertEqual(window.get_config().antenne.typ, "parabol")
            self.assertTrue(window.tabs.ant_regler["durchmesser_m"].isVisibleTo(window.tabs.familien["Antenne"]))
            self.assertGreater(len(window.views.sichtkeule.getData()[0]), 90)
        finally:
            window.close()
            self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
