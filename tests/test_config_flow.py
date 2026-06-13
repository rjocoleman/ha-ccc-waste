"""Tests for the address-lookup config flow."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import aiohttp
from aioresponses import aioresponses
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ccc_waste.api import CCC_SUGGEST_URL
from custom_components.ccc_waste.config_flow import CCCConfigFlow
from custom_components.ccc_waste.const import (
    CONF_ADDRESS,
    CONF_RATING_UNIT_ID,
    DOMAIN,
)
from custom_components.ccc_waste.models import CCCAddress
from tests.conftest import load_fixture

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

SUGGEST_PATTERN = re.compile(rf"{re.escape(CCC_SUGGEST_URL)}\?.*")

_SINGLE_RESULT = """
{"0": {"StreetAddressID": 1, "FullStreetAddress": "110 Montreal Street, Sydenham, Christchurch 8023", "RatingUnitID": 192837}}
"""


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_single_result_creates_entry(hass: HomeAssistant) -> None:
    """A unique match skips the picker and creates the entry."""
    flow_id = await _start(hass)
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, body=_SINGLE_RESULT)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_ADDRESS: "110 Montreal"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_ADDRESS: "110 Montreal Street, Sydenham, Christchurch 8023",
        CONF_RATING_UNIT_ID: 192837,
    }
    assert result["result"].unique_id == "192837"


async def test_multiple_results_then_select(hass: HomeAssistant) -> None:
    """Several matches show a picker, then create the chosen entry."""
    flow_id = await _start(hass)
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, body=load_fixture("suggest.json"))
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_ADDRESS: "Montreal"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select"

    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_ADDRESS: "192838"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RATING_UNIT_ID] == 192838


async def test_address_not_found(hass: HomeAssistant) -> None:
    """An empty lookup reshows the form with an error."""
    flow_id = await _start(hass)
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, body="{}")
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_ADDRESS: "nowhere"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "address_not_found"}


async def test_cannot_connect(hass: HomeAssistant) -> None:
    """A transport error reshows the form with a connection error."""
    flow_id = await _start(hass)
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, exception=aiohttp.ClientError("boom"))
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_ADDRESS: "110 Montreal"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_aborts(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """A second entry for the same rating unit aborts."""
    mock_entry.add_to_hass(hass)
    flow_id = await _start(hass)
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, body=_SINGLE_RESULT)
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_ADDRESS: "110 Montreal"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_entry(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """Reconfigure looks up a new address and updates the entry in place."""
    mock_entry.add_to_hass(hass)
    result = await mock_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    new_result = """
    {"0": {"StreetAddressID": 9, "FullStreetAddress": "200 Colombo Street, Sydenham, Christchurch 8023", "RatingUnitID": 222111}}
    """
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, body=new_result)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "200 Colombo"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_entry.data[CONF_RATING_UNIT_ID] == 222111
    assert mock_entry.unique_id == "222111"


async def test_reconfigure_to_other_existing_entry_aborts(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """Reconfiguring onto a property already held by another entry aborts."""
    mock_entry.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="222111",
        data={CONF_RATING_UNIT_ID: 222111, CONF_ADDRESS: "200 Colombo Street"},
    )
    other.add_to_hass(hass)

    result = await mock_entry.start_reconfigure_flow(hass)
    clash = """
    {"0": {"StreetAddressID": 9, "FullStreetAddress": "200 Colombo Street, Sydenham, Christchurch 8023", "RatingUnitID": 222111}}
    """
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, body=clash)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "200 Colombo"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    # The original entry is untouched.
    assert mock_entry.data[CONF_RATING_UNIT_ID] == 192837


async def test_select_unknown_selection_aborts(hass: HomeAssistant) -> None:
    """A selection matching no stored suggestion aborts instead of crashing.

    The list selector normally constrains input to its options, so this guards
    against anomalous internal state rather than ordinary UI use.
    """
    flow = CCCConfigFlow()
    flow.hass = hass
    flow._suggestions = [
        CCCAddress(rating_unit_id=192837, full_address="110 Montreal Street")
    ]

    result = await flow.async_step_select({CONF_ADDRESS: "000000"})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"
