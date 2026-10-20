"""Eingaben für einen festen Fremdsender und einen festen passiven Empfänger."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PassivSettings:
    sender_x_m: float = -20000.
    sender_y_m: float = 0.
    sender_z_m: float = 0.
    maximaler_umweg_m: float = 30000.
    direktweg_db: float = 20.  # Leistung relativ zu Aref²=1 im Überwachungskanal.
    direktweg_entfernen: bool = True

    @property
    def senderort(self) -> tuple[float, float, float]:
        return self.sender_x_m, self.sender_y_m, self.sender_z_m
