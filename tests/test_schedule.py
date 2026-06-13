"""Tests for the pure date-selection logic (faithful port of the CCC client)."""

from __future__ import annotations

from datetime import date

from custom_components.ccc_waste.models import (
    CCCCollection,
    CCCContainer,
    CCCDateOverride,
    CCCProperty,
    CCCRoute,
)
from custom_components.ccc_waste.schedule import (
    apply_override,
    compute_collections,
    roll_forward,
)


def _override(original: str, new: str, *, expired: bool = False) -> CCCDateOverride:
    return CCCDateOverride(
        id=1,
        title="Holiday",
        original_date=date.fromisoformat(original),
        new_date=date.fromisoformat(new),
        expired=expired,
    )


def _collection(
    material: str,
    *,
    app: str | None,
    planned: str | None = None,
    group: str = "100",
) -> CCCCollection:
    return CCCCollection(
        material=material,
        pick_up_group=group,
        next_planned_date=date.fromisoformat(planned) if planned else None,
        next_planned_date_app=date.fromisoformat(app) if app else None,
        out_of_date=False,
    )


def _property(
    collections: list[CCCCollection],
    routes: list[CCCRoute] | None = None,
    containers: list[CCCContainer] | None = None,
) -> CCCProperty:
    return CCCProperty(
        rating_unit_id=192837,
        address="110 Montreal Street Sydenham Christchurch",
        latitude=-43.54612,
        longitude=172.63298,
        containers=tuple(containers or []),
        routes=tuple(routes or []),
        collections=tuple(collections),
    )


# --- roll_forward -----------------------------------------------------------


def test_roll_forward_fortnightly() -> None:
    """A stale fortnightly date advances in two-week steps until it is current."""
    result = roll_forward(date(2026, 5, 12), date(2026, 6, 13), weekly=False)
    assert result == date(2026, 6, 23)


def test_roll_forward_weekly() -> None:
    """A stale weekly date advances in one-week steps."""
    result = roll_forward(date(2026, 5, 19), date(2026, 6, 13), weekly=True)
    assert result == date(2026, 6, 16)


def test_roll_forward_already_current() -> None:
    """A date already on or after today is returned unchanged."""
    assert roll_forward(date(2026, 6, 23), date(2026, 6, 13), weekly=False) == date(
        2026, 6, 23
    )


def test_roll_forward_today_is_inclusive() -> None:
    """Today counts as current; no roll occurs."""
    assert roll_forward(date(2026, 6, 13), date(2026, 6, 13), weekly=True) == date(
        2026, 6, 13
    )


def test_roll_forward_safety_cap() -> None:
    """An impossibly stale date stops at the safety cap rather than looping."""
    # 208 fortnights is ~8 years; from 1900 it cannot reach 2026.
    result = roll_forward(date(1900, 1, 1), date(2026, 6, 13), weekly=False)
    assert result < date(2026, 6, 13)


# --- apply_override ---------------------------------------------------------


def test_apply_override_match() -> None:
    """A date matching an OriginalDate is swapped to the NewDate."""
    overrides = [_override("2026-12-25", "2026-12-26")]
    effective, changed, original = apply_override(date(2026, 12, 25), overrides)
    assert effective == date(2026, 12, 26)
    assert changed is True
    assert original == date(2026, 12, 25)


def test_apply_override_single_pass_no_cascade() -> None:
    """Matching is single-pass; pre-flattened cascades are not chained."""
    overrides = [
        _override("2026-12-25", "2026-12-26"),
        _override("2026-12-26", "2026-12-28"),
    ]
    effective, changed, original = apply_override(date(2026, 12, 25), overrides)
    # 25 -> 26, and NOT on to 28.
    assert effective == date(2026, 12, 26)
    assert changed is True
    assert original == date(2026, 12, 25)


def test_apply_override_no_match_passes_through() -> None:
    """A date with no override is returned unchanged and unflagged."""
    overrides = [_override("2026-12-25", "2026-12-26")]
    effective, changed, original = apply_override(date(2026, 6, 23), overrides)
    assert effective == date(2026, 6, 23)
    assert changed is False
    assert original is None


def test_apply_override_skips_expired() -> None:
    """An expired override is ignored even if its date matches."""
    overrides = [_override("2026-12-25", "2026-12-26", expired=True)]
    effective, changed, original = apply_override(date(2026, 12, 25), overrides)
    assert effective == date(2026, 12, 25)
    assert changed is False
    assert original is None


# --- compute_collections ----------------------------------------------------


def test_compute_uses_app_date_not_planned() -> None:
    """The authoritative field is next_planned_date_app, not next_planned_date."""
    prop = _property(
        [_collection("Garbage", app="2026-06-23", planned="2026-06-10", group="204")]
    )
    results = {r.material: r for r in compute_collections(prop, [], date(2026, 6, 13))}
    # Using _app (06-23) gives 06-23; using planned (06-10) would roll to 06-24.
    assert results["Garbage"].next_date == date(2026, 6, 23)


def test_compute_rolls_weekly_and_fortnightly() -> None:
    """Organic rolls weekly; Garbage and Recycle roll fortnightly."""
    prop = _property(
        [
            _collection("Garbage", app="2026-05-12", group="204"),
            _collection("Recycle", app="2026-05-12", group="104"),
            _collection("Organic", app="2026-05-19", group="305"),
        ]
    )
    results = {r.material: r for r in compute_collections(prop, [], date(2026, 6, 13))}
    assert results["Garbage"].next_date == date(2026, 6, 23)
    assert results["Recycle"].next_date == date(2026, 6, 23)
    assert results["Organic"].next_date == date(2026, 6, 16)


def test_compute_excludes_non_kerbside_groups() -> None:
    """Daily and Not Collected rows are skipped entirely."""
    prop = _property(
        [
            _collection("Garbage", app="2026-06-23", group="Daily"),
            _collection("Recycle", app="2026-06-23", group="Not Collected"),
        ]
    )
    assert compute_collections(prop, [], date(2026, 6, 13)) == []


def test_compute_latest_app_row_wins() -> None:
    """With multiple rows for a material, the most recent app date is used."""
    prop = _property(
        [
            _collection("Recycle", app="2026-01-06", group="104"),
            _collection("Recycle", app="2026-05-12", group="104"),
        ]
    )
    results = {r.material: r for r in compute_collections(prop, [], date(2026, 6, 13))}
    # Latest app (05-12) rolls fortnightly to 06-23.
    assert results["Recycle"].next_date == date(2026, 6, 23)


def test_compute_applies_override_after_roll() -> None:
    """An override matching the rolled date is applied and flagged."""
    prop = _property([_collection("Organic", app="2026-12-25", group="305")])
    overrides = [_override("2026-12-25", "2026-12-26")]
    results = {
        r.material: r for r in compute_collections(prop, overrides, date(2026, 12, 20))
    }
    organic = results["Organic"]
    assert organic.next_date == date(2026, 12, 26)
    assert organic.temporary_change is True
    assert organic.original_date == date(2026, 12, 25)


def test_compute_timezone_safe_override_match() -> None:
    """A 25 Dec local date matches the '2025-12-25' override with no UTC drift."""
    prop = _property([_collection("Organic", app="2025-12-25", group="305")])
    overrides = [_override("2025-12-25", "2025-12-26")]
    results = {
        r.material: r for r in compute_collections(prop, overrides, date(2025, 12, 25))
    }
    assert results["Organic"].next_date == date(2025, 12, 26)


def test_compute_attaches_route_day_and_container_type() -> None:
    """Collection day comes from routes and container type from containers."""
    prop = _property(
        [_collection("Garbage", app="2026-06-23", group="204")],
        routes=[CCCRoute(material="Garbage", day_of_week="Tuesday")],
        containers=[
            CCCContainer(material="Garbage", status="Active", container_type="140L WB")
        ],
    )
    results = {r.material: r for r in compute_collections(prop, [], date(2026, 6, 13))}
    assert results["Garbage"].collection_day == "Tuesday"
    assert results["Garbage"].container_type == "140L WB"


def test_compute_skips_rows_without_app_date() -> None:
    """A material whose only row lacks an app date produces no result."""
    prop = _property([_collection("Garbage", app=None, group="204")])
    assert compute_collections(prop, [], date(2026, 6, 13)) == []
