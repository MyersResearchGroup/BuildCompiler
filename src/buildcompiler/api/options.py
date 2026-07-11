"""Build options contracts for full_build configuration."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal


class ProtocolMode(str, Enum):
    """Protocol generation mode."""

    NONE = "none"
    MANUAL = "manual"
    AUTOMATED = "automated"


@dataclass
class CombinatorialOptions:
    max_variants: int = 256
    allow_large_expansion: bool = False


@dataclass
class Lvl2SearchOptions:
    max_exhaustive_region_count: int = 4
    allow_large_order_search: bool = False


@dataclass
class PlanningOptions:
    combinatorial: CombinatorialOptions = field(default_factory=CombinatorialOptions)
    lvl2_search: Lvl2SearchOptions = field(default_factory=Lvl2SearchOptions)


@dataclass
class ExecutionOptions:
    max_iterations: int = 5
    continue_on_error: bool = False


@dataclass
class SelectionOptions:
    prefer_existing_collection_material: bool = True
    prefer_higher_material_state: bool = True


@dataclass
class ProtocolOptions:
    mode: ProtocolMode = ProtocolMode.NONE
    simulate: bool = False
    results_dir: str | Path | None = None


@dataclass
class ReportingOptions:
    include_detailed_report: bool = False
    include_rejected_routes: bool = True
    max_rejected_routes: int = 3


@dataclass
class ApprovalOptions:
    approved_processes: set[str] = field(default_factory=set)
    approved_approval_ids: set[str] = field(default_factory=set)
    scope: Literal["run", "persistent"] = "run"


@dataclass
class ReagentOptions:
    allow_reagent_purchase: bool = False
    default_restriction_enzyme: str = "BsaI"
    default_ligase: str = "T4_DNA_ligase"


@dataclass
class DomesticationOptions:
    allow_sequence_domestication_edits: bool = False


@dataclass
class TransformationOptions:
    enabled: bool = False
    chassis_identity: str | None = None
    chassis_display_id: str | None = None


@dataclass
class BuildOptions:
    planning: PlanningOptions = field(default_factory=PlanningOptions)
    execution: ExecutionOptions = field(default_factory=ExecutionOptions)
    selection: SelectionOptions = field(default_factory=SelectionOptions)
    protocol: ProtocolOptions = field(default_factory=ProtocolOptions)
    reporting: ReportingOptions = field(default_factory=ReportingOptions)
    approvals: ApprovalOptions = field(default_factory=ApprovalOptions)
    reagents: ReagentOptions = field(default_factory=ReagentOptions)
    domestication: DomesticationOptions = field(default_factory=DomesticationOptions)
    transformation: TransformationOptions = field(default_factory=TransformationOptions)
