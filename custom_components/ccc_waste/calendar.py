"""Calendar entity exposing upcoming kerbside collections."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MATERIAL_LABELS, TIMEZONE, WEEKLY_MATERIALS

if TYPE_CHECKING:
    from datetime import date, datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import CCCConfigEntry, CCCCoordinator

PARALLEL_UPDATES = 0

_AUCKLAND = ZoneInfo(TIMEZONE)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CCCConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the single collections calendar."""
    async_add_entities([CCCCollectionCalendar(entry.runtime_data)])


class CCCCollectionCalendar(CoordinatorEntity["CCCCoordinator"], CalendarEntity):
    """All upcoming collections as all-day events."""

    _attr_has_entity_name = True
    _attr_translation_key = "collections"
    _attr_icon = "mdi:calendar"

    def __init__(self, coordinator: CCCCoordinator) -> None:
        """Bind the calendar to the coordinator."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.rating_unit_id}_collections"
        self._attr_device_info = coordinator.device_info

    @property
    def event(self) -> CalendarEvent | None:
        """The soonest upcoming collection across all materials."""
        results = list(self.coordinator.data.collections.values())
        if not results:
            return None
        soonest = min(results, key=lambda r: r.next_date)
        return _event(soonest.material, soonest.next_date)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Project each material forward by its cadence across the window.

        Only the next date carries a confirmed holiday override; dates beyond it
        are projected by cadence, which is what a forward-looking calendar needs.
        """
        window_start = start_date.astimezone(_AUCKLAND).date()
        window_end = end_date.astimezone(_AUCKLAND).date()

        events: list[CalendarEvent] = []
        for result in self.coordinator.data.collections.values():
            step = timedelta(weeks=1 if result.material in WEEKLY_MATERIALS else 2)
            occurrence = result.next_date
            while occurrence <= window_end:
                if occurrence >= window_start:
                    events.append(_event(result.material, occurrence))
                occurrence += step
        events.sort(key=lambda event: event.start)
        return events


def _event(material: str, day: date) -> CalendarEvent:
    label = MATERIAL_LABELS.get(material, material)
    return CalendarEvent(
        summary=f"{label} collection",
        start=day,
        end=day + timedelta(days=1),
    )
