"""Kurzer fachlicher Vergleich direkt in der Anwendung, ohne eigene Rechenmodelle."""

from PyQt6.QtWidgets import QTextBrowser
from .config import RadarConfig


class RadarVergleich(QTextBrowser):
    def __init__(self) -> None:
        super().__init__()
        self.setOpenExternalLinks(True)

    def zeige_config(self, c: RadarConfig) -> None:
        key=(c.radar_mode,c.carrier_hz,c.bandwidth_hz,c.sample_rate_hz,c.chirp_s,c.repetition_s,c.chirps,c.adc_skip_samples)
        if key==getattr(self,"_profil",None):
            return
        self._profil=key
        modus = {"fmcw": "FMCW", "pulse_doppler": "Puls-Doppler / LFM", "passive": "Passiv BETA"}[c.radar_mode]
        self.setHtml(f"""
        <h2>Radarverfahren und ihre Grenzen</h2>
        <p>Aktuell: <b>{modus}</b> · Bandbreite {c.bandwidth_hz/1e3:g} kHz ·
        Integration {c.chirps*c.repetition_s*1000:g} ms · nominale
        {'Umweg' if c.radar_mode=='passive' else 'Entfernungs'}auflösung {c.range_resolution:.2f} m ·
        Abtastraster {c.range_bin_m:.2f} m.</p>
        <table border="1" cellpadding="8" cellspacing="0">
        <tr><th>Aspekt</th><th>FMCW</th><th>Puls-Doppler / LFM</th><th>Passiv BETA</th></tr>
        <tr><td>Entfernung</td><td>Beat-Frequenz, Range-FFT</td><td>Laufzeit, Matched Filter</td><td>Referenz gegen Überwachung; zusätzlicher Weg über Target</td></tr>
        <tr><td>Nominale Auflösung</td><td>c/(2·beobachtete Bandbreite)</td><td>c/(2B), auch bei langem LFM-Puls</td><td>c/B im Umweg, stark von Fremdsender und Geometrie abhängig</td></tr>
        <tr><td>Nahbereich</td><td>Kein Puls-Sendeblindbereich; reale Leckage hier nicht modelliert</td><td>Während Senden blind: mindestens c·Tp/2</td><td>Kein eigener Sender; Direktweg und Clutter können nahe Echos verdecken</td></tr>
        <tr><td>Fernbereich</td><td>Auch möglich; größere Laufzeit benötigt längere Rampen und passenden ADC-Start</td><td>Längeres PRI erlaubt weiter entfernte Echos, aber weniger eindeutige Geschwindigkeit</td><td>Abhängig von Beleuchtung und beiden Ausbreitungswegen</td></tr>
        <tr><td>Geschwindigkeit</td><td>λfd/2, eindeutig |v|&lt;λ/(4Tr)</td><td>λfd/2, derselbe PRI-Zielkonflikt</td><td>λfd ist die Wegänderungsrate; keine monostatische Radialgeschwindigkeit</td></tr>
        <tr><td>Signalenergie</td><td>Hoher Tastgrad möglich</td><td>Längerer Puls trägt bei gleicher Spitze mehr Energie, vergrößert aber Blindbereich</td><td>Empfänger bestimmt Sendeleistung und Signalform nicht</td></tr>
        <tr><td>ADC / Aufwand</td><td>Beat kann viel schmalbandiger als der ausgesendete Hub sein</td><td>Pulsbandbreite abtasten, Kompression nötig</td><td>Zwei kohärente Kanäle und aufwendige Kreuzambiguität</td></tr>
        <tr><td>Kopplung</td><td>Rapp=R+fc·v/S</td><td>LFM-Kompressionsgrat näherungsweise ebenfalls verschoben</td><td>Ambiguität folgt dem Fremdsendersignal; keine FMCW-Korrektur anwenden</td></tr>
        </table>
        <h3>300-km-Beispiel</h3>
        <p>Beide aktiven Profile verwenden 300 MHz Träger, 100 kHz Hub, 500 kSamples/s,
        3 ms Wiederholintervall und dieselbe relative Leistungsreferenz. Puls: 50 µs aktiv,
        nominal 1498,96 m Auflösung. FMCW: 2,9 ms Rampe, ADC erst ab 2,1 ms,
        nur 27,59 kHz beobachtet, nominal 5433,74 m. Beide können das Beispiel messen.
        Die Referenz-SNR gilt pro aktivem Sample; das ist kein Vergleich gleicher
        mittlerer Sendeleistung, Rauschbandbreite oder Hardware.</p>
        <p>Maximaler eindeutiger Betrag der radialen Geschwindigkeit in diesen beiden
        Profilen: 83,28 m/s. Große Reichweite und sehr hohe eindeutige Geschwindigkeit
        sind bei einem einzelnen PRI nicht gleichzeitig beliebig wählbar.
        Der Sender erzeugt bei Puls weniger aktive Samples; eine bessere Entfernungstrennung
        bedeutet deshalb nicht automatisch bessere Detektionswahrscheinlichkeit.</p>
        <h3>Modellgrenzen</h3>
        <p>Flache Welt und freie Sicht; keine Erdkrümmung, Atmosphäre, Bodenreflexion,
        Hardware-Leckage oder absolute Empfangsleistung. Die relative Empfangsleistung
        fällt monostatisch mit σ/R⁴, bistatisch mit σb/(Rt²Rr²). CFAR-Pfa ist nach
        Fensterung, Pulskompression oder CAF nur nominell. Keine Winkelmessung,
        keine Mehr-PRF-Entfaltung und kein Tracking.</p>
        <p><b>Passiv BETA:</b> Synthetischer Breitband-Fremdsender, idealer Referenzkanal,
        feste Tx/Rx. Keine FM-/DVB-Hardware-Nachbildung. Die wählbare Bandbreite ist
        eine Simulationseingabe; ein echter passiver Empfänger kann den Fremdsender
        nicht entsprechend umstellen. Die Direktweg-Projektion ist kein vollständiges Cluttermodell.</p>
        """)
