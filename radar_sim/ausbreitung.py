"""Freie Sicht, effektive Erdkugel und homogene atmosphärische Dämpfung.

Die Weltansicht bleibt eine Karte: (x,y) sind Bogenkoordinaten in Metern,
z ist Höhe über einer glatten Erde. Keine Gelände- oder Beugungsrechnung.
Bei ausgeschalteter Erdkrümmung gelten die bisherigen kartesischen Koordinaten.
"""

import numpy as np
from .effekt_config import Stoereffekte

ERDRADIUS_M = 6_371_000.0


def erdkoordinaten(ort, tempo, effekte: Stoereffekte) -> tuple[np.ndarray, np.ndarray]:
    """Kartenort und dessen Zeitableitung auf der effektiven Kugel [m, m/s].

    Mit s=hypot(x,y), θ=s/Re, q=(x,y)/s gilt
    P=((Re+z) sin(θ) q, (Re+z) cos(θ)). V=dP/dt folgt analytisch.
    P und V haben Form [3]. Die letzte Achse zeigt vom Erdmittelpunkt nach oben.
    """
    p, v = np.asarray(ort, dtype=float), np.asarray(tempo, dtype=float)
    if not effekte.erdkruemmung:
        return p, v
    re = ERDRADIUS_M*effekte.erdradius_faktor
    s = float(np.linalg.norm(p[:2]))
    r = re+p[2]
    if s < 1e-9:
        return np.array([0., 0., r]), np.array([r/re*v[0], r/re*v[1], v[2]])
    q, theta = p[:2]/s, s/re
    ds = float(q@v[:2])
    dq = (v[:2]-q*ds)/s
    sin, cos = np.sin(theta), np.cos(theta)
    pos = np.r_[r*sin*q, r*cos]
    vel = np.r_[v[2]*sin*q+r*(cos*ds/re*q+sin*dq), v[2]*cos-r*sin*ds/re]
    return pos, vel


def freie_sicht(start: np.ndarray, ende: np.ndarray, effekte: Stoereffekte) -> bool:
    """Schneidet das Segment zwischen zwei Kugelorten das Erdinnere?

    Der nächste Punkt auf P(u)=start+u·(ende−start), 0≤u≤1 wird analytisch
    bestimmt. Eine Tangente ist sichtbar; 1 µm Toleranz fängt Rundung ab.
    """
    if not effekte.erdkruemmung:
        return True
    delta = ende-start
    quadrat = float(delta@delta)
    u = np.clip(-float(start@delta)/quadrat, 0., 1.) if quadrat else 0.
    radius = ERDRADIUS_M*effekte.erdradius_faktor
    return bool(np.linalg.norm(start+u*delta) >= radius-1e-6)


def atmosphaerenfaktor(weg_m: float, effekte: Stoereffekte) -> float:
    """Amplitudenfaktor 10^(−γ·L_km/20), nicht Leistungsfaktor.

    Monostatisch L=2R, bistatisch L=Rt+Rr. γ ist eine vorgegebene Konstante;
    keine automatische ITU-, Regen-, Temperatur- oder Feuchtemodellierung.
    """
    return 10**(-effekte.daempfung_db_km*weg_m/20000) if effekte.atmosphaere else 1.


def empfaengerort(eingabe, radar_zustand=None) -> tuple[np.ndarray, np.ndarray]:
    """Weltort und Geschwindigkeit; der Mast wird zur Plattformhöhe addiert."""
    ort = np.array(radar_zustand.position_m if radar_zustand else (0., 0., 0.), dtype=float)
    ort[2] += eingabe.effekte.stationshoehe_m
    tempo = np.array((radar_zustand.geschwindigkeit_x_mps, radar_zustand.geschwindigkeit_y_mps,
                      radar_zustand.geschwindigkeit_hoehe_mps) if radar_zustand else (0., 0., 0.))
    return ort, tempo


def monostatische_geometrie(ort, tempo, radarort, radartempo, effekte: Stoereffekte) -> tuple[float, float, bool, np.ndarray]:
    """R, v_radial, Sichtbarkeit und Blickvektor am lokalen Radar [m, m/s, bool, 3]."""
    ziel, ziel_v = erdkoordinaten(ort, tempo, effekte)
    radar, radar_v = erdkoordinaten(radarort, radartempo, effekte)
    blick = ziel-radar
    r = float(np.linalg.norm(blick))
    if r <= 0:
        raise ValueError("Echoquelle und Empfänger dürfen nicht zusammenfallen.")
    radial = float(blick@(ziel_v-radar_v)/r)
    if effekte.erdkruemmung:
        # Lokale Tangentialachsen am Radar für dessen Antennenmodell.
        s = float(np.linalg.norm(np.asarray(radarort)[:2]))
        if s > 1e-9:
            q = np.asarray(radarort)[:2]/s
            theta = s/(ERDRADIUS_M*effekte.erdradius_faktor)
            radial_ebene = np.r_[np.cos(theta)*q, -np.sin(theta)]
            quer = np.array([-q[1], q[0], 0.])
            oben = radar/np.linalg.norm(radar)
            xy = q*float(blick@radial_ebene)+np.array([-q[1], q[0]])*float(blick@quer)
            blick = np.r_[xy, float(blick@oben)]
    return r, radial, freie_sicht(radar, ziel, effekte), blick
