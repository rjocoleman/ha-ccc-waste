"""Tests for redacted diagnostics output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aioresponses import aioresponses
from freezegun import freeze_time

from custom_components.ccc_waste.const import CONF_ADDRESS, CONF_RATING_UNIT_ID
from custom_components.ccc_waste.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.conftest import mock_ccc_endpoints

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

FROZEN_NOW = "2026-06-13 00:00:00"


@freeze_time(FROZEN_NOW)
async def test_diagnostics_redacts_personal_data(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """Address, rating unit and coordinates are redacted; schedule is kept."""
    mock_entry.add_to_hass(hass)
    with aioresponses() as mock:
        mock_ccc_endpoints(mock)
        assert await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, mock_entry)

    assert diagnostics["entry"][CONF_ADDRESS] == "**REDACTED**"
    assert diagnostics["entry"][CONF_RATING_UNIT_ID] == "**REDACTED**"
    data = diagnostics["data"]
    assert data["address"] == "**REDACTED**"
    assert data["latitude"] == "**REDACTED**"
    # The non-identifying schedule survives redaction.
    assert data["collections"]["Garbage"]["next_date"] == "2026-06-23"
    assert data["collections"]["Garbage"]["collection_day"] == "Tuesday"
