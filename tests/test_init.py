"""Tests for setup, unload and setup-failure handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
from freezegun import freeze_time
from homeassistant.config_entries import ConfigEntryState

from custom_components.ccc_waste.api import CCC_PROPERTY_URL
from tests.conftest import load_fixture, mock_ccc_endpoints

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

FROZEN_NOW = "2026-06-13 00:00:00"


@freeze_time(FROZEN_NOW)
async def test_setup_and_unload(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A healthy entry loads its platforms and unloads cleanly."""
    mock_entry.add_to_hass(hass)
    mock_ccc_endpoints(aioclient_mock)
    assert await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.LOADED
    # Three material sensors + next-collection summary, plus one calendar.
    assert len(hass.states.async_entity_ids("sensor")) == 4
    assert len(hass.states.async_entity_ids("calendar")) == 1

    assert await hass.config_entries.async_unload(mock_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_entry.state is ConfigEntryState.NOT_LOADED


@freeze_time(FROZEN_NOW)
async def test_setup_retry_on_connection_error(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A connection error during first refresh defers setup for retry."""
    mock_entry.add_to_hass(hass)
    aioclient_mock.get(CCC_PROPERTY_URL, exc=aiohttp.ClientError("boom"))
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.SETUP_RETRY


@freeze_time(FROZEN_NOW)
async def test_setup_error_when_no_kerbside(
    hass: HomeAssistant,
    mock_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """A property with no kerbside collection fails setup permanently."""
    mock_entry.add_to_hass(hass)
    aioclient_mock.get(
        CCC_PROPERTY_URL,
        text=load_fixture("getProperty_no_kerbside.json"),
    )
    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_entry.state is ConfigEntryState.SETUP_ERROR
