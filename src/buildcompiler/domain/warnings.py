"""Domain warning contracts."""

from dataclasses import dataclass, field
from typing import Any

from .build_stage import BuildStage


@dataclass
class BuildWarning:
    """Structured non-fatal warning for planning/execution/reporting."""

    code: str
    message: str
    stage: BuildStage | None = None
    source_identity: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
