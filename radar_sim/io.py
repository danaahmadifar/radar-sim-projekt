"""JSON-Konfiguration und CSV-Export ausschließlich mit Standardbibliothek."""

import csv
from dataclasses import asdict, fields
import json
from pathlib import Path

from .config import RadarConfig, validate_config
from .detection import Candidate
from .flugbahn import Flugzustand


def schreibe_json(path: str | Path, daten) -> None:
    """Einheitliches UTF-8-JSON für Konfigurationen und gemessene Berichte."""
    Path(path).write_text(json.dumps(daten, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def schreibe_markdown(path: str | Path, zeilen: list[str]) -> None:
    """Schreibt einen Bericht mit abschließendem Zeilenumbruch."""
    Path(path).write_text("\n".join(zeilen) + "\n", encoding="utf-8")


def save_config(path: str | Path, config: RadarConfig) -> None:
    validate_config(config)
    schreibe_json(path, config.to_dict())


def load_config(path: str | Path) -> RadarConfig:
    file = Path(path)
    if file.stat().st_size > 1_000_000:
        raise ValueError("Konfigurationsdatei ist größer als 1 MB.")
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Die Konfiguration muss ein JSON-Objekt sein.")
    return RadarConfig.from_dict(data)


def export_candidates(path: str | Path, candidates: list[Candidate]) -> None:
    """UTF-8-SIG und Semikolon für Windows/Excel; Einheiten stehen in Feldnamen."""
    with Path(path).open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=[f.name for f in fields(Candidate)], delimiter=";")
        writer.writeheader()
        writer.writerows(asdict(candidate) for candidate in candidates)


def export_flugzustaende(path: str | Path, zeit_s: float, zustaende: tuple[Flugzustand, ...]) -> None:
    """Bekannte Flugpositionen getrennt exportieren: Das Radar hat sie nicht geschätzt."""
    spalten = ["objekt", "zeit_s"] + [feld.name for feld in fields(Flugzustand)]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as datei:
        tabelle = csv.DictWriter(datei, fieldnames=spalten, delimiter=";")
        tabelle.writeheader()
        for nummer, zustand in enumerate(zustaende, 1):
            tabelle.writerow({"objekt": nummer, "zeit_s": zeit_s, **asdict(zustand)})
