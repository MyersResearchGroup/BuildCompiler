"""Domain contracts for BuildCompiler clean architecture."""

from .approvals import ApprovalStatus, RequiredApproval
from .build_request import BuildRequest
from .build_result import FullBuildResult, StageResult
from .build_stage import BuildStage
from .design import DesignKind
from .material_state import MaterialState
from .missing_input import MissingBuildInput
from .plasmid import IndexedBackbone, IndexedPlasmid
from .reagent import IndexedReagent
from .status import BuildStatus, StageStatus
from .warnings import BuildWarning

__all__ = [
    "ApprovalStatus",
    "BuildRequest",
    "BuildResult",
    "BuildStage",
    "BuildStatus",
    "BuildWarning",
    "DesignKind",
    "FullBuildResult",
    "IndexedBackbone",
    "IndexedPlasmid",
    "IndexedReagent",
    "MaterialState",
    "MissingBuildInput",
    "RequiredApproval",
    "StageResult",
    "StageStatus",
]

BuildResult = FullBuildResult
