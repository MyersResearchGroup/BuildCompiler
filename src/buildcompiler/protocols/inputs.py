"""Explicit conversion from existing assembly JSON to typed protocol inputs."""

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from buildcompiler.domain.protocol_requests import (
    AssemblyReaction,
    AssemblyRequest,
    MaterialRef,
    TransformationReaction,
    TransformationRequest,
)


def material_ref(identity: str, label: str | None = None) -> MaterialRef:
    if not isinstance(identity, str) or not identity:
        raise ValueError("Material identities must be nonempty strings.")
    if label is None:
        segments = [part for part in urlsplit(identity).path.split("/") if part]
        label = (
            segments[-2]
            if len(segments) > 1 and segments[-1].isdigit()
            else (segments[-1] if segments else identity)
        )
    return MaterialRef(identity=identity, label=label)


def assembly_request_from_json(
    payload: Sequence[Mapping[str, object]],
    *,
    request_id: str,
    source_stage_id: str | None = None,
) -> AssemblyRequest:
    """Decode this one format explicitly; never guess a method from its keys."""
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise TypeError("Assembly JSON must be a sequence of reaction objects.")
    reactions = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, Mapping):
            raise TypeError("Each assembly entry must be an object.")
        required = {"Product", "Backbone", "PartsList", "Restriction Enzyme"}
        if missing := required - entry.keys():
            raise ValueError(f"Assembly {index} is missing {sorted(missing)}.")
        parts = entry["PartsList"]
        if not isinstance(parts, (list, tuple)):
            raise TypeError("PartsList must be an ordered list.")
        reactions.append(
            AssemblyReaction(
                id=f"{request_id}/reaction/{index}",
                product=material_ref(entry["Product"]),
                backbone=material_ref(entry["Backbone"]),
                parts=tuple(material_ref(part) for part in parts),
                restriction_enzyme=material_ref(entry["Restriction Enzyme"]),
            )
        )
    return AssemblyRequest(
        id=request_id, reactions=tuple(reactions), source_stage_id=source_stage_id
    )


def transformation_request_from_json(
    payload: Sequence[Mapping[str, object]],
    *,
    request_id: str,
    source_stage_id: str | None = None,
) -> TransformationRequest:
    if isinstance(payload, (str, bytes)) or not isinstance(payload, Sequence):
        raise TypeError("Transformation JSON must be a sequence of reaction objects.")
    reactions = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, Mapping):
            raise TypeError("Each transformation entry must be an object.")
        if missing := {"Strain", "Chassis", "Plasmids"} - entry.keys():
            raise ValueError(f"Transformation {index} is missing {sorted(missing)}.")
        if not isinstance(entry["Plasmids"], (list, tuple)):
            raise TypeError("Plasmids must be an ordered list.")
        reactions.append(
            TransformationReaction(
                id=f"{request_id}/reaction/{index}",
                strain=material_ref(entry["Strain"]),
                chassis=material_ref(entry["Chassis"]),
                plasmids=tuple(material_ref(p) for p in entry["Plasmids"]),
            )
        )
    return TransformationRequest(
        id=request_id, reactions=tuple(reactions), source_stage_id=source_stage_id
    )
