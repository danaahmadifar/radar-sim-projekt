"""Tatsächliche Ergebnisse: Fernbereich, Auflösungsdemo und passives Radar."""

from dataclasses import replace
from pathlib import Path
import numpy as np
from .config import Target
from .fernradar import fern_config
from .passivradar import passiv_config, erzeuge_passivempfang, kreuzambiguitaet
from .pipeline import simulate_frame
from .evaluation import match_targets, schaetztoleranzen
from .detection import ca_cfar
from .io import schreibe_json, schreibe_markdown


def pruefe_fern_und_passiv() -> dict:
    fern = []
    trennung = []
    for modus in ("fmcw", "pulse_doppler"):
        c = fern_config(modus)
        werte = []
        for nummer in (0,30,60):
            f=simulate_frame(c,nummer)
            paare=match_targets(f.config,f.candidates)
            rt,vt=schaetztoleranzen(c)
            p=paare[0] if paare else None
            werte.append({"frame":nummer,"r_fehler_m":p.range_error_m if p else None,
                          "v_fehler_mps":p.velocity_error_mps if p else None,
                          "extras":len(f.candidates)-len(paare),
                          "bestanden":p is not None and abs(p.range_error_m)<=rt*1.01 and abs(p.velocity_error_mps)<=vt*1.01})
        fern.append({"modus":modus,"delta_r_m":c.range_resolution,"bin_m":c.range_bin_m,
                     "beobachtete_bandbreite_hz":c.bandwidth_hz if modus=="pulse_doppler" else c.slope*c.adc_duration_s,
                     "eindeutiger_betrag_v_mps":c.max_velocity,"messwerte":werte,
                     "bestanden":all(w["bestanden"] for w in werte)})
        c=replace(c,flugszene=None,targets=(Target(300000,-50,10),Target(306000,-50,10)))
        f=simulate_frame(c)
        trennung.append({"modus":modus,"abstand_m":6000,"soll":2,"zugeordnet":len(match_targets(c,f.candidates)),
                         "detektionen":[d.range_m for d in f.candidates],
                         "hinweis":"Auflösungsdemo bei Hann, keine universelle Trennungs- oder Detektionsgarantie."})
    beta=[]
    c=passiv_config()
    for nummer in (0,10,20,30,40):
        f=simulate_frame(c,nummer)
        paare=match_targets(f.config,f.candidates)
        rt,vt=schaetztoleranzen(c)
        p=paare[0] if paare else None
        beta.append({"frame":nummer,"umweg_m":f.config.targets[0].range_m,
                     "rate_mps":f.config.targets[0].velocity_mps,"zugeordnet":len(paare),
                     "extras":len(f.candidates)-len(paare),
                     "fehler_umweg_m":p.range_error_m if p else None,"fehler_rate_mps":p.velocity_error_mps if p else None,
                     "bestanden":p is not None and abs(p.range_error_m)<=rt*1.01 and abs(p.velocity_error_mps)<=vt*1.01})
    # Kleine Stichprobe, keine behauptete CFAR-Kalibrierung des Passivmodells.
    rauschen=[]
    n=alarme=0
    for i in range(8):
        r=replace(c,pfa=1e-3)
        kanal=erzeuge_passivempfang(r,[],100+i)
        spektrum=kreuzambiguitaet(kanal,r)
        cf=ca_cfar(spektrum.power,r)
        count,alarm=int(cf.valid.sum()),int(cf.mask.sum())
        n+=count
        alarme+=alarm
        rauschen.append(alarm/count)
    return {"bestanden":all(x["bestanden"] for x in fern+beta),"fern":fern,"trennung":trennung,"beta":beta,
            "beta_rauschen":{"frames":8,"cut":n,"alarme":alarme,"nominal":.001,"gemessen":alarme/n,
                             "frame_raten":rauschen,"hinweis":"Kleine korrelierte CAF-Stichprobe, keine Einhaltung der unabhängigen CA-CFAR-Formel behauptet."}}


def schreibe_fern_passivbericht(ordner: Path, daten: dict) -> None:
    schreibe_json(ordner/"fern_und_passiv.json",daten)
    zeilen=["# Fernbereich und Passivradar", "", "Reproduzieren: `python -m radar_sim --validate`.", "",
            "Beide Fernprofile: fc=300 MHz, B=100 kHz, fs=500 kSamples/s, Tr=3 ms, M=64, Referenz 100 km / 10 m² und SNR=20 dB pro aktivem Sample. Keine gleiche mittlere Sendeleistung oder identische Hardware behauptet.", "",
            "| Verfahren | Beobachtete Bandbreite / Hz | Nominale ΔR / m | Raster / m | Eindeutiger Betrag v / m/s | Ergebnis |", "|---|---:|---:|---:|---:|---|"]
    for p in daten["fern"]:
        zeilen.append(f"| {p['modus']} | {p['beobachtete_bandbreite_hz']:.6g} | {p['delta_r_m']:.6g} | {p['bin_m']:.6g} | {p['eindeutiger_betrag_v_mps']:.6g} | {'OK' if p['bestanden'] else 'FEHLER'} |")
    zeilen += ["", "Je drei Frames: Start, Mitte, Ende des 300-km-Flugs. Rauschfreie Halb-Bin-Toleranzen plus Dopplerkorrektur; konkrete Werte und Extras in der JSON-Datei.",
               "FMCW ist ebenfalls fernbereichsfähig. Der Unterschied hier entsteht aus der verkürzten beobachteten Bandbreite und dem Puls-PRI-Zielkonflikt, nicht aus einer künstlich bevorzugten Radarart.", "",
               "## Zwei Targets, Abstand 6 km", "", "| Verfahren | Soll | Zugeordnet | Schätzwerte R / m |", "|---|---:|---:|---|"]
    for p in daten["trennung"]:
        zeilen.append(f"| {p['modus']} | 2 | {p['zugeordnet']} | {p['detektionen']} |")
    zeilen += ["", "Diese Hann-Auflösungsdemo wird gemessen, nicht als universelle harte Trennungsprüfung gewertet.", "",
               "## Passivradar", "", "Fester Sender bei (−20 km,0,0), fester Empfänger im Ursprung. 600 MHz Träger, 400 kHz synthetisches Breitband, fs=1 MHz, 64 ms Integration. Ideal synchroner, rauschfreier Referenzkanal. CFAR benutzt keine Sollwerte.", "",
               "| Frame | Umweg / m | Wegänderungsrate / m/s | Zugeordnet | Extra | Fehler Umweg / m | Fehler Rate / m/s | Ergebnis |", "|---:|---:|---:|---:|---:|---:|---:|---|"]
    for b in daten["beta"]:
        zeilen.append(f"| {b['frame']} | {b['umweg_m']:.6g} | {b['rate_mps']:.6g} | {b['zugeordnet']} | {b['extras']} | {b['fehler_umweg_m']} | {b['fehler_rate_mps']} | {'OK' if b['bestanden'] else 'FEHLER'} |")
    r=daten["beta_rauschen"]
    zeilen += ["", f"Direktweg + AWGN ohne Echos: {r['frames']} Frames, {r['cut']} gültige CUTs, {r['alarme']} Alarme. Pfa nominal {r['nominal']}, gemessen {r['gemessen']:.6g}. Kleine Stichprobe, keine kalibrierte Pfa-Garantie.",
               "Die Unit-Tests prüfen die CAF gegen direkte Summen, Dopplervorzeichen, Empfänger-Leistungsgewinn, geometrische Ableitungen, reproduzierbaren Seed und reine Direktweg-Unterdrückung ohne Rundungsgeister.", "",
               "![Fernbereichsspektren](fernvergleich.png)", "![Passive CAF](passiv_caf.png)", "",
               "Modellgrenzen: keine reale FM-/DVB-Wellenform, Referenzrauschen, Mehrwege, Clutter, bewegte Tx/Rx oder XYZ-Lokalisierung. Fernmodelle: flache Welt ohne Erdkrümmung/Atmosphäre und ohne absolute Sendeleistungsbilanz.", "",
               "Gesamtergebnis der harten Prüfungen: **"+("BESTANDEN" if daten["bestanden"] else "FEHLER")+"**.",
               "Details: [Fernbereich und Passivradar](../docs/FERNBEREICH_UND_PASSIV.md)."]
    schreibe_markdown(ordner/"FERN_UND_PASSIV.md",zeilen)


def export_fern_passivplots(ordner: Path) -> None:
    from PyQt6.QtCore import QRectF
    import pyqtgraph as pg
    from .processing import power_db
    from .report_plots import _plotfenster,export_plot
    app,fenster,plot=_plotfenster()
    plot.setTitle("300 und 306 km · identische nominelle TX-Bandbreite, verschiedene beobachtete Bandbreite")
    plot.setLabel("bottom","Scheinentfernung",units="m")
    plot.setLabel("left","Leistung / Aref²",units="dB")
    plot.addLegend()
    for modus,farbe in (("fmcw","#ffbd59"),("pulse_doppler","#59dcd0")):
        c=replace(fern_config(modus),flugszene=None,targets=(Target(300000,-50,10),Target(306000,-50,10)))
        f=simulate_frame(c)
        plot.plot(f.spectrum.apparent_range_m,power_db(f.spectrum.range_power),pen=pg.mkPen(farbe,width=2),name=modus)
    plot.setXRange(280000,330000,padding=0)
    plot.setYRange(-65,0,padding=0)
    app.processEvents()
    export_plot(plot,ordner/"fernvergleich.png")
    plot.clear()
    f=simulate_frame(passiv_config())
    c,s=f.config,f.spectrum
    image=pg.ImageItem(power_db(s.power),axisOrder="row-major")
    image.setColorMap(pg.colormap.get("viridis"))
    image.setLevels((-80,5))
    image.setRect(QRectF(-c.range_bin_m/2,s.velocity_mps[0]-c.velocity_resolution/2,c.range_bin_m*c.range_bins,c.velocity_resolution*c.chirps))
    plot.addItem(image)
    plot.setTitle("Passivradar · CAF-Leistung / Aref², Farbskala −80…+5 dB")
    plot.setLabel("bottom","Bistatischer Umweg ΔL",units="m")
    plot.setLabel("left","Wegänderungsrate dΔL/dt",units="m/s")
    plot.setXRange(0,c.timing_range_limit,padding=0)
    plot.setYRange(-c.max_velocity,c.max_velocity,padding=0)
    app.processEvents()
    export_plot(plot,ordner/"passiv_caf.png")
    fenster.close()
