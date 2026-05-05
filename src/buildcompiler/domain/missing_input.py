"""Missing input/blocker contracts."""

from dataclasses import dataclass, field
from typing import Literal

from .build_stage import BuildStage

MissingKind = Literal[
    "engineered_region",
    "promoter",
    "rbs",
    "cds",
    "terminator",
    "backbone",
    "restriction_enzyme",
    "ligase",
    "reagent",
]


@dataclass
class MissingBuildInput:
    """Expected blocker produced when build inputs are unavailable."""

    source_stage: BuildStage
    source_design_identity: str
    missing_identity: str
    missing_display_id: str | None
    missing_kind: MissingKind
    required_stage: BuildStage | Literal["fatal"]
    reason: str
    candidates_tried: list[str] = field(default_factory=list)
