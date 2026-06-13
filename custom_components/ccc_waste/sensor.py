"""Per-material next-collection sensors."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_COLLECTION_DAY,
    ATTR_CONTAINER_TYPE,
    ATTR_DAYS_UNTIL,
    ATTR_ORIGINAL_DATE,
    ATTR_TEMPORARY_CHANGE,
    DEFAULT_ICON,
    DOMAIN,
    ICONS,
    TIMEZONE,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import CCCConfigEntry, CCCCoordinator
    from .models import CollectionResult

# A single coordinator owns the data; entities never poll independently.
PARALLEL_UPDATES = 0

_AUCKLAND = ZoneInfo(TIMEZONE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CCCConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one sensor per material present at the property."""
    coordinator = entry.runtime_data
    async_add_entities(
        CCCBinSensor(coordinator, material)
        for material in sorted(coordinator.data.collections)
    )


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
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(coordinator.rating_unit_id))},
            name=coordinator.address,
            manufacturer="Christchurch City Council",
            model="Kerbside collection",
        )

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
        return datetime.combine(result.next_date, time.min, tzinfo=_AUCKLAND)

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
