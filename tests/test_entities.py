"""Tests for the sensor and calendar entities."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from aioresponses import aioresponses
from freezegun import freeze_time

from custom_components.ccc_waste.const import TIMEZONE
from custom_components.ccc_waste.coordinator import CCCData
from custom_components.ccc_waste.models import CollectionResult
from custom_components.ccc_waste.sensor import CCCBinSensor, CCCNextCollectionSensor
from tests.conftest import mock_ccc_endpoints

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

FROZEN_NOW = "2026-06-13 00:00:00"
_AUCKLAND = ZoneInfo(TIMEZONE)

_DEVICE = "110_montreal_street_sydenham_christchurch_8023"
RUBBISH = f"sensor.{_DEVICE}_rubbish"
ORGANIC = f"sensor.{_DEVICE}_organic"
NEXT = f"sensor.{_DEVICE}_next_collection"
CALENDAR = f"calendar.{_DEVICE}_collection_calendar"


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    with aioresponses() as mock:
        mock_ccc_endpoints(mock)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


@freeze_time(FROZEN_NOW)
async def test_sensor_state_and_attributes(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """The rubbish sensor reports an Auckland-midnight timestamp and days_until."""
    await _setup(hass, mock_entry)

    state = hass.states.get(RUBBISH)
    assert state is not None
    # HA stores timestamps in UTC; compare the instant, not its representation.
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 6, 23, tzinfo=_AUCKLAND
    )
    assert state.attributes["days_until"] == 10
    assert state.attributes["collection_day"] == "Tuesday"
    assert state.attributes["container_type"] == "140L WB"
    assert state.attributes["temporary_change"] is False


@freeze_time(FROZEN_NOW)
async def test_weekly_sensor_rolls_to_nearest(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """Organic (weekly) rolls to the nearest upcoming Tuesday."""
    await _setup(hass, mock_entry)

    state = hass.states.get(ORGANIC)
    assert state is not None
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 6, 16, tzinfo=_AUCKLAND
    )


@freeze_time(FROZEN_NOW)
async def test_next_collection_summary(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """The summary sensor reports the soonest date and every bin sharing it."""
    await _setup(hass, mock_entry)

    state = hass.states.get(NEXT)
    assert state is not None
    assert datetime.fromisoformat(state.state) == datetime(
        2026, 6, 16, tzinfo=_AUCKLAND
    )
    assert state.attributes["days_until"] == 3
    # In this fixture Organic (16 Jun) is soonest; Recycling/Rubbish are 23 Jun.
    assert state.attributes["bins"] == ["Organic"]
    assert state.attributes["collection_day"] == "Tuesday"


@freeze_time(FROZEN_NOW)
async def test_next_collection_groups_same_day(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """When several bins share the soonest date, all are listed."""
    await _setup(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    data = coordinator.data
    coordinator.async_set_updated_data(
        CCCData(
            rating_unit_id=data.rating_unit_id,
            address=data.address,
            latitude=data.latitude,
            longitude=data.longitude,
            collections={
                "Organic": CollectionResult(
                    "Organic", date(2026, 6, 16), False, None, "Tuesday", "80L WB"
                ),
                "Recycle": CollectionResult(
                    "Recycle", date(2026, 6, 16), False, None, "Tuesday", "240L WB"
                ),
                "Garbage": CollectionResult(
                    "Garbage", date(2026, 6, 23), False, None, "Tuesday", "140L WB"
                ),
            },
        )
    )
    await hass.async_block_till_done()

    state = hass.states.get(NEXT)
    assert state is not None
    assert state.attributes["bins"] == ["Organic", "Recycling"]


@freeze_time(FROZEN_NOW)
async def test_calendar_event_is_soonest(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """The calendar's current event is the soonest collection (Organic, 16 Jun)."""
    await _setup(hass, mock_entry)

    state = hass.states.get(CALENDAR)
    assert state is not None
    assert state.attributes["message"] == "Organic collection"


@freeze_time(FROZEN_NOW)
async def test_calendar_get_events_projects_window(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """async_get_events projects each material forward across the window."""
    await _setup(hass, mock_entry)
    component = hass.data["calendar"]
    entity = component.get_entity(CALENDAR)
    assert entity is not None

    # Window starts after the first organic occurrence (16 Jun) so it is skipped.
    start = datetime(2026, 6, 20, tzinfo=_AUCKLAND)
    end = datetime(2026, 7, 20, tzinfo=_AUCKLAND)
    events = await entity.async_get_events(hass, start, end)

    summaries = sorted({event.summary for event in events})
    assert summaries == [
        "Organic collection",
        "Recycling collection",
        "Rubbish collection",
    ]
    organic_dates = sorted(e.start for e in events if e.summary == "Organic collection")
    assert organic_dates[0] == date(2026, 6, 23)  # 16 Jun fell outside the window


@freeze_time(FROZEN_NOW)
async def test_sensor_unavailable_when_material_disappears(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """A material absent from a later update makes its sensor unavailable."""
    await _setup(hass, mock_entry)
    coordinator = mock_entry.runtime_data
    data = coordinator.data
    coordinator.async_set_updated_data(
        CCCData(
            rating_unit_id=data.rating_unit_id,
            address=data.address,
            latitude=data.latitude,
            longitude=data.longitude,
            collections={"Garbage": data.collections["Garbage"]},
        )
    )
    await hass.async_block_till_done()

    organic = hass.states.get(ORGANIC)
    assert organic is not None
    assert organic.state == "unavailable"


@freeze_time(FROZEN_NOW)
async def test_calendar_empty_when_no_materials(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """A property whose rows are all non-kerbside yields no sensors and no event."""
    mock_entry.add_to_hass(hass)
    with aioresponses() as mock:
        mock_ccc_endpoints(mock, property_fixture="getProperty_all_excluded.json")
        assert await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.async_entity_ids("sensor") == []
    state = hass.states.get(CALENDAR)
    assert state is not None
    assert state.state == "off"
    assert "message" not in state.attributes


@freeze_time(FROZEN_NOW)
async def test_sensor_properties_none_for_absent_material(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """A sensor whose material is missing reports no value and is unavailable."""
    await _setup(hass, mock_entry)
    sensor = CCCBinSensor(mock_entry.runtime_data, "Nonexistent")

    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None
    assert sensor.available is False


@freeze_time(FROZEN_NOW)
async def test_next_collection_unavailable_when_empty(
    hass: HomeAssistant, mock_entry: MockConfigEntry
) -> None:
    """With no collections, the summary sensor reports nothing and is unavailable."""
    mock_entry.add_to_hass(hass)
    with aioresponses() as mock:
        mock_ccc_endpoints(mock, property_fixture="getProperty_all_excluded.json")
        assert await hass.config_entries.async_setup(mock_entry.entry_id)
        await hass.async_block_till_done()

    sensor = CCCNextCollectionSensor(mock_entry.runtime_data)
    assert sensor._soonest == []
    assert sensor.native_value is None
    assert sensor.extra_state_attributes is None
    assert sensor.available is False
