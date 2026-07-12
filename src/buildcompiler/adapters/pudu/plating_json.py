"""In-memory adapter for compiler-level PUDU plating JSON payloads."""

from collections import OrderedDict
from collections.abc import Mapping
from typing import Any


def plating_to_pudu_json(
    *,
    bacterium_locations: Mapping[str, str | list[str]],
    advanced_parameters: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Adapt plating records into PUDU's plating input JSON.

    PUDU expects thermocycler source wells as keys and transformed construct
    identifiers as values, wrapped under ``bacterium_locations``.
    """

    stable_locations = OrderedDict(
        sorted(bacterium_locations.items(), key=lambda kv: kv[0])
    )
    payload: dict[str, Any] = {
        "bacterium_locations": dict(stable_locations),
    }
    if advanced_parameters:
        payload.update(dict(advanced_parameters))
    return payload
