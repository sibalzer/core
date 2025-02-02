"""Config flow for Plugwise integration."""
from __future__ import annotations

from typing import Any

from plugwise.exceptions import InvalidAuthentication, PlugwiseException
from plugwise.smile import Smile
import voluptuous as vol

from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import (
    CONF_BASE,
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
    DOMAIN,
    FLOW_SMILE,
    FLOW_STRETCH,
    LOGGER,
    PW_TYPE,
    SMILE,
    STRETCH,
    STRETCH_USERNAME,
    ZEROCONF_MAP,
)


def _base_gw_schema(discovery_info):
    """Generate base schema for gateways."""
    base_gw_schema = {}

    if not discovery_info:
        base_gw_schema[vol.Required(CONF_HOST)] = str
        base_gw_schema[vol.Optional(CONF_PORT, default=DEFAULT_PORT)] = int
        base_gw_schema[vol.Required(CONF_USERNAME, default=SMILE)] = vol.In(
            {SMILE: FLOW_SMILE, STRETCH: FLOW_STRETCH}
        )

    base_gw_schema.update({vol.Required(CONF_PASSWORD): str})

    return vol.Schema(base_gw_schema)


async def validate_gw_input(hass: HomeAssistant, data: dict[str, Any]) -> Smile:
    """
    Validate whether the user input allows us to connect to the gateway.

    Data has the keys from _base_gw_schema() with values provided by the user.
    """
    websession = async_get_clientsession(hass, verify_ssl=False)
    api = Smile(
        host=data[CONF_HOST],
        password=data[CONF_PASSWORD],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        timeout=30,
        websession=websession,
    )
    await api.connect()
    return api


class PlugwiseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Plugwise Smile."""

    VERSION = 1

    discovery_info: ZeroconfServiceInfo | None = None
    _username: str = DEFAULT_USERNAME

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> FlowResult:
        """Prepare configuration for a discovered Plugwise Smile."""
        self.discovery_info = discovery_info
        _properties = discovery_info.properties

        unique_id = discovery_info.hostname.split(".")[0]
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured({CONF_HOST: discovery_info.host})

        if DEFAULT_USERNAME not in unique_id:
            self._username = STRETCH_USERNAME
        _product = _properties.get("product", None)
        _version = _properties.get("version", "n/a")
        _name = f"{ZEROCONF_MAP.get(_product, _product)} v{_version}"

        self.context["title_placeholders"] = {
            CONF_HOST: discovery_info.host,
            CONF_NAME: _name,
            CONF_PORT: discovery_info.port,
            CONF_USERNAME: self._username,
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step when using network/gateway setups."""
        errors = {}

        if user_input is not None:
            if self.discovery_info:
                user_input[CONF_HOST] = self.discovery_info.host
                user_input[CONF_PORT] = self.discovery_info.port
                user_input[CONF_USERNAME] = self._username

            try:
                api = await validate_gw_input(self.hass, user_input)
            except InvalidAuthentication:
                errors[CONF_BASE] = "invalid_auth"
            except PlugwiseException:
                errors[CONF_BASE] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception")
                errors[CONF_BASE] = "unknown"
            else:
                await self.async_set_unique_id(
                    api.smile_hostname or api.gateway_id, raise_on_progress=False
                )
                self._abort_if_unique_id_configured()

                user_input[PW_TYPE] = API
                return self.async_create_entry(title=api.smile_name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_base_gw_schema(self.discovery_info),
            errors=errors,
        )
