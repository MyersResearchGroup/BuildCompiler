"""Planning contracts for full-build planning output."""

from dataclasses import dataclass, field
from typing import Any

from buildcompiler.domain import BuildRequest, BuildWarning, DesignKind


@dataclass
class UnsupportedPlanningRecord:
    source_identity: str
    source_display_id: str | None
    source_kind: DesignKind
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildPlan:
    lvl2_requests: list[BuildRequest] = field(default_factory=list)
    lvl1_requests: list[BuildRequest] = field(default_factory=list)
    domestication_requests: list[BuildRequest] = field(default_factory=list)
    unsupported: list[UnsupportedPlanningRecord] = field(default_factory=list)
    warnings: list[BuildWarning] = field(default_factory=list)
