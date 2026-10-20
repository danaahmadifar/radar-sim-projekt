"""Relative Fernfeld-Richtdiagramme, ohne absolute Gewinne oder Detektionsgarantie.

G ist der normierte EINWEG-Leistungsgewinn. Für dieselbe Sende-/Empfangsantenne
gilt Pr proportional G² und deshalb komplexe Echoamplitude proportional G.
Die Richtungen werden aus den bekannten 3D-Positionen berechnet, nicht geschätzt.
"""

from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class Antenne:
    typ: str = "isotrop"
    azimut_grad: float = 180.0
    elevation_grad: float = 10.0
    breite_az_grad: float = 12.0
    breite_el_grad: float = 40.0
    durchmesser_m: float = 0.6
    elemente_horizontal: int = 16
    elemente_vertikal: int = 8
    zeichenlaenge_m: float = 6000.0  # Nur Darstellung, kein harter Empfangsrand!


ANTENNENTYPEN = {
    "isotrop": "Isotrop · Vergleich ohne Richtwirkung",
    "patch_array": "Phased Array · Patch-Feld (idealisiert)",
    "parabol": "Parabolantenne · Gauß-Hauptkeule",
    "faecher": "Fächerkeule · Gauß-Modell",
}


def pruefe_antenne(a: Antenne) -> None:
    if not isinstance(a, Antenne) or a.typ not in ANTENNENTYPEN:
        raise ValueError("Unbekannter Antennentyp.")
    for name in ("azimut_grad", "elevation_grad", "breite_az_grad", "breite_el_grad",
                 "durchmesser_m", "zeichenlaenge_m"):
        wert = getattr(a, name)
        if isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert):
            raise ValueError("Antennenwerte müssen endliche Zahlen sein.")
    if not -180 <= a.azimut_grad <= 180 or not -89 <= a.elevation_grad <= 89:
        raise ValueError("Antennenausrichtung: Azimut ±180°, Elevation ±89°.")
    if not 0.2 <= a.breite_az_grad <= 120 or not 0.2 <= a.breite_el_grad <= 120:
        raise ValueError("Keulenbreiten müssen zwischen 0,2° und 120° liegen.")
    if not 0.05 <= a.durchmesser_m <= 10 or not 10 <= a.zeichenlaenge_m <= 10000000:
        raise ValueError("Antennendurchmesser: 0,05–10 m; Zeichenlänge: 10–10.000.000 m.")
    for n in (a.elemente_horizontal, a.elemente_vertikal):
        if type(n) is not int or not 2 <= n <= 128:
            raise ValueError("Das Patch-Feld braucht 2–128 Elemente je Richtung.")


def antennenbasis(a: Antenne) -> np.ndarray:
    """Spalten: Blickrichtung, seitlich, oben; orthonormale Basis im Weltsystem."""
    az, el = np.deg2rad([a.azimut_grad, a.elevation_grad])
    return np.array([[np.cos(el)*np.cos(az), -np.sin(az), -np.sin(el)*np.cos(az)],
                     [np.cos(el)*np.sin(az), np.cos(az), -np.sin(el)*np.sin(az)],
                     [np.sin(el), 0., np.cos(el)]])


def _lokaler_gewinn(a: Antenne, richtungen: np.ndarray, traeger_hz: float) -> np.ndarray:
    """Eingang [...,3]: normierte Richtungsvektoren im Antennensystem."""
    if a.typ == "isotrop":
        return np.ones(richtungen.shape[:-1])
    vor, seit, hoch = np.moveaxis(richtungen, -1, 0)
    az = np.rad2deg(np.arctan2(seit, vor))
    el = np.rad2deg(np.arctan2(hoch, np.hypot(vor, seit)))
    if a.typ == "patch_array":
        # Gleichphasiges Rechteckfeld mit d=λ/2: AF=sin(Nπu/2)/(N sin(πu/2)).
        # np.sinc vermeidet die hebbare Singularität auf der Hauptachse.
        def faktor(u, n):
            return np.sinc(n*u/2) / np.sinc(u/2)
        feld = faktor(seit, a.elemente_horizontal) * faktor(hoch, a.elemente_vertikal)
        # Vereinfachtes Patch-Element: cos² zur Flächennormalen, keine Rückkeule.
        gewinn = feld**2 * np.maximum(vor, 0)**2
    else:
        if a.typ == "parabol":
            breite = 70 * (299_792_458 / traeger_hz) / a.durchmesser_m
            # Kreisförmiger Reflektor: echter Winkel zur Achse, rotationssymmetrisch.
            # sqrt(az²+el²) wäre nur für kleine Winkel eine Näherung dafür.
            achsenwinkel = np.rad2deg(np.arctan2(np.hypot(seit, hoch), vor))
            gewinn = np.exp(-4*np.log(2)*(achsenwinkel/breite)**2)
        else:
            breite_az, breite_el = a.breite_az_grad, a.breite_el_grad
            gewinn = np.exp(-4*np.log(2)*((az/breite_az)**2 + (el/breite_el)**2))
    return np.where(vor > 0, np.clip(gewinn, 0, 1), 0.)


def antennengewinn(a: Antenne, positionen_m, traeger_hz: float) -> np.ndarray:
    """Einweg-G in [0,1] für ein (x,y,z)-Tripel oder Array [...,3].

    Nur relative Winkelabhängigkeit im Fernfeld. Kein HF-Frontend, keine
    Polarisation, Verluste oder Antennenphasenkalibrierung. Kein Beamforming
    empfangener Kanäle und keine Winkelschätzung. Orientierung bleibt je Frame fest.
    """
    p = np.asarray(positionen_m, dtype=float)
    norm = np.linalg.norm(p, axis=-1, keepdims=True)
    if np.any(norm == 0):
        raise ValueError("Ein Target darf nicht im Antennenursprung liegen.")
    lokal = (p / norm) @ antennenbasis(a)
    return _lokaler_gewinn(a, lokal, traeger_hz)


def richtdiagramm(a: Antenne, azimut_grad, elevation_grad, traeger_hz: float) -> np.ndarray:
    """Normierte Einweg-Leistung G für lokale Antennenwinkel in Grad.

    Azimut 0° / Elevation 0° ist die Hauptachse, unabhängig von deren
    Ausrichtung im Raum. Winkelarrays werden nach NumPy-Regeln kombiniert:
    [1, Naz] und [Nel, 1] ergeben eine Karte [Nel, Naz]. Ein einzelner
    Winkelschnitt nutzt eine skalare Null als jeweils anderen Winkel.
    Dieselbe Gewinnfunktion gewichtet die Echos in antennengewinn().
    """
    az, el = np.broadcast_arrays(np.deg2rad(azimut_grad), np.deg2rad(elevation_grad))
    richtungen = np.stack((np.cos(el)*np.cos(az), np.cos(el)*np.sin(az), np.sin(el)), axis=-1)
    return _lokaler_gewinn(a, richtungen, traeger_hz)


def keulenrand(a: Antenne, traeger_hz: float) -> np.ndarray:
    """[97,3]: Rand der EINWEG-Halbwertskeule an der reinen Zeichenlänge.

    Der erste Schnitt G=0,5 wird je Richtung gesucht. So zeigt ein Patch-Array
    die Hauptkeule; seine Nebenkeulen beeinflussen trotzdem die Echos.
    Projektionen dieses Randes sind keine Schnitte bei y=0 bzw. x=0.
    Ohne Halbwertsgrenze im Vorderraum enthält der betreffende Punkt NaN.
    """
    phi = np.linspace(0, 2*np.pi, 97)
    if a.typ == "isotrop":
        # Legacy-Kreis für Aufrufer; die GUI blendet ihn aus (keine Halbwertsgrenze).
        return a.zeichenlaenge_m * np.column_stack((np.cos(phi), np.sin(phi), np.zeros_like(phi)))
    def richtungen(winkel):
        # Polarwinkel um die lokale Vorwärtsachse, phi dreht um diese Achse.
        return np.column_stack((np.cos(winkel), np.sin(winkel)*np.cos(phi), np.sin(winkel)*np.sin(phi)))

    unten, oben = np.zeros_like(phi), np.full_like(phi, np.deg2rad(89.999999))
    # Bei elektrisch kleinen Reflektoren kann die Gaußbreite >180° werden.
    # Dann existiert keine Halbwertsgrenze im Vorderraum: keine falsche Keule zeichnen.
    gueltig = _lokaler_gewinn(a, richtungen(oben), traeger_hz) < .5
    for _ in range(45):
        winkel = (unten+oben)/2
        stark = _lokaler_gewinn(a, richtungen(winkel), traeger_hz) >= .5
        unten = np.where(stark, winkel, unten)
        oben = np.where(stark, oben, winkel)
    lokal = richtungen((unten+oben)/2)
    lokal[~gueltig] = np.nan
    return a.zeichenlaenge_m * lokal @ antennenbasis(a).T


def keulenlinien(a: Antenne, traeger_hz: float, ringe=(1.,), mantellinien: int = 4) -> np.ndarray:
    """Drahtmodell [N,3] in m; NaN trennt Ringe und Linien, isotrop bleibt leer.

    Gemeinsame Geometrie für räumliche Ansicht und die drei ebenen Projektionen.
    Die zusätzlichen Ringe ändern nur die Zeichnung, nicht den Antennengewinn.
    """
    if a.typ == "isotrop":
        return np.empty((0, 3))
    rand = keulenrand(a, traeger_hz)
    teile = [np.vstack((rand*faktor, [[np.nan]*3])) for faktor in ringe]
    teile.extend(np.array([[0., 0., 0.], rand[i], [np.nan]*3]) for i in range(0, 96, 96//mantellinien))
    return np.vstack(teile)
