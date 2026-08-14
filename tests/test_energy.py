"""Unit tests for the pure power/energy math."""

from __future__ import annotations

import pytest

from loader import load_module

energy = load_module("energy", "energy.py")


def test_power_watts():
    assert energy.power_watts(230.0, 1.0) == 230.0
    assert energy.power_watts(231.5, 2.0) == 463.0
    assert energy.power_watts(230.0, 0.0) == 0.0


def test_integrate_energy():
    # 1 A @ 230 V for 1 hour == 0.23 kWh
    result = energy.integrate_energy_kwh(0.0, energy.power_watts(230.0, 1.0), 3600.0)
    assert result == pytest.approx(0.23)

    # 1000 W for 1 hour == 1 kWh
    assert energy.integrate_energy_kwh(0.0, 1000.0, 3600.0) == pytest.approx(1.0)

    # accumulates
    total = energy.integrate_energy_kwh(0.0, 500.0, 3600.0)  # 0.5 kWh
    total = energy.integrate_energy_kwh(total, 500.0, 1800.0)  # +0.25 kWh
    assert total == pytest.approx(0.75)
