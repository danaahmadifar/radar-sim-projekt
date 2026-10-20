"""Endliche Bodenfläche aus kohärenten Punktstreuern, kein Landdatenmodell."""

import numpy as np
from .ausbreitung import ERDRADIUS_M


def bodenpunkte(config) -> list[tuple[np.ndarray, float, float]]:
    """Liste (Weltort [3] in m, RCS in m², Phase in rad).

    Feste Ring-/Sektorflächen um den Kartenursprung; σ=σ0·A·|ξ|² mit
    ξ~CN(0,1). E|ξ|²=1. Ein Streuer pro Fläche approximiert deren Summe;
    keine behauptete hochaufgelöste Landkarte. Seed OHNE Frameindex:
    dieselben Terrainstreuer bleiben zwischen Frames kohärent.
    """
    e = config.effekte
    if not e.bodenclutter:
        return []
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, 305]))
    kanten = np.linspace(e.clutter_innen_m**2, e.clutter_aussen_m**2, e.clutter_ringe+1)
    winkel = 2*np.pi/e.clutter_sektoren
    punkte = []
    for innen2, aussen2 in zip(kanten[:-1], kanten[1:]):
        r = np.sqrt((innen2+aussen2)/2)
        for sektor in range(e.clutter_sektoren):
            az = (sektor+.5)*winkel
            flaeche = .5*(aussen2-innen2)*winkel
            if e.erdkruemmung:
                re = ERDRADIUS_M*e.erdradius_faktor
                # Kugelringfläche statt ebener Kreisringfläche.
                # sin-Identität vermeidet Auslöschung bei kleinen Winkeln.
                a, b = np.sqrt(innen2)/re, np.sqrt(aussen2)/re
                flaeche = 2*re**2*np.sin((a+b)/2)*np.sin((b-a)/2)*winkel
            xi = (rng.normal()+1j*rng.normal())/np.sqrt(2)
            sigma = 10**(e.sigma0_db/10)*flaeche*abs(xi)**2
            punkte.append((np.array([r*np.cos(az), r*np.sin(az), 0.]), float(sigma), float(np.angle(xi))))
    return punkte


def aktive_bodenquellen(config, eingabe, radar_zustand=None):
    """Clutter als zusätzliche Echoquellen, getrennt von den Soll-Targets.

    Statische Erde: v_radial=−u·v_Radar. Beim bewegten Radar entsteht daher
    ein Dopplerband statt pauschal Null-Doppler. Es gilt stets σ/R⁴, auch
    wenn die Flug-Targets das didaktische Amplitudenmodell verwenden.
    """
    from .config import C, Target
    from .antenne import antennengewinn
    from .ausbreitung import empfaengerort, monostatische_geometrie, atmosphaerenfaktor
    from .empfaenger import phasen_bandreserve
    e = config.effekte
    radarort, radartempo = empfaengerort(eingabe, radar_zustand)
    quellen = []
    for ort, sigma, phase in bodenpunkte(config):
        r, v, sichtbar, blick = monostatische_geometrie(ort, np.zeros(3), radarort, radartempo, e)
        if not sichtbar:
            continue
        # Keine Echos früherer Rampen/PRIs oder unsichtbar gefaltete Frequenzen.
        if r > config.timing_range_limit or abs(v) >= config.max_velocity:
            raise ValueError("Bodenfläche überschreitet Laufzeit-/Dopplergrenzen. Kleinere Fläche oder passendes Radarprofil wählen.")
        fd = 2*v/config.wavelength
        if config.radar_mode == "fmcw" and abs(2*config.slope*r/C+fd)+phasen_bandreserve(config) >= config.sample_rate_hz/2:
            raise ValueError("Bodenclutter überschreitet die Beat-Nyquist-Grenze.")
        if config.radar_mode == "pulse_doppler" and config.bandwidth_hz/2+abs(fd)+phasen_bandreserve(config) >= config.sample_rate_hz/2:
            raise ValueError("Bodenclutter-Doppler plus Pulsbandbreite überschreiten ADC-Nyquist.")
        dauer = config.chirps*config.repetition_s
        if abs(v)*dauer > .25*config.range_resolution:
            raise ValueError("Bodenclutter wandert während des Messpakets zu weit durch Entfernungszellen.")
        a = float(radartempo@radartempo)/r
        if radar_zustand is not None and eingabe.flugszene is not None:
            a += abs(eingabe.flugszene.radar_bahn.beschleunigung_hoehe_mps2)
        if a*dauer > .25*config.velocity_resolution:
            raise ValueError("Bodenclutter-Doppler ändert sich innerhalb des Messpakets zu stark. Integration verkürzen.")
        g = float(antennengewinn(config.antenne, blick, config.carrier_hz))
        staerke = sigma if config.amplitude_model == "radar" else sigma/config.reference_rcs_m2*(config.reference_range_m/r)**4
        quellen.append(Target(r, v, staerke, phase, g, atmosphaerenfaktor(2*r, e)))
    return tuple(quellen)
