"""Eine gezeichnete Route glatt und mit gleichbleibendem Flugtempo abfliegen.

Zwischen den Maus-Punkten liegt eine natürliche kubische Kurve. Anders als bei
einem Linienzug entstehen an den Punkten keine plötzlichen Richtungssprünge.
Die Zeit richtet sich nach der zurückgelegten Strecke, nicht nach Punktabständen.
"""

from dataclasses import dataclass
from functools import lru_cache
import math
import numpy as np
from numpy.polynomial import polynomial as polynom

MAX_ROUTENPUNKTE = 256  # Begrenzt Geometriearbeit beim interaktiven Verschieben.


@dataclass(frozen=True)
class GezeichneteRoute:
    punkte: tuple[tuple[float, ...], ...]  # (x,y,z) in m; alte (x,z)-Dateien bleiben lesbar
    geschwindigkeit_mps: float = 5.0


@dataclass
class RoutenDaten:
    koeffizienten: np.ndarray  # [Abschnitt, Polynomgrad 0..3, Koordinate x/y/z bzw. alt x/z]
    strecken: np.ndarray  # aufsummierte Abschnittslängen [m], beginnt mit 0
    teilstrecken: np.ndarray  # [Abschnitt, Stützstelle] für die Zeitzuordnung
    kleinste_hoehe_m: float
    groesste_hoehe_m: float
    groesstes_abs_x_m: float
    kruemmungsgrenze_pro_m: float
    groesstes_abs_y_m: float = 0.0

    @property
    def laenge_m(self) -> float:
        return float(self.strecken[-1])


# Acht Integrationspunkte genügen pro kleinem Kurvenstück. NumPy liefert die
# Gewichte; keine zusätzliche Mathematik-Bibliothek wird benötigt.
GAUSS_PUNKTE, GAUSS_GEWICHTE = np.polynomial.legendre.leggauss(8)
U_STUETZSTELLEN = np.linspace(0, 1, 65)


def _ableitung(koeffizienten: np.ndarray, u: np.ndarray | float) -> np.ndarray:
    u = np.asarray(u)
    return (koeffizienten[1] + 2 * u[..., None] * koeffizienten[2]
            + 3 * u[..., None]**2 * koeffizienten[3])


def _streckenintegral(koeffizienten: np.ndarray, anfang: float | np.ndarray,
                     ende: float | np.ndarray) -> np.ndarray:
    """Strecke = Integral über die Länge des Tangentenvektors, Einheit Meter."""
    mitte = (np.asarray(anfang) + np.asarray(ende)) / 2
    halbe_breite = (np.asarray(ende) - np.asarray(anfang)) / 2
    u = mitte[..., None] + halbe_breite[..., None] * GAUSS_PUNKTE
    tempo = np.linalg.norm(_ableitung(koeffizienten, u), axis=-1)
    return halbe_breite * np.sum(tempo * GAUSS_GEWICHTE, axis=-1)


def _nullstellen_im_abschnitt(koeffizienten: np.ndarray) -> list[float]:
    """Reelle Nullstellen eines Polynoms innerhalb 0<u<1, aufsteigende Koeffizienten."""
    werte = np.trim_zeros(np.asarray(koeffizienten), trim="b")
    if len(werte) < 2:
        return []
    return [float(z.real) for z in polynom.polyroots(werte)
            if abs(z.imag) < 1e-9 and 0 < z.real < 1]


def berechne_routendaten(route: GezeichneteRoute) -> RoutenDaten:
    """Prüft das Tempo; die Geometrie wird unabhängig davon zwischengespeichert."""
    if (isinstance(route.geschwindigkeit_mps, bool) or not math.isfinite(route.geschwindigkeit_mps)
            or not 0 < route.geschwindigkeit_mps <= 1e6):
        raise ValueError("Das Routentempo muss positiv und höchstens 1.000.000 m/s sein.")
    return _routengeometrie(route.punkte)


@lru_cache(maxsize=32)
def _routengeometrie(stuetzpunkte: tuple[tuple[float, ...], ...]) -> RoutenDaten:
    """Bereitet die Geometrie einmal vor; nachfolgende Frames verwenden sie wieder.

    Das Kurvenstück ist p(u)=a+b*u+c*u²+d*u³, 0<=u<=1. Die erste und zweite
    Ableitung passen an den Abschnittsgrenzen zusammen (natürliche kubische
    Interpolation mit Sehnenlängen als Knotenabstand). Höhenextrema werden
    analytisch geprüft, damit die Kurve nicht zwischen Mauspunkten unter den
    Boden schwingt. Spitzkehren mit verschwindender Tangente sind unzulässig.
    """
    if not 2 <= len(stuetzpunkte) <= MAX_ROUTENPUNKTE:
        raise ValueError(f"Eine Route braucht 2 bis {MAX_ROUTENPUNKTE} Punkte.")
    punkte = np.asarray(stuetzpunkte, dtype=float)
    if punkte.ndim != 2 or punkte.shape[1] not in (2, 3) or not np.isfinite(punkte).all():
        raise ValueError("Routenpunkte müssen endliche (x,y,z)-Tripel oder alte (x,z)-Paare sein.")
    dimensionen = punkte.shape[1]
    if np.any(np.abs(punkte) > 1e4) or np.any(punkte[:, -1] <= 0):
        raise ValueError("Routenpunkte müssen über dem Boden und innerhalb ±10.000 m liegen.")
    abstaende = np.linalg.norm(np.diff(punkte, axis=0), axis=1)
    if np.any(abstaende < 0.05):
        raise ValueError("Benachbarte Routenpunkte brauchen mindestens 5 cm Abstand.")

    # Dreidiagonales Gleichungssystem für die zweiten Ableitungen, Randwerte 0.
    # Vorwärts eliminieren und rückwärts einsetzen braucht nur O(Punktzahl),
    # statt eine volle Matrix aufzubauen. Alle Raumkoordinaten laufen gemeinsam.
    anzahl = len(punkte)
    diagonale = np.ones(anzahl)
    rechte_seite = np.zeros((anzahl, dimensionen))
    for i in range(1, anzahl - 1):
        links, rechts = abstaende[i - 1], abstaende[i]
        faktor = links / diagonale[i - 1]
        diagonale[i] = 2*(links+rechts) - faktor*(abstaende[i-1] if i > 1 else 0)
        rechte_seite[i] = 6 * ((punkte[i + 1] - punkte[i]) / rechts
                               - (punkte[i] - punkte[i - 1]) / links) - faktor*rechte_seite[i-1]
    zweite_ableitungen = np.zeros_like(rechte_seite)
    for i in range(anzahl-2, 0, -1):
        zweite_ableitungen[i] = (rechte_seite[i] - abstaende[i]*zweite_ableitungen[i+1])/diagonale[i]
    abschnitte = []
    strecken = [0.0]
    teilstrecken = []
    alle_hoehen = []
    alle_x = []
    alle_y = []
    kruemmungsgrenze = 0.0
    for i, abstand in enumerate(abstaende):
        a = punkte[i]
        b = punkte[i + 1] - punkte[i] - abstand**2 * (2 * zweite_ableitungen[i] + zweite_ableitungen[i + 1]) / 6
        c = abstand**2 * zweite_ableitungen[i] / 2
        d = abstand**2 * (zweite_ableitungen[i + 1] - zweite_ableitungen[i]) / 6
        k = np.array([a, b, c, d])
        abschnitte.append(k)
        sammlungen = [alle_x, alle_hoehen] if dimensionen == 2 else [alle_x, alle_y, alle_hoehen]
        for achse, sammlung in enumerate(sammlungen):
            u_werte = [0.0, 1.0] + _nullstellen_im_abschnitt(k[1:, achse] * np.arange(1, 4))
            sammlung.extend(float(polynom.polyval(u, k[:, achse])) for u in u_werte)

        # Sichere Krümmungsschranke: κ <= max|p''| / min|p'|².
        # Das Minimum des quadratischen Tangentenbetrags wird über dessen
        # Ableitungsnullstellen exakt auf jedem Abschnitt gesucht.
        tangente = k[1:] * np.arange(1, 4)[:, None]
        quadrat = np.zeros(5)
        for achse in range(dimensionen):
            quadrat = polynom.polyadd(
                quadrat, polynom.polymul(tangente[:, achse], tangente[:, achse]))
        pruefpunkte = [0.0, 1.0] + _nullstellen_im_abschnitt(polynom.polyder(quadrat))
        minimum = min(float(np.linalg.norm(_ableitung(k, u))**2) for u in pruefpunkte)
        if minimum < (1e-5 * abstand)**2:
            raise ValueError("Die Route enthält eine zu spitze Umkehr. Eine größere Kurve zeichnen.")
        zweite_max = max(np.linalg.norm(2 * c), np.linalg.norm(2 * c + 6 * d))
        kruemmungsgrenze = max(kruemmungsgrenze, float(zweite_max / minimum))
        stuecke = _streckenintegral(k, U_STUETZSTELLEN[:-1], U_STUETZSTELLEN[1:])
        summen = np.concatenate(([0.0], np.cumsum(stuecke)))
        teilstrecken.append(summen)
        strecken.append(strecken[-1] + summen[-1])
    if min(alle_hoehen) <= 0:
        raise ValueError("Die geglättete Route berührt den Boden. Eine höhere oder flachere Kurve zeichnen.")
    return RoutenDaten(np.asarray(abschnitte), np.asarray(strecken), np.asarray(teilstrecken),
                       min(alle_hoehen), max(alle_hoehen), max(map(abs, alle_x)), kruemmungsgrenze,
                       max(map(abs, alle_y), default=0.0))


def routen_position(route: GezeichneteRoute, zeit_s: float) -> tuple[float, ...]:
    """Liefert x, Höhe, vx, vh bei konstantem Tempo entlang der geglätteten Kurve.

    Die Weglänge s=v*t bestimmt die Position. Eine kurze Newton-Korrektur
    invertiert das Bogenlängenintegral; die Fluggeschwindigkeit ist die
    normierte Kurventangente mal eingestelltes Tempo. Am letzten Zeitpunkt
    endet die Darstellung; eine Bremsbewegung wird nicht behauptet.
    """
    daten = berechne_routendaten(route)
    s = min(max(0.0, zeit_s * route.geschwindigkeit_mps), daten.laenge_m)
    abschnitt = min(int(np.searchsorted(daten.strecken, s, side="right") - 1), len(daten.koeffizienten) - 1)
    teil_s = s - daten.strecken[abschnitt]
    tabelle = daten.teilstrecken[abschnitt]
    index = min(max(int(np.searchsorted(tabelle, teil_s, side="right") - 1), 0), len(tabelle) - 2)
    u0 = U_STUETZSTELLEN[index]
    u = float(np.interp(teil_s, tabelle, U_STUETZSTELLEN))
    k = daten.koeffizienten[abschnitt]
    for _ in range(3):
        fehler = tabelle[index] + float(_streckenintegral(k, u0, u)) - teil_s
        u = float(np.clip(u - fehler / np.linalg.norm(_ableitung(k, u)), 0, 1))
    ort = k[0] + u * k[1] + u**2 * k[2] + u**3 * k[3]
    tangente = _ableitung(k, u)
    geschwindigkeit = route.geschwindigkeit_mps * tangente / np.linalg.norm(tangente)
    return tuple(float(wert) for wert in np.concatenate((ort, geschwindigkeit)))


def routen_position_3d(route: GezeichneteRoute, zeit_s: float) -> tuple[float, ...]:
    """Immer (x,y,z,vx,vy,vz); alte ebene Routen liegen in der Ebene y=0."""
    werte = routen_position(route, zeit_s)
    if len(werte) == 4:
        x, z, vx, vz = werte
        return x, 0.0, z, vx, 0.0, vz
    return werte


def punkt_auf_route(route: GezeichneteRoute, achsen: tuple[int, int], klickpunkt,
                   pixel_pro_meter) -> tuple[int, np.ndarray, float]:
    """Nächster Kurvenpunkt in einer Projektion; dritte Koordinate aus der 3D-Kurve.

    Eingang: zwei Achsenindizes, Klickort [m] und zwei Bildskalierungen [Pixel/m].
    Rückgabe: Abschnittsindex, räumlicher Punkt [m], Abstand zum Klick [Pixel].
    Das Minimum von |p(u)-Klick|² liegt am Rand oder bei einer Nullstelle seiner
    Ableitung (Polynomgrad 5). So hängt das Einfügen nicht von der Plot-Abtastung ab.
    """
    daten = berechne_routendaten(route)
    beste = None
    for i, original in enumerate(daten.koeffizienten):
        k = original if original.shape[1] == 3 else np.column_stack(
            (original[:, 0], np.zeros(4), original[:, 1]))
        projiziert = k[:, list(achsen)].copy()
        projiziert[0] -= np.asarray(klickpunkt)
        projiziert *= np.asarray(pixel_pro_meter)
        ableitung = np.zeros(6)
        for j in range(2):
            ableitung = polynom.polyadd(ableitung,
                polynom.polymul(projiziert[:, j],
                                                 polynom.polyder(projiziert[:, j])))
        for u in [0., 1.] + _nullstellen_im_abschnitt(ableitung):
            abstand = float(np.linalg.norm(polynom.polyval(u, projiziert)))
            if beste is None or abstand < beste[2]:
                beste = (i, polynom.polyval(u, k), abstand)
    return beste
