"""Design classification helpers for planning."""

from __future__ import annotations

import re
from collections import Counter

import sbol2

from buildcompiler.domain import BuildRequest, BuildStage, DesignKind
from buildcompiler.planning.models import UnsupportedPlanningRecord
from buildcompiler.planning.validation import classify_part_role, ordered_lvl1_parts

RECOMMENDED_LVL1_PARTS = ("promoter", "rbs", "cds", "terminator")


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
        region_identities: list[str] = []
        region_part_identities: dict[str, list[str]] = {}
        doc = getattr(design, "doc", None)

        for functional_component in design.functionalComponents:
            region_identity = functional_component.definition
            if not region_identity:
                continue
            region_identities.append(region_identity)
            region_definition = doc.find(region_identity) if doc is not None else None
            if isinstance(region_definition, sbol2.ComponentDefinition):
                ordered_parts, _warnings = ordered_lvl1_parts(region_definition)
                if ordered_parts:
                    region_part_identities[region_identity] = ordered_parts

        constraints = {}
        if region_identities:
            constraints["engineered_region_identities"] = region_identities
        if region_part_identities:
            constraints["lvl1_region_part_identities"] = region_part_identities

        return BuildRequest(
            request_id_for(BuildStage.ASSEMBLY_LVL2, design.identity, design.displayId),
            BuildStage.ASSEMBLY_LVL2,
            design.identity,
            design.displayId,
            DesignKind.MODULE_DEFINITION,
            constraints=constraints,
        )

    if isinstance(design, sbol2.ComponentDefinition):
        count = len(design.components)
        if count > 1:
            observed_roles: list[str] = []
            for component in design.components:
                target = (
                    component.doc.find(component.definition)
                    if getattr(component, "doc", None) is not None
                    else None
                )
                if isinstance(target, sbol2.ComponentDefinition):
                    role = classify_part_role(target)
                    if role is not None:
                        observed_roles.append(role)

            counts = Counter(observed_roles)
            missing = [role for role in RECOMMENDED_LVL1_PARTS if counts[role] != 1]
            has_role_evidence = len(observed_roles) > 0
            if count != 4 or (has_role_evidence and missing):
                return UnsupportedPlanningRecord(
                    design.identity,
                    design.displayId,
                    DesignKind.COMPONENT_DEFINITION,
                    "Warning: Level-1 planning expects exactly four parts (promoter, RBS, CDS, terminator).",
                    {
                        "component_count": count,
                        "observed_role_counts": {
                            role: counts.get(role, 0) for role in RECOMMENDED_LVL1_PARTS
                        },
                        "suggested_parts": list(RECOMMENDED_LVL1_PARTS),
                    },
                )
            ordered_part_identities, ordering_warnings = ordered_lvl1_parts(design)
            constraints = {"ordered_part_identities": ordered_part_identities}
            if ordering_warnings:
                constraints["ordering_warnings"] = [
                    warning.__dict__.copy() for warning in ordering_warnings
                ]

            return BuildRequest(
                request_id_for(
                    BuildStage.ASSEMBLY_LVL1, design.identity, design.displayId
                ),
                BuildStage.ASSEMBLY_LVL1,
                design.identity,
                design.displayId,
                DesignKind.COMPONENT_DEFINITION,
                constraints=constraints,
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
