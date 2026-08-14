"""Switch platform for the Value IP PDU integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN, OUTLET_COUNT, SWITCH_DEVICE_CLASS
from .coordinator import ValuePDUCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Value IP PDU outlet switches."""
    coordinator: ValuePDUCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ValuePDUOutletSwitch(coordinator, entry, index) for index in range(OUTLET_COUNT)
    )


class ValuePDUOutletSwitch(CoordinatorEntity, SwitchEntity):
    """One outlet of the PDU, exposed as an on/off switch."""

    def __init__(self, coordinator: ValuePDUCoordinator, entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator)
        self._index = index
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{entry.entry_id}_outlet_{index}"
        self._attr_name = coordinator.outlet_name(index)
        self._attr_has_entity_name = True
        self._attr_device_class = SWITCH_DEVICE_CLASS

    @property
    def icon(self) -> str:
        return "mdi:power-plug" if self.is_on else "mdi:power-plug-off"

    @property
    def is_on(self) -> bool:
        # While a command is within its configured ON/OFF delay window the PDU
        # has not physically switched yet; keep showing the target state so a
        # stale poll cannot revert the UI.
        pending = self.coordinator.outlet_pending(self._index)
        if pending is not None:
            return pending
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.outlets[self._index]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        on_delay, off_delay = self.coordinator.outlet_delay(self._index)
        return {"on_delay": on_delay, "off_delay": off_delay}

    async def _async_guard_locked(self) -> bool:
        """Return True (and ignore the command) if the outlet is read-only."""
        if self.coordinator.outlet_locked(self._index):
            _LOGGER.warning(
                "Outlet %d is read-only — command ignored", self._index + 1
            )
            await self.coordinator.async_request_refresh()
            return True
        return False

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the outlet on."""
        if await self._async_guard_locked():
            return
        await self.coordinator.async_turn_on({self._index})

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the outlet off."""
        if await self._async_guard_locked():
            return
        await self.coordinator.async_turn_off({self._index})
