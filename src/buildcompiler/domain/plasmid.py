"""Normalized plasmid/backbone records."""

from dataclasses import dataclass, field
from typing import Any

from .material_state import MaterialState


@dataclass
class IndexedPlasmid:
    """Inventory/index record for a plasmid-like material."""

    identity: str
    display_id: str | None = None
    name: str | None = None
    state: MaterialState = MaterialState.PLANNED
    roles: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    sbol_component: Any | None = None


@dataclass
class IndexedBackbone:
    """Inventory/index record for a backbone material."""

    identity: str
    display_id: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    sbol_component: Any | None = None
