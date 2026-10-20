"""Öffentlicher, GUI-unabhängiger Frame-Einstieg."""

from dataclasses import dataclass, replace
from .config import RadarConfig, Target, validate_config
from .flugbahn import Flugzustand, berechne_flugzustand, relativer_zustand
import numpy as np
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .passivradar import PassivEmpfang
from .model import EchoFrame, generate_echo
from .processing import Spectrum, process_beat
from .detection import CFARResult, Candidate, ca_cfar, group_candidates
from .antenne import antennengewinn
from .ausbreitung import empfaengerort, monostatische_geometrie, atmosphaerenfaktor


@dataclass
class FrameResult:
    """Alle Ergebnisse eines Messpakets. config enthält die aktuellen Radar-Ziele,
    input_config die ursprünglichen Eingaben samt Flugbahn. zeit_s ist die Flugzeit.
    """
    config: RadarConfig
    echo: EchoFrame
    spectrum: Spectrum
    cfar: CFARResult
    candidates: list[Candidate]
    warnings: list[str]
    frame_index: int
    input_config: RadarConfig
    zeit_s: float
    flugzustaende: tuple[Flugzustand, ...]
    radar_zustand: Flugzustand | None = None
    passiv_empfang: "PassivEmpfang | None" = None
    vergleich: Spectrum | None = None  # dieselbe Szene ohne zuschaltbare Störungen


def simulate_frame(config: RadarConfig, frame_index: int = 0) -> FrameResult:
    """Frame plus Vergleich ohne Störungen; beide laufen im selben GUI-Worker.

    Wellenform, Seed, Masthöhe und Puls-Empfangssperre bleiben im Vergleich
    gleich. Nur die sechs zuschaltbaren Störungen werden ausgeschaltet.
    Es wird kein störungsfreies Ergebnis zur Detektion der gestörten Szene benutzt.
    """
    result = _simulate_frame(config, frame_index)
    e = config.effekte
    if any((e.leakage, e.saettigung, e.phasenrauschen, e.erdkruemmung, e.atmosphaere, e.bodenclutter)):
        ideal = replace(e, leakage=False, saettigung=False, phasenrauschen=False,
                        erdkruemmung=False, atmosphaere=False, bodenclutter=False)
        result.vergleich = _simulate_frame(replace(config, effekte=ideal), frame_index).spectrum
    return result


def _simulate_frame(config: RadarConfig, frame_index: int = 0) -> FrameResult:
    """Ein Messpaket berechnen: Flugposition -> Echo -> FFTs -> Detektion.

    config ist die Eingabe einschließlich der vollständigen Flugbahn.
    result.config enthält dagegen nur die Radar-Ziele am aktuellen Zeitpunkt.
    Ein Frame bleibt ein kurzes Messpaket von wenigen Millisekunden. Zwischen
    diesen Paketen bewegt sich das Objekt um den einstellbaren Zeitschritt.
    """
    if type(frame_index) is not int or frame_index < 0:
        raise ValueError("Die Nummer des Messpakets muss eine ganze Zahl ab null sein.")
    if config.radar_mode == "passive":
        from .passivradar import simulate_passive
        return simulate_passive(config, frame_index)
    hinweise = validate_config(config)
    eingabe = config
    zeit_s = 0.0
    flugzustaende = ()
    radar_zustand = None
    if config.flugszene is not None:
        szene = config.flugszene
        if frame_index > szene.letzter_frame:
            raise ValueError("Der Flug ist beendet. Zum erneuten Abspielen bei Frame 0 beginnen.")
        zeit_s = min(frame_index * szene.zeitschritt_s, szene.dauer_s)
        radar_zustand = berechne_flugzustand(szene.radar_bahn, zeit_s) if szene.radar_bahn else None
        flugzustaende = tuple(relativer_zustand(bahn, szene.radar_bahn, zeit_s) for bahn in szene.bahnen)
        ziele = []
        for bahn, zustand in zip(szene.bahnen, flugzustaende):
            radarort, radartempo = empfaengerort(config, radar_zustand)
            tempo = (zustand.geschwindigkeit_x_mps, zustand.geschwindigkeit_y_mps, zustand.geschwindigkeit_hoehe_mps)
            r, v, sichtbar, blick = monostatische_geometrie(zustand.position_m, tempo, radarort, radartempo, config.effekte)
            gewinn = float(antennengewinn(config.antenne, blick, config.carrier_hz))
            ziele.append(Target(r, v, bahn.staerke, antenna_gain=gewinn,
                                path_gain=float(sichtbar)*atmosphaerenfaktor(2*r, config.effekte)))
            if not sichtbar:
                hinweise.append("Ein Soll-Target liegt hinter dem Erdhorizont und liefert kein direktes Echo.")
        flugzustaende = tuple(replace(z, entfernung_m=t.range_m, radialgeschwindigkeit_mps=t.velocity_mps)
                             for z, t in zip(flugzustaende, ziele))
        config = replace(config, flugszene=None, targets=tuple(ziele))
        hinweise += validate_config(config, _geometrie=False)
    elif config.effekte.atmosphaere:
        config = replace(config, targets=tuple(replace(z, path_gain=z.path_gain*atmosphaerenfaktor(2*z.range_m, config.effekte))
                                                for z in config.targets))
    from .bodenclutter import aktive_bodenquellen
    boden = aktive_bodenquellen(config, eingabe, radar_zustand)
    mischsignal = generate_echo(config, frame_index, boden)
    spektrum = process_beat(mischsignal.beat, config)
    detektion = ca_cfar(spektrum.power, config)
    if radar_zustand is not None:
        hinweise.append("Bewegtes Radar: Radialgeschwindigkeit relativ zur Plattform; Antennenrichtung ohne Lageausgleich.")
    if any((config.effekte.saettigung, config.effekte.leakage, config.effekte.bodenclutter)):
        hinweise.append(f"Empfänger: {100*mischsignal.clipped_fraction:.2f} % begrenzt; Leakage-Leistung {mischsignal.leakage_power:.4g}, Clutter-Einzelpowersumme {mischsignal.clutter_power:.4g}, jeweils / Aref² vor Begrenzung.")
    return FrameResult(config, mischsignal, spektrum, detektion,
                       group_candidates(spektrum, detektion, config), hinweise, frame_index,
                       eingabe, zeit_s, flugzustaende, radar_zustand)
