"""Unabhängige CAF-Summen, bistatische Geometrie und 300-km-Profile."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import numpy as np
from radar_sim.config import C, validate_config
from radar_sim.passivradar import (PassivEmpfang, passiv_config, bistatische_werte,
                                 erzeuge_passivempfang, kreuzambiguitaet)
from radar_sim.fernradar import fern_config
from radar_sim.pipeline import simulate_frame
from radar_sim.processing import window_values
from radar_sim.evaluation import match_targets, schaetztoleranzen
from radar_sim.io import save_config, load_config


class PassivUndFernTests(unittest.TestCase):
    def klein(self):
        c = passiv_config()
        return replace(c, sample_rate_hz=20000, bandwidth_hz=8000, chirps=16,
                       repetition_s=.0032, chirp_s=.0032, noise_enabled=False,
                       amplitude_model="didactic", passiv=replace(c.passiv,
                       maximaler_umweg_m=24*C/20000, direktweg_entfernen=False, direktweg_db=-80))

    def test_caf_gegen_explizite_summe_ueber_alle_samples(self):
        zufall = np.random.default_rng(1710)
        for fenster in ("rect", "hann"):
            c = replace(self.klein(), window=fenster)
            l, k = c.chirps*c.samples, c.range_bins-1
            referenz = zufall.normal(size=l+k)+1j*zufall.normal(size=l+k)
            surv = zufall.normal(size=l+k)+1j*zufall.normal(size=l+k)
            s = kreuzambiguitaet(PassivEmpfang(referenz, surv, 0., 0.), c)
            w = window_values(l, fenster)
            norm = np.sum(np.abs(referenz[:l])**2*w)
            erwartet = np.empty_like(s.power)
            for i, f in enumerate(s.doppler_hz):
                for lag in range(k+1):
                    phase = np.exp(-2j*np.pi*f*(np.arange(l)+lag)/c.sample_rate_hz)
                    wert = np.sum(np.conjugate(surv[lag:lag+l])*referenz[:l]*w*phase)/norm
                    erwartet[i, lag] = abs(wert)**2
            np.testing.assert_allclose(s.power, erwartet, atol=1e-14)

    def test_bistatischer_umweg_dopplervorzeichen_und_rx_leistungsgewinn(self):
        c = self.klein()
        for sign in (-1, 1):
            fd = sign*2/(c.chirps*c.repetition_s)
            umweg = 7*C/c.sample_rate_hz
            for gewinn in (1., .25):
                kanal = erzeuge_passivempfang(c, [(umweg, fd*c.wavelength, 10000, 10000, .49, gewinn)], 0)
                # Direktweg ist im Signal vorhanden; hier für die Referenzprüfung
                # exakt abziehen. Der Produktivpfad schätzt seinen Koeffizienten.
                kanal.ueberwachung -= 10**(c.passiv.direktweg_db/20)*kanal.referenz
                s = kreuzambiguitaet(kanal, c)
                i,j = np.unravel_index(np.argmax(s.power), s.power.shape)
                self.assertEqual(j, 7)
                self.assertAlmostEqual(s.velocity_mps[i], fd*c.wavelength)
                self.assertAlmostEqual(s.apparent_range_m[j], umweg)
                self.assertAlmostEqual(s.power[i,j], .49*gewinn, places=12)

    def test_reiner_direktweg_wird_ohne_rundungsgeister_entfernt(self):
        c = replace(self.klein(), passiv=replace(self.klein().passiv, direktweg_entfernen=True, direktweg_db=20))
        kanal = erzeuge_passivempfang(c, [], 0)
        s = kreuzambiguitaet(kanal, c)
        np.testing.assert_array_equal(s.power, 0)

    def test_geometrie_ableitung_und_monostatischer_grenzfall(self):
        p = np.array([-7000.,8000.,1800.])
        v = np.array([40.,-50.,0.])
        tx = (-20000,0,0)
        b, rate, rt, rr = bistatische_werte(p,v,tx)
        self.assertAlmostEqual(b, np.linalg.norm(p-np.array(tx))+np.linalg.norm(p)-20000)
        dt = 1e-4
        a = bistatische_werte(p-v*dt,v,tx)[0]
        z = bistatische_werte(p+v*dt,v,tx)[0]
        self.assertAlmostEqual((z-a)/(2*dt),rate,places=6)
        b,rate,_,_ = bistatische_werte(p,v,(0,0,0))
        self.assertAlmostEqual(b,2*np.linalg.norm(p))
        self.assertAlmostEqual(rate,2*(p@v)/np.linalg.norm(p))

    def test_passive_frames_seed_und_json(self):
        c = passiv_config()
        for nummer in (0,20,40):
            f = simulate_frame(c,nummer)
            paare = match_targets(f.config,f.candidates)
            self.assertEqual(len(paare),1,(nummer,f.candidates))
            rt,vt=schaetztoleranzen(c)
            self.assertLessEqual(abs(paare[0].range_error_m),rt*1.01)
            self.assertLessEqual(abs(paare[0].velocity_error_mps),vt*1.01)
        a = erzeuge_passivempfang(c,[],3)
        b = erzeuge_passivempfang(c,[],3)
        np.testing.assert_array_equal(a.referenz,b.referenz)
        np.testing.assert_array_equal(a.ueberwachung,b.ueberwachung)
        with tempfile.TemporaryDirectory() as ordner:
            datei=Path(ordner)/"beta.json"
            save_config(datei,c)
            self.assertEqual(load_config(datei),c)

    def test_beta_rechenbudget_und_unterstuetzte_geometrie(self):
        c = passiv_config()
        for ungueltig in (replace(c,chirps=256), replace(c,remove_static=True),
                          replace(c,passiv=replace(c.passiv,sender_x_m=0)),
                          replace(c,passiv=replace(c.passiv,maximaler_umweg_m=1e7)),
                          replace(c,passiv=replace(c.passiv,direktweg_db=float('inf')))):
            with self.assertRaises(ValueError):
                validate_config(ungueltig)

    def test_300_km_beide_verfahren_und_tatsaechliche_aufloesung(self):
        for modus in ("fmcw","pulse_doppler"):
            c = fern_config(modus)
            f=simulate_frame(c)
            self.assertGreater(f.config.targets[0].range_m,300000)
            self.assertEqual(len(match_targets(f.config,f.candidates)),1)
            self.assertLess(c.max_velocity,84)
            if modus=="fmcw":
                self.assertLess(c.slope*c.adc_duration_s,c.bandwidth_hz)
        self.assertGreater(fern_config("fmcw").range_resolution,3*fern_config().range_resolution)


if __name__ == "__main__":
    unittest.main()
