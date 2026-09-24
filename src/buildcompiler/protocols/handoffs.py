"""Explicit adapters for PUDU's location-only handoff formats."""

from collections.abc import Mapping

from buildcompiler.protocols.allocation.models import (
    OutputManifest,
    SamplePlacement,
    WellRef,
)
from buildcompiler.protocols.allocation.wells import PLATE_96
from buildcompiler.protocols.inputs import material_ref
from buildcompiler.protocols.materials import Sample
from buildcompiler.domain.protocol_requests import MaterialRef


def plasmid_manifest_from_json(
    payload: Mapping[str, list[str]], *, protocol_id: str = "imported-assembly"
) -> OutputManifest:
    samples, placements = [], []
    for index, (identity, wells) in enumerate(payload.items()):
        if not isinstance(wells, (list, tuple)) or not wells:
            raise ValueError("Each plasmid requires a nonempty list of source wells.")
        for replicate, well in enumerate(wells, 1):
            PLATE_96.index(well)
            sample = Sample(
                id=f"{protocol_id}/{index}/{replicate}",
                material=material_ref(identity),
                replicate=replicate,
            )
            samples.append(sample)
            placements.append(
                SamplePlacement(
                    sample_id=sample.id,
                    location=WellRef(container_id="source_plate", well_name=well),
                )
            )
    return OutputManifest(
        protocol_id=protocol_id, samples=tuple(samples), placements=tuple(placements)
    )


def bacterium_manifest_from_json(
    payload: Mapping, *, protocol_id: str = "imported-transformation"
) -> OutputManifest:
    locations = payload.get("bacterium_locations")
    if not isinstance(locations, Mapping) or not locations:
        raise ValueError("Plating JSON requires nonempty bacterium_locations.")
    samples, placements = [], []
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
        )
        samples.append(sample)
        placements.append(
            SamplePlacement(
                sample_id=sample.id,
                location=WellRef(container_id="source_plate", well_name=well),
            )
        )
    return OutputManifest(
        protocol_id=protocol_id, samples=tuple(samples), placements=tuple(placements)
    )
