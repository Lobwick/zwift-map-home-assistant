"""Zwift Map: the Zwift route you are riding, live in Home Assistant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZwiftClient
from .const import DOMAIN
from .coordinator import ZwiftMapCoordinator
from .http import async_register_http
from .routes import RouteCatalogue

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type ZwiftMapConfigEntry = ConfigEntry[ZwiftMapCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ZwiftMapConfigEntry) -> bool:
    catalogue = await hass.async_add_executor_job(RouteCatalogue.load)
    client = ZwiftClient(
        async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = ZwiftMapCoordinator(hass, entry, client, catalogue)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await async_register_http(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZwiftMapConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unloaded
