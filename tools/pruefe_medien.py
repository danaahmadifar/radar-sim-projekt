"""PNG-Größen, MP4-Samplezahl und tatsächliche Videowiedergabe mit Qt prüfen."""

import json
import os
from pathlib import Path
import struct
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink

ORDNER = Path(__file__).resolve().parents[1]/"docs/media"


def boxen(data):
    """MP4-Boxen: Länge und Typ lesen; große Boxen und Restlänge berücksichtigen."""
    pos = 0
    while pos+8 <= len(data):
        size, typ = struct.unpack_from(">I4s", data, pos)
        header = 8
        if size == 1:
            size = struct.unpack_from(">Q", data, pos+8)[0]
            header = 16
        elif size == 0:
            size = len(data)-pos
        if size < header or pos+size > len(data):
            raise ValueError("Beschädigte MP4-Box")
        yield typ, data[pos+header:pos+size]
        pos += size


def box(data, typ):
    return next(body for name, body in boxen(data) if name == typ)


def videodaten(datei):
    moov = box(datei.read_bytes(), b"moov")
    tracks = [body for name, body in boxen(moov) if name == b"trak"]
    assert len(tracks) == 1, "Genau eine Videospur, keine Tonspur erwartet."
    mdia = box(tracks[0], b"mdia")
    assert box(mdia, b"hdlr")[8:12] == b"vide"
    table = box(box(mdia, b"minf"), b"stbl")
    count = struct.unpack_from(">I", box(table, b"stsz"), 8)[0]
    codec = box(table, b"stsd")[12:16].decode("ascii")
    width, height = struct.unpack(">II", box(tracks[0], b"tkhd")[-8:])
    return {"container_frames": count, "codec": codec, "aufloesung": [width//65536, height//65536]}


def dekodiere(app, datei, erwartet):
    player, sink = QMediaPlayer(), QVideoSink()
    player.setVideoSink(sink)
    sammlung = {"frames": 0, "erstes": None, "mitte": None, "letztes": None, "letzte_zeit_us": 0}
    def bild(frame):
        if not frame.isValid():
            return
        sammlung["frames"] += 1
        sammlung["letzte_zeit_us"] = frame.startTime()
        sammlung["letztes"] = frame.toImage().copy()
        if sammlung["erstes"] is None:
            sammlung["erstes"] = sammlung["letztes"]
        if sammlung["mitte"] is None and frame.startTime() >= erwartet*1e6/2:
            sammlung["mitte"] = sammlung["letztes"]
    sink.videoFrameChanged.connect(bild)
    player.setSource(QUrl.fromLocalFile(str(datei.resolve())))
    player.setPlaybackRate(6)
    player.play()
    deadline = time.monotonic()+45
    while player.mediaStatus() != QMediaPlayer.MediaStatus.EndOfMedia:
        app.processEvents()
        if player.error() != QMediaPlayer.Error.NoError:
            raise RuntimeError(player.errorString())
        if time.monotonic() > deadline:
            raise TimeoutError("Video wurde nicht bis zum Ende abgespielt.")
        time.sleep(.002)
    dauer = player.duration()/1000
    assert abs(dauer-erwartet) < .25, (dauer, erwartet)
    assert sammlung["letzte_zeit_us"] > (erwartet-.5)*1e6
    for name in ("erstes", "mitte", "letztes"):
        img = sammlung[name]
        assert img is not None and not img.isNull()
        assert (img.width(), img.height()) == (1920, 1080)
        # Eine vollständig schwarze oder einfarbige Encoder-Ausgabe ausschließen.
        farben = {img.pixel(x, y) for x in range(50, 1900, 150) for y in range(50, 1050, 100)}
        assert len(farben) > 10, "Leeres/einfarbiges Videobild"
        assert img.save(str(ORDNER/"pruefung"/(datei.stem+"_"+name+".png")))
    player.stop()
    return {"wiedergabe_bis_ende": True, "dauer_s": dauer, "dekodierte_frames": sammlung["frames"],
            "letzter_frame_us": sammlung["letzte_zeit_us"]}


def main():
    app = QApplication.instance() or QApplication([])
    manifest = json.loads((ORDNER/"medien.json").read_text(encoding="utf-8"))
    (ORDNER/"pruefung").mkdir(exist_ok=True)
    ergebnisse = []
    for p in manifest["bilder"]:
        img = QImage(str(ORDNER/p["datei"]))
        assert not img.isNull() and [img.width(), img.height()] == p["aufloesung"]
    for v in manifest["videos"]:
        datei = ORDNER/v["datei"]
        kopf = videodaten(datei)
        assert kopf["container_frames"] == v["frames"]
        assert kopf["codec"] == "avc1" and kopf["aufloesung"] == v["aufloesung"]
        ergebnisse.append({"datei": v["datei"], **kopf, **dekodiere(app, datei, v["dauer_s"])})
        print(json.dumps(ergebnisse[-1], ensure_ascii=False), flush=True)
    (ORDNER/"pruefung.json").write_text(json.dumps({"pngs_geprueft": len(manifest["bilder"]), "videos": ergebnisse,
          "bestanden": True}, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    app.closeAllWindows()
    app.processEvents()


if __name__ == "__main__":
    main()
