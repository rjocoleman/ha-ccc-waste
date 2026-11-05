"""Shared test fixtures and helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ccc_waste.api import CCC_OVERRIDES_URL, CCC_PROPERTY_URL
from custom_components.ccc_waste.const import (
    CONF_ADDRESS,
    CONF_RATING_UNIT_ID,
    DOMAIN,
)

if TYPE_CHECKING:
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )

FIXTURE_DIR = Path(__file__).parent / "fixtures"

ALLPRESS_ADDRESS = "110 Montreal Street, Sydenham, Christchurch 8023"
ALLPRESS_RATING_UNIT_ID = 192837


def load_fixture(name: str) -> str:
    """Return the raw text of a JSON fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def load_json_fixture(name: str) -> Any:
    """Return a parsed JSON fixture."""
    return json.loads(load_fixture(name))


def mock_ccc_endpoints(
    aioclient_mock: AiohttpClientMocker,
    *,
    property_fixture: str = "getProperty.json",
    overrides_fixture: str | None = "overrides.json",
) -> None:
    """Serve the property and overrides endpoints from fixtures."""
    aioclient_mock.get(CCC_PROPERTY_URL, text=load_fixture(property_fixture))
    if overrides_fixture is not None:
        aioclient_mock.get(CCC_OVERRIDES_URL, text=load_fixture(overrides_fixture))


@pytest.fixture(autouse=True)
def _auto_enable_custom_integrations(
    enable_custom_integrations: object,
) -> None:
    """Load the custom integration in every test."""
    return


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """A config entry for the Allpress fixture address."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(ALLPRESS_RATING_UNIT_ID),
        data={
            CONF_RATING_UNIT_ID: ALLPRESS_RATING_UNIT_ID,
            CONF_ADDRESS: ALLPRESS_ADDRESS,
        },
    )


@pytest.fixture
def suggest_payload() -> Any:
    """Address suggest response (object-keyed)."""
    return load_json_fixture("suggest.json")


@pytest.fixture
def property_payload() -> Any:
    """getProperty response for the Allpress fixture address."""
    return load_json_fixture("getProperty.json")


@pytest.fixture
def overrides_payload() -> Any:
    """kerbsidedateoverrides response."""
    return load_json_fixture("overrides.json")
