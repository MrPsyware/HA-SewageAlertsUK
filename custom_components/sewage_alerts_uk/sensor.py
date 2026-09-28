"""Outfall status, event timestamps and durations."""

from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .entity import SewageEntity
from .watch import WatchEntity

DESCRIPTIONS = (
    ("status", "Status"),
    ("last_discharge", "Last discharge"),
    ("discharge_duration", "Discharge duration"),
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
                ("last_discharge", "Latest discharge"),
                ("discharge_duration", "Latest discharge duration"),
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
        elif key == "last_discharge":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key == "discharge_duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = "s"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.key == "discharge_duration":
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_refresh_duration, timedelta(minutes=1)
                )
            )

    async def _async_refresh_duration(self, _now):
        self.async_write_ha_state()

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
        if self.key == "last_discharge":
            return state.latest_discharge()
        if self.key == "discharge_duration":
            return state.latest_event_duration(now)
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
            ]
        elif key in ("last_discharge", "latest_start", "latest_end"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif key == "discharge_duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = "s"

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.key == "discharge_duration":
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_refresh_duration, timedelta(minutes=1)
                )
            )

    async def _async_refresh_duration(self, _now):
        self.async_write_ha_state()

    @property
    def native_value(self):
        if self.key == "status":
            return self.coordinator.data.effective_status(dt_util.utcnow())
        if self.key == "last_discharge":
            return self.coordinator.data.latest_start
        if self.key == "discharge_duration":
            return self.coordinator.data.discharge_duration(dt_util.utcnow())
        return getattr(self.coordinator.data, self.key)
