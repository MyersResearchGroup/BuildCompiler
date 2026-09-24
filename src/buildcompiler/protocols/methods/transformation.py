"""Transformation method: configuration, planning and well allocation."""

from collections import Counter
from dataclasses import dataclass
from itertools import groupby
from math import ceil

from buildcompiler.domain.protocol_requests import MaterialRef, TransformationRequest
from buildcompiler.protocols.models import (
    BLOCK_24,
    PLATE_96,
    ConfigOverrides,
    ContainerSpec,
    Distribute,
    LidAction,
    OutputManifest,
    ProtocolPlan,
    RunTemperatureProgram,
    Sample,
    SamplePoint,
    SetTemperature,
    TemperatureProgram,
    TemperatureStep,
    Transfer,
    WellRef,
    positive,
    positive_integer,
    validate_slots,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationConfig(ConfigOverrides):
    """Transfer volumes, source tube volumes, replicates and incubations."""

    volume_dna: float = 20
    transfer_volume_dna: float = 2
    transfer_volume_competent_cell: float = 20
    tube_volume_competent_cell: float = 100
    transfer_volume_recovery_media: float = 60
    tube_volume_recovery_media: float = 1200
    replicates: int = 2
    aspiration_rate: float = 0.5
    dispense_rate: float = 1
    water_testing: bool = False
    cold_incubation1: TemperatureStep = TemperatureStep(celsius=4, minutes=30)
    heat_shock: TemperatureStep = TemperatureStep(celsius=42, minutes=1)
    cold_incubation2: TemperatureStep = TemperatureStep(celsius=4, minutes=2)
    recovery_incubation: TemperatureStep = TemperatureStep(celsius=37, minutes=60)

    def __post_init__(self) -> None:
        positive_integer(self.replicates, "replicates")
        for name in (
            "volume_dna",
            "transfer_volume_dna",
            "transfer_volume_competent_cell",
            "tube_volume_competent_cell",
            "transfer_volume_recovery_media",
            "tube_volume_recovery_media",
            "aspiration_rate",
            "dispense_rate",
        ):
            positive(getattr(self, name), name)
        if type(self.water_testing) is not bool:
            raise ValueError("water_testing must be a boolean.")
        if self.tube_volume_competent_cell < self.transfer_volume_competent_cell:
            raise ValueError("A cell tube must supply at least one transfer.")
        if self.tube_volume_recovery_media < self.transfer_volume_recovery_media:
            raise ValueError("A media tube must supply at least one transfer.")
        for step in (
            self.cold_incubation1,
            self.heat_shock,
            self.cold_incubation2,
            self.recovery_incubation,
        ):
            if not isinstance(step, TemperatureStep):
                raise TypeError("Incubations must be TemperatureStep records.")


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsTransformationProfile:
    """Transformation deck slots and source, reaction and tip offsets."""

    api_level: str = "2.21"
    temperature_module_position: str = "1"
    dna_plate_position: str = "2"
    tube_rack_position: str = "3"
    tiprack_p20_position: str = "9"
    tiprack_p200_position: str = "6"
    thermocycler_starting_well: int = 0
    initial_dna_well: int = 0
    initial_tip_p20: str | None = None
    initial_tip_p300: str | None = None

    def __post_init__(self) -> None:
        if self.api_level != "2.21":
            raise ValueError("This backend currently supports API 2.21.")
        PLATE_96.name(self.thermocycler_starting_well)
        BLOCK_24.name(self.initial_dna_well)
        for tip in (self.initial_tip_p20, self.initial_tip_p300):
            if tip is not None:
                PLATE_96.index(tip)
        validate_slots(
            (
                self.temperature_module_position,
                self.dna_plate_position,
                self.tube_rack_position,
                self.tiprack_p20_position,
                self.tiprack_p200_position,
            )
        )


def plan_transformation(
    request: TransformationRequest,
    *,
    config: TransformationConfig,
    inputs: tuple[Sample, ...] | None = None,
) -> ProtocolPlan:
    """Expand source and method replicates, grouping transfers by source tube."""

    plasmids = {p.identity: p for r in request.reactions for p in r.plasmids}
    chassis = {r.chassis.identity: r.chassis for r in request.reactions}
    ordered_plasmids = sorted(plasmids.values(), key=lambda p: (p.label, p.identity))
    ordered_chassis = sorted(chassis.values(), key=lambda c: (c.label, c.identity))
    available = {identity: [] for identity in plasmids}
    for sample in inputs or ():
        if sample.material.identity in available:
            available[sample.material.identity].append(sample)
    # Each source location gets its own set of transformation replicates. Pair
    # plasmids by source index, so every plasmid must have the same source count.
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
    # Combine consecutive transfers from the same tube without reordering
    # reactions. A chassis can recur later after another chassis was handled.
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
        # Reuse the DNA tip for the finishing movements, then discard it.
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
    # Use the same tube boundaries that assigned each output's media parent.
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


def allocate_transformation(
    plan: ProtocolPlan,
    *,
    profile: OpentronsTransformationProfile,
    inputs: OutputManifest | None = None,
) -> ProtocolPlan:
    """Bind mapped DNA wells or allocate fresh sources, tubes and reactions."""

    containers = [
        ContainerSpec(
            id="sources",
            definition_id="opentrons_24_aluminumblock_nest_1.5ml_snapcap",
            parent="source_module",
        ),
        ContainerSpec(
            id="reactions",
            definition_id="nest_96_wellplate_100ul_pcr_full_skirt",
            parent="reaction_module",
        ),
    ]
    upstream = {}
    if inputs is not None:
        if len({p.location.container_id for p in inputs.samples}) != 1:
            raise ValueError("The transformation target accepts one source DNA plate.")
        containers.append(
            ContainerSpec(
                id="dna_plate",
                definition_id="nest_96_wellplate_100ul_pcr_full_skirt",
                parent=profile.dna_plate_position,
            )
        )
        upstream = {p.id: p.location for p in inputs.samples}
    containers.append(
        ContainerSpec(
            id="tube_rack",
            definition_id="opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap",
            parent=profile.tube_rack_position,
        )
    )
    locations = {}
    dna_index, tube_index, reaction_index = (
        profile.initial_dna_well,
        0,
        profile.thermocycler_starting_well,
    )
    for sample in plan.samples:
        if sample.role == "dna":
            if inputs is None:
                location = WellRef(
                    container_id="sources", well_name=BLOCK_24.name(dna_index)
                )
                dna_index += 1
            else:
                # The plate changes its deck role, but the source well and
                # upstream sample identity remain the same.
                well = upstream[sample.source_sample_id].well_name
                PLATE_96.index(well)
                location = WellRef(container_id="dna_plate", well_name=well)
        elif sample.role in ("cells", "media"):
            location = WellRef(
                container_id="tube_rack", well_name=BLOCK_24.name(tube_index)
            )
            tube_index += 1
            if sample.initial_volume_ul > 1500:
                raise ValueError("Reagent loading exceeds tube capacity.")
        elif sample.role == "reaction":
            location = WellRef(
                container_id="reactions", well_name=PLATE_96.name(reaction_index)
            )
            reaction_index += 1
        else:
            raise ValueError(f"Unknown transformation sample role {sample.role!r}.")
        locations[sample.id] = location
    return plan.with_locations(tuple(containers), locations)
