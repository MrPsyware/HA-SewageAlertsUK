"""Map entities for the monitored sewage outfalls."""

from datetime import timedelta

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTRIBUTION, DOMAIN
from .watch import site_key

SOURCE = DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    """Add one map marker for every outfall in this watch."""
    coordinator = entry.runtime_data
    if entry.data.get("mode") in ("upstream", "coastal"):
        sites = coordinator.sites
    else:
        sites = [
            {
                "site_id": entry.data["site_id"],
                "provider": entry.data["provider"],
                "company": entry.data["company"],
                "river": coordinator.data.river,
                "distance_m": None,
            }
        ]
    async_add_entities(
        OutfallLocation(coordinator, entry, site) for site in sites
    )


class OutfallLocation(CoordinatorEntity, GeolocationEvent):
    """A persistent map marker for a configured outfall."""

    _attr_attribution = ATTRIBUTION
    _attr_source = SOURCE
    _attr_icon = "mdi:pipe-disconnected"

    def __init__(self, coordinator, entry, site):
        super().__init__(coordinator)
        self.entry = entry
        self.site = site
        self.site_id = site["site_id"]
        self._attr_unique_id = (
            f"{getattr(entry, 'unique_id', entry.entry_id)}_map_{self.site_id}"
        )
        self._attr_name = f"{site['company']} {self.site_id}"
        self._attr_device_info = None

    def _record(self):
        if hasattr(self.coordinator.data, "records"):
            return self.coordinator.data.records.get(site_key(self.site))
        data = self.coordinator.data
        return data if data and data.site_id == self.site_id else None

    @property
    def latitude(self):
        record = self._record()
        return record.latitude if record and record.latitude is not None else self.site.get("latitude")

    @property
    def longitude(self):
        record = self._record()
        return record.longitude if record and record.longitude is not None else self.site.get("longitude")

    @property
    def distance(self):
        distance_m = self.site.get("distance_m")
        return round(distance_m / 1000, 2) if distance_m is not None else None

    @property
    def extra_state_attributes(self):
        record = self._record()
        now = dt_util.utcnow()
        status = record.effective_status(now) if record else "unavailable"
        contamination_until = None
        if record:
            if record.status == "discharging":
                contamination_until = now + timedelta(
                    hours=float(self.entry.data.get("contamination_hours", 96))
                )
            elif record.latest_end:
                contamination_until = record.latest_end + timedelta(
                    hours=float(self.entry.data.get("contamination_hours", 96))
                )
        return {
            "site_id": self.site_id,
            "company": self.site["company"],
            "receiving_watercourse": (
                record.river if record and record.river else self.site.get("river", "")
            ),
            "status": status,
            "last_discharge": record.latest_start if record else None,
            "latest_end": record.latest_end if record else None,
            "discharge_duration_seconds": record.discharge_duration(now)
            if record
            else None,
            "possible_contamination": bool(
                contamination_until and contamination_until > now
            ),
            "contamination_until": contamination_until,
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_refresh_duration, timedelta(minutes=1)
            )
        )

    async def _async_refresh_duration(self, _now):
        self.async_write_ha_state()
