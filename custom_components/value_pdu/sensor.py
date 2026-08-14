"""Sensor platform for the Value IP PDU integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_DESCRIPTORS
from .coordinator import ValuePDUCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Value IP PDU sensors."""
    coordinator: ValuePDUCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ValuePDUSensor(coordinator, entry, descriptor) for descriptor in SENSOR_DESCRIPTORS
    )


class ValuePDUSensor(CoordinatorEntity):
    """A sensor whose value is pulled from the coordinator."""

    def __init__(self, coordinator: ValuePDUCoordinator, entry: ConfigEntry, descriptor: dict) -> None:
        super().__init__(coordinator)
        self._descriptor = descriptor
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{entry.entry_id}_{descriptor['key']}"
        self._attr_name = descriptor["name"]
        self._attr_has_entity_name = True
        self._attr_device_class = descriptor["device_class"]
        self._attr_native_unit_of_measurement = descriptor["unit"]
        self._attr_state_class = descriptor["state_class"]
        self._attr_icon = descriptor["icon"]
        if descriptor.get("entity_category"):
            self._attr_entity_category = EntityCategory(descriptor["entity_category"])

    @property
    def native_value(self):
        coordinator = self.coordinator
        key = self._descriptor["key"]
        if key == "current":
            return coordinator.data.current
        if key == "temperature":
            return coordinator.data.temperature
        if key == "humidity":
            return coordinator.data.humidity
        if key == "power":
            return coordinator.power_w
        if key == "energy":
            return coordinator.energy_kwh
        if key == "voltage":
            return coordinator.voltage
        return None
