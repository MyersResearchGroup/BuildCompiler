"""Compile stage requests and physical handoffs without rerunning SBOL operations."""

from buildcompiler.domain import StageResult, StageStatus
from buildcompiler.domain.protocol_requests import (
    AssemblyRequest,
    TransformationRequest,
)
from buildcompiler.protocols.allocation.models import OutputManifest
from buildcompiler.protocols import (
    AssemblyConfig,
    CompiledProtocol,
    OpentronsAssemblyProfile,
    ProtocolCompiler,
    TransformationConfig,
    OpentronsTransformationProfile,
    PlatingConfig,
    PlatingRequest,
    OpentronsPlatingProfile,
)


def compile_assembly(
    result: StageResult,
    *,
    config: AssemblyConfig = AssemblyConfig(),
    profile: OpentronsAssemblyProfile = OpentronsAssemblyProfile(),
) -> CompiledProtocol:
    """Allocate the stage's complete batch once and return in-memory artifacts."""
    if result.status not in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS):
        raise ValueError("Only successful stage outputs can be compiled.")
    if not result.protocol_requests:
        raise ValueError("The stage contains no typed assembly requests.")
    if any(
        not isinstance(request, AssemblyRequest) for request in result.protocol_requests
    ):
        raise TypeError("The stage contains requests for another method.")
    reactions = tuple(
        reaction
        for request in result.protocol_requests
        for reaction in request.reactions
    )
    request = AssemblyRequest(
        id=result.id, reactions=reactions, source_stage_id=result.id
    )
    return ProtocolCompiler(assembly=config).compile(request, profile=profile)


def compile_transformation(
    result: StageResult,
    *,
    config: TransformationConfig = TransformationConfig(),
    profile: OpentronsTransformationProfile = OpentronsTransformationProfile(),
    inputs: OutputManifest | None = None,
) -> CompiledProtocol:
    """Compile the complete transformation batch against an optional assembly manifest."""
    if result.status not in (StageStatus.SUCCESS, StageStatus.PARTIAL_SUCCESS):
        raise ValueError("Only successful stage outputs can be compiled.")
    if not result.protocol_requests:
        raise ValueError("The stage contains no typed transformation requests.")
    if any(
        not isinstance(request, TransformationRequest)
        for request in result.protocol_requests
    ):
        raise TypeError("The stage contains requests for another method.")
    request = TransformationRequest(
        id=result.id,
        source_stage_id=result.id,
        reactions=tuple(
            reaction
            for request in result.protocol_requests
            for reaction in request.reactions
        ),
    )
    return ProtocolCompiler(transformation=config).compile(
        request, profile=profile, inputs=inputs
    )


def compile_plating(
    inputs: OutputManifest,
    *,
    request_id: str = "plating",
    config: PlatingConfig = PlatingConfig(),
    profile: OpentronsPlatingProfile = OpentronsPlatingProfile(),
) -> CompiledProtocol:
    """Compile plating for the exact physical samples in a transformation manifest."""
    request = PlatingRequest(
        id=request_id,
        source_stage_id=inputs.protocol_id,
        sample_ids=tuple(sample.id for sample in inputs.samples),
    )
    return ProtocolCompiler(plating=config).compile(
        request, profile=profile, inputs=inputs
    )
