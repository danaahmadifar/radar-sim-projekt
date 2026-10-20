"""Störmodelle vor großen Allokationen prüfen; keine Signalberechnung."""

from dataclasses import fields
import math
from .effekt_config import Stoereffekte
from .config import C


def pruefe_effekte(c, geometrie: bool = True) -> list[str]:
    e = c.effekte
    if not isinstance(e, Stoereffekte):
        raise ValueError("Ungültige Störeffekt-Einstellungen.")
    schalter = {"leakage", "saettigung", "phasenrauschen", "erdkruemmung", "atmosphaere", "bodenclutter", "teilpulse"}
    ganze = {"clutter_ringe", "clutter_sektoren"}
    for feld in fields(e):
        wert = getattr(e, feld.name)
        if feld.name in schalter:
            if type(wert) is not bool:
                raise ValueError(f"{feld.name}: Schalter muss boolesch sein.")
        elif isinstance(wert, bool) or not isinstance(wert, (int, float)) or not math.isfinite(wert):
            raise ValueError(f"{feld.name}: endliche Zahl erforderlich.")
        elif feld.name in ganze and type(wert) is not int:
            raise ValueError("Clutter-Ringe und -Sektoren müssen ganze Zahlen sein.")
    bereiche = {
        "leakage_db": (-80, 100), "leakage_delay_s": (0, .001),
        "saettigung_db": (-60, 100), "phase_rms_rad": (0, 3), "phase_zeit_s": (1e-9, 1),
        "erdradius_faktor": (1, 2), "stationshoehe_m": (0, 10000),
        "daempfung_db_km": (0, 100), "sigma0_db": (-80, 0),
        "clutter_innen_m": (1, 1e6), "clutter_aussen_m": (2, 1e6),
        "clutter_ringe": (1, 12), "clutter_sektoren": (4, 36),
    }
    for name, (unten, oben) in bereiche.items():
        if not unten <= getattr(e, name) <= oben:
            raise ValueError(f"{name}: erlaubt {unten:g} bis {oben:g}.")
    if e.clutter_innen_m >= e.clutter_aussen_m or e.clutter_ringe*e.clutter_sektoren > 128:
        raise ValueError("Clutter: Innenradius < Außenradius und höchstens 128 Flächen erforderlich.")
    if c.radar_mode == "passive" and e.leakage:
        raise ValueError("Passivradar besitzt keinen eigenen Sender. Den Direktweg im Tab Passivradar verwenden.")
    if geometrie and c.flugszene is None and (e.erdkruemmung or e.stationshoehe_m):
        raise ValueError("Erdkrümmung und Masthöhe benötigen eine räumliche Flugbahn, keine reinen R/v-Targets.")
    if e.leakage:
        from .empfaenger import phasen_bandreserve
        if c.radar_mode == "fmcw":
            if e.leakage_delay_s > c.timing_range_limit*2/C or c.slope*e.leakage_delay_s+phasen_bandreserve(c) >= .45*c.sample_rate_hz:
                raise ValueError("Leakage-Verzögerung überschreitet Rampen-/ADC-Grenzen. Kürzeren Kopplungsweg einstellen.")
        elif e.leakage_delay_s+c.chirp_s >= c.repetition_s:
            raise ValueError("Das verzögerte Leakage-Pulssignal muss vor dem nächsten PRI enden.")
    if e.bodenclutter:
        quellen = len(c.targets) if c.flugszene is None else len(c.flugszene.bahnen)
        arbeit = c.chirps*c.samples*(quellen+e.clutter_ringe*e.clutter_sektoren)
        if arbeit > 16777216:
            raise ValueError("Clutter-Rechenbudget überschritten: weniger Flächen, Chirps oder Samples wählen.")
    if e.phasenrauschen:
        # Für Laufzeiten ist höchstens der erfasste Rampen-/Pulsbereich nötig;
        # beim Passivempfang kommt Suchverzögerung zum Integrationsende hinzu.
        delay = (c.timing_range_limit/C if c.radar_mode == "passive"
                 else max(2*c.timing_range_limit/C, e.leakage_delay_s if e.leakage else 0))
        dauer = c.chirps*c.repetition_s+delay+16*e.phase_zeit_s
        if not math.isfinite(dauer) or dauer/(e.phase_zeit_s/8) >= 262144:
            raise ValueError("Phasenprozess zu groß: Korrelationszeit erhöhen oder Messpaket verkürzen.")
        if e.phase_rms_rad/(2*math.pi*e.phase_zeit_s) > .02*c.sample_rate_hz:
            raise ValueError("Phasenrauschen zu schnell für den ADC: Korrelationszeit erhöhen oder RMS-Phase senken.")
    if geometrie and c.radar_mode == "passive" and e.erdkruemmung:
        from .ausbreitung import erdkoordinaten, freie_sicht
        tx, _ = erdkoordinaten(c.passiv.senderort, (0, 0, 0), e)
        rx, _ = erdkoordinaten((0, 0, e.stationshoehe_m), (0, 0, 0), e)
        if not freie_sicht(tx, rx, e):
            raise ValueError("Der passive Direktweg liegt hinter dem Erdhorizont. Für den idealen Referenzkanal müssen Tx und Rx freie Sicht haben.")
    aktiv = [name for name in schalter if getattr(e, name)]
    return (["Aktive Ersatzmodelle: "+", ".join(sorted(aktiv))+". Details im Tab Effekte und in der technischen Dokumentation."] if aktiv else [])
