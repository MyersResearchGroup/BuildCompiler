"""Protocol artifact boundaries for optional file output."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from buildcompiler.api.options import ProtocolMode, ProtocolOptions
from buildcompiler.domain.build_result import StageResult


@dataclass
class ProtocolArtifact:
    kind: str
    path: Path | None = None
    content: str | dict[str, object] | list[dict[str, object]] | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ProtocolBundle:
    """Deterministic collection of requested protocol deliverables."""

    status: str
    artifacts: dict[str, ProtocolArtifact] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _artifact_filename(*, basename: str, kind: str) -> str:
    safe_kind = kind.replace(" ", "_").lower()
    return f"{basename}_{safe_kind}.json"


def maybe_write_protocol_artifacts(
    *,
    payloads: dict[str, object],
    options: ProtocolOptions,
    basename: str = "buildcompiler_protocol",
) -> dict[str, ProtocolArtifact]:
    """Return in-memory protocol payloads and optionally write them to disk."""

    file_mode = options.mode in {ProtocolMode.MANUAL, ProtocolMode.AUTOMATED}
    if file_mode and options.results_dir is None:
        raise ValueError(
            "ProtocolOptions.results_dir is required for file output modes."
        )
    should_write = file_mode
    output_dir = Path(options.results_dir) if should_write else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, ProtocolArtifact] = {}
    for kind, payload in payloads.items():
        artifact = ProtocolArtifact(kind=kind, content=payload)
        if output_dir is not None:
            path = output_dir / _artifact_filename(basename=basename, kind=kind)
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
            )
            artifact.path = path
            artifact.metadata["written"] = True
        else:
            artifact.metadata["written"] = False
        artifacts[kind] = artifact

    return artifacts


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _manual_protocol(*, stage: str, payload: object) -> str:
    instructions = {
        "assembly_lvl1": [
            "Confirm each source plasmid and backbone identity against the run sheet.",
            "Prepare the Golden Gate reaction using the volumes and replicates in Parameters.",
            "Run the validated restriction/ligation thermocycler program.",
        ],
        "assembly_lvl2": [
            "Confirm the ordered level-1 plasmids and level-2 backbone.",
            "Prepare the Golden Gate reaction using the volumes and replicates in Parameters.",
            "Run the validated restriction/ligation thermocycler program.",
        ],
        "domestication": [
            "Verify the generated insert sequence and intended replacement coordinates.",
            "Prepare the restriction/ligation reaction described by the canonical specification.",
            "Sequence-verify the resulting plasmid before promoting its material state.",
        ],
        "transformation": [
            "Combine competent cells and DNA using the quantities in Parameters.",
            "Apply the specified heat-shock temperature and duration.",
            "Recover at the specified temperature and duration before plating.",
        ],
        "plating": [
            "Verify source wells, destination wells, medium, and antibiotic.",
            "Transfer the specified volume and incubate using the listed conditions.",
        ],
    }.get(stage, ["Execute the canonical specification using a validated local SOP."])
    lines = [
        f"# {stage.replace('_', ' ').title()} Protocol",
        "",
        "## Procedure",
        "",
    ]
    lines.extend(
        f"{index}. {instruction}" for index, instruction in enumerate(instructions, 1)
    )
    lines.extend(
        [
            "",
            "Verify reagent concentrations, controls, labware, and local biosafety requirements before execution.",
            "",
            "## Canonical specification",
            "",
            "```json",
            json.dumps(payload, indent=2, sort_keys=True),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _generate_automated_protocol(*, stage: str, payload: object) -> str:
    try:
        from pudu.generate_protocol import generate_protocol
    except ImportError as exc:
        from buildcompiler.adapters.opentrons import OptionalAutomationDependencyError

        raise OptionalAutomationDependencyError(
            "Install synbio-buildcompiler[automation] to generate automated protocols."
        ) from exc

    protocol_type = {
        "assembly_lvl1": "assembly",
        "assembly_lvl2": "assembly",
        "domestication": "assembly",
        "transformation": "transformation",
        "plating": "plating",
    }.get(stage)
    if protocol_type is None:
        raise ValueError(f"No automated protocol mapping exists for stage: {stage}")
    kwargs: dict[str, object] = {
        "protocol_data": payload,
        "protocol_type": protocol_type,
        "metadata": {
            "protocolName": f"BuildCompiler {stage.replace('_', ' ').title()}",
            "author": "BuildCompiler",
            "description": "Generated from a canonical BuildCompiler protocol specification.",
        },
    }
    if protocol_type == "assembly":
        kwargs["assembly_subtype"] = "SBOL"
    return generate_protocol(**kwargs)


def _write_text(path: Path, content: str) -> ProtocolArtifact:
    path.write_text(content, encoding="utf-8")
    return ProtocolArtifact(
        kind=path.suffix.lstrip("."),
        path=path,
        content=content,
        metadata={"written": True, "sha256": _sha256(content)},
    )


def build_protocol_bundle(
    *, stage_results: list[StageResult], options: ProtocolOptions
) -> ProtocolBundle:
    """Build canonical JSON/manual artifacts at the orchestration boundary."""

    payloads = [
        (result.stage.value, result.json_intermediate)
        for result in stage_results
        if result.json_intermediate is not None
        and result.status.value in {"success", "partial_success"}
    ]
    manifest_entries: list[dict[str, object]] = []
    artifacts: dict[str, ProtocolArtifact] = {}
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "mode": options.mode.value,
        "simulate": options.simulate,
        "software": {
            "python": platform.python_version(),
            "synbio-buildcompiler": _package_version("synbio-buildcompiler"),
            "pudupy": _package_version("pudupy"),
            "opentrons": _package_version("opentrons"),
        },
        "artifacts": manifest_entries,
    }
    if options.mode == ProtocolMode.NONE:
        for index, (stage, payload) in enumerate(payloads, start=1):
            key = f"{stage}_{index:03d}_json"
            content = _canonical_json(payload)
            artifacts[key] = ProtocolArtifact(
                kind="json",
                content=payload,
                metadata={"written": False, "sha256": _sha256(content)},
            )
        return ProtocolBundle(status="success", artifacts=artifacts, manifest=manifest)

    if options.results_dir is None:
        raise ValueError(
            "ProtocolOptions.results_dir is required for file output modes."
        )
    output_dir = Path(options.results_dir)
    if output_dir.exists() and any(output_dir.iterdir()) and not options.overwrite:
        raise FileExistsError(
            f"Protocol results directory is not empty: {output_dir}. "
            "Set ProtocolOptions.overwrite=True to replace known bundle files."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    stage_counts: dict[str, int] = {}
    for stage, payload in payloads:
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        basename = f"{stage}_{stage_counts[stage]:03d}"
        json_content = _canonical_json(payload)
        json_artifact = _write_text(output_dir / f"{basename}.json", json_content)
        json_artifact.content = payload
        artifacts[f"{basename}_json"] = json_artifact
        manual_artifact = _write_text(
            output_dir / f"{basename}.md",
            _manual_protocol(stage=stage, payload=payload),
        )
        artifacts[f"{basename}_manual"] = manual_artifact
        if options.mode == ProtocolMode.AUTOMATED:
            script_artifact = _write_text(
                output_dir / f"{basename}.py",
                _generate_automated_protocol(stage=stage, payload=payload),
            )
            artifacts[f"{basename}_automated"] = script_artifact
            if options.simulate:
                from buildcompiler.adapters.opentrons import OpentronsSimulationAdapter

                simulation = OpentronsSimulationAdapter().simulate(
                    script_artifact.path,
                    options=options,
                )
                log_content = "".join(simulation.logs)
                log_artifact = _write_text(
                    output_dir / f"{basename}.simulate.log", log_content
                )
                log_artifact.metadata.update(simulation.metadata)
                artifacts[f"{basename}_simulation"] = log_artifact

    for name, artifact in sorted(artifacts.items()):
        manifest_entries.append(
            {
                "name": name,
                "kind": artifact.kind,
                "path": artifact.path.name if artifact.path else None,
                "sha256": artifact.metadata["sha256"],
            }
        )

    manifest_content = _canonical_json(manifest)
    manifest_artifact = _write_text(
        output_dir / "protocol_manifest.json", manifest_content
    )
    manifest_artifact.content = manifest
    artifacts["manifest"] = manifest_artifact
    return ProtocolBundle(status="success", artifacts=artifacts, manifest=manifest)
