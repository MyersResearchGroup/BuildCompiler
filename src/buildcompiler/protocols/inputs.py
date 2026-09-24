"""Decode protocol inputs and stage records without importing robot dependencies."""

from collections.abc import Mapping, Sequence
from urllib.parse import urlsplit

from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent
from buildcompiler.domain.protocol_requests import (
    AssemblyReaction,
    AssemblyRequest,
    MaterialRef,
    TransformationReaction,
    TransformationRequest,
)
from buildcompiler.protocols.models import PLATE_96, OutputManifest, Sample, WellRef


def material_ref(identity: str, label: str | None = None) -> MaterialRef:
    """Keep the full identity and derive a display label when none is supplied."""

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
    """Decode products and ordered components into an assembly batch."""
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
    """Decode strains, chassis and ordered plasmids into a transformation batch."""

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


def plasmid_manifest_from_json(
    payload: Mapping[str, list[str]], *, protocol_id: str = "imported-assembly"
) -> OutputManifest:
    """Import identity-to-well mappings as distinct physical source replicates."""

    samples = []
    for index, (identity, wells) in enumerate(payload.items()):
        if not isinstance(wells, (list, tuple)) or not wells:
            raise ValueError("Each plasmid requires a nonempty list of source wells.")
        for replicate, well in enumerate(wells, 1):
            PLATE_96.index(well)
            sample = Sample(
                id=f"{protocol_id}/{index}/{replicate}",
                material=material_ref(identity),
                replicate=replicate,
                location=WellRef(container_id="source_plate", well_name=well),
            )
            samples.append(sample)
    return OutputManifest(protocol_id=protocol_id, samples=tuple(samples))


def bacterium_manifest_from_json(
    payload: Mapping, *, protocol_id: str = "imported-transformation"
) -> OutputManifest:
    """Import culture-well labels, assigning local identities when none are present."""

    locations = payload.get("bacterium_locations")
    if not isinstance(locations, Mapping) or not locations:
        raise ValueError("Plating JSON requires nonempty bacterium_locations.")
    samples = []
    for index, (well, contents) in enumerate(locations.items()):
        PLATE_96.index(well)
        if isinstance(contents, str):
            labels = (contents,)
        elif (
            isinstance(contents, (list, tuple))
            and contents
            and all(isinstance(v, str) for v in contents)
        ):
            labels = tuple(contents)
        else:
            raise ValueError(
                "Bacterium contents must be a string or nonempty list of strings."
            )
        # The legacy format has labels only: do not pretend they are SBOL identities.
        sample = Sample(
            id=f"{protocol_id}/{index}",
            material=MaterialRef(
                identity=f"urn:buildcompiler:imported:{protocol_id}:{index}",
                label=", ".join(labels),
            ),
            contents=labels,
            liquid_label=str(contents),
            location=WellRef(container_id="source_plate", well_name=well),
        )
        samples.append(sample)
    return OutputManifest(protocol_id=protocol_id, samples=tuple(samples))


def assembly_request_from_route(
    *,
    stage_id: str,
    products: Sequence[IndexedPlasmid],
    parts: Sequence[IndexedPlasmid],
    backbone: IndexedBackbone,
    restriction_enzyme: IndexedReagent,
) -> AssemblyRequest:
    """Use actual produced identities and preserve the selected component order."""

    def material(record) -> MaterialRef:
        """Keep indexed identities and choose the most specific display label."""
        return MaterialRef(
            identity=record.identity,
            label=record.name or record.display_id or record.identity,
        )

    return AssemblyRequest(
        id=stage_id,
        source_stage_id=stage_id,
        reactions=tuple(
            AssemblyReaction(
                id=f"{stage_id}/product/{index}",
                product=material(product),
                backbone=material(backbone),
                parts=tuple(material(part) for part in parts),
                restriction_enzyme=material(restriction_enzyme),
            )
            for index, product in enumerate(products)
        ),
    )
