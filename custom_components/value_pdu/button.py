"""Button platform for the Value IP PDU integration (outlet power-cycle)."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.button import ButtonEntity

from .const import CYCLE_BUTTON_DEVICE_CLASS, DOMAIN, OUTLET_COUNT
from .coordinator import ValuePDUCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Value IP PDU power-cycle buttons."""
    coordinator: ValuePDUCoordinator = hass.data[DOMAIN][entry.entry_id]
    # Read-only (locked) outlets get no cycle button.
    async_add_entities(
        ValuePDUCycleButton(coordinator, entry, index)
        for index in range(OUTLET_COUNT)
        if not coordinator.outlet_locked(index)
    )


class ValuePDUCycleButton(CoordinatorEntity, ButtonEntity):
    """Power-cycle (ON/OFF) a single outlet."""

    def __init__(self, coordinator: ValuePDUCoordinator, entry: ConfigEntry, index: int) -> None:
        super().__init__(coordinator)
        self._index = index
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{entry.entry_id}_outlet_{index}_cycle"
        self._attr_name = f"{coordinator.outlet_name(index)} cycle"
        self._attr_has_entity_name = True
        self._attr_device_class = CYCLE_BUTTON_DEVICE_CLASS
        self._attr_icon = "mdi:restart"

    async def async_press(self) -> None:
        """Power-cycle the outlet."""
        # Belt-and-suspenders guard: lockouts are enforced by the coordinator.
        await self.coordinator.async_cycle({self._index})
