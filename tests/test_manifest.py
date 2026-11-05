"""Tests for version consistency between the manifest and pyproject."""

from __future__ import annotations

import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).parent.parent


def test_manifest_version_matches_pyproject() -> None:
    """The release workflow requires the tag to equal both versions."""
    manifest = json.loads(
        (ROOT / "custom_components/ccc_waste/manifest.json").read_text(encoding="utf-8")
    )
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["version"] == pyproject["project"]["version"]
