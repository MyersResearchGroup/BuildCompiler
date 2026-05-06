"""In-memory adapter for compiler-level PUDU plating JSON payloads."""

from collections import OrderedDict
from collections.abc import Mapping
from typing import Any


def plating_to_pudu_json(
    *,
    bacterium_locations: Mapping[str, str],
    advanced_parameters: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Adapt plating records into deterministic legacy-compatible PUDU JSON keys."""

    stable_locations = OrderedDict(
        sorted(bacterium_locations.items(), key=lambda kv: kv[0])
    )
    payload: dict[str, Any] = {
        "bacterium_locations": dict(stable_locations),
        "advanced_parameters": dict(advanced_parameters or {}),
    }
    return payload
