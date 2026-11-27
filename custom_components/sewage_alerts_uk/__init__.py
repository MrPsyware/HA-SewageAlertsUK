"""Sewage Alerts UK custom integration."""

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import SewageCoordinator
from .watch import WatchCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.GEO_LOCATION]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the bundled dashboard card once per Home Assistant startup."""
    card_name = "sewage-alerts-uk-card.js"
    card_path = Path(__file__).parent / "frontend" / card_name
    await hass.http.async_register_static_paths(
        [StaticPathConfig(f"/{DOMAIN}/{card_name}", str(card_path), False)]
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = (
        WatchCoordinator(hass, entry)
        if entry.data.get("mode") in ("upstream", "coastal")
        else SewageCoordinator(hass, entry)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
