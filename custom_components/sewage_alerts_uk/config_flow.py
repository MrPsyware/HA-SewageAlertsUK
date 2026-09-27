"""Choose a company, search a river, then select an outfall."""

import json
from pathlib import Path

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import FeedError, StormOverflowClient
from .const import CONF_PROVIDER, CONF_SITE_ID, DOMAIN
from .location_flow import LocationFlowMixin


def _load_providers():
    return json.loads(Path(__file__).with_name("providers.json").read_text())


class SewageConfigFlow(LocationFlowMixin, config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.providers = None
        self.matches = {}
        self.provider = None

    async def _ensure_providers(self):
        if self.providers is None:
            self.providers = await self.hass.async_add_executor_job(_load_providers)

    async def async_step_manual(self, user_input=None):
        await self._ensure_providers()
        errors = {}
        if user_input is not None:
            self.provider = user_input[CONF_PROVIDER]
            term = user_input["search"].strip().casefold()
            if not term:
                errors["search"] = "empty_search"
            else:
                client = StormOverflowClient(
                    async_get_clientsession(self.hass),
                    self.providers[self.provider]["url"],
                )
                try:
                    outfalls = await client.fetch()
                except FeedError:
                    errors["base"] = "cannot_connect"
                else:
                    self.matches = {
                        key: outfall
                        for key, outfall in outfalls.items()
                        if term in outfall.river.casefold() or term in key.casefold()
                    }
                    if not self.matches:
                        errors["base"] = "no_results"
                    elif len(self.matches) > 250:
                        errors["base"] = "too_many_results"
                    else:
                        return await self.async_step_site()
        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": key, "label": value["name"]}
                                for key, value in self.providers.items()
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required("search"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_site(self, user_input=None):
        errors = {}
        if user_input is not None:
            site_id = user_input[CONF_SITE_ID]
            if site_id not in self.matches:
                errors["base"] = "invalid_site"
            else:
                await self.async_set_unique_id(f"{self.provider}_{site_id}")
                self._abort_if_unique_id_configured()
                outfall = self.matches[site_id]
                provider = self.providers[self.provider]
                return self.async_create_entry(
                    title=outfall.label,
                    data={
                        CONF_PROVIDER: self.provider,
                        CONF_SITE_ID: site_id,
                        "company": provider["name"],
                        "url": provider["url"],
                    },
                )
        options = []
        for key, outfall in sorted(
            self.matches.items(), key=lambda item: item[1].label
        ):
            label = outfall.label
            if outfall.latitude is not None and outfall.longitude is not None:
                label += f" ({outfall.latitude:.5f}, {outfall.longitude:.5f})"
            options.append({"value": key, "label": label})
        return self.async_show_form(
            step_id="site",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SITE_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
            errors=errors,
        )
