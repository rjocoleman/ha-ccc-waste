"""Pure date-selection logic, a faithful port of the official CCC client.

No Home Assistant imports. The council's own JS (``GetCollectionDay``,
``CheckSpecialDate``, ``SortCollections``) returns stale dates by design and
expects the consumer to roll them forward, then apply holiday overrides. This
module replicates that exactly so it can be unit tested in isolation.

All inputs are naive local dates; callers must pass a ``today`` already
expressed in ``Pacific/Auckland`` so the exact-date override match lines up.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from .const import EXCLUDED_PICK_UP_GROUPS, ROLL_SAFETY_CAP, WEEKLY_MATERIALS
from .models import CollectionResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from .models import CCCDateOverride, CCCProperty


def roll_forward(start: date, today: date, *, weekly: bool) -> date:
    """Advance ``start`` by whole cycles until it is on or after ``today``.

    Organic is weekly (+1 week), everything else fortnightly (+2 weeks).
    """
    step = timedelta(weeks=1 if weekly else 2)
    current = start
    for _ in range(ROLL_SAFETY_CAP):
        if current >= today:
            return current
        current += step
    return current


def apply_override(
    collection_date: date, overrides: Sequence[CCCDateOverride]
) -> tuple[date, bool, date | None]:
    """Apply a single-pass holiday override to ``collection_date``.

    Returns ``(effective_date, temporary_change, original_date)``. The match is
    single-pass: the council pre-flattens cascades (25 Dec -> 26 -> 27) into
    discrete rows, so we never re-check whether the new date is itself shifted.

    Expired rows are skipped. The official client matches purely on date, but an
    expired override points at a past original date that a forward-rolled date
    can never equal, so skipping it is safe and keeps the feed's flag meaningful.
    """
    for override in overrides:
        if override.expired:
            continue
        if override.original_date == collection_date:
            return override.new_date, True, collection_date
    return collection_date, False, None


def compute_collections(
    prop: CCCProperty,
    overrides: Sequence[CCCDateOverride],
    today: date,
) -> list[CollectionResult]:
    """Compute the next effective collection date for each material."""
    rows_by_material = _schedulable_rows_by_material(prop)

    results: list[CollectionResult] = []
    for material, app_date in rows_by_material.items():
        rolled = roll_forward(
            app_date,
            today,
            weekly=material in WEEKLY_MATERIALS,
        )
        effective, changed, original = apply_override(rolled, overrides)
        results.append(
            CollectionResult(
                material=material,
                next_date=effective,
                temporary_change=changed,
                original_date=original,
                collection_day=_route_day(prop, material),
                container_type=_container_type(prop, material),
            )
        )

    results.sort(key=lambda r: (r.next_date, r.material))
    return results


def _schedulable_rows_by_material(prop: CCCProperty) -> dict[str, date]:
    """Pick the most-current schedulable app date per material.

    Rows in excluded pick-up groups and rows without an app date are dropped.
    Where a material has several rows, the latest app date wins (the others are
    historical).
    """
    chosen: dict[str, date] = {}
    for row in prop.collections:
        app_date = row.next_planned_date_app
        if row.pick_up_group in EXCLUDED_PICK_UP_GROUPS or app_date is None:
            continue
        current = chosen.get(row.material)
        if current is None or app_date > current:
            chosen[row.material] = app_date
    return chosen


def _route_day(prop: CCCProperty, material: str) -> str | None:
    for route in prop.routes:
        if route.material == material:
            return route.day_of_week
    return None


def _container_type(prop: CCCProperty, material: str) -> str | None:
    for container in prop.containers:
        if container.material == material:
            return container.container_type
    return None
