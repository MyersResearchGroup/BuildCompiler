"""Protocol artifact boundaries for optional file output."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from buildcompiler.api import ProtocolMode, ProtocolOptions


@dataclass
class ProtocolArtifact:
    kind: str
    path: Path | None = None
    content: str | dict[str, object] | list[dict[str, object]] | None = None
    metadata: dict[str, object] = field(default_factory=dict)


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

    should_write = (
        options.mode in {ProtocolMode.MANUAL, ProtocolMode.AUTOMATED}
        and options.results_dir is not None
    )
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
