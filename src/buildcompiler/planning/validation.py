"""Deterministic validation helpers for level-1 designs."""

from __future__ import annotations

from collections import Counter

import sbol2

from buildcompiler.constants import PART_ROLES
from buildcompiler.domain import BuildStage, BuildWarning

ROLE_TO_NAME = {
    "http://identifiers.org/so/SO:0000167": "promoter",
    "http://identifiers.org/so/SO:0000139": "rbs",
    "http://identifiers.org/so/SO:0000316": "cds",
    "http://identifiers.org/so/SO:0000141": "terminator",
}
CANONICAL_ROLE_ORDER = ["promoter", "rbs", "cds", "terminator"]


def classify_part_role(component_definition: sbol2.ComponentDefinition) -> str | None:
    matches = sorted(
        ROLE_TO_NAME[role] for role in component_definition.roles if role in PART_ROLES
    )
    if len(matches) != 1:
        return None
    return matches[0]


def validate_lvl1_cardinality(
    component_definition: sbol2.ComponentDefinition,
) -> tuple[bool, list[BuildWarning]]:
    warnings: list[BuildWarning] = []
    if len(component_definition.components) != 4:
        warnings.append(
            BuildWarning(
                code="lvl1.variable_length",
                message="Level-1 v1 requires exactly four components.",
                stage=BuildStage.ASSEMBLY_LVL1,
                source_identity=component_definition.identity,
            )
        )
        return False, warnings

    roles = []
    for comp in component_definition.components:
        target = (
            comp.doc.find(comp.definition)
            if getattr(comp, "doc", None) is not None
            else None
        )
        if not isinstance(target, sbol2.ComponentDefinition):
            continue
        role = classify_part_role(target)
        if role is not None:
            roles.append(role)

    counts = Counter(roles)
    ok = True
    for required in CANONICAL_ROLE_ORDER:
        if counts[required] != 1:
            ok = False
            warnings.append(
                BuildWarning(
                    code="lvl1.invalid_cardinality",
                    message=f"Expected exactly one {required}, found {counts[required]}.",
                    stage=BuildStage.ASSEMBLY_LVL1,
                    source_identity=component_definition.identity,
                    metadata={"role": required, "count": counts[required]},
                )
            )
    return ok, warnings


def ordered_lvl1_parts(
    component_definition: sbol2.ComponentDefinition,
) -> tuple[list[str], list[BuildWarning]]:
    warnings: list[BuildWarning] = []
    role_to_identity: dict[str, str] = {}
    comp_by_identity: dict[str, sbol2.Component] = {}
    for comp in component_definition.components:
        target = (
            comp.doc.find(comp.definition)
            if getattr(comp, "doc", None) is not None
            else None
        )
        if isinstance(target, sbol2.ComponentDefinition):
            role = classify_part_role(target)
            if role:
                role_to_identity[role] = target.identity
                comp_by_identity[target.identity] = comp

    if len(role_to_identity) < 4:
        return [
            role_to_identity[r] for r in CANONICAL_ROLE_ORDER if r in role_to_identity
        ], warnings

    try:
        ordered_components = list(component_definition.getInSequentialOrder())
    except Exception:
        ordered_components = []

    if len(ordered_components) == 4:
        ordered_part_ids = []
        ordered_roles = []
        for comp in ordered_components:
            target = (
                comp.doc.find(comp.definition)
                if getattr(comp, "doc", None) is not None
                else None
            )
            if isinstance(target, sbol2.ComponentDefinition):
                role = classify_part_role(target)
                if role:
                    ordered_roles.append(role)
                    ordered_part_ids.append(target.identity)
        if len(ordered_part_ids) == 4 and set(ordered_roles) == set(
            CANONICAL_ROLE_ORDER
        ):
            if ordered_roles != CANONICAL_ROLE_ORDER:
                warnings.append(
                    BuildWarning(
                        code="lvl1.non_canonical_order",
                        message="SBOL order is non-canonical and will be preserved.",
                        stage=BuildStage.ASSEMBLY_LVL1,
                        source_identity=component_definition.identity,
                        metadata={"ordered_roles": ordered_roles},
                    )
                )
            return ordered_part_ids, warnings

    warnings.append(
        BuildWarning(
            code="lvl1.ambiguous_order",
            message="SBOL order unavailable or ambiguous; using canonical order.",
            stage=BuildStage.ASSEMBLY_LVL1,
            source_identity=component_definition.identity,
        )
    )
    return [role_to_identity[role] for role in CANONICAL_ROLE_ORDER], warnings
