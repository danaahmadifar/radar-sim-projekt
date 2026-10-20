"""Unabhängige Referenzen: Element-Summen, bekannte Nullstellen und Gauß-Halbwerte."""

from dataclasses import replace
from pathlib import Path
import math
import numpy as np
from .antenne import Antenne, antennenbasis, antennengewinn, richtdiagramm, keulenrand
from .antennendiagramm import halbwertsbreite
from .io import schreibe_json, schreibe_markdown


def pruefe_patterns() -> dict:
    """Keine Messdatenvalidierung: prüft die Implementierung der idealisierten Modelle.

    Arrayreferenz: Jedes Element strahlt mit Phase k*r·u. Für d=λ/2 ist
    die Phasendifferenz π*u. Direkte komplexe Summen ersetzen hier bewusst
    die sinc-Formel aus dem Produktivcode. Nach Betragsquadrat wird das
    vereinfachte cos²-Leistungsdiagramm des Elements angewendet.
    """
    messungen = []

    def pruefung(name: str, fehler: float, toleranz: float) -> None:
        messungen.append({"pruefung": name, "max_abs_fehler": float(fehler),
                          "toleranz": toleranz, "bestanden": bool(fehler <= toleranz)})

    zufall = np.random.default_rng(20261019)
    richtungen = zufall.normal(size=(513, 3))
    richtungen /= np.linalg.norm(richtungen, axis=1, keepdims=True)
    for nh, nv in ((2, 2), (3, 5), (16, 8), (128, 127)):
        a = Antenne(typ="patch_array", azimut_grad=137, elevation_grad=23,
                    elemente_horizontal=nh, elemente_vertikal=nv)
        # Direkte Element-Summen, nicht die geschlossene Arrayfaktor-Formel.
        horizontal = np.mean(np.exp(1j*np.pi*richtungen[:, 1, None]*np.arange(nh)), axis=1)
        vertikal = np.mean(np.exp(1j*np.pi*richtungen[:, 2, None]*np.arange(nv)), axis=1)
        referenz = np.abs(horizontal*vertikal)**2 * np.maximum(richtungen[:, 0], 0)**2
        welt = richtungen @ antennenbasis(a).T
        g = antennengewinn(a, welt, 9.3e9)
        pruefung(f"Array {nh}×{nv}: 513 Richtungen gegen Element-Summen, gedreht", np.max(np.abs(g-referenz)), 2e-13)
        for vert, n in ((False, nh), (True, nv)):
            winkel = math.degrees(math.asin(2/n))
            null = richtdiagramm(a, 0 if vert else winkel, winkel if vert else 0, 9.3e9)
            pruefung(f"Array {nh}×{nv}: erste Nullstelle {'El' if vert else 'Az'}", float(null), 1e-25)
            breite = halbwertsbreite(a, 9.3e9, vert)
            halb = richtdiagramm(a, 0 if vert else breite/2, breite/2 if vert else 0, 9.3e9)
            pruefung(f"Array {nh}×{nv}: Halbwert {'El' if vert else 'Az'}", abs(float(halb)-.5), 2e-12)

    for az, el in ((.2, .4), (12, 40), (120, 120)):
        a = Antenne(typ="faecher", breite_az_grad=az, breite_el_grad=el)
        pruefung(f"Gauß {az}°×{el}°: Breite Az", abs(halbwertsbreite(a, 9.3e9)-az), 1e-10)
        pruefung(f"Gauß {az}°×{el}°: Breite El", abs(halbwertsbreite(a, 9.3e9, True)-el), 1e-10)
        # Kreuzung beider Halbwinkel: exp(−ln2−ln2) = 1/4, nicht 1/2.
        pruefung(f"Gauß {az}°×{el}°: diagonaler Viertelwert", abs(float(richtdiagramm(a, az/2, el/2, 9.3e9))-.25), 2e-14)

    for frequenz, durchmesser in ((2.7e9, .05), (9.3e9, .6), (77e9, 1.2), (300e9, 10)):
        a = Antenne(typ="parabol", durchmesser_m=durchmesser)
        beta = 70*299_792_458/frequenz/durchmesser
        pruefung(f"Parabol-Gauß {frequenz/1e9:g} GHz / {durchmesser:g} m: β=70λ/D", abs(halbwertsbreite(a, frequenz)-beta), 1e-10)
        # Der runde Reflektor muss auch außerhalb der Hauptschnitte rund sein.
        phi = np.linspace(0, 2*np.pi, 129)
        theta = math.radians(beta/2)
        lokal = np.column_stack((np.full_like(phi, math.cos(theta)), np.sin(theta)*np.cos(phi), np.sin(theta)*np.sin(phi)))
        welt = lokal @ antennenbasis(a).T
        pruefung(f"Parabol {frequenz/1e9:g} GHz: rotationssymmetrischer Halbwertskreis", np.max(np.abs(antennengewinn(a, welt, frequenz)-.5)), 2e-11)
        pruefung(f"Parabol {frequenz/1e9:g} GHz: gezeichnete Halbwertskeule", np.max(np.abs(antennengewinn(a, keulenrand(a, frequenz), frequenz)-.5)), 2e-8)

    for typ in ("isotrop", "faecher", "parabol", "patch_array"):
        a = Antenne(typ=typ, azimut_grad=-37, elevation_grad=41)
        g = antennengewinn(a, antennenbasis(a)[:, 0], 9.3e9)
        pruefung(f"{typ}: Achsennormierung", abs(float(g)-1), 1e-14)
        az = np.linspace(-179, 179, 719)
        g = richtdiagramm(a, az, 0, 9.3e9)
        pruefung(f"{typ}: Spiegelsymmetrie", np.max(np.abs(g-g[::-1])), 1e-13)
        pruefung(f"{typ}: Leistungsbereich [0,1]", max(0., float(-g.min()), float(g.max()-1)), 0.)
        if typ != "isotrop":
            rand = keulenrand(a, 9.3e9)
            pruefung(f"{typ}: räumliche Keule entspricht G=0,5", np.max(np.abs(antennengewinn(a, rand, 9.3e9)-.5)), 2e-7)

    a = Antenne(typ="parabol", durchmesser_m=.05)
    keine_grenze = halbwertsbreite(a, 1e6) is None and np.all(np.isnan(keulenrand(a, 1e6)))
    pruefung("Extrem breite Gaußkeule: keine erfundene Halbwertsgrenze", 0. if keine_grenze else 1., 0.)
    pruefung("Isotrop: keine Halbwertsbreite", 0. if halbwertsbreite(replace(a, typ="isotrop"), 9.3e9) is None else 1., 0.)
    kennwerte = []
    for typ in ("isotrop", "patch_array", "parabol", "faecher"):
        a = Antenne(typ=typ)
        kennwerte.append({"typ": typ, "traeger_hz": 9.3e9, "wellenlaenge_m": 299_792_458/9.3e9,
                          "halbwertsbreite_az_grad": halbwertsbreite(a, 9.3e9),
                          "halbwertsbreite_el_grad": halbwertsbreite(a, 9.3e9, True)})
    return {"seed": 20261019, "bestanden": all(m["bestanden"] for m in messungen),
            "messungen": messungen, "kennwerte": kennwerte}


def schreibe_antennenbericht(ordner: Path, bericht: dict) -> None:
    schreibe_json(ordner / "antennen.json", bericht)
    zeilen = ["# Prüfung der Antennendiagramme", "",
              "Reproduzieren: `python -m radar_sim --validate`. Seed 20261019.", "",
              "Geprüft wird die mathematische Umsetzung idealisierter Fernfeldmodelle, keine gemessene Hardwareantenne.",
              "Array: Vergleich gegen direkte komplexe Element-Summen in 513 zufälligen Raumrichtungen je Arraygröße, einschließlich Rückraum und gedrehter Antennenbasis.",
              "Gauß: analytische Halbwertsbreiten, Viertelwert in beiden Halbwinkeln; Parabol: Frequenz- und Durchmesserskalierung. Absolute Fehlertoleranzen betreffen lineare normierte Leistung, bei Breiten Grad.", "",
              "| Prüfung | Max. absoluter Fehler | Toleranz | Ergebnis |", "|---|---:|---:|---|"]
    zeilen += [f"| {m['pruefung']} | {m['max_abs_fehler']:.6g} | {m['toleranz']:.6g} | {'OK' if m['bestanden'] else 'FEHLER'} |" for m in bericht["messungen"]]
    zeilen += ["", "Gesamtergebnis: **" + ("BESTANDEN" if bericht["bestanden"] else "FEHLER") + "**.", "",
               "## Berechnete Beispiele bei 9,3 GHz", "",
               "λ = 32,2357 mm. Patch: 16×8 Elemente, d=λ/2; Parabol: D=0,6 m; Fächer: Vorgabe 12°×40°.", "",
               "| Modell | Volle HPBW Azimut / ° | Volle HPBW Elevation / ° |", "|---|---:|---:|"]
    for k in bericht["kennwerte"]:
        az = "nicht definiert" if k["halbwertsbreite_az_grad"] is None else f"{k['halbwertsbreite_az_grad']:.8g}"
        el = "nicht definiert" if k["halbwertsbreite_el_grad"] is None else f"{k['halbwertsbreite_el_grad']:.8g}"
        zeilen.append(f"| {k['typ']} | {az} | {el} |")
    zeilen += ["",
               "Die PNGs zeigen das 16×8-Array bei 9,3 GHz; Bezug ist der Einweg-Achsenpegel G=1, kein absoluter Gewinn in dBi.",
               "Polar: 0° oben, 0 dB am Außenkreis, −30 dB im Zentrum; geometrische Hauptschnitte, ohne E-/H-Polarisationszuordnung.",
               "![Polardiagramm](antenne_polar.png)", "![Azimut](antenne_azimut.png)", "![Elevation](antenne_elevation.png)", "![Winkelkarte](antenne_winkelkarte.png)", "",
               "Die Gaußform ist eine Hauptkeulennäherung. Reale Parabol-Nebenkeulen, Patch-Geometrie, Kopplung, Polarisation und Verluste werden nicht vorhergesagt.",
               "Herleitung, Grenzen und Quellen: [Antennendiagramme](../docs/ANTENNENDIAGRAMME.md)."]
    schreibe_markdown(ordner / "ANTENNEN.md", zeilen)


def export_antennenplots(ordner: Path) -> None:
    """Verwendet zum Export genau dieselbe Ansicht wie die GUI."""
    from PyQt6.QtWidgets import QApplication
    from .antennenansicht import AntennenAnsicht
    from .report_plots import export_plot
    app = QApplication.instance() or QApplication([])
    fenster = AntennenAnsicht()
    fenster.resize(1200, 850)
    fenster.zeige_antenne(Antenne(typ="patch_array"), 9.3e9)
    fenster.show()
    app.processEvents()
    for name, plot in fenster.diagramme():
        export_plot(plot, ordner / f"{name}.png")
    fenster.close()
