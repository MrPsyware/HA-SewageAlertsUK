"""Location-first configuration and confirmation of an upstream river watch."""

import asyncio
import hashlib
import math

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import FeedError, StormOverflowClient
from .location import load_network, lookup_postcode, lookup_town


def selection(options):
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )


class LocationFlowMixin:
    async def async_step_user(self, user_input=None):
        return self.async_show_menu(
            step_id="user",
            menu_options=["home", "postcode", "town", "coordinates", "manual"],
        )

    async def async_step_home(self, user_input=None):
        # Reuse the editable coordinate form, prefilled from HA's home location.
        return await self.async_step_coordinates(user_input)

    async def async_step_coordinates(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.location = {**user_input, "label": "River watch"}
            result = await self._find_rivers()
            if result is not None:
                return result
            errors["base"] = self.location_error
        return self.async_show_form(
            step_id="coordinates",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "latitude", default=self.hass.config.latitude
                    ): vol.All(vol.Coerce(float), vol.Range(min=49, max=56)),
                    vol.Required(
                        "longitude", default=self.hass.config.longitude
                    ): vol.All(vol.Coerce(float), vol.Range(min=-7, max=2)),
                }
            ),
            errors=errors,
        )

    async def async_step_postcode(self, user_input=None):
        return await self._lookup_location("postcode", lookup_postcode, user_input)

    async def async_step_town(self, user_input=None):
        return await self._lookup_location("town", lookup_town, user_input)

    async def _lookup_location(self, step, lookup, user_input):
        errors = {}
        if user_input is not None:
            term = user_input[step].strip()
            try:
                self.places = (
                    await lookup(async_get_clientsession(self.hass), term)
                    if term
                    else []
                )
            except FeedError:
                errors["base"] = "cannot_connect"
            else:
                if not self.places:
                    errors["base"] = "location_not_found"
                else:
                    return await self.async_step_place()
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema({vol.Required(step): str}),
            errors=errors,
        )

    async def async_step_place(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.location = self.places[int(user_input["place"])]
            result = await self._find_rivers()
            if result is not None:
                return result
            errors["base"] = self.location_error
        return self.async_show_form(
            step_id="place",
            data_schema=vol.Schema(
                {
                    vol.Required("place", default="0"): selection(
                        [
                            {
                                "value": str(index),
                                "label": f"{place['label']} ({place['latitude']:.5f}, {place['longitude']:.5f})",
                            }
                            for index, place in enumerate(self.places)
                        ]
                    ),
                }
            ),
            errors=errors,
        )

    async def _find_rivers(self):
        latitude, longitude = self.location["latitude"], self.location["longitude"]
        if not (49 <= latitude <= 56 and -7 <= longitude <= 2):
            self.location_error = "outside_coverage"
            return None
        return await self.async_step_area()

    async def async_step_area(self, user_input=None):
        """Choose a directed river watch or a geographic coastal watch."""
        if user_input is not None:
            if user_input["area_type"] == "coast":
                self.target_coords = (
                    self.location["latitude"],
                    self.location["longitude"],
                )
                return await self.async_step_coast()
            try:
                return await self._load_river_candidates()
            except FeedError:
                self.location_error = "cannot_connect"
                return self.async_show_form(
                    step_id="area",
                    data_schema=self._area_schema(),
                    errors={"base": self.location_error},
                )
        return self.async_show_form(step_id="area", data_schema=self._area_schema())

    @staticmethod
    def _area_schema():
        return vol.Schema(
            {
                vol.Required("area_type", default="river"): selection(
                    [
                        {"value": "river", "label": "River and upstream outfalls"},
                        {"value": "coast", "label": "Coastal area and beach outfalls"},
                    ]
                )
            }
        )

    async def _load_river_candidates(self):
        latitude, longitude = self.location["latitude"], self.location["longitude"]
        try:
            self.network = await load_network(
                self.hass, async_get_clientsession(self.hass), latitude, longitude, 5000
            )
            candidates = await self.hass.async_add_executor_job(
                self.network.nearest, latitude, longitude, 30
            )
            self.rivers = {
                snap.link.id: snap
                for snap in candidates
                if snap.link.routable and snap.link.form == "inlandRiver"
            }
        except FeedError:
            self.location_error = "cannot_connect"
            return None
        if not self.rivers:
            raise FeedError("No supported river found")
        return await self.async_step_river()

    async def async_step_coast(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.range_km = user_input["coastal_radius_km"]
            self.coast_name = self.location.get("label", "Coastal area")
            try:
                await self._discover_coastal()
            except FeedError:
                errors["base"] = "discovery_failed"
            else:
                if not self.sites:
                    errors["base"] = "no_coastal_outfalls"
                elif len(self.sites) > 100:
                    errors["base"] = "too_many_coastal_outfalls"
                else:
                    return await self.async_step_confirm()
        return self.async_show_form(
            step_id="coast",
            data_schema=vol.Schema(
                {
                    vol.Required("coastal_radius_km", default=10): vol.All(
                        vol.Coerce(float), vol.Range(min=1, max=25)
                    )
                }
            ),
            errors=errors,
        )

    async def _discover_coastal(self):
        session = async_get_clientsession(self.hass)
        latitude, longitude = self.target_coords
        radius = self.range_km * 1000
        await self._ensure_providers()
        semaphore = asyncio.Semaphore(3)

        async def fetch(key, provider):
            async with semaphore:
                records = await StormOverflowClient(session, provider["url"]).fetch(
                    center=(latitude, longitude), radius=radius
                )
                return key, records

        responses = await asyncio.gather(
            *(fetch(key, provider) for key, provider in self.providers.items()),
            return_exceptions=True,
        )
        if any(isinstance(response, BaseException) for response in responses):
            raise FeedError(
                "Could not check all water companies; discovery is incomplete"
            )
        self.sites = []
        for provider, records in responses:
            for site_id, data in records.items():
                if data.latitude is None or data.longitude is None:
                    continue
                distance = self._distance_m(
                    latitude, longitude, data.latitude, data.longitude
                )
                if distance <= radius:
                    self.sites.append(
                        {
                            "provider": provider,
                            "site_id": site_id,
                            "river": data.river,
                            "distance_m": round(distance, 1),
                            "company": self.providers[provider]["name"],
                            "url": self.providers[provider]["url"],
                            "latitude": data.latitude,
                            "longitude": data.longitude,
                        }
                    )
        self.sites.sort(key=lambda site: site["distance_m"])

    @staticmethod
    def _distance_m(lat1, lon1, lat2, lon2):
        radius = 6371008.8
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return 2 * radius * math.asin(math.sqrt(a))

    async def async_step_river(self, user_input=None):
        errors = {}
        if user_input is not None:
            selected = self.rivers[user_input["river"]]
            self.range_km = user_input["upstream_km"]
            self.river_name = selected.link.name
            self.target_coords = self.network.unproject(selected.point)
            try:
                await self._discover_upstream(selected.link.id)
            except FeedError:
                errors["base"] = "discovery_failed"
            else:
                if not self.sites:
                    errors["base"] = "no_upstream_outfalls"
                elif len(self.sites) > 100:
                    errors["base"] = "too_many_outfalls"
                else:
                    return await self.async_step_confirm()
        options = []
        for key, snap in self.rivers.items():
            latitude, longitude = self.network.unproject(snap.point)
            options.append(
                {
                    "value": key,
                    "label": f"{snap.link.name} — {snap.distance / 1000:.2f} km away ({latitude:.5f}, {longitude:.5f})",
                }
            )
        return self.async_show_form(
            step_id="river",
            data_schema=vol.Schema(
                {
                    vol.Required("river", default=next(iter(self.rivers))): selection(
                        options
                    ),
                    vol.Required("upstream_km", default=10): vol.All(
                        vol.Coerce(float), vol.Range(min=1, max=25)
                    ),
                }
            ),
            errors=errors,
        )

    async def _discover_upstream(self, link_id):
        session = async_get_clientsession(self.hass)
        latitude, longitude = self.target_coords
        # Extra 1 km covers snapping and small projection differences at the edge.
        radius = self.range_km * 1000 + 1000
        network = await load_network(self.hass, session, latitude, longitude, radius)
        if link_id not in network.links:
            raise FeedError("Selected river section disappeared")
        target = network.snap(
            network.links[link_id], network.project(latitude, longitude)
        )
        await self._ensure_providers()
        semaphore = asyncio.Semaphore(3)

        async def fetch(key, provider):
            async with semaphore:
                records = await StormOverflowClient(session, provider["url"]).fetch(
                    center=(latitude, longitude), radius=radius
                )
                return key, records

        responses = await asyncio.gather(
            *(fetch(key, provider) for key, provider in self.providers.items()),
            return_exceptions=True,
        )
        if any(isinstance(response, BaseException) for response in responses):
            raise FeedError(
                "Could not check all water companies; discovery is incomplete"
            )
        records = {
            f"{provider}:{site_id}": outfall
            for provider, outfalls in responses
            for site_id, outfall in outfalls.items()
        }
        matches = await self.hass.async_add_executor_job(
            network.match_outfalls, records, target, self.range_km * 1000
        )
        self.sites = []
        for key, distance in sorted(matches.items(), key=lambda item: item[1]):
            provider, site_id = key.split(":", 1)
            data = records[key]
            self.sites.append(
                {
                    "provider": provider,
                    "site_id": site_id,
                    "river": data.river,
                    "distance_m": distance,
                    "company": self.providers[provider]["name"],
                    "url": self.providers[provider]["url"],
                    "latitude": data.latitude,
                    "longitude": data.longitude,
                }
            )

    async def async_step_confirm(self, user_input=None):
        watch_name = getattr(self, "river_name", None) or getattr(
            self, "coast_name", "Coastal area"
        )
        if user_input is not None:
            latitude, longitude = self.target_coords
            mode = "coastal" if hasattr(self, "coast_name") else "upstream"
            identity = f"{mode}:{latitude:.5f}:{longitude:.5f}:{self.range_km:g}"
            await self.async_set_unique_id(
                "watch_" + hashlib.sha256(identity.encode()).hexdigest()[:20]
            )
            self._abort_if_unique_id_configured()
            title = (
                f"{self.coast_name} coastal watch"
                if mode == "coastal"
                else f"{self.river_name} upstream"
            )
            data = {
                "mode": mode,
                "latitude": latitude,
                "longitude": longitude,
                "range_km": self.range_km,
                "river": watch_name,
                "sites": self.sites,
            }
            return self.async_create_entry(
                title=title,
                data=data,
            )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "river": watch_name,
                "range": f"{self.range_km:g}",
                "latitude": f"{self.target_coords[0]:.5f}",
                "longitude": f"{self.target_coords[1]:.5f}",
                "count": str(len(self.sites)),
                "outfalls": "\n".join(
                    f"- {site['company']}: {site['site_id']} — {site['river']} ({site['distance_m'] / 1000:.2f} km away)"
                    for site in self.sites
                ),
            },
        )
