"""Plan transformation batches with explicit source aliquots and tube usage.

The planner first expands samples and their lineage, then emits cell additions,
DNA additions and incubation/recovery operations. The allocator binds those
samples to wells, preserving upstream DNA locations when a manifest is supplied.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby
from math import ceil

from buildcompiler.domain.protocol_requests import (
    MaterialRef,
    TransformationReaction,
    TransformationRequest,
)
from buildcompiler.protocols.methods import (
    bind_source_wells,
    reaction_entries,
    sequential_wells,
)
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
    """Source loading, transfer volumes in microliters, and incubation settings.

    ``volume_dna`` is the declared loading of each DNA source, whereas
    ``transfer_volume_dna`` is drawn for each output. ``replicates`` applies
    separately to every set of upstream source locations. Rates are pipette
    speed multipliers; temperature-step durations are in minutes.
    """

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
    """Transformation deck slots and source, reaction and tip offsets.

    DNA and reaction offsets are zero-based, column-major indices; tips use well
    names. ``initial_dna_well`` applies only to fresh sources in the source block.
    With an input manifest, DNA keeps its existing wells on ``dna_plate_position``.
    """

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


def transformation_request_from_json(
    payload: Sequence[Mapping[str, object]],
    *,
    request_id: str,
    source_stage_id: str | None = None,
) -> TransformationRequest:
    """Decode strains, chassis and ordered plasmids into a transformation batch."""

    reactions = []
    for index, entry in reaction_entries(
        payload, method="transformation", required={"Strain", "Chassis", "Plasmids"}
    ):
        if not isinstance(entry["Plasmids"], (list, tuple)):
            raise TypeError("Plasmids must be an ordered list.")
        reactions.append(
            TransformationReaction(
                id=f"{request_id}/reaction/{index}",
                strain=MaterialRef.from_identity(entry["Strain"]),
                chassis=MaterialRef.from_identity(entry["Chassis"]),
                plasmids=tuple(MaterialRef.from_identity(p) for p in entry["Plasmids"]),
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
                material=MaterialRef.from_identity(identity),
                replicate=replicate,
                location=WellRef(container_id="source_plate", well_name=well),
            )
            samples.append(sample)
    return OutputManifest(protocol_id=protocol_id, samples=tuple(samples))


def plan_transformation(
    request: TransformationRequest,
    *,
    config: TransformationConfig,
    inputs: tuple[Sample, ...] | None = None,
) -> ProtocolPlan:
    """Expand reactions into outputs and record every contributing source.

    For each reaction, source sets follow manifest order and each set produces
    ``config.replicates`` outputs. Multiple plasmids are paired by source index,
    not combined as a Cartesian product. Without upstream samples, each plasmid
    gets one fresh source. Allocation later supplies all physical locations.
    """

    # Stock sorting makes source IDs stable without reordering requested outputs.
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
    # Give each aliquot a local ID while retaining the upstream ID for handoffs.
    # A material identity alone cannot distinguish its physical source replicates.
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
    # Count whole transfers per tube. Any remainder stays in that tube; ceil
    # below allocates another tube when the last group needs fewer transfers.
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
    # Record source/output pairs before emitting operations so all cell additions
    # precede DNA additions while both phases retain the same output order.
    outputs = []
    cell_transfers = []
    dna_transfers = []
    cell_counts = Counter()
    # Cell consumption is tracked per chassis across interleaved reactions.
    # Media consumption instead follows the global output index.
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
    # Water testing removes temperature commands from the plan. Ordinary plans
    # retain them with a simulation guard, so review documents still show them.
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
    # groupby combines consecutive uses of one physical tube, not all uses of
    # a chassis. Sorting first would change reaction order and tip boundaries.
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
        # The DNA transfer owns the tip through both finishing movements. Only
        # the second movement performs touch-tip and cleanup before the next DNA.
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
    """Return a located plan using fresh DNA stocks or one upstream DNA plate.

    Manifest wells are rebound to this protocol's DNA plate without moving the
    aliquots within it. Cell and media tubes share a separate rack; reactions
    occupy consecutive wells beginning at the configured reaction offset.
    """

    # Preserve plan order within each physical resource. In particular, cell and
    # media tubes share a rack and must be allocated together.
    dna, tubes, reactions = [], [], []
    for sample in plan.samples:
        if sample.role == "dna":
            dna.append(sample)
        elif sample.role in ("cells", "media"):
            if sample.initial_volume_ul > 1500:
                raise ValueError("Reagent loading exceeds tube capacity.")
            tubes.append(sample)
        elif sample.role == "reaction":
            reactions.append(sample)
        else:
            raise ValueError(f"Unknown transformation sample role {sample.role!r}.")

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
    if inputs is not None:
        # This target reserves one plate for the complete DNA handoff, including
        # any manifest samples not selected by the current request.
        if len({p.location.container_id for p in inputs.samples}) != 1:
            raise ValueError("The transformation target accepts one source DNA plate.")
        containers.append(
            ContainerSpec(
                id="dna_plate",
                definition_id="nest_96_wellplate_100ul_pcr_full_skirt",
                parent=profile.dna_plate_position,
            )
        )
        locations = bind_source_wells(
            dna, inputs, container_id="dna_plate", grid=PLATE_96
        )
    else:
        locations = sequential_wells(
            (s.id for s in dna),
            container_id="sources",
            grid=BLOCK_24,
            start=profile.initial_dna_well,
        )
    containers.append(
        ContainerSpec(
            id="tube_rack",
            definition_id="opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap",
            parent=profile.tube_rack_position,
        )
    )
    # Tube placement always begins at rack A1; only reactions have an offset here.
    locations.update(
        sequential_wells((s.id for s in tubes), container_id="tube_rack", grid=BLOCK_24)
    )
    locations.update(
        sequential_wells(
            (s.id for s in reactions),
            container_id="reactions",
            grid=PLATE_96,
            start=profile.thermocycler_starting_well,
        )
    )
    return plan.with_locations(tuple(containers), locations)
