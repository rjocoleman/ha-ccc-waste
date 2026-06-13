"""Tests for the coordinator orchestration and error mapping."""

from __future__ import annotations

from datetime import date
import re
from typing import TYPE_CHECKING

import aiohttp
from aioresponses import aioresponses
from freezegun import freeze_time
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ccc_waste.api import (
    CCC_OVERRIDES_URL,
    CCC_PROPERTY_URL,
)
from custom_components.ccc_waste.const import (
    CONF_ADDRESS,
    CONF_RATING_UNIT_ID,
    DOMAIN,
)
from custom_components.ccc_waste.coordinator import CCCCoordinator
from tests.conftest import load_fixture

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PROPERTY_PATTERN = re.compile(rf"{re.escape(CCC_PROPERTY_URL)}\?.*")

FROZEN_NOW = "2026-06-13 00:00:00"


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="192837",
        data={CONF_RATING_UNIT_ID: 192837, CONF_ADDRESS: "110 Montreal Street"},
    )


def _coordinator(hass: HomeAssistant) -> CCCCoordinator:
    entry = _entry()
    entry.add_to_hass(hass)
    return CCCCoordinator(hass, entry)


@freeze_time(FROZEN_NOW)
async def test_update_happy_path(hass: HomeAssistant) -> None:
    """A successful fetch computes per-material results in Auckland time."""
    coordinator = _coordinator(hass)
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, body=load_fixture("getProperty.json"))
        mock.get(CCC_OVERRIDES_URL, body=load_fixture("overrides.json"))
        data = await coordinator._async_update_data()

    assert set(data.collections) == {"Garbage", "Recycle", "Organic"}
    assert data.collections["Garbage"].next_date == date(2026, 6, 23)
    assert data.collections["Organic"].next_date == date(2026, 6, 16)
    assert data.address == "110 Montreal Street"
    assert data.rating_unit_id == 192837


@freeze_time(FROZEN_NOW)
async def test_overrides_soft_fail(hass: HomeAssistant) -> None:
    """If the overrides feed fails, dates are still produced unadjusted."""
    coordinator = _coordinator(hass)
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, body=load_fixture("getProperty.json"))
        mock.get(CCC_OVERRIDES_URL, exception=aiohttp.ClientError("boom"))
        data = await coordinator._async_update_data()

    assert data.collections["Garbage"].next_date == date(2026, 6, 23)
    assert all(not c.temporary_change for c in data.collections.values())


@freeze_time(FROZEN_NOW)
async def test_connection_error_raises_update_failed(hass: HomeAssistant) -> None:
    """A property fetch transport error becomes UpdateFailed (transient)."""
    coordinator = _coordinator(hass)
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, exception=aiohttp.ClientError("boom"))
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@freeze_time(FROZEN_NOW)
async def test_no_kerbside_raises_config_entry_error(hass: HomeAssistant) -> None:
    """A property with no kerbside collection is a permanent config error."""
    coordinator = _coordinator(hass)
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, body=load_fixture("getProperty_no_kerbside.json"))
        with pytest.raises(ConfigEntryError):
            await coordinator._async_update_data()


@freeze_time(FROZEN_NOW)
async def test_parse_error_raises_update_failed(hass: HomeAssistant) -> None:
    """A malformed property payload becomes UpdateFailed."""
    coordinator = _coordinator(hass)
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, body=load_fixture("getProperty_malformed.json"))
        mock.get(CCC_OVERRIDES_URL, body=load_fixture("overrides.json"))
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
