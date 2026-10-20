"""python -m radar_sim [--config DATEI | --validate | --effects | --steps]."""

import argparse
import logging
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Radar Lab: FMCW, Puls-Doppler und reproduzierbare Validierung")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--validate", action="store_true", help="Validierungsbericht mit PNGs erzeugen")
    action.add_argument("--steps", action="store_true", help="Fünf Lernschritte ohne GUI ausführen")
    action.add_argument("--effects", action="store_true", help="Nur Störmodelle prüfen und Vergleichsdiagramme exportieren")
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument("--config", type=Path, help="JSON-Szenario beim Start laden")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.steps:
        from .learning_steps import run_steps
        return run_steps()
    if args.validate or args.effects:
        from PyQt6.QtWidgets import QApplication
        # Eine QApplication für ALLE Exporte am Leben halten. Wiederholtes
        # Erzeugen/Zerstören zwischen Plotfenstern kann Qt beim Beenden blockieren.
        app = QApplication.instance() or QApplication([])
        try:
            if args.validate:
                from .validation import run_validation
                report = run_validation(args.output)
                bestanden, datei = report["passed"], "VALIDATION.md"
            else:
                from .effekt_validierung import pruefe_stoermodelle, schreibe_effektbericht, export_effektplots
                args.output.mkdir(parents=True, exist_ok=True)
                report = pruefe_stoermodelle()
                schreibe_effektbericht(args.output, report)
                export_effektplots(args.output)
                bestanden, datei = report["bestanden"], "STOEREFFEKTE.md"
        finally:
            app.closeAllWindows()
            app.processEvents()
        print(f"Bericht: {args.output.resolve() / datei}", flush=True)
        print("BESTANDEN" if bestanden else "FEHLER – Bericht prüfen", flush=True)
        return 0 if bestanden else 1
    from .gui import run_gui
    from .io import load_config
    try:
        config = load_config(args.config) if args.config else None
        return run_gui(config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
