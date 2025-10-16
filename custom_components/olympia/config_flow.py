"""Config flow for Olympia Splendid AC."""
import broadlink
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_TEMP_SENSOR,
    CONF_DEVICE_IP,
    CONF_DEVICE_MAC,
    CONF_DEVICE_TYPE,
)


class OlympiaACConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Olympia Splendid AC."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.discovered_devices = {}
        self.selected_device_data = {}

    async def async_step_user(self, user_input=None):
        """Handle the initial step: discover devices."""
        devices = await self.hass.async_add_executor_job(broadlink.discover)

        if not devices:
            return await self.async_step_manual()

        self.discovered_devices = {
            f"{dev.type} ({dev.host[0]})": dev for dev in devices
        }

        return await self.async_step_select_device()

    async def async_step_select_device(self, user_input=None):
        """Handle the step to select a discovered device."""
        if user_input is not None:
            selected_key = user_input["selected_device"]
            device = self.discovered_devices[selected_key]
            self.selected_device_data = {
                CONF_DEVICE_IP: device.host[0],
                CONF_DEVICE_MAC: device.mac.hex(),
                CONF_DEVICE_TYPE: device.devtype,
            }
            return await self.async_step_settings()

        data_schema = vol.Schema({
            vol.Required("selected_device"): vol.In(list(self.discovered_devices.keys())),
        })
        return self.async_show_form(
            step_id="select_device", data_schema=data_schema
        )

    async def async_step_manual(self, user_input=None):
        """Handle the step to manually enter an IP address."""
        errors = {}
        if user_input is not None:
            ip_address = user_input[CONF_IP_ADDRESS]
            try:
                devices = await self.hass.async_add_executor_job(
                    broadlink.discover, None, ip_address
                )
                if not devices:
                    errors["base"] = "no_device_found"
                else:
                    device = devices[0]
                    self.selected_device_data = {
                        CONF_DEVICE_IP: device.host[0],
                        CONF_DEVICE_MAC: device.mac.hex(),
                        CONF_DEVICE_TYPE: device.type,
                    }
                    return await self.async_step_settings()
            except Exception:
                errors["base"] = "cannot_connect"

        data_schema = vol.Schema({vol.Required(CONF_IP_ADDRESS): str})
        return self.async_show_form(
            step_id="manual", data_schema=data_schema, errors=errors
        )

    async def async_step_settings(self, user_input=None):
        """Handle the final settings step."""
        if user_input is not None:
            final_data = self.selected_device_data.copy()
            final_data[CONF_TEMP_SENSOR] = user_input[CONF_TEMP_SENSOR]
            return self.async_create_entry(title="Olympia Splendid AC", data=final_data)

        data_schema = vol.Schema({
            vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                ),
            )
        })
        return self.async_show_form(step_id="settings", data_schema=data_schema)
