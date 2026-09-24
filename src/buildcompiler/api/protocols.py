"""Compile stage requests and physical handoffs without rerunning SBOL operations."""

from dataclasses import fields

from buildcompiler.domain import StageResult, StageStatus
from buildcompiler.domain.protocol_requests import (
    AssemblyRequest,
    TransformationRequest,
)
from buildcompiler.protocols import (
    AssemblyConfig,
    CompiledProtocol,
    OpentronsAssemblyProfile,
    OpentronsPlatingProfile,
    OpentronsTransformationProfile,
    PlatingConfig,
    PlatingRequest,
    ProtocolCompiler,
    TransformationConfig,
)
from buildcompiler.protocols.backends import ProtocolBackend
from buildcompiler.protocols.methods.plating import bacterium_manifest_from_json
from buildcompiler.protocols.models import OutputManifest


def compile_assembly(
    result: StageResult,
    *,
    config: AssemblyConfig = AssemblyConfig(),
    profile: OpentronsAssemblyProfile = OpentronsAssemblyProfile(),
    backend: ProtocolBackend = "opentrons_ot2_python",
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
    return ProtocolCompiler(assembly=config).compile(
        request, profile=profile, backend=backend
    )


def compile_transformation(
    result: StageResult,
    *,
    config: TransformationConfig = TransformationConfig(),
    profile: OpentronsTransformationProfile = OpentronsTransformationProfile(),
    inputs: OutputManifest | None = None,
    backend: ProtocolBackend = "opentrons_ot2_python",
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
        request, profile=profile, inputs=inputs, backend=backend
    )


def compile_plating(
    inputs: OutputManifest,
    *,
    request_id: str = "plating",
    config: PlatingConfig = PlatingConfig(),
    profile: OpentronsPlatingProfile = OpentronsPlatingProfile(),
    backend: ProtocolBackend = "opentrons_ot2_python",
) -> CompiledProtocol:
    """Compile plating for the exact physical samples in a transformation manifest."""
    request = PlatingRequest(
        id=request_id,
        source_stage_id=inputs.protocol_id,
        sample_ids=tuple(sample.id for sample in inputs.samples),
    )
    return ProtocolCompiler(plating=config).compile(
        request, profile=profile, inputs=inputs, backend=backend
    )


def compile_plating_json(
    payload, *, advanced_params=None, backend: ProtocolBackend = "opentrons_ot2_python"
):
    """Compile a JSON plating payload with explicitly supplied overrides."""

    parameters = dict(payload)
    parameters.update(advanced_params or {})
    inputs = bacterium_manifest_from_json(parameters)
    parameters.pop("bacterium_locations")
    name = parameters.pop("protocol_name", "BuildCompiler Plating")
    config_names = {f.name for f in fields(PlatingConfig)}
    profile_names = {f.name for f in fields(OpentronsPlatingProfile)}
    config = PlatingConfig(
        **{key: value for key, value in parameters.items() if key in config_names}
    )
    profile = OpentronsPlatingProfile(
        **{key: value for key, value in parameters.items() if key in profile_names}
    )
    unknown = set(parameters) - config_names - profile_names
    if unknown:
        raise ValueError(
            f"Unsupported native plating parameters: {sorted(unknown)}. Use a supported target profile."
        )
    return compile_plating(
        inputs, request_id=name, config=config, profile=profile, backend=backend
    )
