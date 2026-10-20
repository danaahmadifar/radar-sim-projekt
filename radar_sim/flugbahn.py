"""Bekannte Flugbewegung in Weltkoordinaten (x,y,z), Z über dem Boden.

Die Station steht standardmäßig im Ursprung; optional trägt eine zweite Bahn
das monostatische Radar. Entfernung und radiale Geschwindigkeit beziehen sich
auf dessen Position und Geschwindigkeit. Die Höhe ist keine Radarschätzung.
"""

from dataclasses import dataclass, replace
import math
import numpy as np
from .route import GezeichneteRoute, berechne_routendaten, routen_position_3d


@dataclass(frozen=True)
class Flugbahn:
    """Startwerte einer Flugbahn; Meter, Sekunden und daraus abgeleitete Einheiten.

    x: horizontaler Ort; positive Geschwindigkeit bedeutet Flug nach rechts.
    hoehe: Höhe über Boden; positive Geschwindigkeit bedeutet Steigen.
    beschleunigung_hoehe_mps2: konstante senkrechte Beschleunigung.
    Null ergibt eine gerade Bahn, ein negativer Wert eine nach unten offene Parabel.
    Wenn route gesetzt ist, bestimmen deren Punkte und Tempo die Bewegung;
    die analytischen Geschwindigkeits-/Beschleunigungsfelder werden dann nicht benutzt.
    """

    start_x_m: float = -100.0
    start_hoehe_m: float = 35.0
    geschwindigkeit_x_mps: float = 10.0
    geschwindigkeit_hoehe_mps: float = 0.0
    beschleunigung_hoehe_mps2: float = 0.0
    staerke: float = 1.0
    route: GezeichneteRoute | None = None
    start_y_m: float = 0.0
    geschwindigkeit_y_mps: float = 0.0


@dataclass(frozen=True)
class Flugszene:
    name: str
    bahnen: tuple[Flugbahn, ...]
    dauer_s: float = 20.0
    zeitschritt_s: float = 0.1
    radar_bahn: Flugbahn | None = None  # Monostatischer Sender UND Empfänger auf dieser Bahn.

    @property
    def letzter_frame(self) -> int:
        """Der letzte Frame liegt genau am Ende; sein Zeitschritt darf kürzer sein."""
        return math.ceil(self.dauer_s / self.zeitschritt_s)


@dataclass(frozen=True)
class Flugzustand:
    x_m: float
    hoehe_m: float
    geschwindigkeit_x_mps: float
    geschwindigkeit_hoehe_mps: float
    entfernung_m: float
    radialgeschwindigkeit_mps: float
    y_m: float = 0.0
    geschwindigkeit_y_mps: float = 0.0

    @property
    def position_m(self) -> tuple[float, float, float]:
        return self.x_m, self.y_m, self.hoehe_m


@dataclass(frozen=True)
class BahnGrenzen:
    entfernung_max_m: float
    tempo_max_mps: float
    radialbeschleunigung_max_mps2: float


def relativer_zustand(bahn: Flugbahn, radar_bahn: Flugbahn | None, zeit_s: float) -> Flugzustand:
    """Weltposition beibehalten, aber R und dR/dt relativ zum Radar berechnen.

    p = p_target − p_radar, u = v_target − v_radar;
    R = |p|, v_radial = p·u/R. Positives Vorzeichen bedeutet Entfernen.
    Die Radarplattform ist kein zusätzliches Echoziel ihres eigenen Radars.
    """
    ziel = berechne_flugzustand(bahn, zeit_s)
    if radar_bahn is None:
        return ziel
    radar = berechne_flugzustand(radar_bahn, zeit_s)
    ort = np.array(ziel.position_m) - radar.position_m
    tempo = np.array([ziel.geschwindigkeit_x_mps-radar.geschwindigkeit_x_mps,
                      ziel.geschwindigkeit_y_mps-radar.geschwindigkeit_y_mps,
                      ziel.geschwindigkeit_hoehe_mps-radar.geschwindigkeit_hoehe_mps])
    entfernung = float(np.linalg.norm(ort))
    if entfernung <= 0:
        raise ValueError("Radarflugzeug und Target dürfen nicht am selben Ort sein.")
    return replace(ziel, entfernung_m=entfernung, radialgeschwindigkeit_mps=float(ort@tempo/entfernung))


def relative_bahngrenzen(bahn: Flugbahn, szene: Flugszene) -> BahnGrenzen:
    """Analytische sichere Grenzen; bewegtes Radar zunächst mit analytischen Bahnen.

    Relative Lage ist höchstens quadratisch in t. Extrema von |p|² folgen
    aus den reellen Nullstellen seiner kubischen Ableitung. Keine zeitliche
    Stichprobe, die eine Annäherung zwischen Frames übersehen könnte.
    """
    radar = szene.radar_bahn
    if radar is None:
        return grenzen_der_flugbahn(bahn, szene.dauer_s)
    if radar.route is not None or bahn.route is not None:
        raise ValueError("Bewegtes Radar: zunächst gerade oder parabelförmige Bahnen verwenden; freie Routen sind hier nicht freigegeben.")
    abstaende, tempo, beschleunigung = _relative_extrema(bahn, radar, szene.dauer_s)
    minimum = min(abstaende)
    if minimum < 1:
        raise ValueError("Die beiden Flugzeuge müssen während der gesamten Szene mindestens 1 m Abstand halten.")
    return BahnGrenzen(max(abstaende), tempo, tempo**2/minimum + beschleunigung)


def kleinster_abstand(bahn: Flugbahn, szene: Flugszene) -> float:
    """Minimale relative Entfernung einer analytischen Bahn, ohne Zeitraster.

    Freie Routen bei fester Bodenstation: kleinste Höhe als sichere Untergrenze.
    """
    if bahn.route is not None:
        return berechne_routendaten(bahn.route).kleinste_hoehe_m
    abstaende, _, _ = _relative_extrema(bahn, szene.radar_bahn or Flugbahn(0, 0, 0), szene.dauer_s)
    return min(abstaende)


def _relative_extrema(bahn: Flugbahn, radar: Flugbahn, dauer_s: float) -> tuple[list[float], float, float]:
    """Abstands-Extrema, maximales Relativtempo und Betrag der Relativbeschleunigung."""
    p = np.array([bahn.start_x_m-radar.start_x_m, bahn.start_y_m-radar.start_y_m,
                  bahn.start_hoehe_m-radar.start_hoehe_m])
    v = np.array([bahn.geschwindigkeit_x_mps-radar.geschwindigkeit_x_mps,
                  bahn.geschwindigkeit_y_mps-radar.geschwindigkeit_y_mps,
                  bahn.geschwindigkeit_hoehe_mps-radar.geschwindigkeit_hoehe_mps])
    a = np.array([0., 0., bahn.beschleunigung_hoehe_mps2-radar.beschleunigung_hoehe_mps2])
    koeffizienten = np.array([p@p, 2*p@v, v@v+p@a, v@a, a@a/4])
    wurzeln = np.polynomial.polynomial.polyroots(np.polynomial.polynomial.polyder(koeffizienten))
    zeiten = [0., dauer_s] + [float(t.real) for t in wurzeln if abs(t.imag)<1e-9 and 0<t.real<dauer_s]
    abstaende = [float(np.linalg.norm(p+v*t+a*t*t/2)) for t in zeiten]
    tempo = max(float(np.linalg.norm(v)), float(np.linalg.norm(v+a*dauer_s)))
    return abstaende, tempo, float(np.linalg.norm(a))


def grenzen_der_flugbahn(bahn: Flugbahn, dauer_s: float) -> BahnGrenzen:
    """Sichere Schranken der ganzen Bahn, gemeinsam für Prüfung und Slider.

    Radiale Beschleunigung <= Tempo²/kleinste Höhe + Flugbeschleunigung.
    Bei einer gezeichneten Kurve ist Flugbeschleunigung <= Tempo²*Krümmung.
    Die Schranken sind vorsichtig; nicht alle Extrema müssen gleichzeitig auftreten.
    """
    if bahn.route is not None:
        daten = berechne_routendaten(bahn.route)
        tempo = bahn.route.geschwindigkeit_mps
        entfernung = math.hypot(daten.groesstes_abs_x_m, daten.groesstes_abs_y_m, daten.groesste_hoehe_m)
        beschleunigung = tempo**2 * (1 / daten.kleinste_hoehe_m + daten.kruemmungsgrenze_pro_m)
        return BahnGrenzen(entfernung, tempo, beschleunigung)
    zustaende = [berechne_flugzustand(bahn, zeit) for zeit in _extremzeiten(bahn, dauer_s)]
    groesstes_x = max(abs(z.x_m) for z in zustaende)
    groesstes_y = max(abs(z.y_m) for z in zustaende)
    groesste_hoehe = max(z.hoehe_m for z in zustaende)
    kleinste_hoehe = min(z.hoehe_m for z in zustaende)
    steigrate = max(abs(z.geschwindigkeit_hoehe_mps) for z in zustaende)
    tempo = math.hypot(bahn.geschwindigkeit_x_mps, bahn.geschwindigkeit_y_mps, steigrate)
    beschleunigung = tempo**2 / kleinste_hoehe + abs(bahn.beschleunigung_hoehe_mps2)
    return BahnGrenzen(math.hypot(groesstes_x, groesstes_y, groesste_hoehe), tempo, beschleunigung)


def erstelle_routenszene(route: GezeichneteRoute, zeitschritt_s: float = 0.1,
                         staerke: float = 1.0) -> Flugszene:
    """Die Flugdauer folgt aus Kurvenlänge / Tempo, nicht aus einer zweiten Eingabe."""
    daten = berechne_routendaten(route)
    erster_punkt = routen_position_3d(route, 0)
    bahn = Flugbahn(start_x_m=erster_punkt[0], start_y_m=erster_punkt[1], start_hoehe_m=erster_punkt[2],
                    staerke=staerke, route=route)
    return Flugszene("Gezeichnete Flugroute", (bahn,), daten.laenge_m / route.geschwindigkeit_mps, zeitschritt_s)


def _extremzeiten(bahn: Flugbahn, dauer_s: float) -> list[float]:
    """Randzeiten und möglicher Scheitel der vorgegebenen Höhenparabel [s]."""
    zeiten = [0.0, dauer_s]
    if bahn.beschleunigung_hoehe_mps2:
        scheitel = -bahn.geschwindigkeit_hoehe_mps / bahn.beschleunigung_hoehe_mps2
        if 0 < scheitel < dauer_s:
            zeiten.append(scheitel)
    return zeiten


def berechne_flugzustand(bahn: Flugbahn, zeit_s: float) -> Flugzustand:
    """Berechnet den Ort und die Bewegung zu einem Zeitpunkt t [s].

    x(t) = x0 + vx*t
    h(t) = h0 + vh0*t + a*t²/2
    y(t) = y0 + vy*t, R(t) = sqrt(x²+y²+h²)
    v_radial(t) = dR/dt = (x*vx + y*vy + h*vh)/R

    Wichtig: v_radial ist NICHT die gesamte Fluggeschwindigkeit.
    Negativ heißt Annäherung an die Station, positiv heißt Entfernung.
    """
    if not math.isfinite(zeit_s) or zeit_s < 0:
        raise ValueError("Die Flugzeit muss eine endliche Zahl ab null Sekunden sein.")
    if bahn.route is not None:
        x_m, y_m, hoehe_m, waagerechte_geschwindigkeit, geschwindigkeit_y, senkrechte_geschwindigkeit = routen_position_3d(bahn.route, zeit_s)
    else:
        x_m = bahn.start_x_m + bahn.geschwindigkeit_x_mps * zeit_s
        y_m = bahn.start_y_m + bahn.geschwindigkeit_y_mps * zeit_s
        geschwindigkeit_y = bahn.geschwindigkeit_y_mps
        hoehe_m = (bahn.start_hoehe_m + bahn.geschwindigkeit_hoehe_mps * zeit_s
                   + 0.5 * bahn.beschleunigung_hoehe_mps2 * zeit_s**2)
        waagerechte_geschwindigkeit = bahn.geschwindigkeit_x_mps
        senkrechte_geschwindigkeit = (bahn.geschwindigkeit_hoehe_mps
                                     + bahn.beschleunigung_hoehe_mps2 * zeit_s)
    entfernung_m = math.hypot(x_m, y_m, hoehe_m)
    if hoehe_m <= 0:
        raise ValueError("Die Flugbahn muss während der gesamten Szene über dem Boden bleiben (Z > 0).")
    radialgeschwindigkeit = (x_m * waagerechte_geschwindigkeit
                             + y_m * geschwindigkeit_y
                             + hoehe_m * senkrechte_geschwindigkeit) / entfernung_m
    return Flugzustand(x_m, hoehe_m, waagerechte_geschwindigkeit,
                       senkrechte_geschwindigkeit, entfernung_m, radialgeschwindigkeit, y_m, geschwindigkeit_y)


def flugbahn_punkte(bahn: Flugbahn, dauer_s: float) -> np.ndarray:
    """XYZ-Array [N,3] in m für Diagramme; mehr Punkte bei komplexen Routen.

    Dies ist nur die Zeichenabtastung. Die Frameberechnung wertet die glatte
    Flugkurve unabhängig davon zum tatsächlichen Zeitpunkt aus.
    """
    anzahl = max(201, 4*len(bahn.route.punkte)) if bahn.route else 201
    return np.array([berechne_flugzustand(bahn, float(t)).position_m
                     for t in np.linspace(0, dauer_s, anzahl)])


def pruefe_flugszene(szene: Flugszene) -> None:
    """Prüft Eingaben und Höhe über die gesamte Bahn, auch zwischen Frames."""
    if not isinstance(szene.name, str) or not 1 <= len(szene.name) <= 80:
        raise ValueError("Eine Flugszene braucht einen Namen mit 1 bis 80 Zeichen.")
    for wert in (szene.dauer_s, szene.zeitschritt_s):
        if isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert):
            raise ValueError("Flugdauer und Zeitschritt müssen endliche Zahlen sein.")
    if min(szene.dauer_s, szene.zeitschritt_s) <= 0:
        raise ValueError("Flugdauer und Zeitschritt müssen größer als null sein.")
    if not math.isfinite(szene.dauer_s / szene.zeitschritt_s):
        raise ValueError("Die Kombination aus Flugdauer und Zeitschritt ist numerisch zu groß.")
    if not 1 <= len(szene.bahnen) <= 8:
        raise ValueError("Eine Flugszene braucht 1 bis 8 Flugobjekte.")
    if szene.radar_bahn is not None and not isinstance(szene.radar_bahn, Flugbahn):
        raise ValueError("Die Radarplattform muss eine Flugbahn sein.")
    for nummer, bahn in enumerate(szene.bahnen, 1):
        if not isinstance(bahn, Flugbahn):
            raise ValueError("Jedes Flugobjekt muss eine Flugbahn sein.")
        if bahn.route is not None:
            if not isinstance(bahn.route, GezeichneteRoute) or len(szene.bahnen) != 1:
                raise ValueError("Eine gezeichnete Route wird mit genau einem Flugobjekt verwendet.")
            daten = berechne_routendaten(bahn.route)
            if not math.isclose(szene.dauer_s, daten.laenge_m / bahn.route.geschwindigkeit_mps, rel_tol=1e-8):
                raise ValueError("Bei einer Route muss die Flugdauer zu Kurvenlänge und Tempo passen.")
        werte = (bahn.start_x_m, bahn.start_hoehe_m, bahn.geschwindigkeit_x_mps,
                 bahn.geschwindigkeit_hoehe_mps, bahn.beschleunigung_hoehe_mps2, bahn.staerke,
                 bahn.start_y_m, bahn.geschwindigkeit_y_mps)
        if any(isinstance(wert, bool) or not isinstance(wert, (int, float))
               or not math.isfinite(wert) or abs(wert) > 1e7 for wert in werte):
            raise ValueError(f"Flugobjekt {nummer}: endliche Zahlen mit Betrag höchstens 10⁷ eingeben.")
        if not 0 < bahn.staerke <= 1e6:
            raise ValueError(f"Flugobjekt {nummer}: Die Echostärke muss positiv sein.")
        # Die größte/kleinste Höhe einer Parabel liegt am Rand oder am Scheitel.
        for zeit in _extremzeiten(bahn, szene.dauer_s):
            berechne_flugzustand(bahn, zeit)
    if szene.radar_bahn is not None:
        pruefe_flugszene(replace(szene, bahnen=(szene.radar_bahn,), radar_bahn=None))
        for bahn in szene.bahnen:
            relative_bahngrenzen(bahn, szene)


def flugszenen() -> dict[str, Flugszene]:
    """Drei überschaubare Beispiele: kleine Flugobjekte mit 10 m/s = 36 km/h."""
    return {
        "06_ueberflug": Flugszene("Ein Objekt: Überflug in 35 m Höhe", (Flugbahn(),)),
        "07_gegenverkehr": Flugszene("Zwei Objekte: entgegengesetzte Flugrichtung", (
            Flugbahn(), Flugbahn(80.0, 60.0, -10.0, staerke=0.8))),
        "08_parabel": Flugszene("Ein Objekt: parabelförmiger Überflug", (
            Flugbahn(-100.0, 25.0, 10.0, 4.0, -0.4),)),
    }
