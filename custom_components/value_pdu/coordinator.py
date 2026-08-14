"""DataUpdateCoordinator for the Value IP PDU integration."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_NOMINAL_VOLTAGE,
    CONF_OUTLET_LOCKED,
    CONF_OUTLET_NAMES,
    CONF_SCAN_INTERVAL,
    CONF_VOLTAGE_SENSOR,
    DEFAULT_NOMINAL_VOLTAGE,
    DEFAULT_OUTLET_NAMES,
    DOMAIN,
    MANUFACTURER,
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
_DELAYS_REFRESH_SECONDS = 900


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
        # Per-outlet (on_delay, off_delay) seconds, read from config_PDU.htm.
        self._delays: dict[int, tuple[int, int]] = {}
        self._last_delays_fetch = 0.0
        # Per-outlet pending command: {index: (target_state, deadline_monotonic)}.
        self._pending: dict[int, tuple[bool, float]] = {}
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

    def set_energy_base(self, value: float) -> None:
        """Seed the energy counter (e.g. from HA's restored sensor state)."""
        if value > self._energy_kwh:
            self._energy_kwh = value

    @property
    def power_w(self) -> float:
        """Most recently derived power draw in watts."""
        return self._last_power_w

    @property
    def voltage(self) -> float:
        """Voltage value used for the last power calculation."""
        return self._last_voltage

    def outlet_name(self, index: int) -> str:
        """Friendly name configured for an outlet (falls back to 'Outlet N')."""
        names = self._entry.options.get(CONF_OUTLET_NAMES, {})
        name = names.get(str(index))
        if name and name.strip():
            return name.strip()
        return DEFAULT_OUTLET_NAMES[index]

    def outlet_locked(self, index: int) -> bool:
        """Return whether an outlet is locked (read-only)."""
        locked = self._entry.options.get(CONF_OUTLET_LOCKED, {})
        return bool(locked.get(str(index)))

    def outlet_delay(self, index: int) -> tuple[int, int]:
        """Return the configured (on_delay, off_delay) in seconds for an outlet."""
        return self._delays.get(index, (0, 0))

    def outlet_pending(self, index: int) -> bool | None:
        """Return the target state of a still-in-flight delayed command, else None.

        While an outlet command is within its configured ON/OFF delay window the
        PDU has not physically switched yet, so polling would report the stale
        state. The switch entity uses this to keep showing the target.
        """
        pending = self._pending.get(index)
        if pending is None:
            return None
        target, deadline = pending
        if time.monotonic() >= deadline:
            self._pending.pop(index, None)
            return None
        return target

    async def async_fetch_delays(self) -> None:
        """Cache per-outlet delays from the PDU (best-effort)."""
        try:
            self._delays = await self._api.async_fetch_delays()
            self._last_delays_fetch = time.monotonic()
            _LOGGER.debug("PDU outlet delays: %s", self._delays)
        except PDUSessionError as err:
            _LOGGER.warning("Could not read outlet delays from PDU: %s", err)
            self._delays = {}

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
        """Send a control command and refresh state afterwards.

        Outlets marked read-only are rejected — this is the security boundary
        all control paths (switches, cycle buttons, services) go through.

        The PDU applies per-outlet ON/OFF delays before physically switching,
        so during that window the switch keeps showing the command's target
        state; a refresh is scheduled for when the delay elapses.
        """
        locked = [index + 1 for index in sorted(outlets) if self.outlet_locked(index)]
        if locked:
            raise HomeAssistantError(
                f"Outlet {', '.join(str(i) for i in locked)} is read-only"
            )
        busy = self._busy_outlets(outlets)
        if busy:
            details = ", ".join(
                f"{index + 1} ({remaining:.0f}s)" for index, remaining in busy.items()
            )
            raise HomeAssistantError(
                f"Outlet {details} is still switching — wait for the ON/OFF delay"
            )
        await self._api.async_control_outlets(outlets, op)

        max_delay = 0.0
        for index in outlets:
            target, delay = self._command_target(index, op)
            if delay > 0:
                self._pending[index] = (target, time.monotonic() + delay)
                max_delay = max(max_delay, delay)
        await self.async_request_refresh()
        if max_delay > 0:
            async_call_later(self.hass, max_delay, self._async_on_delay_elapsed)

    def _busy_outlets(self, outlets: set[int]) -> dict[int, float]:
        """Return {index: remaining_seconds} for outlets with an in-flight command."""
        now = time.monotonic()
        busy: dict[int, float] = {}
        for index in outlets:
            pending = self._pending.get(index)
            if pending is not None and now < pending[1]:
                busy[index] = pending[1] - now
        return busy

    def _command_target(self, index: int, op: str) -> tuple[bool, float]:
        """Return (target_state, delay_seconds) for a command on an outlet."""
        on_delay, off_delay = self.outlet_delay(index)
        if op == OP_ON:
            return True, float(on_delay)
        if op == OP_OFF:
            return False, float(off_delay)
        # Cycle (ON/OFF): the outlet ends up back where it started.
        current = self.data.outlets[index] if self.data else False
        return current, float(on_delay + off_delay)

    async def _async_on_delay_elapsed(self, _now: Any) -> None:
        """Re-poll once the slowest pending delay has elapsed."""
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
        if time.monotonic() - self._last_delays_fetch > _DELAYS_REFRESH_SECONDS:
            await self.async_fetch_delays()
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

        self._last_sample_time = now
        self._last_power_w = power_w
