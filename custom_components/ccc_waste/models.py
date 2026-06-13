"""Typed data models for CCC kerbside data.

Pure dataclasses with no Home Assistant imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


@dataclass(frozen=True, slots=True)
class CCCAddress:
    """A single address suggestion."""

    rating_unit_id: int
    full_address: str
    street_address_id: int | None = None


@dataclass(frozen=True, slots=True)
class CCCContainer:
    """A physical bin allocated to a property."""

    material: str
    status: str
    container_type: str | None = None
    serial_no: str | None = None


@dataclass(frozen=True, slots=True)
class CCCRoute:
    """The collection route for a material at a property."""

    material: str
    day_of_week: str | None = None
    customer_group: str | None = None


@dataclass(frozen=True, slots=True)
class CCCCollection:
    """A single raw collection row from the CCC feed."""

    material: str
    pick_up_group: str
    next_planned_date: date | None
    next_planned_date_app: date | None
    out_of_date: bool


@dataclass(frozen=True, slots=True)
class CCCProperty:
    """A property and its allocated bins, routes and collections."""

    rating_unit_id: int
    address: str
    latitude: float | None
    longitude: float | None
    containers: tuple[CCCContainer, ...]
    routes: tuple[CCCRoute, ...]
    collections: tuple[CCCCollection, ...]


@dataclass(frozen=True, slots=True)
class CCCDateOverride:
    """A holiday date shift from the overrides feed."""

    id: int
    title: str
    original_date: date
    new_date: date
    expired: bool


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """The computed next collection for a single material."""

    material: str
    next_date: date
    temporary_change: bool
    original_date: date | None
    collection_day: str | None
    container_type: str | None
