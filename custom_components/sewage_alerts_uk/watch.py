"""Aggregate status for a configured set of connected upstream outfalls."""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .api import FeedError, StormOverflowClient
from .const import ATTRIBUTION, DOMAIN, POLL_INTERVAL


def site_key(site):
    return f"{site['provider']}:{site['site_id']}"


@dataclass
class WatchState:
    records: dict
    failed_companies: list[str]

    def counts(self, now):
        active = unknown = 0
        for outfall in self.records.values():
            status = outfall.effective_status(now) if outfall else "unknown"
            active += status == "discharging"
            unknown += status not in ("discharging", "not_discharging")
        return active, unknown

    def discharging(self, now):
        active, unknown = self.counts(now)
        if active:
            return True
        if unknown or not self.records:
            return None
        return False

    def latest_discharge(self):
        events = [
            record for record in self.records.values() if record and record.latest_start
        ]
        return max((record.latest_start for record in events), default=None)

    def latest_event_duration(self, now):
        events = [
            record for record in self.records.values() if record and record.latest_start
        ]
        if not events:
            return None
        latest = max(events, key=lambda record: record.latest_start)
        return latest.discharge_duration(now)


class WatchCoordinator(DataUpdateCoordinator[WatchState]):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=DOMAIN,
            config_entry=entry,
            update_interval=POLL_INTERVAL,
        )
        self.sites = entry.data["sites"]
        self.session = async_get_clientsession(hass)

    async def _async_update_data(self):
        groups = defaultdict(list)
        for site in self.sites:
            groups[site["provider"]].append(site)
        semaphore = asyncio.Semaphore(3)

        async def fetch(sites):
            async with semaphore:
                try:
                    data = await StormOverflowClient(
                        self.session, sites[0]["url"]
                    ).fetch(site_ids=[site["site_id"] for site in sites])
                    return {
                        site_key(site): data.get(site["site_id"]) for site in sites
                    }, []
                except FeedError:
                    return {site_key(site): None for site in sites}, [
                        sites[0]["company"]
                    ]

        responses = await asyncio.gather(*(fetch(sites) for sites in groups.values()))
        return WatchState(
            {key: value for records, _ in responses for key, value in records.items()},
            [company for _, failed in responses for company in failed],
        )


class WatchEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="Sewage Alerts UK",
            model=(
                "Coastal area watch"
                if entry.data.get("mode") == "coastal"
                else "Upstream river watch"
            ),
        )

    @property
    def extra_state_attributes(self):
        state = self.coordinator.data
        now = dt_util.utcnow()
        range_km = self.entry.data.get("range_km", self.entry.data.get("upstream_km"))
        return {
            "river": self.entry.data["river"],
            "latitude": self.entry.data["latitude"],
            "longitude": self.entry.data["longitude"],
            "range_km": range_km,
            "range_type": (
                "coastal_radius"
                if self.entry.data.get("mode") == "coastal"
                else "upstream_river_distance"
            ),
            "monitored_outfalls": len(self.coordinator.sites),
            "failed_companies": state.failed_companies,
            "outfalls": [
                {
                    "site_id": site["site_id"],
                    "company": site["company"],
                    "river": site["river"],
                    "distance_km": round(site["distance_m"] / 1000, 2),
                    "status": record.effective_status(now)
                    if (record := state.records.get(site_key(site)))
                    else "unavailable",
                    "last_discharge": record.latest_start.isoformat()
                    if record and record.latest_start
                    else None,
                    "discharge_duration_seconds": record.discharge_duration(now)
                    if record
                    else None,
                }
                for site in self.coordinator.sites
            ],
        }
