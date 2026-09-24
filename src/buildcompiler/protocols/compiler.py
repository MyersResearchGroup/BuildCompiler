"""Compile requests into plans, review documents and standalone robot scripts."""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType

from buildcompiler.domain.protocol_requests import (
    AssemblyRequest,
    PlatingRequest,
    ProtocolRequest,
    TransformationRequest,
)
from buildcompiler.protocols.backends.markdown import render_markdown
from buildcompiler.protocols.backends.opentrons import TargetProfile, render_python
from buildcompiler.protocols.methods.assembly import (
    AssemblyConfig,
    OpentronsAssemblyProfile,
    allocate_assembly,
    plan_assembly,
)
from buildcompiler.protocols.methods.plating import (
    OpentronsPlatingProfile,
    PlatingConfig,
    allocate_plating,
    plan_plating,
    plating_layout,
)
from buildcompiler.protocols.methods.transformation import (
    OpentronsTransformationProfile,
    TransformationConfig,
    allocate_transformation,
    plan_transformation,
)
from buildcompiler.protocols.models import OutputManifest, ProtocolPlan


def _json(value: object) -> str:
    """Use the same deterministic encoding for every JSON artifact."""
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


@dataclass(frozen=True, slots=True, kw_only=True)
class CompiledProtocol:
    """A located plan and its files; compilation itself performs no file writes."""

    plan: ProtocolPlan
    script: str
    markdown: str
    manifest: OutputManifest
    files: Mapping[str, str]

    def __post_init__(self) -> None:
        for name in self.files:
            if (
                not name
                or name in (".", "..")
                or Path(name).name != name
                or "\\" in name
            ):
                raise ValueError("Artifact names must be plain filenames.")
        object.__setattr__(self, "files", MappingProxyType(dict(self.files)))

    def write(
        self, directory: str | Path, *, overwrite: bool = False
    ) -> tuple[Path, ...]:
        """Write the complete bundle, refusing existing files unless requested."""
        directory = Path(directory)
        paths = tuple(directory / name for name in self.files)
        if not overwrite and any(path.exists() for path in paths):
            raise FileExistsError("One or more output artifacts already exist.")
        directory.mkdir(parents=True, exist_ok=True)
        for path, content in zip(paths, self.files.values(), strict=True):
            with path.open("w" if overwrite else "x", encoding="utf-8") as handle:
                handle.write(content)
        return paths


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolCompiler:
    """Select a method, place its samples and render both outputs from one plan."""

    assembly: AssemblyConfig = AssemblyConfig()
    transformation: TransformationConfig = TransformationConfig()
    plating: PlatingConfig = PlatingConfig()

    def plan(
        self, request: ProtocolRequest, *, inputs: OutputManifest | None = None
    ) -> ProtocolPlan:
        """Expand a request into operations without assigning hardware locations."""
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
        profile: TargetProfile | None = None,
        inputs: OutputManifest | None = None,
    ) -> CompiledProtocol:
        """Return an allocated plan and files, leaving writing and simulation explicit."""
        plan = self.plan(request, inputs=inputs)
        if isinstance(request, AssemblyRequest):
            profile = profile or OpentronsAssemblyProfile()
            if not isinstance(profile, OpentronsAssemblyProfile):
                raise TypeError("Assembly requires an OpentronsAssemblyProfile.")
            method, config = "assembly", self.assembly
            plan = allocate_assembly(plan, profile=profile)
            handoff_name = "transformation_input.json"
            handoff = plan.output_manifest().plasmid_locations()
        elif isinstance(request, TransformationRequest):
            profile = profile or OpentronsTransformationProfile()
            if not isinstance(profile, OpentronsTransformationProfile):
                raise TypeError(
                    "Transformation requires an OpentronsTransformationProfile."
                )
            method, config = "transformation", self.transformation
            plan = allocate_transformation(plan, profile=profile, inputs=inputs)
            handoff_name = "plating_input.json"
            handoff = {
                "bacterium_locations": plan.output_manifest().bacterium_locations()
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
            plan = allocate_plating(plan, profile=profile, inputs=inputs)
            handoff_name = "plating_layout.json"
            handoff = plating_layout(plan, dilution_factor=config.dilution_factor)
        script = render_python(plan, profile=profile)
        markdown = render_markdown(plan)
        manifest = plan.output_manifest()
        metadata = {
            "schema_version": "1.0",
            "method": method,
            "configuration": asdict(config),
            "target_profile": asdict(profile),
            "plan": {
                **asdict(plan),
                "steps": [
                    {"kind": type(step).__name__, **asdict(step)} for step in plan.steps
                ],
            },
        }
        return CompiledProtocol(
            plan=plan,
            script=script,
            markdown=markdown,
            manifest=manifest,
            files={
                "protocol.py": script,
                "protocol.md": markdown,
                "manifest.json": _json(manifest.to_dict()),
                "compilation.json": _json(metadata),
                handoff_name: _json(handoff),
            },
        )
