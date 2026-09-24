"""Compilation facade; planning, rendering, writing and simulation are separate."""

import json
from dataclasses import asdict, dataclass

from buildcompiler.domain.protocol_requests import (
    AssemblyRequest,
    TransformationRequest,
    PlatingRequest,
    ProtocolRequest,
)

from buildcompiler.protocols.allocation.models import (
    AllocatedProtocolPlan,
    OutputManifest,
)
from buildcompiler.protocols.allocation.plating import plating_layout
from buildcompiler.protocols.artifacts import ArtifactBundle, ProtocolArtifact
from buildcompiler.protocols.attribution import PUDU_REVISION
from buildcompiler.protocols.backends.markdown import render_markdown
from buildcompiler.protocols.backends.opentrons.allocation import allocate
from buildcompiler.protocols.backends.opentrons.lowering import lower
from buildcompiler.protocols.backends.opentrons.profile import (
    OpentronsAssemblyProfile,
    OpentronsTransformationProfile,
    OpentronsPlatingProfile,
)
from buildcompiler.protocols.backends.opentrons.plating import (
    allocate_plating,
    lower_plating,
)
from buildcompiler.protocols.backends.opentrons.transformation import (
    allocate_transformation,
    lower_transformation,
)
from buildcompiler.protocols.backends.opentrons.program import OpentronsProgram
from buildcompiler.protocols.backends.opentrons.rendering import render_python
from buildcompiler.protocols.config import AssemblyConfig
from buildcompiler.protocols.methods.assembly import plan_assembly
from buildcompiler.protocols.methods.transformation import plan_transformation
from buildcompiler.protocols.methods.transformation_config import TransformationConfig
from buildcompiler.protocols.methods.plating import plan_plating
from buildcompiler.protocols.methods.plating_config import PlatingConfig
from buildcompiler.protocols.plans import ProtocolPlan


@dataclass(frozen=True, slots=True, kw_only=True)
class CompiledProtocol:
    allocation: AllocatedProtocolPlan
    program: OpentronsProgram
    script: str
    markdown: str
    manifest: OutputManifest
    artifacts: ArtifactBundle


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolCompiler:
    assembly: AssemblyConfig = AssemblyConfig()
    transformation: TransformationConfig = TransformationConfig()
    plating: PlatingConfig = PlatingConfig()

    def plan(
        self,
        request: ProtocolRequest,
        *,
        inputs: OutputManifest | None = None,
    ) -> ProtocolPlan:
        if isinstance(request, AssemblyRequest):
            if inputs is not None:
                raise ValueError(
                    "Assembly does not accept an upstream output manifest."
                )
            return plan_assembly(request, config=self.assembly)
        if isinstance(request, TransformationRequest):
            return plan_transformation(
                request,
                config=self.transformation,
                inputs=inputs.samples if inputs is not None else None,
            )
        if isinstance(request, PlatingRequest):
            if inputs is None:
                raise ValueError("Plating requires a source manifest.")
            return plan_plating(request, config=self.plating, inputs=inputs.samples)
        raise TypeError(f"Unsupported protocol request: {type(request).__name__}")

    def compile(
        self,
        request: ProtocolRequest,
        *,
        profile: OpentronsAssemblyProfile
        | OpentronsTransformationProfile
        | OpentronsPlatingProfile
        | None = None,
        inputs: OutputManifest | None = None,
    ) -> CompiledProtocol:
        plan = self.plan(request, inputs=inputs)
        if isinstance(request, AssemblyRequest):
            profile = profile or OpentronsAssemblyProfile()
            if not isinstance(profile, OpentronsAssemblyProfile):
                raise TypeError("Assembly requires an OpentronsAssemblyProfile.")
            method, config = "assembly", self.assembly
            allocated = allocate(plan, profile=profile)
            program = lower(allocated, profile=profile)
            handoff_name = "transformation_input.json"
            handoff = allocated.output_manifest().plasmid_locations()
        elif isinstance(request, TransformationRequest):
            profile = profile or OpentronsTransformationProfile()
            if not isinstance(profile, OpentronsTransformationProfile):
                raise TypeError(
                    "Transformation requires an OpentronsTransformationProfile."
                )
            method, config = "transformation", self.transformation
            allocated = allocate_transformation(plan, profile=profile, inputs=inputs)
            program = lower_transformation(allocated, profile=profile)
            handoff_name = "plating_input.json"
            handoff = {
                "bacterium_locations": allocated.output_manifest().bacterium_locations()
            }
        else:
            profile = profile or OpentronsPlatingProfile()
            if not isinstance(profile, OpentronsPlatingProfile):
                raise TypeError("Plating requires an OpentronsPlatingProfile.")
            method, config = "plating", self.plating
            if config.dilution_volume > 100:
                raise ValueError(
                    "Dilution volume exceeds the supported plate capacity."
                )
            allocated = allocate_plating(plan, profile=profile, inputs=inputs)
            program = lower_plating(allocated, profile=profile)
            handoff_name = "plating_layout.json"
            handoff = plating_layout(allocated, dilution_factor=config.dilution_factor)
        script = render_python(program, name=request.id)
        markdown = render_markdown(plan, allocation=allocated)
        manifest = allocated.output_manifest()
        artifacts = ArtifactBundle(
            artifacts=(
                ProtocolArtifact(
                    name="protocol.py", media_type="text/x-python", content=script
                ),
                ProtocolArtifact(
                    name="compilation.json",
                    media_type="application/json",
                    content=json.dumps(
                        {
                            "schema_version": "1.0",
                            "method": method,
                            "reference_revision": PUDU_REVISION,
                            "configuration": asdict(config),
                            "target_profile": asdict(profile),
                            "plan": {
                                **asdict(plan),
                                "steps": [
                                    {"kind": type(s).__name__, **asdict(s)}
                                    for s in plan.steps
                                ],
                            },
                            "containers": [asdict(c) for c in allocated.containers],
                            "placements": [asdict(p) for p in allocated.placements],
                        },
                        indent=2,
                        sort_keys=True,
                        allow_nan=False,
                    )
                    + "\n",
                ),
                ProtocolArtifact(
                    name="protocol.md", media_type="text/markdown", content=markdown
                ),
                ProtocolArtifact(
                    name="manifest.json",
                    media_type="application/json",
                    content=json.dumps(manifest.to_dict(), indent=2, sort_keys=True)
                    + "\n",
                ),
                ProtocolArtifact(
                    name=handoff_name,
                    media_type="application/json",
                    content=json.dumps(handoff, indent=2, sort_keys=True) + "\n",
                ),
            )
        )
        return CompiledProtocol(
            allocation=allocated,
            program=program,
            script=script,
            markdown=markdown,
            manifest=manifest,
            artifacts=artifacts,
        )
