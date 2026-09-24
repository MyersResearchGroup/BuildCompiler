"""In-memory adapter for compiler-level PUDU assembly JSON payloads."""

from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any

from buildcompiler.domain import (
    AssemblyProtocolSpec,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
)


def _stable_identifier(identity: str, display_id: str | None) -> str:
    return identity or display_id or ""


def assembly_route_to_pudu_json(
    *,
    product_identity: str,
    part_plasmids: Sequence[IndexedPlasmid],
    backbone: IndexedBackbone,
    restriction_enzyme: IndexedReagent,
    ligase: IndexedReagent | None = None,
) -> dict[str, object]:
    """Adapt a selected lvl1 route into legacy-compatible assembly JSON keys."""

    parts_list = [
        _stable_identifier(identity=part.identity, display_id=part.display_id)
        for part in part_plasmids
    ]
    ligase_name = (
        ligase.name
        if ligase is not None and ligase.name
        else (ligase.identity if ligase is not None else "T4_DNA_ligase")
    )
    spec = AssemblyProtocolSpec(
        product_identity=product_identity,
        backbone_identity=_stable_identifier(
            identity=backbone.identity, display_id=backbone.display_id
        ),
        part_identities=tuple(parts_list),
        restriction_enzyme=(
            restriction_enzyme.name
            or _stable_identifier(
                identity=restriction_enzyme.identity,
                display_id=restriction_enzyme.display_id,
            )
        ),
        ligase=ligase_name,
    )
    return {
        "Product": product_identity,
        "Backbone": spec.backbone_identity,
        "PartsList": parts_list,
        "Restriction Enzyme": spec.restriction_enzyme,
        "Ligase": spec.ligase,
        "Parameters": spec.to_dict(),
    }


def assembly_routes_to_pudu_json(
    *,
    product_identities: Sequence[str],
    part_plasmid_routes: Sequence[Sequence[IndexedPlasmid]],
    backbones: Sequence[IndexedBackbone],
    restriction_enzymes: Sequence[IndexedReagent],
    ligases: Sequence[IndexedReagent] | None = None,
) -> list[dict[str, object]]:
    """Batch helper for deterministic in-memory assembly JSON payloads."""

    active_ligases = (
        list(ligases) if ligases is not None else [None] * len(product_identities)
    )
    return [
        assembly_route_to_pudu_json(
            product_identity=product_identity,
            part_plasmids=part_plasmids,
            backbone=backbone,
            restriction_enzyme=restriction_enzyme,
            ligase=ligase,
        )
        for product_identity, part_plasmids, backbone, restriction_enzyme, ligase in zip(
            product_identities,
            part_plasmid_routes,
            backbones,
            restriction_enzymes,
            active_ligases,
            strict=True,
        )
    ]


def _sbol_identity(obj: Any) -> str:
    return str(getattr(obj, "identity", None) or getattr(obj, "displayId", ""))


def _plasmid_definition_identity(plasmid: Any) -> str:
    definition = getattr(plasmid, "plasmid_definition", plasmid)
    return _sbol_identity(definition)


def _reagent_definition_identity(reagent_implementation: Any) -> str:
    return str(
        getattr(reagent_implementation, "built", None)
        or getattr(reagent_implementation, "identity", None)
        or getattr(reagent_implementation, "displayId", "")
    )


def legacy_assembly_route_to_pudu_json(
    *,
    product_plasmid: Any,
    part_plasmids: Sequence[Any],
    backbone: Any,
    restriction_enzyme: Any,
) -> dict[str, object]:
    """Adapt legacy ``Plasmid`` route objects into PUDU assembly JSON.

    This path intentionally uses route inputs rather than scraping the generated
    SBOL product document. The product SBOL document may omit source plasmid
    definitions, but the route always knows the product plasmid, backbone
    plasmid, selected part plasmids, and restriction enzyme implementation.
    """

    return {
        "Product": _plasmid_definition_identity(product_plasmid),
        "Backbone": _plasmid_definition_identity(backbone),
        "PartsList": [
            _plasmid_definition_identity(plasmid) for plasmid in part_plasmids
        ],
        "Restriction Enzyme": _reagent_definition_identity(restriction_enzyme),
    }


def legacy_assembly_routes_to_pudu_json(
    *,
    product_plasmids: Sequence[Any],
    part_plasmid_routes: Sequence[Sequence[Any]],
    backbones: Sequence[Any],
    restriction_enzymes: Sequence[Any],
) -> list[dict[str, object]]:
    """Batch helper for deterministic legacy PUDU assembly JSON payloads."""

    return [
        legacy_assembly_route_to_pudu_json(
            product_plasmid=product_plasmid,
            part_plasmids=part_plasmids,
            backbone=backbone,
            restriction_enzyme=restriction_enzyme,
        )
        for product_plasmid, part_plasmids, backbone, restriction_enzyme in zip(
            product_plasmids,
            part_plasmid_routes,
            backbones,
            restriction_enzymes,
            strict=True,
        )
    ]


def domestication_artifact_to_pudu_json(
    artifact: dict[str, Any],
) -> dict[str, object]:
    """Adapt one domestication artifact into PUDU assembly-style JSON."""

    domestication = artifact.get("domestication", artifact)
    restriction_enzyme = domestication.get("restriction_enzyme", {})
    restriction_enzyme_identity = (
        restriction_enzyme.get("identity")
        if isinstance(restriction_enzyme, dict)
        else restriction_enzyme
    )
    generated_insert_sequence = str(domestication["generated_insert_sequence"])
    generated_insert_identity = str(domestication["generated_insert_identity"])
    ligase = domestication.get("ligase", {})
    ligase_identity = ligase.get("identity") if isinstance(ligase, dict) else ligase
    spec = AssemblyProtocolSpec(
        product_identity=str(domestication["product_identity"]),
        backbone_identity=str(domestication["backbone_identity"]),
        part_identities=(generated_insert_identity,),
        restriction_enzyme=str(restriction_enzyme_identity),
        ligase=str(ligase_identity or "T4_DNA_ligase"),
    )
    return {
        "Product": spec.product_identity,
        "Backbone": spec.backbone_identity,
        "PartsList": [generated_insert_identity],
        "Generated Insert Sequence": generated_insert_sequence,
        "Restriction Enzyme": spec.restriction_enzyme,
        "Ligase": spec.ligase,
        "Parameters": spec.to_dict(),
    }


def domestication_artifacts_to_pudu_json(
    artifacts: Sequence[dict[str, Any]],
) -> list[dict[str, object]]:
    """Batch helper for domestication PUDU assembly-style JSON payloads."""

    return [domestication_artifact_to_pudu_json(artifact) for artifact in artifacts]


def write_assembly_pudu_input_json(
    payload: dict[str, object] | Sequence[dict[str, object]],
    output_path: str | Path,
) -> Path:
    """Write a deterministic PUDU assembly input JSON file."""

    path = Path(output_path)
    entries: dict[str, object] | list[dict[str, object]]
    if isinstance(payload, dict):
        entries = payload
    else:
        entries = list(payload)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(entries, handle, indent=4)
        handle.write("\n")
    return path
