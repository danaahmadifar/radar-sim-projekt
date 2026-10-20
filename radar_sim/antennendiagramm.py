"""Winkelschnitte und Hauptkeulenbreiten; ohne Qt und ohne neue Antennenformeln."""

from dataclasses import dataclass
import math
import numpy as np
from .antenne import Antenne, pruefe_antenne, richtdiagramm


@dataclass(frozen=True)
class AntennenDiagramm:
    """Winkel in Grad, Leistungen linear relativ zur Hauptachse (G=1)."""

    azimut: np.ndarray                 # [Naz]: vollständiger horizontaler Schnitt
    elevation: np.ndarray              # [Nel]: vollständiger vertikaler Schnitt
    leistung_az: np.ndarray            # [Naz], Elevation = 0°
    leistung_el: np.ndarray            # [Nel], Azimut = 0°
    breite_az: float | None            # volle Einweg-Halbwertsbreiten [°]
    breite_el: float | None            # None: keine Halbwertsgrenze im Vorderraum
    karten_az: np.ndarray              # [401]: Ausschnitt um die Hauptkeule
    karten_el: np.ndarray              # [301]
    karte: np.ndarray                 # [301,401]: G(el,az), keine Raumprojektion


def halbwertsbreite(a: Antenne, traeger_hz: float, vertikal: bool = False) -> float | None:
    """Erster Schnitt G=0,5 beiderseits der Achse, volle Breite in Grad.

    Die Modelle sind in beiden Hauptschnitten symmetrisch. Beim Array liegt
    die erste Nullstelle bei sin(θ)=2/N. Wir suchen nur davor, damit kein
    Intervall mit Nebenkeulen mit der Hauptkeule verwechselt wird.
    Eine Gaußkeule, die bis zum Vorderraumrand nicht halbiert ist, liefert
    None; ihre künstliche Rückraum-Abschaltung ist keine Halbwertsstelle.
    """
    if a.typ == "isotrop":
        return None
    oben = 89.999999
    if a.typ == "patch_array":
        anzahl = a.elemente_vertikal if vertikal else a.elemente_horizontal
        oben = math.degrees(math.asin(2 / anzahl))

    def leistung(winkel: float) -> float:
        return float(richtdiagramm(a, 0 if vertikal else winkel, winkel if vertikal else 0, traeger_hz))

    if leistung(oben) >= .5:
        return None
    unten = 0.
    for _ in range(45):
        mitte = (unten + oben) / 2
        if leistung(mitte) >= .5:
            unten = mitte
        else:
            oben = mitte
    return unten + oben  # 2 × halber Öffnungswinkel


def berechne_diagramm(a: Antenne, traeger_hz: float) -> AntennenDiagramm:
    """Feste Speichergrenze: 301×401 Kartenzellen und zwei kleine Schnitte.

    Auch sehr schmale Keulen erhalten dichte Winkelwerte um die Hauptachse.
    Das verändert nur die Darstellung, niemals die Breite oder Echopegel.
    """
    pruefe_antenne(a)
    if not math.isfinite(traeger_hz) or traeger_hz <= 0:
        raise ValueError("Für das Antennendiagramm muss die Trägerfrequenz positiv und endlich sein.")
    breite_az = halbwertsbreite(a, traeger_hz)
    breite_el = halbwertsbreite(a, traeger_hz, vertikal=True)

    def ausschnitt(breite: float | None, maximum: float) -> float:
        return maximum if breite is None else min(maximum, 3 * breite)

    grenze_az = ausschnitt(breite_az, 180 if a.typ == "isotrop" else 89)
    grenze_el = ausschnitt(breite_el, 90)

    def winkelwerte(grenze: float, fokus: float) -> np.ndarray:
        return np.unique(np.r_[np.linspace(-grenze, grenze, 3601), np.linspace(-fokus, fokus, 2001)])

    az = winkelwerte(180, grenze_az)
    el = winkelwerte(90, grenze_el)
    karten_az = np.linspace(-grenze_az, grenze_az, 401)
    karten_el = np.linspace(-grenze_el, grenze_el, 301)
    return AntennenDiagramm(az, el, richtdiagramm(a, az, 0, traeger_hz),
                           richtdiagramm(a, 0, el, traeger_hz), breite_az, breite_el,
                           karten_az, karten_el,
                           richtdiagramm(a, karten_az[None, :], karten_el[:, None], traeger_hz))


def relative_db(leistung: np.ndarray) -> np.ndarray:
    """10 log10(G); nur die Anzeige wird bei −60 dB abgeschnitten, Referenz G=1."""
    return 10 * np.log10(np.maximum(leistung, 1e-6))


def polarschnitte(a: Antenne, traeger_hz: float, daten: AntennenDiagramm) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vollkreisschnitte [N]: Winkel [°], horizontale und vertikale Einweg-Leistung.

    θ dreht um die lokale Antennenachse: 0° vorwärts, ±90° seitlich/oben
    bzw. unten, ±180° rückwärts. Im vertikalen Schnitt ist θ außerhalb
    ±90° kein Elevationswinkel mehr, sondern ein Umlaufwinkel in der Ebene.
    Die gemeinsamen Winkel enthalten die dichten Werte BEIDER Hauptkeulen.
    """
    winkel = np.unique(np.r_[daten.azimut, daten.elevation])
    theta = np.deg2rad(winkel)
    # Elevation bleibt im Bereich ±90°; im Rückraum ist der lokale Azimut 180°.
    # So wird z.B. ein Umlaufwinkel von 120° nicht fälschlich vorwärts gespiegelt.
    azimut_vertikal = np.where(np.cos(theta) >= 0, 0., 180.)
    elevation = np.rad2deg(np.arctan2(np.sin(theta), np.abs(np.cos(theta))))
    return (winkel, richtdiagramm(a, winkel, 0, traeger_hz),
            richtdiagramm(a, azimut_vertikal, elevation, traeger_hz))


def polarkoordinaten(winkel_grad: np.ndarray, leistung: np.ndarray,
                     untergrenze_db: float = -30.) -> tuple[np.ndarray, np.ndarray]:
    """Logarithmischer Polarplot: 0 dB am Außenkreis, ≤ Untergrenze im Zentrum.

    r = (clip(10 log10(G), Untergrenze, 0) − Untergrenze) / |Untergrenze|.
    x = r sin(θ), y = r cos(θ): 0° oben, positive Winkel im Uhrzeigersinn.
    Dies ist eine reine Zeichenkoordinate, kein linearer Leistungsradius.
    Die Begrenzung verändert weder das Antennenmodell noch die Echopegel.
    """
    if not math.isfinite(untergrenze_db) or untergrenze_db >= 0:
        raise ValueError("Die dB-Untergrenze muss endlich und negativ sein.")
    with np.errstate(divide="ignore"):
        db = 10 * np.log10(leistung)
    radius = (np.clip(db, untergrenze_db, 0) - untergrenze_db) / abs(untergrenze_db)
    theta = np.deg2rad(winkel_grad)
    return radius * np.sin(theta), radius * np.cos(theta)
