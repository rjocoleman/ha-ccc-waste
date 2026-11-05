"""Tests for the HA-free CCC API client."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING

import aiohttp
import pytest

from custom_components.ccc_waste.api import (
    CCC_OVERRIDES_URL,
    CCC_PROPERTY_URL,
    CCC_SUGGEST_URL,
    CCCApiClient,
)
from custom_components.ccc_waste.exceptions import (
    CCCAddressNotFound,
    CCCConnectionError,
    CCCParseError,
    CCCPropertyNotFound,
)
from tests.conftest import load_fixture

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )


@pytest.fixture
async def client(
    aioclient_mock: AiohttpClientMocker,
) -> AsyncIterator[CCCApiClient]:
    """A client backed by a session bound to the HTTP mocker."""
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield CCCApiClient(session)
    await session.close()


async def test_suggest_returns_addresses(
    client: CCCApiClient,
    suggest_payload: object,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Object-keyed suggest payload parses into addresses."""
    aioclient_mock.get(CCC_SUGGEST_URL, json=suggest_payload)
    results = await client.async_suggest_addresses("110 Montreal")

    assert len(results) == 3
    first = results[0]
    assert first.rating_unit_id == 192837
    assert first.full_address == "110 Montreal Street, Sydenham, Christchurch 8023"


async def test_suggest_parses_array_shape(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A true-array suggest payload is also accepted (defensive)."""
    payload = [
        {
            "StreetAddressID": 1,
            "FullStreetAddress": "1 Test Street, Sydenham, Christchurch 8023",
            "RatingUnitID": 42,
        }
    ]
    aioclient_mock.get(CCC_SUGGEST_URL, json=payload)
    results = await client.async_suggest_addresses("1 Test")

    assert len(results) == 1
    assert results[0].rating_unit_id == 42


async def test_suggest_empty_raises_not_found(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """An empty suggest result raises CCCAddressNotFound."""
    aioclient_mock.get(CCC_SUGGEST_URL, json={})
    with pytest.raises(CCCAddressNotFound):
        await client.async_suggest_addresses("nowhere")


async def test_suggest_connection_error(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Transport errors surface as CCCConnectionError."""
    aioclient_mock.get(CCC_SUGGEST_URL, exc=aiohttp.ClientError("boom"))
    with pytest.raises(CCCConnectionError):
        await client.async_suggest_addresses("110 Montreal")


async def test_fetch_property_happy(
    client: CCCApiClient,
    property_payload: object,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """getProperty parses containers, routes and collections."""
    aioclient_mock.get(CCC_PROPERTY_URL, json=property_payload)
    prop = await client.async_fetch_property(192837)

    assert prop.rating_unit_id == 192837
    assert prop.latitude == pytest.approx(-43.54612)
    assert {c.material for c in prop.containers} == {"Garbage", "Recycle", "Organic"}
    assert all(c.status == "Active" for c in prop.containers)
    # Six collection rows are parsed verbatim; filtering happens later.
    assert len(prop.collections) == 6
    garbage = next(
        c
        for c in prop.collections
        if c.material == "Garbage" and c.pick_up_group == "204"
    )
    assert garbage.next_planned_date == date(2026, 6, 10)
    assert garbage.next_planned_date_app == date(2026, 6, 23)
    assert garbage.out_of_date is False


async def test_fetch_property_no_kerbside_raises(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A property with no kerbside collection raises a clean error."""
    payload = {"id": "305512", "address": "793 McLeans Island Road Christchurch"}
    aioclient_mock.get(CCC_PROPERTY_URL, json=payload)
    with pytest.raises(CCCPropertyNotFound):
        await client.async_fetch_property(305512)


async def test_fetch_property_malformed_raises_parse_error(
    client: CCCApiClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Structural surprises raise CCCParseError, not a bare KeyError/TypeError."""
    aioclient_mock.get(
        CCC_PROPERTY_URL, text=load_fixture("getProperty_malformed.json")
    )
    with pytest.raises(CCCParseError):
        await client.async_fetch_property(192837)


async def test_fetch_property_invalid_json_raises_parse_error(
    client: CCCApiClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Non-JSON body raises CCCParseError."""
    aioclient_mock.get(CCC_PROPERTY_URL, text="<html>nope</html>")
    with pytest.raises(CCCParseError):
        await client.async_fetch_property(192837)


async def test_fetch_property_connection_error(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Transport errors during getProperty surface as CCCConnectionError."""
    aioclient_mock.get(CCC_PROPERTY_URL, exc=aiohttp.ClientError("boom"))
    with pytest.raises(CCCConnectionError):
        await client.async_fetch_property(192837)


async def test_fetch_overrides_parses(
    client: CCCApiClient,
    overrides_payload: object,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """The overrides feed parses into typed records."""
    aioclient_mock.get(CCC_OVERRIDES_URL, json=overrides_payload)
    overrides = await client.async_fetch_overrides()

    assert len(overrides) == 5
    xmas = next(o for o in overrides if o.original_date == date(2026, 12, 25))
    assert xmas.new_date == date(2026, 12, 26)
    assert xmas.expired is False


async def test_fetch_overrides_connection_error(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Override transport errors raise so the coordinator can soft-fail."""
    aioclient_mock.get(CCC_OVERRIDES_URL, exc=aiohttp.ClientError("boom"))
    with pytest.raises(CCCConnectionError):
        await client.async_fetch_overrides()


async def test_suggest_non_collection_payload_raises(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A suggest payload that is neither list nor object raises CCCParseError."""
    aioclient_mock.get(CCC_SUGGEST_URL, json="unexpected")
    with pytest.raises(CCCParseError):
        await client.async_suggest_addresses("110 Montreal")


async def test_suggest_skips_incomplete_entries(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Non-dict and key-less entries are skipped, not fatal."""
    payload = {
        "0": "garbage",
        "1": {"RatingUnitID": 5},
        "2": {
            "RatingUnitID": 7,
            "FullStreetAddress": "7 Real Street, Sydenham, Christchurch 8023",
        },
    }
    aioclient_mock.get(CCC_SUGGEST_URL, json=payload)
    results = await client.async_suggest_addresses("real")

    assert [a.rating_unit_id for a in results] == [7]


async def test_suggest_non_numeric_id_raises(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A non-numeric RatingUnitID is a structural error."""
    payload = {
        "0": {"RatingUnitID": "not-a-number", "FullStreetAddress": "1 X St"},
    }
    aioclient_mock.get(CCC_SUGGEST_URL, json=payload)
    with pytest.raises(CCCParseError):
        await client.async_suggest_addresses("x")


async def test_fetch_property_non_object_raises(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A getProperty payload that is not an object raises CCCParseError."""
    aioclient_mock.get(CCC_PROPERTY_URL, json=[1, 2, 3])
    with pytest.raises(CCCParseError):
        await client.async_fetch_property(192837)


async def test_fetch_property_coerces_empty_dates_and_bool_flags(
    client: CCCApiClient,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Empty date strings become None and real JSON booleans are honoured."""
    payload = {
        "id": "192837",
        "address": "110 Montreal Street Sydenham Christchurch",
        "bins": {
            "containers": [],
            "routes": [],
            "collections": [
                {
                    "material": "Garbage",
                    "pick_up_group": "204",
                    "next_planned_date": "",
                    "next_planned_date_app": "2026-06-23",
                    "out_of_date": True,
                }
            ],
        },
    }
    aioclient_mock.get(CCC_PROPERTY_URL, json=payload)
    prop = await client.async_fetch_property(192837)

    row = prop.collections[0]
    assert row.next_planned_date is None
    assert row.next_planned_date_app == date(2026, 6, 23)
    assert row.out_of_date is True


async def test_fetch_overrides_non_list_raises(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """An overrides payload that is not a list raises CCCParseError."""
    aioclient_mock.get(CCC_OVERRIDES_URL, json={"not": "a list"})
    with pytest.raises(CCCParseError):
        await client.async_fetch_overrides()


async def test_fetch_overrides_malformed_row_raises(
    client: CCCApiClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A row with a missing/invalid date raises CCCParseError."""
    aioclient_mock.get(CCC_OVERRIDES_URL, json=[{"ID": 1, "Title": "Bad"}])
    with pytest.raises(CCCParseError):
        await client.async_fetch_overrides()
