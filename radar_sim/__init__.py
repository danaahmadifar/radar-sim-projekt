"""FMCW-Labor: transparenter Rechenkern ohne GUI-Abhängigkeit."""

from .config import RadarConfig, Target, validate_config
from .pipeline import simulate_frame

__all__ = ["RadarConfig", "Target", "validate_config", "simulate_frame"]
