"""Value IP PDU integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    OP_CYCLE,
    OUTLET_COUNT,
)
from .coordinator import ValuePDUCoordinator
from .pdu_api import PDUSessionError, ValuePDU

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON]

SERVICE_CYCLE_OUTLET = "cycle_outlet"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Value IP PDU from a config entry."""
    session = async_get_clientsession(hass)
    api = ValuePDU(
        host=entry.data[CONF_HOST],
        username=entry.options.get(CONF_USERNAME, entry.data[CONF_USERNAME]),
        password=entry.options.get(CONF_PASSWORD, entry.data[CONF_PASSWORD]),
        session=session,
    )

    coordinator = ValuePDUCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except (PDUSessionError, TimeoutError) as err:
        raise ConfigEntryNotReady(f"PDU not reachable: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await _async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options (credentials, interval, voltage) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register the cycle_outlet service (power-cycle an outlet)."""

    async def _handle_cycle(call: ServiceCall) -> None:
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        if not coordinators:
            return
        coordinator = coordinators[0]
        outlet = call.data["outlet"]
        if not 0 <= outlet < OUTLET_COUNT:
            raise ValueError(f"outlet must be 0..{OUTLET_COUNT - 1}, got {outlet}")
        await coordinator.async_cycle({outlet})

    service.async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CYCLE_OUTLET,
        _handle_cycle,
        schema=vol.Schema({vol.Required("outlet"): cv.positive_int}),
    )
