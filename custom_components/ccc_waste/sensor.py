"""Collection sensors: one per material plus a next-collection summary."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_BINS,
    ATTR_COLLECTION_DAY,
    ATTR_CONTAINER_TYPE,
    ATTR_DAYS_UNTIL,
    ATTR_ORIGINAL_DATE,
    ATTR_TEMPORARY_CHANGE,
    DEFAULT_ICON,
    ICONS,
    MATERIAL_LABELS,
    TIMEZONE,
)

if TYPE_CHECKING:
    from datetime import date

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import CCCConfigEntry, CCCCoordinator
    from .models import CollectionResult

# A single coordinator owns the data; entities never poll independently.
PARALLEL_UPDATES = 0

_AUCKLAND = ZoneInfo(TIMEZONE)


def _local_midnight(day: date) -> datetime:
    """Express a collection date as an Auckland-local midnight timestamp."""
    return datetime.combine(day, time.min, tzinfo=_AUCKLAND)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CCCConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create a sensor per material plus a next-collection summary."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        CCCBinSensor(coordinator, material)
        for material in sorted(coordinator.data.collections)
    ]
    if coordinator.data.collections:
        entities.append(CCCNextCollectionSensor(coordinator))
    async_add_entities(entities)


class CCCBinSensor(CoordinatorEntity["CCCCoordinator"], SensorEntity):
    """Next collection date for one bin material."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: CCCCoordinator, material: str) -> None:
        """Bind the sensor to a coordinator and material."""
        super().__init__(coordinator)
        self._material = material
        self._attr_translation_key = material.lower()
        self._attr_unique_id = f"{coordinator.rating_unit_id}_{material.lower()}"
        self._attr_icon = ICONS.get(material, DEFAULT_ICON)
        self._attr_device_info = coordinator.device_info

    @property
    def _result(self) -> CollectionResult | None:
        return self.coordinator.data.collections.get(self._material)

    @property
    def available(self) -> bool:
        """Available only while the material is present in the latest data."""
        return super().available and self._result is not None

    @property
    def native_value(self) -> datetime | None:
        """Next collection as an Auckland-local midnight timestamp."""
        result = self._result
        if result is None:
            return None
        return _local_midnight(result.next_date)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the detail cards and automations key off."""
        result = self._result
        if result is None:
            return None
        today = dt_util.now(_AUCKLAND).date()
        return {
            ATTR_DAYS_UNTIL: (result.next_date - today).days,
            ATTR_COLLECTION_DAY: result.collection_day,
            ATTR_TEMPORARY_CHANGE: result.temporary_change,
            ATTR_ORIGINAL_DATE: result.original_date,
            ATTR_CONTAINER_TYPE: result.container_type,
        }


class CCCNextCollectionSensor(CoordinatorEntity["CCCCoordinator"], SensorEntity):
    """The soonest upcoming collection across all materials."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_collection"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: CCCCoordinator) -> None:
        """Bind the summary sensor to the coordinator."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.rating_unit_id}_next_collection"
        self._attr_device_info = coordinator.device_info

    @property
    def _soonest(self) -> list[CollectionResult]:
        """All materials sharing the earliest upcoming date."""
        results = list(self.coordinator.data.collections.values())
        if not results:
            return []
        earliest = min(result.next_date for result in results)
        return sorted(
            (result for result in results if result.next_date == earliest),
            key=lambda result: result.material,
        )

    @property
    def available(self) -> bool:
        """Available while any collection is known."""
        return super().available and bool(self.coordinator.data.collections)

    @property
    def native_value(self) -> datetime | None:
        """The earliest upcoming collection date as a timestamp."""
        soonest = self._soonest
        if not soonest:
            return None
        return _local_midnight(soonest[0].next_date)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Which bins go out next, and when."""
        soonest = self._soonest
        if not soonest:
            return None
        today = dt_util.now(_AUCKLAND).date()
        return {
            ATTR_DAYS_UNTIL: (soonest[0].next_date - today).days,
            ATTR_BINS: [MATERIAL_LABELS.get(r.material, r.material) for r in soonest],
            ATTR_COLLECTION_DAY: soonest[0].collection_day,
            ATTR_TEMPORARY_CHANGE: any(result.temporary_change for result in soonest),
        }
