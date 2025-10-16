"""Climate platform for the Olympia Splendid AC integration."""
import datetime
import logging

import broadlink
from broadlink.remote import pulses_to_data
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    FAN_AUTO,
    SWING_OFF,
    SWING_ON
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_TEMP_SENSOR, CONF_DEVICE_IP, CONF_DEVICE_MAC, CONF_DEVICE_TYPE

_LOGGER = logging.getLogger(__name__)

SUPPORT_FAN = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]
SUPPORT_SWING = [SWING_OFF, SWING_ON]

SUPPORT_HVAC = [
    HVACMode.OFF,
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.FAN_ONLY,
    HVACMode.DRY,
    HVACMode.AUTO,
]


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the climate entity from a config entry."""
    # Get the sensor entity_id that the user chose during setup
    sensor_entity_id = entry.data[CONF_TEMP_SENSOR]
    device_ip = entry.data[CONF_DEVICE_IP]
    device_mac = entry.data[CONF_DEVICE_MAC]
    device_type = entry.data[CONF_DEVICE_TYPE]
    mac_bytes = bytes.fromhex(device_mac)
    broadlink_device = broadlink.gendevice(dev_type=device_type, host=(device_ip, 80), mac=mac_bytes)
    await hass.async_add_executor_job(broadlink_device.auth)
    async_add_entities([OlympiaACClimate(sensor_entity_id, broadlink_device)])


class OlympiaACClimate(ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = "Olympia Splendid AC"
    _attr_unique_id = "olympia_splendid"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = HVACMode.OFF
    _attr_fan_mode = FAN_AUTO
    _attr_swing_mode = SWING_OFF
    _attr_target_temperature = 22

    _attr_hvac_modes = SUPPORT_HVAC
    _attr_fan_modes = SUPPORT_FAN
    _attr_swing_modes = SUPPORT_SWING
    _attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE
    )
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 16
    _attr_max_temp = 30

    def __init__(self, temp_sensor_entity_id: str, broadlink) -> None:
        """Initialize the climate entity."""
        self._temp_sensor_entity_id = temp_sensor_entity_id
        self._broadlink = broadlink
        self._attr_current_temperature = None

    @callback
    def _async_update_temp(self, event) -> None:
        """Update the current temperature from the sensor."""
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in ("unknown", "unavailable"):
            return

        try:
            self._attr_current_temperature = float(new_state.state)
            self.async_write_ha_state()
        except (ValueError, TypeError):
            _LOGGER.error(f"Could not parse temperature from {self._temp_sensor_entity_id}")

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._temp_sensor_entity_id], self._async_update_temp
            )
        )

        sensor_state = self.hass.states.get(self._temp_sensor_entity_id)
        if sensor_state and sensor_state.state not in ("unknown", "unavailable"):
            try:
                self._attr_current_temperature = float(sensor_state.state)
            except (ValueError, TypeError):
                _LOGGER.error(f"Could not parse initial temperature from {self._temp_sensor_entity_id}")

    def send_command(self):
        num_bits = 70
        command = 0
        # Home
        command |= (0 << (num_bits - 0))
        # Night Mode
        command |= (0 << (num_bits - 1))
        # Swing
        command |= (SUPPORT_SWING.index(self._attr_swing_mode) << (num_bits - 2))
        # Fan (2 bits)
        command |= (SUPPORT_FAN.index(self._attr_fan_mode) << (num_bits - 4))
        # Mode (3 bits)
        command |= (SUPPORT_HVAC.index(self._attr_hvac_mode) << (num_bits - 7))
        # Clock Hours (6 bits)
        now = datetime.datetime.now()
        command |= (now.hour << (num_bits - 16))
        # Clock Minutes (7 bits)
        command |= (now.minute << (num_bits - 25))
        # Timer 1 On/Off
        command |= (0 << (num_bits - 27))
        # Timer 1 On 30 minutes
        command |= (0 << (num_bits - 28))
        # Timer 1 On Hours (6 bits)
        command |= (0 << (num_bits - 34))
        # Timer 1 Off 30 minutes
        command |= (0 << (num_bits - 37))
        # Timer 1 Off Hours (6 bits)
        command |= (0 << (num_bits - 43))
        # Timer 2 On/Off
        command |= (0 << (num_bits - 45))
        # Timer 2 On 30 minutes
        command |= (0 << (num_bits - 46))
        # Timer 2 On Hours (6 bits)
        command |= (0 << (num_bits - 52))
        # Timer 2 Off 30 minutes
        command |= (0 << (num_bits - 55))
        # Timer 2 Off Hours (6 bits)
        command |= (0 << (num_bits - 61))
        # Temperature (4 bits)
        command |= ((int(self._attr_target_temperature) - 15) << (num_bits - 70))
        bytes_if_set = [460, 1350]
        bytes_if_unset = [460, 950]

        packet_list = []

        for i in range(num_bits, -1, -1):
            mask = 1 << i
            if command & mask:
                packet_list.extend(bytes_if_set)
            else:
                packet_list.extend(bytes_if_unset)
        packet_list.extend([460, 109455])
        packet = pulses_to_data(packet_list)
        self._broadlink.send_data(packet)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        _LOGGER.info(f"User requested to change HVAC mode to: {hvac_mode}")
        self._attr_hvac_mode = hvac_mode
        self.send_command()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        _LOGGER.info(f"User requested to change Fan mode to: {fan_mode}")
        self._attr_fan_mode = fan_mode
        if self._attr_hvac_mode != HVACMode.OFF:
            self.send_command()
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target fan mode."""
        _LOGGER.info(f"User requested to change Swing mode to: {swing_mode}")
        self._attr_swing_mode = swing_mode
        if self._attr_hvac_mode != HVACMode.OFF:
            self.send_command()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temp = kwargs.get("temperature")
        if temp is None:
            return
        _LOGGER.info(f"User requested to change Temperature to: {temp}°C")
        self._attr_target_temperature = temp
        if self._attr_hvac_mode != HVACMode.OFF:
            self.send_command()
        self.async_write_ha_state()
