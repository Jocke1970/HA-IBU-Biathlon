"""Home Assistant IBU collector. YAML-configured research integration."""
from datetime import timedelta
from pathlib import Path
import logging

import voluptuous as vol
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval

from .collector import Collector

DOMAIN = "ibu_biathlon"
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Optional("season", default="2627"): cv.string,
        vol.Optional("api_key", default=""): cv.string,
        vol.Optional("min_delay", default=1.0): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
    }),
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    settings = config.get(DOMAIN)
    if settings is None:
        return True
    root = Path(hass.config.path("ibu_biathlon"))
    collector = Collector(async_get_clientsession(hass), root,
                          season=settings["season"], api_key=settings["api_key"],
                          delay=settings["min_delay"])
    hass.data[DOMAIN] = collector

    def start_cycle(_now=None):
        hass.async_create_task(collector.cycle())

    unsubscribe = async_track_time_interval(hass, start_cycle, timedelta(minutes=1))
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda _event: unsubscribe())
    start_cycle()
    _LOGGER.info("IBU collector initialized; data: %s", root)
    return True
