"""Common outfall device identity and attributes."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, CONF_PROVIDER, DOMAIN


class SewageEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        identity = f"{entry.data[CONF_PROVIDER]}_{coordinator.site_id}"
        self._attr_unique_id = f"{identity}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name=entry.title,
            manufacturer=entry.data["company"],
            model="Storm overflow monitor",
        )

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        return {
            "site_id": data.site_id,
            "receiving_watercourse": data.river,
            "latitude": data.latitude,
            "longitude": data.longitude,
        }
