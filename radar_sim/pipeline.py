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


def simulate_frame(config: RadarConfig, frame_index: int = 0) -> FrameResult:
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
            radarort = radar_zustand.position_m if radar_zustand else (0, 0, 0)
            gewinn = float(antennengewinn(config.antenne, np.array(zustand.position_m)-radarort, config.carrier_hz))
            ziele.append(Target(zustand.entfernung_m, zustand.radialgeschwindigkeit_mps, bahn.staerke,
                                antenna_gain=gewinn))
        config = replace(config, flugszene=None, targets=tuple(ziele))
        hinweise = validate_config(config)
    mischsignal = generate_echo(config, frame_index)
    spektrum = process_beat(mischsignal.beat, config)
    detektion = ca_cfar(spektrum.power, config)
    if radar_zustand is not None:
        hinweise.append("Bewegtes Radar: gemessene Radialgeschwindigkeit relativ zum Radarflugzeug; kein Bodenclutter oder Lageausgleich.")
    return FrameResult(config, mischsignal, spektrum, detektion,
                       group_candidates(spektrum, detektion, config), hinweise, frame_index,
                       eingabe, zeit_s, flugzustaende, radar_zustand)
