"""python -m radar_sim [--config DATEI | --validate | --steps]."""

import argparse
import logging
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Radar Lab: FMCW, Puls-Doppler und reproduzierbare Validierung")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--validate", action="store_true", help="Validierungsbericht mit PNGs erzeugen")
    action.add_argument("--steps", action="store_true", help="Fünf Lernschritte ohne GUI ausführen")
    parser.add_argument("--output", type=Path, default=Path("reports"))
    parser.add_argument("--config", type=Path, help="JSON-Szenario beim Start laden")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.validate:
        from .validation import run_validation
        report = run_validation(args.output)
        print(f"Bericht: {args.output.resolve() / 'VALIDATION.md'}")
        print("BESTANDEN" if report["passed"] else "FEHLER – Bericht prüfen")
        return 0 if report["passed"] else 1
    if args.steps:
        from .learning_steps import run_steps
        return run_steps()
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
