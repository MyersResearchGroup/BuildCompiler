"""Build request contract dataclass."""

from dataclasses import dataclass, field
from typing import Any

from .build_stage import BuildStage
from .design import DesignKind


@dataclass
class BuildRequest:
    """Planner-produced request for a single stage/source item."""

    id: str
    stage: BuildStage
    source_identity: str
    source_display_id: str | None
    source_kind: DesignKind
    parent_group: str | None = None
    variant_index: int | None = None
    constraints: dict[str, Any] = field(default_factory=dict)
