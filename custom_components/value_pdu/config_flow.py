"""Config flow for the Value IP PDU integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_HOST,
    CONF_NOMINAL_VOLTAGE,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    CONF_VOLTAGE_SENSOR,
    DEFAULT_NOMINAL_VOLTAGE,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MIN_UPDATE_INTERVAL_SECONDS,
)
from .pdu_api import PDUSessionError, ValuePDU

_LOGGER = logging.getLogger(__name__)


async def _async_test_connection(
    hass: HomeAssistant, host: str, username: str, password: str
) -> None:
    """Raise PDUSessionError if the PDU is not reachable with the given credentials."""
    session = async_get_clientsession(hass)
    api = ValuePDU(host=host, username=username, password=password, session=session)
    await api.async_fetch_status()


class ValuePDUConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Value IP PDU."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            try:
                await _async_test_connection(
                    self.hass,
                    user_input[CONF_HOST],
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
            except (PDUSessionError, TimeoutError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_HOST], data=user_input
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): TextSelector(),
                vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): TextSelector(),
                vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL_SECONDS,
                        max=3600,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    CONF_NOMINAL_VOLTAGE, default=DEFAULT_NOMINAL_VOLTAGE
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=90,
                        max=300,
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="V",
                    )
                ),
                vol.Optional(CONF_VOLTAGE_SENSOR): EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="voltage")
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ValuePDUOptionsFlow(config_entry)


class ValuePDUOptionsFlow(OptionsFlow):
    """Handle options for the Value IP PDU integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        data = self._config_entry.data

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, data.get(CONF_SCAN_INTERVAL)),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_UPDATE_INTERVAL_SECONDS,
                        max=3600,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="s",
                    )
                ),
                vol.Required(
                    CONF_NOMINAL_VOLTAGE,
                    default=options.get(
                        CONF_NOMINAL_VOLTAGE, data.get(CONF_NOMINAL_VOLTAGE, DEFAULT_NOMINAL_VOLTAGE)
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=90,
                        max=300,
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="V",
                    )
                ),
                vol.Optional(
                    CONF_VOLTAGE_SENSOR,
                    default=options.get(CONF_VOLTAGE_SENSOR, data.get(CONF_VOLTAGE_SENSOR)),
                ): EntitySelector(
                    EntitySelectorConfig(domain="sensor", device_class="voltage")
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=options_schema)

