"""Async client for the Christchurch City Council kerbside endpoints.

No Home Assistant imports: the client takes an injected ``aiohttp`` session
and returns typed models, so it can be unit tested against recorded fixtures.

The endpoints are the credential-free ones the council website itself uses.
There are no API keys, cookies or WAF steps; if CCC ever gates these we want
a visible failure, not a secret to maintain.
"""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING, Any

import aiohttp

from .exceptions import (
    CCCAddressNotFound,
    CCCConnectionError,
    CCCParseError,
    CCCPropertyNotFound,
)
from .models import (
    CCCAddress,
    CCCCollection,
    CCCContainer,
    CCCDateOverride,
    CCCProperty,
    CCCRoute,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

CCC_SUGGEST_URL = "https://opendata.ccc.govt.nz/CCCSearch/rest/address/suggest"
CCC_PROPERTY_URL = (
    "https://ccc.govt.nz/services/rubbish-and-recycling/collections/getProperty"
)
CCC_OVERRIDES_URL = "https://ccc.govt.nz/api/kerbsidedateoverrides"

_COLLECTIONS_REFERER = "https://ccc.govt.nz/services/rubbish-and-recycling/collections"

_SUGGEST_HEADERS = {
    "Referer": "https://ccc.govt.nz/",
    "Origin": "https://ccc.govt.nz",
    "Accept": "*/*",
}
_AJAX_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": _COLLECTIONS_REFERER,
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class CCCApiClient:
    """Talks to the CCC address and kerbside collection endpoints."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Store the injected session."""
        self._session = session

    async def async_suggest_addresses(self, query: str) -> list[CCCAddress]:
        """Return address suggestions for a partial address string."""
        data = await self._get_json(
            CCC_SUGGEST_URL, params={"q": query}, headers=_SUGGEST_HEADERS
        )
        addresses = _parse_addresses(data)
        if not addresses:
            msg = f"No CCC address matched {query!r}"
            raise CCCAddressNotFound(msg)
        return addresses

    async def async_fetch_property(self, rating_unit_id: int) -> CCCProperty:
        """Return the bins, routes and collections for a rating unit."""
        data = await self._get_json(
            CCC_PROPERTY_URL,
            params={"ID": str(rating_unit_id)},
            headers=_AJAX_HEADERS,
        )
        return _parse_property(data)

    async def async_fetch_overrides(self) -> list[CCCDateOverride]:
        """Return the holiday date overrides feed."""
        data = await self._get_json(CCC_OVERRIDES_URL, headers=_AJAX_HEADERS)
        return _parse_overrides(data)

    async def _get_json(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
    ) -> Any:
        """Fetch and decode JSON, mapping transport/decode failures to typed errors."""
        try:
            async with self._session.get(
                url, params=params, headers=headers
            ) as response:
                response.raise_for_status()
                text = await response.text()
        except aiohttp.ClientError as err:
            msg = f"Failed to reach {url}"
            raise CCCConnectionError(msg) from err

        try:
            return json.loads(text)
        except ValueError as err:
            msg = f"Response from {url} was not valid JSON"
            raise CCCParseError(msg) from err


def _parse_addresses(data: Any) -> list[CCCAddress]:
    """Parse a suggest response, accepting object-keyed maps and arrays."""
    if isinstance(data, list):
        entries: list[Any] = data
    elif isinstance(data, dict):
        entries = list(data.values())
    else:
        msg = "Unexpected suggest payload shape"
        raise CCCParseError(msg)

    addresses: list[CCCAddress] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rating_unit_id = entry.get("RatingUnitID")
        full_address = entry.get("FullStreetAddress")
        if rating_unit_id is None or full_address is None:
            continue
        try:
            addresses.append(
                CCCAddress(
                    rating_unit_id=int(rating_unit_id),
                    full_address=str(full_address),
                    street_address_id=_optional_int(entry.get("StreetAddressID")),
                )
            )
        except (TypeError, ValueError) as err:
            msg = "Malformed address entry"
            raise CCCParseError(msg) from err
    return addresses


def _parse_property(data: Any) -> CCCProperty:
    """Parse a getProperty response into a typed property."""
    if not isinstance(data, dict):
        msg = "Unexpected getProperty payload shape"
        raise CCCParseError(msg)

    bins = data.get("bins")
    if not isinstance(bins, dict) or not bins.get("collections"):
        msg = "Property has no kerbside collection"
        raise CCCPropertyNotFound(msg)

    try:
        return CCCProperty(
            rating_unit_id=int(data["id"]),
            address=str(data.get("address", "")),
            latitude=_optional_float(data.get("latitude")),
            longitude=_optional_float(data.get("longitude")),
            containers=tuple(_parse_container(c) for c in bins.get("containers", [])),
            routes=tuple(_parse_route(r) for r in bins.get("routes", [])),
            collections=tuple(_parse_collection(c) for c in bins["collections"]),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        msg = "Malformed getProperty payload"
        raise CCCParseError(msg) from err


def _parse_container(raw: Any) -> CCCContainer:
    return CCCContainer(
        material=str(raw["material"]),
        status=str(raw.get("status", "")),
        container_type=_optional_str(raw.get("container_type")),
        serial_no=_optional_str(raw.get("serial_no")),
    )


def _parse_route(raw: Any) -> CCCRoute:
    return CCCRoute(
        material=str(raw["material"]),
        day_of_week=_optional_str(raw.get("day_of_week")),
        customer_group=_optional_str(raw.get("customer_group")),
    )


def _parse_collection(raw: Any) -> CCCCollection:
    return CCCCollection(
        material=str(raw["material"]),
        pick_up_group=str(raw.get("pick_up_group", "")),
        next_planned_date=_optional_date(raw.get("next_planned_date")),
        next_planned_date_app=_optional_date(raw.get("next_planned_date_app")),
        out_of_date=_to_bool(raw.get("out_of_date")),
    )


def _parse_overrides(data: Any) -> list[CCCDateOverride]:
    """Parse the overrides feed (flat array)."""
    if not isinstance(data, list):
        msg = "Unexpected overrides payload shape"
        raise CCCParseError(msg)
    try:
        return [
            CCCDateOverride(
                id=int(row["ID"]),
                title=str(row.get("Title", "")),
                original_date=date.fromisoformat(row["OriginalDate"]),
                new_date=date.fromisoformat(row["NewDate"]),
                expired=bool(int(row.get("Expired", 0))),
            )
            for row in data
        ]
    except (KeyError, TypeError, ValueError) as err:
        msg = "Malformed overrides payload"
        raise CCCParseError(msg) from err


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value))


def _to_bool(value: Any) -> bool:
    """Coerce the API's string booleans (``"True"``/``"False"``) to bool."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"
