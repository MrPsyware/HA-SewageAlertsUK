"""An automation-friendly indicator that never interprets missing data as off."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.util import dt as dt_util

from .entity import SewageEntity
from .watch import WatchEntity


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("mode") == "upstream":
        async_add_entities(
            [UpstreamDischargingSensor(entry.runtime_data, entry, "discharging")]
        )
        return
    async_add_entities([DischargingSensor(entry.runtime_data, entry, "discharging")])


class UpstreamDischargingSensor(WatchEntity, BinarySensorEntity):
    _attr_name = "Upstream discharging"
    _attr_icon = "mdi:pipe-leak"

    @property
    def is_on(self):
        return self.coordinator.data.discharging(dt_util.utcnow())


class DischargingSensor(SewageEntity, BinarySensorEntity):
    _attr_name = "Discharging"
    _attr_icon = "mdi:pipe-leak"

    @property
    def is_on(self):
        status = self.coordinator.data.effective_status(dt_util.utcnow())
        if status in ("discharging", "not_discharging"):
            return status == "discharging"
        return None
