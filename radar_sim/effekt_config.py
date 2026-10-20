"""Zuschaltbare, relative Stör- und Ausbreitungsmodelle; SI-Einheiten."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Stoereffekte:
    leakage: bool = False
    leakage_db: float = 30.0       # Empfangsleistung / Aref² vor Begrenzung
    leakage_delay_s: float = 50e-9 # ein verzögerter Kopplungsweg, keine Zielentfernung
    saettigung: bool = False
    saettigung_db: float = 10.0    # maximale komplexe Hüllkurvenleistung / Aref²
    phasenrauschen: bool = False
    phase_rms_rad: float = 0.3     # RMS-Phase des einzelnen gemeinsamen Oszillators
    phase_zeit_s: float = 10e-6    # Korrelationszeit des glatten Gauß-Phasenprozesses
    erdkruemmung: bool = False
    erdradius_faktor: float = 4/3  # 1: geometrisch; 4/3: übliche Refraktionsnäherung
    stationshoehe_m: float = 0.0   # Mast über Boden, zusätzlich zur Radarplattform
    atmosphaere: bool = False
    daempfung_db_km: float = 0.01  # vorgegebene homogene spezifische Dämpfung
    bodenclutter: bool = False
    sigma0_db: float = -25.0       # mittlere Boden-RCS pro m²
    clutter_innen_m: float = 500.0
    clutter_aussen_m: float = 5000.0
    clutter_ringe: int = 4
    clutter_sektoren: int = 12
    teilpulse: bool = False        # Puls-Nahbereich mit unvollständigem Empfang auswerten
