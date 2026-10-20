"""Offene Lehrszenarien: konkrete Nachteile statt pauschaler Radar-Rangliste."""

from dataclasses import replace
from .config import RadarConfig, Target
from .effekt_config import Stoereffekte
from .antenne import Antenne
from .flugbahn import Flugbahn, Flugszene


def effektbeispiele() -> dict[str, tuple[str, RadarConfig]]:
    """Titel, Erklärung und vollständig ladbare Konfigurationen."""
    from .fernradar import fern_config
    from .passivradar import passiv_config
    from .flughafen import flughafen_config
    basis = RadarConfig(targets=(Target(25, -5, .001),), noise_enabled=False, pfa=1e-6)
    leakage = replace(basis, effekte=Stoereffekte(leakage=True, leakage_db=50,
                      phasenrauschen=True, phase_rms_rad=.5, phase_zeit_s=.8e-6))
    satt = replace(basis, effekte=Stoereffekte(leakage=True, leakage_db=40,
                   saettigung=True, saettigung_db=3))
    nah = RadarConfig(radar_mode="pulse_doppler", carrier_hz=3e9, bandwidth_hz=2e6,
                      chirp_s=12e-6, repetition_s=200e-6, sample_rate_hz=5e6, chirps=64,
                      targets=(Target(900, 0),), noise_enabled=False, window="rect",
                      effekte=Stoereffekte(teilpulse=True))
    fern = fern_config()
    niedrig = replace(fern, noise_enabled=False, antenne=Antenne(),
                      flugszene=Flugszene("Horizont · tiefer Flug bei 300 km", (Flugbahn(-300000, 1000, 50, staerke=10),), 60, 1),
                      effekte=Stoereffekte(erdkruemmung=True, stationshoehe_m=20))
    atmos = replace(fern, noise_enabled=False, antenne=Antenne(),
                    effekte=Stoereffekte(atmosphaere=True, daempfung_db_km=.02))
    clutter = replace(flughafen_config(), antenne=Antenne(), noise_enabled=False,
                      effekte=Stoereffekte(bodenclutter=True, stationshoehe_m=20, sigma0_db=-18))
    fliegend = replace(flughafen_config("15_zwei_flugzeuge_radar"), antenne=Antenne(), noise_enabled=False,
                       effekte=Stoereffekte(bodenclutter=True, clutter_innen_m=300, clutter_aussen_m=2000,
                                           sigma0_db=-25))
    # Konservatives |v| muss auch für statische Bodenstreuer zum bewegten Radar passen.
    fliegend = replace(fliegend, carrier_hz=3e9, repetition_s=100e-6,
                       flugszene=replace(fliegend.flugszene, dauer_s=8))
    passiv = replace(passiv_config(), effekte=Stoereffekte(saettigung=True, saettigung_db=0,
                     bodenclutter=True, sigma0_db=-30, clutter_innen_m=1000, clutter_aussen_m=4000))
    return {
        "FMCW · Leakage und Phasenrauschen": ("Starke TX→RX-Kopplung hebt mit laufzeitabhängigem Phasenrauschen den Untergrund an. Das schwache Target kann verdeckt werden.", leakage),
        "FMCW · Empfänger übersteuert": ("Leakage und Target werden vor FFT und digitalem Abzug gemeinsam begrenzt. Ein späterer Filter kann die verlorene Amplitudeninformation nicht zurückholen.", satt),
        "Puls · unvollständiges Nah-Echo": ("12-µs-Puls, Target bei 900 m: Nur rund die halbe Pulsdauer liegt nach der Sendephase. Der matched-filter Peak verliert rund 6 dB. Der Vergleich behält dieselbe Empfangssperre; für den kurzen Puls die nächste Demo laden.", nah),
        "Puls · kurzer Puls zum Vergleich": ("Dasselbe 900-m-Target mit 4 µs statt 12 µs: vollständiger Empfang. Gleiche Bandbreite, aber weniger Sendeenergie bei gleicher Spitzenamplitude.", replace(nah, chirp_s=4e-6)),
        "Fernbereich · hinter dem Erdhorizont": ("20-m-Mast, Target in 1 km Höhe bei 300 km. Die direkte Verbindung schneidet die effektive Erdkugel. Hohe Sendeleistung oder Puls-Doppler beseitigen diese Sichtgrenze nicht.", niedrig),
        "Fernbereich · atmosphärische Dämpfung": ("Vorgegebene homogene Dämpfung 0,02 dB/km: über rund 600 km Hin- und Rückweg ungefähr 12 dB Leistungsverlust. Kein aus Wetterdaten berechneter Koeffizient.", atmos),
        "Aktiv · stationärer Bodenclutter": ("Feste Bodenflächen erzeugen kohärente Echos bei Null-Doppler. Sie können langsame Targets verdecken und CFAR-Schwellen erhöhen. Null-Doppler-Abzug entfernt auch langsame Nutzanteile.", clutter),
        "Air-to-Air · bewegter Bodenclutter": ("Der Boden steht in Weltkoordinaten still. Durch die Eigenbewegung des Radars verteilt sich sein Clutter jedoch über Doppler; ein bloßer Null-Doppler-Abzug reicht nicht.", fliegend),
        "Passivradar · Direktweg und Übersteuerung": ("Der starke Fremdsender-Direktweg übersteuert den Überwachungskanal. Eine digitale Referenzprojektion nach der Begrenzung kann die ursprünglichen Echos nicht rekonstruieren. Zusätzliche Bodenstreuer sind keine Flugtargets.", passiv),
    }
