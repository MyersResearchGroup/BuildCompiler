"""Pure heat-shock planning, preserving PUDU's ordering and tube grouping.

Derived from pudu/transformation.py (MIT); see protocols/attribution.py.
Source-location replicates and method replicates are distinct axes.
"""

from collections import Counter
from itertools import groupby
from math import ceil

from buildcompiler.domain.protocol_requests import MaterialRef, TransformationRequest
from buildcompiler.protocols.materials import Sample, SamplePoint
from buildcompiler.protocols.methods.transformation_config import TransformationConfig
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.steps import (
    Distribute,
    LidAction,
    RunTemperatureProgram,
    SetTemperature,
    TemperatureProgram,
    Transfer,
)


def plan_transformation(
    request: TransformationRequest,
    *,
    config: TransformationConfig,
    inputs: tuple[Sample, ...] | None = None,
) -> ProtocolPlan:
    plasmids = {p.identity: p for r in request.reactions for p in r.plasmids}
    chassis = {r.chassis.identity: r.chassis for r in request.reactions}
    ordered_plasmids = sorted(plasmids.values(), key=lambda p: (p.label, p.identity))
    ordered_chassis = sorted(chassis.values(), key=lambda c: (c.label, c.identity))
    available = {identity: [] for identity in plasmids}
    for sample in inputs or ():
        if sample.material.identity in available:
            available[sample.material.identity].append(sample)
    if inputs is not None:
        if any(not samples for samples in available.values()):
            raise ValueError(
                "The source manifest must contain every requested plasmid."
            )
        counts = {len(samples) for samples in available.values()}
        if len(counts) != 1:
            raise ValueError("Plasmid source-location replicate counts must be equal.")
        location_replicates = counts.pop()
    else:
        location_replicates = 1
    samples = []
    dna = {}
    for index, plasmid in enumerate(ordered_plasmids):
        dna[plasmid.identity] = []
        for location_index in range(location_replicates):
            upstream = (
                available[plasmid.identity][location_index]
                if inputs is not None
                else None
            )
            sample = Sample(
                id=f"{request.id}/dna/{index}/{location_index}",
                material=plasmid,
                role="dna",
                replicate=location_index + 1,
                source_sample_id=upstream.id if upstream else None,
                initial_volume_ul=config.volume_dna,
            )
            samples.append(sample)
            dna[plasmid.identity].append(sample)
    per_cell_tube = int(
        config.tube_volume_competent_cell // config.transfer_volume_competent_cell
    )
    per_media_tube = int(
        config.tube_volume_recovery_media // config.transfer_volume_recovery_media
    )
    reaction_counts = Counter(r.chassis.identity for r in request.reactions)
    cells = {}
    for index, cell in enumerate(ordered_chassis):
        count = reaction_counts[cell.identity] * location_replicates * config.replicates
        cells[cell.identity] = []
        for tube in range(ceil(count / per_cell_tube)):
            sample = Sample(
                id=f"{request.id}/cells/{index}/{tube}",
                material=cell,
                role="cells",
                liquid_label=f"Competent Cell {cell.label}_{tube + 1}",
                replicate=tube + 1,
                initial_volume_ul=config.tube_volume_competent_cell,
            )
            samples.append(sample)
            cells[cell.identity].append(sample)
    total = len(request.reactions) * location_replicates * config.replicates
    media = []
    for tube in range(ceil(total / per_media_tube)):
        sample = Sample(
            id=f"{request.id}/media/{tube}",
            role="media",
            material=MaterialRef(
                identity="urn:buildcompiler:recovery-media", label="Media"
            ),
            liquid_label=f"Media_{tube + 1}",
            replicate=tube + 1,
            initial_volume_ul=config.tube_volume_recovery_media,
        )
        samples.append(sample)
        media.append(sample)
    input_ids = tuple(s.id for s in samples)
    outputs = []
    cell_transfers = []
    dna_transfers = []
    cell_counts = Counter()
    for reaction in request.reactions:
        for location_index in range(location_replicates):
            for replicate in range(config.replicates):
                cell = cells[reaction.chassis.identity][
                    cell_counts[reaction.chassis.identity] // per_cell_tube
                ]
                cell_counts[reaction.chassis.identity] += 1
                parents = tuple(
                    dna[p.identity][location_index] for p in reaction.plasmids
                )
                medium = media[len(outputs) // per_media_tube]
                output = Sample(
                    id=f"{request.id}/reaction/{len(outputs)}",
                    material=reaction.strain,
                    role="reaction",
                    replicate=replicate + 1,
                    parent_ids=(cell.id, *(p.id for p in parents), medium.id),
                    contents=(
                        reaction.strain.label,
                        f"Competent_Cell_{reaction.chassis.label}",
                        *(p.label for p in reaction.plasmids),
                        medium.liquid_label,
                    ),
                )
                outputs.append(output)
                cell_transfers.append((cell, output))
                dna_transfers.extend((parent, output) for parent in parents)
    steps = [LidAction(id="open-lid", action="open")]
    if not config.water_testing:
        steps.extend(
            (
                SetTemperature(
                    id="chill-source",
                    module="source",
                    celsius=4,
                    skip_during_simulation=True,
                ),
                SetTemperature(
                    id="chill-reactions",
                    module="reaction",
                    celsius=4,
                    skip_during_simulation=True,
                ),
            )
        )
    for index, (source_id, group) in enumerate(
        groupby(cell_transfers, key=lambda pair: pair[0].id)
    ):
        steps.append(
            Distribute(
                id=f"cells/{index}",
                source=SamplePoint(sample_id=source_id),
                destinations=tuple(
                    SamplePoint(sample_id=output.id) for _, output in group
                ),
                volume_ul=config.transfer_volume_competent_cell,
                mix_before=(3, 50),
            )
        )
    instrument = "large" if config.transfer_volume_dna > 20 else "small"
    for index, (source, output) in enumerate(dna_transfers):
        steps.append(
            Transfer(
                id=f"dna/{index}",
                instrument=instrument,
                source=SamplePoint(sample_id=source.id),
                destination=SamplePoint(sample_id=output.id),
                volume_ul=config.transfer_volume_dna,
                mix_before_ul=config.transfer_volume_dna,
                aspiration_rate=config.aspiration_rate,
                dispense_rate=config.dispense_rate,
                touch_tip=False,
                drop_tip=False,
            )
        )
        for movement in range(2):
            steps.append(
                Transfer(
                    id=f"dna/{index}/finish/{movement}",
                    instrument=instrument,
                    source=SamplePoint(sample_id=output.id, bottom_mm=0),
                    destination=SamplePoint(sample_id=output.id, bottom_mm=8),
                    volume_ul=20,
                    aspiration_rate=config.dispense_rate,
                    dispense_rate=config.dispense_rate,
                    new_tip=False,
                    blow_out=False,
                    touch_tip=movement == 1,
                    drop_tip=movement == 1,
                )
            )
    steps.append(LidAction(id="close-before-incubation", action="close"))
    if not config.water_testing:
        steps.append(
            RunTemperatureProgram(
                id="heat-shock",
                skip_during_simulation=True,
                program=TemperatureProgram(
                    steps=(
                        config.cold_incubation1,
                        config.heat_shock,
                        config.cold_incubation2,
                    ),
                    repetitions=1,
                    block_max_volume_ul=30,
                ),
            )
        )
    steps.append(LidAction(id="open-for-recovery", action="open"))
    for index, medium in enumerate(media):
        destinations = outputs[index * per_media_tube : (index + 1) * per_media_tube]
        steps.append(
            Distribute(
                id=f"media/{index}",
                source=SamplePoint(sample_id=medium.id),
                destinations=tuple(
                    SamplePoint(sample_id=s.id, top_mm=2) for s in destinations
                ),
                volume_ul=config.transfer_volume_recovery_media,
                air_gap_ul=10,
            )
        )
    steps.append(LidAction(id="close-for-recovery", action="close"))
    if not config.water_testing:
        steps.append(
            RunTemperatureProgram(
                id="recovery",
                skip_during_simulation=True,
                program=TemperatureProgram(
                    steps=(config.recovery_incubation,),
                    repetitions=1,
                    block_max_volume_ul=30,
                ),
            )
        )
    return ProtocolPlan(
        id=request.id,
        request_id=request.id,
        samples=tuple(samples + outputs),
        input_sample_ids=input_ids,
        output_sample_ids=tuple(s.id for s in outputs),
        steps=tuple(steps),
    )
