"""Stage/full-build result contracts."""

from dataclasses import dataclass, field
from typing import Any

from .approvals import RequiredApproval
from .build_stage import BuildStage
from .missing_input import MissingBuildInput
from .plasmid import IndexedPlasmid
from .status import BuildStatus, StageStatus
from .warnings import BuildWarning


@dataclass
class StageResult:
    """Output contract from a single stage invocation."""

    id: str
    stage: BuildStage
    status: StageStatus
    request_ids: list[str] = field(default_factory=list)
    products: list[IndexedPlasmid] = field(default_factory=list)
    missing_inputs: list[MissingBuildInput] = field(default_factory=list)
    required_approvals: list[RequiredApproval] = field(default_factory=list)
    warnings: list[BuildWarning] = field(default_factory=list)
    sbol_document: Any | None = None
    json_intermediate: dict[str, Any] | list[Any] | None = None
    protocol_artifacts: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


@dataclass
class FullBuildResult:
    """Aggregate full-build output contract.

    Neighboring contracts (plan/graph/summary/report) are intentionally typed
    conservatively until their milestone implementations are added.
    """

    status: BuildStatus
    plan: Any
    build_document: Any
    stage_results: list[StageResult] = field(default_factory=list)
    graph: Any = None
    final_products: list[IndexedPlasmid] = field(default_factory=list)
    missing_inputs: list[MissingBuildInput] = field(default_factory=list)
    required_approvals: list[RequiredApproval] = field(default_factory=list)
    warnings: list[BuildWarning] = field(default_factory=list)
    summary: Any = None
    report: Any | None = None
