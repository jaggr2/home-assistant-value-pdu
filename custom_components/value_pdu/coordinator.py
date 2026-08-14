"""DataUpdateCoordinator for the Value IP PDU integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_NOMINAL_VOLTAGE,
    CONF_SCAN_INTERVAL,
    CONF_VOLTAGE_SENSOR,
    DEFAULT_NOMINAL_VOLTAGE,
    DOMAIN,
    MANUFACTURER,
    MIN_ENERGY_PERSIST_SECONDS,
    MODEL,
    OP_OFF,
    OP_ON,
    OP_CYCLE,
    OUTLET_COUNT,
)
from .energy import integrate_energy_kwh
from .pdu_api import PDUSessionError, PDUSnapshot, ValuePDU

_LOGGER = logging.getLogger(__name__)

_MAX_GAP_BEFORE_RESET_SECONDS = 600


class ValuePDUCoordinator(DataUpdateCoordinator[PDUSnapshot]):
    """Poll the PDU and derive power/energy from current + voltage."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, api: ValuePDU
    ) -> None:
        self._entry = entry
        self._api = api
        self._energy_kwh: float = float(entry.data.get("energy_kwh", 0.0))
        self._last_sample_time: float | None = None
        self._last_power_w: float = 0.0
        self._last_voltage: float = 0.0
        self._last_energy_persist = 0.0
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=int(entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL)))
            ),
        )

    # ------------------------------------------------------------------
    # Device/entry helpers
    # ------------------------------------------------------------------
    @property
    def device_info(self) -> DeviceInfo:
        """Device registry entry for this PDU."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def energy_kwh(self) -> float:
        return self._energy_kwh

    @property
    def power_w(self) -> float:
        """Most recently derived power draw in watts."""
        return self._last_power_w

    @property
    def voltage(self) -> float:
        """Voltage value used for the last power calculation."""
        return self._last_voltage

    # ------------------------------------------------------------------
    # Voltage resolution
    # ------------------------------------------------------------------
    def _resolve_voltage(self) -> float:
        """Return the voltage used for power calculations.

        Prefers a configured HA sensor (e.g. a wall/rack meter measuring the
        same feed); falls back to the configurable nominal voltage constant.
        """
        sensor_entity = self._entry.options.get(
            CONF_VOLTAGE_SENSOR, self._entry.data.get(CONF_VOLTAGE_SENSOR)
        )
        if sensor_entity:
            state = self.hass.states.get(sensor_entity)
            if state is not None:
                try:
                    value = float(state.state)
                except (TypeError, ValueError):
                    _LOGGER.debug(
                        "Voltage sensor %s has non-numeric state %r; using nominal voltage",
                        sensor_entity,
                        state.state,
                    )
                else:
                    if value > 0:
                        return value
        return float(
            self._entry.options.get(
                CONF_NOMINAL_VOLTAGE, self._entry.data.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE)
            )
        )

    # ------------------------------------------------------------------
    # Outlet control
    # ------------------------------------------------------------------
    async def async_control_outlets(self, outlets: set[int], op: str) -> None:
        """Send a control command and refresh state afterwards."""
        await self._api.async_control_outlets(outlets, op)
        await self.async_request_refresh()

    async def async_turn_on(self, outlets: set[int]) -> None:
        await self.async_control_outlets(outlets, OP_ON)

    async def async_turn_off(self, outlets: set[int]) -> None:
        await self.async_control_outlets(outlets, OP_OFF)

    async def async_cycle(self, outlets: set[int]) -> None:
        await self.async_control_outlets(outlets, OP_CYCLE)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> PDUSnapshot:
        try:
            snapshot = await self._api.async_fetch_status()
        except PDUSessionError as err:
            raise UpdateFailed(f"PDU unreachable: {err}") from err

        voltage = self._resolve_voltage()
        power_w = voltage * snapshot.current
        self._last_voltage = voltage
        self._last_power_w = power_w
        self._accumulate_energy(power_w)

        if len(snapshot.outlets) != OUTLET_COUNT:
            raise UpdateFailed(
                f"Unexpected outlet count in status.xml: {len(snapshot.outlets)}"
            )

        _LOGGER.debug(
            "PDU poll: current=%.2f A voltage=%.1f V power=%.1f W energy=%.4f kWh",
            snapshot.current,
            voltage,
            power_w,
            self._energy_kwh,
        )
        return snapshot

    def _accumulate_energy(self, power_w: float) -> None:
        """Integrate power over time into the kWh counter."""
        now = time.time()
        if self._last_sample_time is None:
            # First sample: no interval yet, just remember the baseline.
            self._last_sample_time = now
            self._last_power_w = power_w
            return

        gap = now - self._last_sample_time
        if gap > _MAX_GAP_BEFORE_RESET_SECONDS:
            # Long gap (HA slept / device offline): don't fabricate usage.
            self._last_sample_time = now
            self._last_power_w = power_w
            return

        if gap > 0:
            self._energy_kwh = integrate_energy_kwh(self._energy_kwh, self._last_power_w, gap)
            self._maybe_persist_energy(now)

        self._last_sample_time = now
        self._last_power_w = power_w

    def _maybe_persist_energy(self, now: float) -> None:
        """Throttled write of the energy counter into the config entry."""
        if now - self._last_energy_persist < MIN_ENERGY_PERSIST_SECONDS:
            return
        self._last_energy_persist = now
        data = {**self._entry.data, "energy_kwh": self._energy_kwh}
        self.hass.config_entries.async_update_entry(self._entry, data=data)
