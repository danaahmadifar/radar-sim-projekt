"""Passiver, bistatischer Empfänger mit idealem Referenzkanal und exakter CAF.

Fester Fremdsender Tx, Empfänger Rx=(0,0,0). Gemessen wird der Umweg
b=|p−Tx|+|p−Rx|−|Tx−Rx|, nicht die monostatische Entfernung.
b_dot=(uTx+uRx)·v, Doppler f_b=b_dot/λ. Positive Werte verlängern den Weg.
Der Breitband-Fremdsender ist synthetisch und kein nachgebautes Rundfunksystem.
"""

from dataclasses import dataclass, replace
import math
import numpy as np
from .config import C, RadarConfig, Target
from .passiv_config import PassivSettings
from .flugbahn import Flugbahn, Flugszene, berechne_flugzustand, pruefe_flugszene, grenzen_der_flugbahn, kleinster_abstand
from .antenne import Antenne, antennengewinn
from .model import EchoFrame
from .processing import Spectrum, window_values
from .ausbreitung import erdkoordinaten, freie_sicht, atmosphaerenfaktor


@dataclass
class PassivEmpfang:
    referenz: np.ndarray       # [L+K]: idealer komplexer Direktweg-Referenzkanal
    ueberwachung: np.ndarray   # [L+K]: komplexe RX-Samples, noch nicht konjugiert
    rauschleistung: float
    echoleistung: float
    clipped_fraction: float = 0.
    reference_clipped_fraction: float = 0.
    clutter_power: float = 0.


def bistatische_werte(position, geschwindigkeit, senderort) -> tuple[float, float, float, float]:
    """Umweg [m], Wegänderungsrate [m/s], Tx-Target- und Target-Rx-Abstand [m]."""
    p, v, tx = np.asarray(position), np.asarray(geschwindigkeit), np.asarray(senderort)
    rt, rr = float(np.linalg.norm(p-tx)), float(np.linalg.norm(p))
    if min(rt, rr) <= 0:
        raise ValueError("Ein Target darf nicht auf Sender oder Empfänger liegen.")
    umweg = max(0., rt+rr-float(np.linalg.norm(tx)))
    rate = float(((p-tx)/rt+p/rr)@v)
    return umweg, rate, rt, rr


def passiv_config() -> RadarConfig:
    """Offene Passivradar-Demo: 600 MHz, 400 kHz Breitbandsignal, 64 ms Integration."""
    szene = Flugszene("Passivradar · Fremdsender und Flugzeug", (
        Flugbahn(-7000, 1800, 40, start_y_m=8000, geschwindigkeit_y_mps=-50, staerke=10),), 20, .5)
    return RadarConfig(radar_mode="passive", carrier_hz=600e6, bandwidth_hz=400e3,
                       sample_rate_hz=1e6, chirp_s=.001, repetition_s=.001, chirps=64,
                       targets=(), flugszene=szene, snr_db=10, pfa=1e-6,
                       amplitude_model="radar", reference_range_m=10000, reference_rcs_m2=10,
                       antenne=Antenne(), passiv=PassivSettings())


def validate_passive(c: RadarConfig) -> list[str]:
    """Zusätzliche Modellgrenzen, bevor Signale/FFT-Speicher angelegt werden."""
    p = c.passiv
    if not isinstance(p, PassivSettings):
        raise ValueError("Passivradar benötigt gültige Sender-/Empfängereinstellungen.")
    for wert in (*p.senderort, p.maximaler_umweg_m, p.direktweg_db):
        if isinstance(wert, bool) or not isinstance(wert, (float, int)) or not math.isfinite(wert):
            raise ValueError("Passivwerte müssen endliche Zahlen sein.")
    if np.linalg.norm(p.senderort) < 1 or p.sender_z_m < 0:
        raise ValueError("Der feste Fremdsender braucht mindestens 1 m Abstand zum Empfänger und Z≥0.")
    if not 1000 <= p.maximaler_umweg_m <= 1e7 or not -80 <= p.direktweg_db <= 60:
        raise ValueError("Passivradar: Umweg-Suchbereich 1 km bis 10.000 km, Direktweg −80…60 dB.")
    if type(p.direktweg_entfernen) is not bool or c.adc_skip_samples != 0:
        raise ValueError("Passivradar: boolescher Direktweg-Schalter und ADC-Vorlauf 0 erforderlich.")
    if c.remove_static:
        raise ValueError("Passivradar: monostatischen Null-Doppler-Abzug ausschalten; stattdessen Direktweg-Projektion verwenden.")
    if not 0 < c.bandwidth_hz < c.sample_rate_hz:
        raise ValueError("Passiver Breitbandempfang benötigt 0<B<fs.")
    laenge = c.samples*c.chirps
    if c.bandwidth_hz*c.chirps*c.repetition_s < 16:
        raise ValueError("Passivradar benötigt B·Integrationsdauer ≥ 16 für ein brauchbares Breitband-Referenzsignal.")
    k = c.range_bins-1
    fft_laenge = 1 << (2*laenge+k-2).bit_length()
    if not 16 <= c.chirps <= 128 or not 1024 <= laenge <= 131072 or not 20 <= k <= 2048 or c.chirps*fft_laenge > 33554432:
        raise ValueError("Passivradar-Rechenbudget: 16–128 Dopplerbins, 1024–131072 Integrationssamples, 20–2048 Verzögerungsbins und begrenzte CAF-FFT-Arbeit.")
    if c.flugszene is None or c.targets:
        raise ValueError("Passivradar benötigt eine räumliche Flugbahn; feste R/v-Werte bestimmen keine bistatische Geometrie.")
    s = c.flugszene
    pruefe_flugszene(s)
    if s.radar_bahn is not None or any(b.route is not None for b in s.bahnen):
        raise ValueError("Passivradar unterstützt zunächst feste Tx/Rx und analytische Flugbahnen.")
    dauer = c.chirps*c.repetition_s
    if s.zeitschritt_s < dauer:
        raise ValueError("Der Flugzeitschritt muss mindestens der passiven Integrationsdauer entsprechen.")
    tx_bahn = Flugbahn(p.sender_x_m, p.sender_z_m, 0, start_y_m=p.sender_y_m)
    for bahn in s.bahnen:
        g = grenzen_der_flugbahn(bahn, s.dauer_s)
        if 2*g.entfernung_max_m > c.timing_range_limit:
            raise ValueError("Passiv: sichere Umweggrenze 2·Rmax liegt außerhalb des Suchfensters. Umweg-Suchbereich vergrößern.")
        if 2*g.tempo_max_mps >= c.max_velocity:
            raise ValueError("Passiv: sichere Wegänderungsrate liegt außerhalb des Doppler-Suchbereichs. Blockabstand verkleinern.")
        from .empfaenger import phasen_bandreserve
        if c.bandwidth_hz/2+2*g.tempo_max_mps/c.wavelength+phasen_bandreserve(c) >= c.sample_rate_hz/2:
            raise ValueError("Passiv: Fremdsenderband plus bistatischer Doppler überschreitet ADC-Nyquist.")
        if 2*g.tempo_max_mps*dauer > .25*c.range_resolution:
            raise ValueError("Passiv: Umweg ändert sich während der Integration zu stark. Kürzere Integration wählen.")
        r_min = kleinster_abstand(bahn, s)
        t_min = kleinster_abstand(bahn, replace(s, radar_bahn=tx_bahn))
        if min(r_min, t_min) < 1:
            raise ValueError("Target muss während der ganzen Bahn Abstand zu Tx und Rx halten.")
        a = g.tempo_max_mps**2*(1/r_min+1/t_min)+2*abs(bahn.beschleunigung_hoehe_mps2)
        if a*dauer > .25*c.velocity_resolution:
            raise ValueError("Passiv: Wegänderungsrate verändert sich im Integrationsfenster zu stark.")
    return ["Passivradar: synthetischer Breitband-Fremdsender und idealer synchroner Referenzkanal; keine FM-/DVB-Nachbildung.",
            "Gemessen werden Umweg ΔL und dessen Änderungsrate, keine monostatische Entfernung oder eindeutige XYZ-Position.",
            "Exakte diskrete Kreuzambiguität auf begrenztem Dopplerraster. Korrelierte Zellen; CFAR-Pfa ist nominell.",
            "Optionale Störungen separat zuschaltbar; keine vollständige Clutter-/Mehrweg-/Referenzrausch- oder PLL-Nachbildung. Direktweg-Projektion kann nahe Null-Doppler auch Zielanteile entfernen."]


def erzeuge_passivempfang(c: RadarConfig, ziele: list[tuple], frame_index: int) -> PassivEmpfang:
    """Bandbegrenztes komplexes Zufallssignal, verzögerte Echos und Direktweg.

    Synthetischer kontinuierlicher Breitbandsender mit flachem Spektralband.
    Fractional Delay durch exp(−j2πfτ) im Spektrum, nicht auf Samples gerundet.
    Ein Guard vor und nach der Auswertung verhindert zyklisches Durchwickeln
    in der verwendeten Aufzeichnung. Die Referenz ist bewusst rauschfrei.
    ziele enthält (Umweg, Rate, Rt, Rr, Stärke, Einweg-Rx-Gewinn).
    """
    l, k = c.chirps*c.samples, c.range_bins-1
    periode = 1 << (l+3*k).bit_length()
    zufall = np.random.default_rng(np.random.SeedSequence([c.seed, frame_index, 701]))
    frequenzen = np.fft.fftfreq(periode, d=1/c.sample_rate_hz)
    band = np.abs(frequenzen) <= c.bandwidth_hz/2
    spektrum = np.zeros(periode, complex)
    spektrum[band] = zufall.normal(size=int(band.sum()))+1j*zufall.normal(size=int(band.sum()))
    norm = np.sqrt(np.mean(np.abs(np.fft.ifft(spektrum))**2))
    spektrum /= norm
    referenz = np.fft.ifft(spektrum)[k:k+l+k].copy()
    t = np.arange(l+k)/c.sample_rate_hz
    empfang = 10**(c.passiv.direktweg_db/20)*referenz
    summe = 0.
    clutter_power = 0.
    for quelle in ziele:
        umweg, rate, rt, rr, staerke, gewinn = quelle[:6]
        phase, wegfaktor = quelle[6:8] if len(quelle) >= 8 else (0., 1.)
        amplitude = np.sqrt(staerke*gewinn)
        if c.amplitude_model == "radar":
            amplitude = np.sqrt(staerke/c.reference_rcs_m2*gewinn)*c.reference_range_m**2/(rt*rr)
        amplitude *= wegfaktor
        tau, fd = umweg/C, rate/c.wavelength
        versetzt = np.fft.ifft(spektrum*np.exp(-2j*np.pi*frequenzen*tau))[k:k+l+k]
        empfang += amplitude*versetzt*np.exp(-2j*np.pi*(fd*t+(c.carrier_hz*tau)%1)+1j*phase)
        summe += amplitude**2
        if len(quelle) >= 9 and quelle[8]:
            clutter_power += amplitude**2
    if c.effekte.atmosphaere:
        tx, _ = erdkoordinaten(c.passiv.senderort, (0, 0, 0), c.effekte)
        rx, _ = erdkoordinaten((0, 0, c.effekte.stationshoehe_m), (0, 0, 0), c.effekte)
        faktor = atmosphaerenfaktor(float(np.linalg.norm(tx-rx)), c.effekte)
        # Direktweg-dB vor atmosphärischer Zusatzdämpfung; Referenz ideal normiert.
        empfang += (faktor-1)*10**(c.passiv.direktweg_db/20)*referenz
    from .empfaenger import Phasenprozess, begrenze_empfang
    if c.effekte.phasenrauschen:
        prozess = Phasenprozess(c, frame_index, (c.range_bins-1)/c.sample_rate_hz)
        rotation = np.exp(-1j*prozess.werte(t))
        # Derselbe Empfangs-LO in beiden Kanälen; keine eigene Radar-TX-Phase.
        referenz *= rotation
        empfang *= rotation
    pn = 10**(-c.snr_db/10) if c.noise_enabled else 0.
    if pn:
        empfang += np.sqrt(pn/2)*(zufall.normal(size=l+k)+1j*zufall.normal(size=l+k))
    empfang, anteil = begrenze_empfang(empfang, c.effekte)
    referenz, ref_anteil = begrenze_empfang(referenz, c.effekte)
    return PassivEmpfang(referenz, empfang, pn, summe-clutter_power, anteil, ref_anteil, clutter_power)


def kreuzambiguitaet(kanal: PassivEmpfang, c: RadarConfig) -> Spectrum:
    """Exakte diskrete CAF auf M Dopplerbins und K+1 nichtnegativen Lags.

    CAF(f,k)=Σ[n=0..L−1] conj(surv[n+k]) ref[n] w[n]
                          exp(−j2πf(n+k)/fs) / Σ |ref[n]|²w[n].
    Jeder Lag nutzt L Samples. Lineare Korrelation mit FFT-Zero-Padding;
    keine Block-Dopplernäherung und keine FMCW-/Puls-Entfernungsumrechnung.
    """
    l, k = c.chirps*c.samples, c.range_bins-1
    if kanal.referenz.shape != (l+k,) or kanal.ueberwachung.shape != (l+k,):
        raise ValueError("CAF-Kanäle benötigen Integrationslänge plus Suchverzögerung als 1D-Arrays.")
    if not np.all(np.isfinite(kanal.referenz)) or not np.all(np.isfinite(kanal.ueberwachung)):
        raise ValueError("CAF-Kanäle müssen endliche komplexe Werte enthalten.")
    if float(np.vdot(kanal.referenz, kanal.referenz).real) <= 0:
        raise ValueError("Der passive Referenzkanal braucht positive Signalenergie.")
    surv = kanal.ueberwachung.copy()
    if c.passiv.direktweg_entfernen:
        vorher = float(np.linalg.norm(surv))
        a = np.vdot(kanal.referenz, surv)/np.vdot(kanal.referenz, kanal.referenz)
        surv -= a*kanal.referenz
        # Ein exakt reiner Direktweg darf keine maschinengenauen Restpeaks
        # erzeugen. Nur vollständig unter der Rundungsgrenze liegende Residuen.
        if np.linalg.norm(surv) <= 64*np.finfo(float).eps*vorher:
            surv[:] = 0
    if c.remove_static:
        raise ValueError("Passivradar verwendet die Direktweg-Projektion; monostatischer Null-Doppler-Abzug ist hier nicht definiert.")
    w = window_values(l, c.window)
    referenz = kanal.referenz[:l]*w
    norm = float(np.sum(np.abs(kanal.referenz[:l])**2*w))
    fft_laenge = 1 << (2*l+k-2).bit_length()
    filter_fft = np.fft.fft(referenz[::-1], n=fft_laenge)
    fd = np.fft.fftshift(np.fft.fftfreq(c.chirps, d=c.repetition_s))
    power = np.empty((c.chirps, k+1))
    t = np.arange(l+k)/c.sample_rate_hz
    for i, f in enumerate(fd):
        gemischt = np.conjugate(surv)*np.exp(-2j*np.pi*f*t)
        korrelation = np.fft.ifft(np.fft.fft(gemischt, n=fft_laenge)*filter_fft)
        power[i] = np.abs(korrelation[l-1:l+k]/norm)**2
    return Spectrum(power, power.max(axis=0), None, fd, np.arange(k+1)*C/c.sample_rate_hz, fd*c.wavelength)


def simulate_passive(c: RadarConfig, frame_index: int):
    """Separater Passivpfad; keine Sollwerte werden in die Detektion eingesetzt."""
    from .pipeline import FrameResult
    from .config import validate_config
    from .detection import ca_cfar, group_candidates
    hinweise = validate_config(c)
    s = c.flugszene
    if frame_index > s.letzter_frame:
        raise ValueError("Der Flug ist beendet.")
    zeit = min(frame_index*s.zeitschritt_s, s.dauer_s)
    zustaende = []
    ziele = []
    soll = []
    def quelle(ort, tempo, staerke, phase=0., clutter=False):
        p, v = erdkoordinaten(ort, tempo, c.effekte)
        tx, _ = erdkoordinaten(c.passiv.senderort, (0, 0, 0), c.effekte)
        rx, _ = erdkoordinaten((0, 0, c.effekte.stationshoehe_m), (0, 0, 0), c.effekte)
        b, rate, rt, rr = bistatische_werte(p-rx, v, tx-rx)
        sichtbar = freie_sicht(tx, p, c.effekte) and freie_sicht(p, rx, c.effekte)
        g = float(antennengewinn(c.antenne, p-rx, c.carrier_hz))
        faktor = float(sichtbar)*atmosphaerenfaktor(rt+rr, c.effekte)
        if clutter and c.amplitude_model == "didactic":
            staerke = staerke/c.reference_rcs_m2*c.reference_range_m**4/(rt*rr)**2
        return b, rate, rt, rr, staerke, g, phase, faktor
    for bahn in s.bahnen:
        z = berechne_flugzustand(bahn, zeit)
        q = quelle(z.position_m, (z.geschwindigkeit_x_mps, z.geschwindigkeit_y_mps, z.geschwindigkeit_hoehe_mps), bahn.staerke)
        ziele.append(q)
        soll.append(Target(q[0], q[1], bahn.staerke, antenna_gain=q[5], path_gain=q[7]))
        zustaende.append(z)  # Weltbewegung mit Rx-Abstand; bistatische Sollwerte stehen separat in soll.
    from .bodenclutter import bodenpunkte
    for ort, sigma, phase in bodenpunkte(c):
        q = quelle(ort, (0, 0, 0), sigma, phase, clutter=True)
        if q[0] > c.timing_range_limit:
            raise ValueError("Passiver Bodenclutter liegt außerhalb des Umweg-Suchfensters.")
        ziele.append((*q, True))
    kanal = erzeuge_passivempfang(c, ziele, frame_index)
    spektrum = kreuzambiguitaet(kanal, c)
    cfar = ca_cfar(spektrum.power, c)
    echo = EchoFrame(np.conjugate(kanal.ueberwachung[:c.chirps*c.samples]).reshape(c.chirps, c.samples),
                     np.arange(c.samples)/c.sample_rate_hz, np.arange(c.chirps)*c.repetition_s,
                     kanal.rauschleistung, kanal.echoleistung, kanal.clipped_fraction, clutter_power=kanal.clutter_power)
    if c.effekte.saettigung:
        hinweise.append(f"Begrenzt: Überwachung {100*kanal.clipped_fraction:.2f} %, Referenz {100*kanal.reference_clipped_fraction:.2f} %. Nichtlineare Verzerrung liegt vor der Direktweg-Projektion.")
    result = FrameResult(replace(c, flugszene=None, targets=tuple(soll)), echo, spektrum, cfar,
                         group_candidates(spektrum, cfar, c), hinweise, frame_index, c, zeit, tuple(zustaende))
    result.passiv_empfang = kanal
    return result
