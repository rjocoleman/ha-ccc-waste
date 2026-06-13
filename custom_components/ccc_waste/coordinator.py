"""Data update coordinator for CCC kerbside collection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date  # noqa: TC003  (used at runtime by dt_util.now().date())
import logging
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import CCCApiClient
from .const import CONF_ADDRESS, CONF_RATING_UNIT_ID, DOMAIN, TIMEZONE, UPDATE_INTERVAL
from .exceptions import (
    CCCConnectionError,
    CCCError,
    CCCParseError,
    CCCPropertyNotFound,
)
from .schedule import compute_collections

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .models import CollectionResult

_LOGGER = logging.getLogger(__name__)

type CCCConfigEntry = ConfigEntry[CCCCoordinator]

_AUCKLAND = ZoneInfo(TIMEZONE)


@dataclass(frozen=True, slots=True)
class CCCData:
    """The coordinator's computed view of a property's collections."""

    rating_unit_id: int
    address: str
    latitude: float | None
    longitude: float | None
    collections: dict[str, CollectionResult]


class CCCCoordinator(DataUpdateCoordinator[CCCData]):
    """Fetches CCC data and computes the next collection per material."""

    config_entry: CCCConfigEntry

    def __init__(self, hass: HomeAssistant, entry: CCCConfigEntry) -> None:
        """Initialise the coordinator from a config entry."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            config_entry=entry,
        )
        self._client = CCCApiClient(async_get_clientsession(hass))
        self.rating_unit_id: int = entry.data[CONF_RATING_UNIT_ID]
        self.address: str = entry.data[CONF_ADDRESS]

    async def _async_update_data(self) -> CCCData:
        """Fetch the property and overrides, then compute collection dates."""
        try:
            prop = await self._client.async_fetch_property(self.rating_unit_id)
        except CCCPropertyNotFound as err:
            raise ConfigEntryError(str(err)) from err
        except (CCCConnectionError, CCCParseError) as err:
            raise UpdateFailed(str(err)) from err

        # The overrides feed is a soft dependency: degrade to unadjusted dates
        # rather than failing the whole update.
        try:
            overrides = await self._client.async_fetch_overrides()
        except CCCError as err:
            _LOGGER.warning("Could not fetch CCC date overrides: %s", err)
            overrides = []

        today: date = dt_util.now(_AUCKLAND).date()
        results = compute_collections(prop, overrides, today)

        return CCCData(
            rating_unit_id=prop.rating_unit_id,
            address=self.address,
            latitude=prop.latitude,
            longitude=prop.longitude,
            collections={result.material: result for result in results},
        )
