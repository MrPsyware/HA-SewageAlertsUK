"""Outfall status and source timestamps."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.util import dt as dt_util

from .entity import SewageEntity
from .watch import WatchEntity

DESCRIPTIONS = (
    ("status", "Status"),
    ("latest_start", "Latest discharge start"),
    ("latest_end", "Latest discharge end"),
    ("updated", "Source last updated"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("mode") == "upstream":
        async_add_entities(
            UpstreamSensor(entry.runtime_data, entry, key, name)
            for key, name in (
                ("status", "Upstream status"),
                ("active", "Reported active outfalls"),
                ("unknown", "Outfalls with unknown status"),
            )
        )
        return
    async_add_entities(
        SewageSensor(entry.runtime_data, entry, key, name) for key, name in DESCRIPTIONS
    )


class UpstreamSensor(WatchEntity, SensorEntity):
    def __init__(self, coordinator, entry, key, name):
        super().__init__(coordinator, entry, key)
        self.key = key
        self._attr_name = name
        if key == "status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ["discharging", "no_reported_discharges", "unknown"]

    @property
    def native_value(self):
        state = self.coordinator.data
        now = dt_util.utcnow()
        if self.key == "status":
            discharging = state.discharging(now)
            return (
                "unknown"
                if discharging is None
                else "discharging"
                if discharging
                else "no_reported_discharges"
            )
        active, unknown = state.counts(now)
        return active if self.key == "active" else unknown


class SewageSensor(SewageEntity, SensorEntity):
    def __init__(self, coordinator, entry, key, name):
        super().__init__(coordinator, entry, key)
        self.key = key
        self._attr_name = name
        if key == "status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [
                "discharging",
                "not_discharging",
                "offline",
                "unknown",
                "stale",
            ]
        else:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        if self.key == "status":
            return self.coordinator.data.effective_status(dt_util.utcnow())
        return getattr(self.coordinator.data, self.key)
