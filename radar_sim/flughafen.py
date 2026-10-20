"""Offengelegte Lehrkonfiguration für Flugzeuge im Flughafennahbereich.

X-Band ist durch reale Flughafenradare motiviert. Wellenform und SNR sind
eigene Simulationswerte, keine nachgebildeten Betriebsdaten eines Herstellers.
"""

import math
from dataclasses import replace
from .config import RadarConfig
from .flugbahn import Flugbahn, Flugszene, erstelle_routenszene
from .antenne import Antenne
from .route import GezeichneteRoute


def flughafenszenen() -> dict[str, Flugszene]:
    sinken = -70*math.tan(math.radians(3))
    return {
        "10_flughafen_anflug": Flugszene("Airport · Anflug mit 3° und 70 m/s", (
            Flugbahn(-5000, 70+5000*math.tan(math.radians(3)), 70, sinken, staerke=10),
        ), 60, .5),
        "11_flughafen_gegenverkehr": Flugszene("Airport · zwei Flugrichtungen, getrennte Bahnen", (
            Flugbahn(-5000, 450, 70, staerke=10, start_y_m=-50),
            Flugbahn(-800, 650, -70, staerke=8, start_y_m=50),
        ), 60, .5),
        "12_flughafen_bogen": Flugszene("Airport · vorgegebener Höhenbogen", (
            Flugbahn(-4200, 300, 70, 10, -1/3, 10, start_y_m=200),
        ), 60, .5),
        "13_flughafen_route3d": replace(erstelle_routenszene(GezeichneteRoute(
            ((-4000., -500., 400.), (-3000., 0., 600.), (-1800., 600., 500.), (-700., 900., 350.)), 70), .5, 10),
            name="Airport · räumliche Beispielroute"),
        "15_zwei_flugzeuge_radar": Flugszene("Air-to-Air · zwei Flugzeuge, Radar fliegt mit", (
            Flugbahn(-5000, 2100, 200, staerke=10, start_y_m=300),
        ), 40, .5, radar_bahn=Flugbahn(0, 1800, 160)),
    }


def flughafen_config(name: str = "10_flughafen_anflug") -> RadarConfig:
    """6-km-Nahbereich, |v|<89,55 m/s, beobachtete Bandbreite 5 MHz.

    TX: 10 MHz in 80 µs, danach 10 µs Pause. ADC: letzte 40 µs mit 10 MHz,
    also 400 Samples. 96 Chirps: 8,64 ms und 1,865 m/s Doppler-Binabstand.
    ΔR=c/(2*S*Tadc)=29,979 m. Hann verbreitert die Hauptkeule zusätzlich.
    """
    return RadarConfig(carrier_hz=9.3e9, bandwidth_hz=10e6, chirp_s=80e-6,
                       repetition_s=90e-6, sample_rate_hz=10e6, adc_skip_samples=400,
                       chirps=96, snr_db=20, pfa=1e-6, amplitude_model="radar",
                       reference_range_m=3000, reference_rcs_m2=10,
                       targets=(), flugszene=flughafenszenen()[name],
                       antenne=(Antenne(typ="faecher", azimut_grad=176.6, breite_az_grad=30, elevation_grad=5)
                                if name == "15_zwei_flugzeuge_radar" else Antenne(typ="faecher", azimut_grad=155, breite_az_grad=80, elevation_grad=20)
                                if name == "13_flughafen_route3d" else Antenne(typ="faecher", elevation_grad=20)))
