"""Tests for the HA-free CCC API client."""

from __future__ import annotations

from datetime import date
import re
from typing import TYPE_CHECKING

import aiohttp
from aioresponses import aioresponses
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

SUGGEST_PATTERN = re.compile(rf"{re.escape(CCC_SUGGEST_URL)}\?.*")
PROPERTY_PATTERN = re.compile(rf"{re.escape(CCC_PROPERTY_URL)}\?.*")


@pytest.fixture
async def client() -> AsyncIterator[CCCApiClient]:
    """A client backed by a real session (HTTP is mocked by aioresponses)."""
    async with aiohttp.ClientSession() as session:
        yield CCCApiClient(session)


async def test_suggest_returns_addresses(
    client: CCCApiClient, suggest_payload: object
) -> None:
    """Object-keyed suggest payload parses into addresses."""
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, payload=suggest_payload)
        results = await client.async_suggest_addresses("110 Montreal")

    assert len(results) == 3
    first = results[0]
    assert first.rating_unit_id == 192837
    assert first.full_address == "110 Montreal Street, Sydenham, Christchurch 8023"


async def test_suggest_parses_array_shape(client: CCCApiClient) -> None:
    """A true-array suggest payload is also accepted (defensive)."""
    payload = [
        {
            "StreetAddressID": 1,
            "FullStreetAddress": "1 Test Street, Sydenham, Christchurch 8023",
            "RatingUnitID": 42,
        }
    ]
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, payload=payload)
        results = await client.async_suggest_addresses("1 Test")

    assert len(results) == 1
    assert results[0].rating_unit_id == 42


async def test_suggest_empty_raises_not_found(client: CCCApiClient) -> None:
    """An empty suggest result raises CCCAddressNotFound."""
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, payload={})
        with pytest.raises(CCCAddressNotFound):
            await client.async_suggest_addresses("nowhere")


async def test_suggest_connection_error(client: CCCApiClient) -> None:
    """Transport errors surface as CCCConnectionError."""
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, exception=aiohttp.ClientError("boom"))
        with pytest.raises(CCCConnectionError):
            await client.async_suggest_addresses("110 Montreal")


async def test_fetch_property_happy(
    client: CCCApiClient, property_payload: object
) -> None:
    """getProperty parses containers, routes and collections."""
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, payload=property_payload)
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


async def test_fetch_property_no_kerbside_raises(client: CCCApiClient) -> None:
    """A property with no kerbside collection raises a clean error."""
    payload = {"id": "305512", "address": "793 McLeans Island Road Christchurch"}
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, payload=payload)
        with pytest.raises(CCCPropertyNotFound):
            await client.async_fetch_property(305512)


async def test_fetch_property_malformed_raises_parse_error(
    client: CCCApiClient,
) -> None:
    """Structural surprises raise CCCParseError, not a bare KeyError/TypeError."""
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, body=load_fixture("getProperty_malformed.json"))
        with pytest.raises(CCCParseError):
            await client.async_fetch_property(192837)


async def test_fetch_property_invalid_json_raises_parse_error(
    client: CCCApiClient,
) -> None:
    """Non-JSON body raises CCCParseError."""
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, body="<html>nope</html>")
        with pytest.raises(CCCParseError):
            await client.async_fetch_property(192837)


async def test_fetch_property_connection_error(client: CCCApiClient) -> None:
    """Transport errors during getProperty surface as CCCConnectionError."""
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, exception=aiohttp.ClientError("boom"))
        with pytest.raises(CCCConnectionError):
            await client.async_fetch_property(192837)


async def test_fetch_overrides_parses(
    client: CCCApiClient, overrides_payload: object
) -> None:
    """The overrides feed parses into typed records."""
    with aioresponses() as mock:
        mock.get(CCC_OVERRIDES_URL, payload=overrides_payload)
        overrides = await client.async_fetch_overrides()

    assert len(overrides) == 5
    xmas = next(o for o in overrides if o.original_date == date(2026, 12, 25))
    assert xmas.new_date == date(2026, 12, 26)
    assert xmas.expired is False


async def test_fetch_overrides_connection_error(client: CCCApiClient) -> None:
    """Override transport errors raise so the coordinator can soft-fail."""
    with aioresponses() as mock:
        mock.get(CCC_OVERRIDES_URL, exception=aiohttp.ClientError("boom"))
        with pytest.raises(CCCConnectionError):
            await client.async_fetch_overrides()


async def test_suggest_non_collection_payload_raises(client: CCCApiClient) -> None:
    """A suggest payload that is neither list nor object raises CCCParseError."""
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, payload="unexpected")
        with pytest.raises(CCCParseError):
            await client.async_suggest_addresses("110 Montreal")


async def test_suggest_skips_incomplete_entries(client: CCCApiClient) -> None:
    """Non-dict and key-less entries are skipped, not fatal."""
    payload = {
        "0": "garbage",
        "1": {"RatingUnitID": 5},
        "2": {
            "RatingUnitID": 7,
            "FullStreetAddress": "7 Real Street, Sydenham, Christchurch 8023",
        },
    }
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, payload=payload)
        results = await client.async_suggest_addresses("real")

    assert [a.rating_unit_id for a in results] == [7]


async def test_suggest_non_numeric_id_raises(client: CCCApiClient) -> None:
    """A non-numeric RatingUnitID is a structural error."""
    payload = {
        "0": {"RatingUnitID": "not-a-number", "FullStreetAddress": "1 X St"},
    }
    with aioresponses() as mock:
        mock.get(SUGGEST_PATTERN, payload=payload)
        with pytest.raises(CCCParseError):
            await client.async_suggest_addresses("x")


async def test_fetch_property_non_object_raises(client: CCCApiClient) -> None:
    """A getProperty payload that is not an object raises CCCParseError."""
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, payload=[1, 2, 3])
        with pytest.raises(CCCParseError):
            await client.async_fetch_property(192837)


async def test_fetch_property_coerces_empty_dates_and_bool_flags(
    client: CCCApiClient,
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
    with aioresponses() as mock:
        mock.get(PROPERTY_PATTERN, payload=payload)
        prop = await client.async_fetch_property(192837)

    row = prop.collections[0]
    assert row.next_planned_date is None
    assert row.next_planned_date_app == date(2026, 6, 23)
    assert row.out_of_date is True


async def test_fetch_overrides_non_list_raises(client: CCCApiClient) -> None:
    """An overrides payload that is not a list raises CCCParseError."""
    with aioresponses() as mock:
        mock.get(CCC_OVERRIDES_URL, payload={"not": "a list"})
        with pytest.raises(CCCParseError):
            await client.async_fetch_overrides()


async def test_fetch_overrides_malformed_row_raises(client: CCCApiClient) -> None:
    """A row with a missing/invalid date raises CCCParseError."""
    with aioresponses() as mock:
        mock.get(CCC_OVERRIDES_URL, payload=[{"ID": 1, "Title": "Bad"}])
        with pytest.raises(CCCParseError):
            await client.async_fetch_overrides()
