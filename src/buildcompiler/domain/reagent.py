"""Normalized reagent record contracts."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndexedReagent:
    """Inventory/index record for reagents."""

    identity: str
    display_id: str | None = None
    name: str | None = None
    reagent_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
