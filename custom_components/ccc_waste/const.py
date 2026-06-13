"""Constants for the CCC kerbside collection integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "ccc_waste"

# All date work is done as naive local dates in this zone. The override match is
# exact-calendar-date equality, so converting through UTC would misalign it.
TIMEZONE: Final = "Pacific/Auckland"

# Collection dates barely move; a long poll interval is the whole point of this
# integration (it decouples the user from upstream release churn).
UPDATE_INTERVAL: Final = timedelta(hours=12)

CONF_ADDRESS: Final = "address"
CONF_RATING_UNIT_ID: Final = "rating_unit_id"

MATERIAL_GARBAGE: Final = "Garbage"
MATERIAL_RECYCLE: Final = "Recycle"
MATERIAL_ORGANIC: Final = "Organic"

# Organic is collected weekly; everything else fortnightly.
WEEKLY_MATERIALS: Final = frozenset({MATERIAL_ORGANIC})

# Rows in these pick-up groups are not real kerbside collections.
EXCLUDED_PICK_UP_GROUPS: Final = frozenset({"Daily", "Not Collected"})

# Upper bound on the forward-roll loop, mirroring the official client.
ROLL_SAFETY_CAP: Final = 208

ICONS: Final = {
    MATERIAL_GARBAGE: "mdi:trash-can",
    MATERIAL_RECYCLE: "mdi:recycle",
    MATERIAL_ORGANIC: "mdi:leaf",
}
DEFAULT_ICON: Final = "mdi:trash-can-outline"

# Human-facing labels for calendar event summaries.
MATERIAL_LABELS: Final = {
    MATERIAL_GARBAGE: "Rubbish",
    MATERIAL_RECYCLE: "Recycling",
    MATERIAL_ORGANIC: "Organic",
}

ATTR_DAYS_UNTIL: Final = "days_until"
ATTR_BIN_TYPE: Final = "bin_type"
ATTR_COLLECTION_DAY: Final = "collection_day"
ATTR_TEMPORARY_CHANGE: Final = "temporary_change"
ATTR_ORIGINAL_DATE: Final = "original_date"
ATTR_CONTAINER_TYPE: Final = "container_type"
