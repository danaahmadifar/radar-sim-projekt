"""Fünf kleine reproduzierbare Lernschritte und gespeicherte Szenen."""

from dataclasses import replace
from pathlib import Path
from .config import RadarConfig, Target
from .io import save_config
from .flugbahn import flugszenen


def scenarios() -> dict[str, RadarConfig]:
    basis = RadarConfig(noise_enabled=False)
    delta_r, delta_v = basis.range_resolution, basis.velocity_resolution
    return {
        "01_stationary": replace(basis, targets=(Target(40 * delta_r, 0),)),
        "02_approach_recede": replace(basis, targets=(Target(40 * delta_r, -18 * delta_v), Target(75 * delta_r, 24 * delta_v))),
        "03_two_ranges": replace(basis, targets=(Target(40 * delta_r, 0), Target(80 * delta_r, 0, 0.5))),
        "03_same_range_two_velocities": replace(basis, targets=(Target(60 * delta_r, -16 * delta_v), Target(60 * delta_r, 20 * delta_v))),
        "04_cfar_noise": replace(basis, noise_enabled=True, snr_db=-15,
                                  targets=(Target(45 * delta_r, -12 * delta_v), Target(90 * delta_r, 18 * delta_v, 0.6))),
        "05_dashboard": RadarConfig(),
        "near_resolution": replace(basis, targets=(Target(60 * delta_r, 0), Target(61.2 * delta_r, 0))),
        "noise_only": replace(basis, targets=(), noise_enabled=True, window="rect", pfa=1e-3),
    }


def write_scenarios(directory: str | Path) -> None:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    for name, config in scenarios().items():
        save_config(path / f"{name}.json", config)
    for name, szene in flugszenen().items():
        save_config(path / f"{name}.json", RadarConfig(targets=(), flugszene=szene))
    from .routen_validierung import beispielroute
    save_config(path / "09_gezeichnete_route.json", beispielroute())
