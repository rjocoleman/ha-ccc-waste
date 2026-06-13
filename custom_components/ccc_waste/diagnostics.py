"""Diagnostics for CCC kerbside collection (with personal data redacted)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data

from .const import CONF_ADDRESS, CONF_RATING_UNIT_ID

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import CCCConfigEntry

TO_REDACT = {
    CONF_ADDRESS,
    CONF_RATING_UNIT_ID,
    "address",
    "rating_unit_id",
    "latitude",
    "longitude",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CCCConfigEntry
) -> dict[str, Any]:
    """Return a redacted diagnostics dump."""
    coordinator = entry.runtime_data
    data = coordinator.data

    collections = {
        material: {
            "next_date": result.next_date.isoformat(),
            "collection_day": result.collection_day,
            "temporary_change": result.temporary_change,
            "original_date": (
                result.original_date.isoformat() if result.original_date else None
            ),
            "container_type": result.container_type,
        }
        for material, result in data.collections.items()
    }

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "data": async_redact_data(
            {
                "rating_unit_id": data.rating_unit_id,
                "address": data.address,
                "latitude": data.latitude,
                "longitude": data.longitude,
                "collections": collections,
            },
            TO_REDACT,
        ),
    }
