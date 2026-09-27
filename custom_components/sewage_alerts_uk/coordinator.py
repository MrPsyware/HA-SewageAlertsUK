"""Fetch each configured outfall on a shared schedule for its entities."""

import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FeedError, Outfall, StormOverflowClient
from .const import CONF_SITE_ID, DOMAIN, POLL_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SewageCoordinator(DataUpdateCoordinator[Outfall]):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=POLL_INTERVAL,
        )
        self.site_id = entry.data[CONF_SITE_ID]
        self.client = StormOverflowClient(
            async_get_clientsession(hass), entry.data["url"]
        )

    async def _async_update_data(self) -> Outfall:
        try:
            outfalls = await self.client.fetch(self.site_id)
            if self.site_id not in outfalls:
                raise FeedError("Selected outfall is missing from the feed")
            return outfalls[self.site_id]
        except FeedError as err:
            raise UpdateFailed(str(err)) from err
