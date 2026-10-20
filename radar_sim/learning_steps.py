"""Fünf ausführbare Lernbeispiele mit analytischen Erwartungen."""

from .config import C
from .evaluation import match_targets
from .pipeline import simulate_frame
from .scenarios import scenarios


def run_steps() -> int:
    namen = ("01_stationary", "02_approach_recede", "03_same_range_two_velocities", "04_cfar_noise", "05_dashboard")
    for schritt, name in enumerate(namen, 1):
        config = scenarios()[name]
        ergebnis = simulate_frame(config)
        print(f"\nSchritt {schritt}: {name} (Seed={config.seed}, Frame=0)")
        for ziel in config.targets:
            doppler_hz = 2 * ziel.velocity_mps / config.wavelength
            beat_hz = 2 * config.slope * ziel.range_m / C + doppler_hz
            print(f"  Erwartet: R={ziel.range_m:.6f} m, v={ziel.velocity_mps:.6f} m/s, fb={beat_hz:.3f} Hz, fd={doppler_hz:.3f} Hz")
        zuordnungen = match_targets(config, ergebnis.candidates)
        for zuordnung in zuordnungen:
            schaetzung = ergebnis.candidates[zuordnung.candidate_index]
            print(f"  Geschätzt: R={schaetzung.range_m:.6f} m, v={schaetzung.velocity_mps:.6f} m/s, "
                  f"Fehler=({zuordnung.range_error_m:+.6f} m, {zuordnung.velocity_error_mps:+.6f} m/s)")
        entfernungstoleranz = config.range_resolution / 2 + C / (4 * config.slope * config.chirps * config.repetition_s)
        if len(zuordnungen) != len(config.targets) or any(abs(m.range_error_m) > 1.01 * entfernungstoleranz
                or abs(m.velocity_error_mps) > 1.01 * config.velocity_resolution / 2 for m in zuordnungen):
            print("FEHLER: Erwartung verfehlt.")
            return 1
        print(f"  OK; {len(ergebnis.candidates) - len(zuordnungen)} zusätzliche Kandidaten (Rauschen/Nebenkeulen).")
    return 0
