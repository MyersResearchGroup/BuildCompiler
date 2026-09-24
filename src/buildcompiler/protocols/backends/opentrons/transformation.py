"""Transformation allocation and resource setup; method ordering lives elsewhere."""

from buildcompiler.protocols.allocation.models import (
    AllocatedProtocolPlan,
    ContainerSpec,
    OutputManifest,
    SamplePlacement,
    WellRef,
)
from buildcompiler.protocols.allocation.wells import BLOCK_24, PLATE_96
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.backends.opentrons.palette import COLORS
from buildcompiler.protocols.backends.opentrons.operations import lower_operations
from buildcompiler.protocols.backends.opentrons.profile import (
    OpentronsTransformationProfile,
)
from buildcompiler.protocols.backends.opentrons.program import (
    Call,
    OpentronsProgram,
    Reference,
    SetStartingTip,
)
from buildcompiler.protocols.backends.opentrons.setup import (
    load_liquid,
    validate_tip_capacity,
    well_aliases,
)


def allocate_transformation(
    plan: ProtocolPlan,
    *,
    profile: OpentronsTransformationProfile,
    inputs: OutputManifest | None = None,
) -> AllocatedProtocolPlan:
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
        if len({p.location.container_id for p in inputs.placements}) != 1:
            raise ValueError("The transformation target accepts one source DNA plate.")
        containers.append(
            ContainerSpec(
                id="dna_plate",
                definition_id="nest_96_wellplate_100ul_pcr_full_skirt",
                parent=profile.dna_plate_position,
            )
        )
        upstream = {p.sample_id: p.location for p in inputs.placements}
    containers.append(
        ContainerSpec(
            id="tube_rack",
            definition_id="opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap",
            parent=profile.tube_rack_position,
        )
    )
    placements = []
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
        placements.append(SamplePlacement(sample_id=sample.id, location=location))
    return AllocatedProtocolPlan(
        protocol=plan, containers=tuple(containers), placements=tuple(placements)
    )


def lower_transformation(
    plan: AllocatedProtocolPlan, *, profile: OpentronsTransformationProfile
) -> OpentronsProgram:
    validate_tip_capacity(
        plan,
        starts={"small": profile.initial_tip_p20, "large": profile.initial_tip_p300},
    )
    containers = {c.id: c for c in plan.containers}
    calls = [
        Call(
            target="protocol",
            method="load_module",
            args=("temperature module", profile.temperature_module_position),
            result="source_module",
        ),
        Call(
            target="source_module",
            method="load_labware",
            args=(containers["sources"].definition_id,),
            result="sources",
        ),
        Call(
            target="protocol",
            method="load_module",
            args=("thermocycler module",),
            result="reaction_module",
        ),
        Call(
            target="reaction_module",
            method="load_labware",
            args=(containers["reactions"].definition_id,),
            result="reactions",
        ),
    ]
    for name in ("dna_plate", "tube_rack"):
        if name in containers:
            container = containers[name]
            calls.append(
                Call(
                    target="protocol",
                    method="load_labware",
                    args=(container.definition_id, container.parent),
                    result=name,
                )
            )
    calls.extend(
        (
            Call(
                target="protocol",
                method="load_labware",
                args=("opentrons_96_tiprack_20ul", profile.tiprack_p20_position),
                result="small_tips",
            ),
            Call(
                target="protocol",
                method="load_labware",
                args=(
                    "opentrons_96_filtertiprack_200ul",
                    profile.tiprack_p200_position,
                ),
                result="large_tips",
            ),
        )
    )
    for instrument, pipette, mount, tip in (
        ("small", "p20_single_gen2", "left", profile.initial_tip_p20),
        ("large", "p300_single_gen2", "right", profile.initial_tip_p300),
    ):
        calls.append(
            Call(
                target="protocol",
                method="load_instrument",
                args=(pipette, mount),
                kwargs=(("tip_racks", (Reference(f"{instrument}_tips"),)),),
                result=instrument,
            )
        )
        if tip:
            calls.append(
                SetStartingTip(
                    pipette=instrument, tip=Reference(f"{instrument}_tips", tip)
                )
            )
    dna_liquids = {}
    for sample in plan.protocol.samples:
        if sample.role == "dna":
            define = sample.material.identity not in dna_liquids
            if define:
                dna_liquids[sample.material.identity] = (
                    f"liquid:{sample.id}",
                    len(dna_liquids),
                )
            liquid_id, color_index = dna_liquids[sample.material.identity]
            calls.extend(
                load_liquid(
                    sample.id,
                    name=sample.material.label,
                    description=f"{sample.material.label} DNA construct",
                    color=COLORS[color_index % len(COLORS)],
                    volume=sample.initial_volume_ul,
                    liquid_id=liquid_id,
                    define=define,
                )
            )
        elif sample.role in ("cells", "media"):
            calls.extend(
                load_liquid(
                    sample.id,
                    name=sample.liquid_label,
                    color=COLORS[(sample.replicate - 1) % len(COLORS)],
                    volume=sample.initial_volume_ul,
                )
            )
    calls.extend(lower_operations(plan, capacities={"small": 20, "large": 200}))
    return OpentronsProgram(
        api_level=profile.api_level, instructions=tuple(calls), wells=well_aliases(plan)
    )
