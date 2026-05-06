"""Design classification helpers for planning."""

from __future__ import annotations

import re

import sbol2

from buildcompiler.domain import BuildRequest, BuildStage, DesignKind
from buildcompiler.planning.models import UnsupportedPlanningRecord
from buildcompiler.planning.validation import classify_part_role


def _stable_slug(identity: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", identity.lower()).strip("-")[-48:]


def request_id_for(
    stage: BuildStage,
    source_identity: str,
    source_display_id: str | None,
    *,
    variant_index: int | None = None,
) -> str:
    base = source_display_id or _stable_slug(source_identity)
    rid = f"{stage.value}:{base}"
    if variant_index is not None:
        rid = f"{rid}:v{variant_index}"
    return rid


def classify_non_combinatorial(
    design: object,
) -> BuildRequest | UnsupportedPlanningRecord:
    if isinstance(design, sbol2.ModuleDefinition):
        return BuildRequest(
            request_id_for(BuildStage.ASSEMBLY_LVL2, design.identity, design.displayId),
            BuildStage.ASSEMBLY_LVL2,
            design.identity,
            design.displayId,
            DesignKind.MODULE_DEFINITION,
        )

    if isinstance(design, sbol2.ComponentDefinition):
        count = len(design.components)
        if count > 1:
            return BuildRequest(
                request_id_for(
                    BuildStage.ASSEMBLY_LVL1, design.identity, design.displayId
                ),
                BuildStage.ASSEMBLY_LVL1,
                design.identity,
                design.displayId,
                DesignKind.COMPONENT_DEFINITION,
            )
        if count <= 1 and classify_part_role(design) is not None:
            return BuildRequest(
                request_id_for(
                    BuildStage.DOMESTICATION, design.identity, design.displayId
                ),
                BuildStage.DOMESTICATION,
                design.identity,
                design.displayId,
                DesignKind.COMPONENT_DEFINITION,
            )
        return UnsupportedPlanningRecord(
            design.identity,
            design.displayId,
            DesignKind.COMPONENT_DEFINITION,
            "ComponentDefinition is single/empty with unsupported role.",
            {"component_count": count, "roles": list(design.roles)},
        )

    return UnsupportedPlanningRecord(
        getattr(design, "identity", str(design)),
        getattr(design, "displayId", None),
        DesignKind.UNSUPPORTED,
        f"Unsupported design type: {type(design).__name__}",
    )
