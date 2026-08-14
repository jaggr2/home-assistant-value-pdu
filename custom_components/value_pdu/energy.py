"""Pure power/energy math helpers (unit-testable, no HA imports)."""

from __future__ import annotations

_WS_PER_KWH = 3600000.0


def integrate_energy_kwh(energy_kwh: float, power_w: float, gap_seconds: float) -> float:
    """Add the energy drawn at `power_w` over `gap_seconds` to a kWh counter.

    energy += power (W) * time (s) / (1000 W/kW * 3600 s/h)  →  kWh
    """
    return energy_kwh + (power_w * gap_seconds) / _WS_PER_KWH


def power_watts(voltage_v: float, current_a: float) -> float:
    """Apparent power in watts from voltage and current."""
    return voltage_v * current_a
