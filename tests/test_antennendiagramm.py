"""Antennenreferenzen, sehr schmale Keulen und konsistente Winkeldarstellung."""

from dataclasses import replace
import unittest
import numpy as np
from radar_sim.antenne import Antenne, antennenbasis, antennengewinn, richtdiagramm
from radar_sim.antennendiagramm import berechne_diagramm, relative_db, polarschnitte, polarkoordinaten
from radar_sim.antennen_validierung import pruefe_patterns


class PatternTests(unittest.TestCase):
    def test_polarwinkel_und_logarithmischer_radius(self):
        # 0° oben, +90° rechts, 180° unten, −90° links. 0 dB ist der Rand.
        x, y = polarkoordinaten(np.array([0., 90., 180., -90.]), np.ones(4))
        np.testing.assert_allclose(x, [0, 1, 0, -1], atol=1e-15)
        np.testing.assert_allclose(y, [1, 0, -1, 0], atol=1e-15)
        pegel = np.array([1., 10**(-15/10), 1e-3, 0.])
        x, y = polarkoordinaten(np.zeros(4), pegel, -30)
        np.testing.assert_allclose(y, [1, .5, 0, 0], atol=1e-15)
        np.testing.assert_array_equal(x, 0)
        # Der Einweg-Halbwert hat im −30-dB-Plot Radius 0,899657, nicht 0,5.
        _, halbwert_radius = polarkoordinaten(np.array([0.]), np.array([.5]), -30)
        self.assertAlmostEqual(float(halbwert_radius[0]), 1 + 10*np.log10(.5)/30)
        for grenze in (0, 1, float('nan')):
            with self.assertRaises(ValueError):
                polarkoordinaten(np.zeros(4), pegel, grenze)

    def test_polarer_hoehenvollkreis_zeigt_rueckraum_statt_spiegelung(self):
        for typ in ("isotrop", "faecher", "parabol", "patch_array"):
            a = Antenne(typ=typ)
            d = berechne_diagramm(a, 9.3e9)
            winkel, horizontal, vertikal = polarschnitte(a, 9.3e9, d)
            self.assertEqual((winkel[0], winkel[-1]), (-180, 180))
            vorne = np.abs(winkel) < 89
            np.testing.assert_allclose(vertikal[vorne], richtdiagramm(a, 0, winkel[vorne], 9.3e9), atol=1e-14)
            hinten = np.abs(winkel) > 91
            np.testing.assert_array_equal(vertikal[hinten], 1 if typ == "isotrop" else 0)
            np.testing.assert_allclose(horizontal, richtdiagramm(a, winkel, 0, 9.3e9), atol=1e-14)
            np.testing.assert_allclose([horizontal[0], vertikal[0]], [horizontal[-1], vertikal[-1]], atol=1e-14)

    def test_unabhaengige_referenzen(self):
        bericht = pruefe_patterns()
        for m in bericht["messungen"]:
            with self.subTest(pruefung=m["pruefung"]):
                self.assertTrue(m["bestanden"], m)

    def test_karte_und_schnitte_sind_dieselbe_echo_gewichtung(self):
        for typ in ("isotrop", "faecher", "parabol", "patch_array"):
            a = Antenne(typ=typ, azimut_grad=53, elevation_grad=-17)
            d = berechne_diagramm(a, 9.3e9)
            self.assertEqual(d.karte.shape, (301, 401))
            # Kartenmitte liegt exakt auf beiden Hauptschnitten.
            np.testing.assert_allclose(d.karte[150], richtdiagramm(a, d.karten_az, 0, 9.3e9), atol=1e-14)
            np.testing.assert_allclose(d.karte[:, 200], richtdiagramm(a, 0, d.karten_el, 9.3e9), atol=1e-14)
            # Unabhängige Weltpositionen aus einem lokalen Azimut-Schnitt.
            winkel = np.deg2rad(d.azimut)
            lokal = np.column_stack((np.cos(winkel), np.sin(winkel), np.zeros_like(winkel)))
            welt = 3500 * lokal @ antennenbasis(a).T
            np.testing.assert_allclose(d.leistung_az, antennengewinn(a, welt, 9.3e9), atol=2e-14)
            self.assertTrue(np.all(np.isfinite(relative_db(d.karte))))

    def test_schmale_keule_bleibt_aufgeloest_und_speicher_begrenzt(self):
        a = Antenne(typ="parabol", durchmesser_m=10)
        d = berechne_diagramm(a, 300e9)
        self.assertAlmostEqual(d.breite_az, 70*299_792_458/300e9/10, places=10)
        self.assertAlmostEqual(float(d.leistung_az.max()), 1)
        # Mehr als 300 Winkelwerte innerhalb einer vollen Halbwertsbreite.
        self.assertGreater(np.count_nonzero(np.abs(d.azimut) < d.breite_az/2), 300)
        self.assertLessEqual(d.azimut.size, 5602)
        self.assertLessEqual(d.karte.nbytes, 301*401*8)
        # Die Ausrichtung und die Zeichenlänge ändern das lokale Pattern nicht.
        anders = berechne_diagramm(replace(a, azimut_grad=0, elevation_grad=45, zeichenlaenge_m=10), 300e9)
        np.testing.assert_array_equal(d.karte, anders.karte)

    def test_db_referenz_einweg_und_zweiweg(self):
        leistung = np.array([1., .5, .25, 0.])
        db = relative_db(leistung)
        np.testing.assert_allclose(db, [0, -3.01029995664, -6.02059991328, -60], atol=1e-10)
        self.assertAlmostEqual(float(relative_db(leistung**2)[1]), -6.02059991328, places=10)
        np.testing.assert_array_equal(leistung, [1, .5, .25, 0])

    def test_ungueltige_frequenz_wird_erklaert(self):
        for frequenz in (0, -1, float("inf"), float("nan")):
            with self.assertRaisesRegex(ValueError, "Trägerfrequenz"):
                berechne_diagramm(Antenne(), frequenz)


if __name__ == "__main__":
    unittest.main()
