"""Plating resource allocation and setup, using shared liquid handling lowering."""

from collections import Counter

from buildcompiler.protocols.allocation.models import (
    AllocatedProtocolPlan,
    ContainerSpec,
    OutputManifest,
    SamplePlacement,
    WellRef,
)
from buildcompiler.protocols.allocation.wells import PLATE_96, WellGrid
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.backends.opentrons.palette import COLORS
from buildcompiler.protocols.backends.opentrons.operations import lower_operations
from buildcompiler.protocols.backends.opentrons.profile import OpentronsPlatingProfile
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


def allocate_plating(
    plan: ProtocolPlan, *, profile: OpentronsPlatingProfile, inputs: OutputManifest
) -> AllocatedProtocolPlan:
    upstream = {p.sample_id: p.location for p in inputs.placements}
    selected = [s for s in plan.samples if s.role == "bacteria"]
    if len({upstream[s.source_sample_id].container_id for s in selected}) != 1:
        raise ValueError("The plating target accepts one source plate.")
    containers = [
        ContainerSpec(
            id="reactions",
            definition_id=profile.thermocycler_labware,
            parent="reaction_module",
        ),
        ContainerSpec(
            id="tube_rack",
            definition_id="opentrons_15_tuberack_falcon_15ml_conical",
            parent=profile.tube_rack_position,
        ),
    ]
    counts = Counter((s.role, s.dilution) for s in plan.samples)
    indices = Counter()
    placements = []
    for sample in plan.samples:
        if sample.role == "broth":
            location = WellRef(
                container_id="tube_rack",
                well_name=WellGrid(rows=3, columns=5).name(profile.lb_tube_position),
            )
            if sample.initial_volume_ul > 15000:
                raise ValueError("Broth loading exceeds tube capacity.")
        elif sample.role == "bacteria":
            well = upstream[sample.source_sample_id].well_name
            PLATE_96.index(well)
            location = WellRef(container_id="reactions", well_name=well)
        elif sample.role in ("dilution", "agar"):
            per_dilution = counts[sample.role, sample.dilution]
            if per_dilution > 96:
                raise ValueError("A dilution exceeds plate capacity.")
            two_plates = counts[sample.role, 2] and per_dilution > 48
            plate = sample.dilution if two_plates else 1
            index = indices[sample.role, sample.dilution]
            indices[sample.role, sample.dilution] += 1
            if sample.dilution == 2 and not two_plates:
                index += 48
            name = f"{sample.role}_{plate}"
            if name not in {c.id for c in containers}:
                containers.append(
                    ContainerSpec(
                        id=name,
                        definition_id="nest_96_wellplate_100ul_pcr_full_skirt",
                        parent=getattr(profile, f"{sample.role}_plate_position{plate}"),
                    )
                )
            location = WellRef(container_id=name, well_name=PLATE_96.name(index))
        else:
            raise ValueError(f"Unknown plating sample role {sample.role!r}.")
        placements.append(SamplePlacement(sample_id=sample.id, location=location))
    return AllocatedProtocolPlan(
        protocol=plan, containers=tuple(containers), placements=tuple(placements)
    )


def lower_plating(
    plan: AllocatedProtocolPlan, *, profile: OpentronsPlatingProfile
) -> OpentronsProgram:
    validate_tip_capacity(
        plan,
        starts={"small": profile.initial_small_tip, "large": profile.initial_large_tip},
    )
    calls = [
        Call(
            target="protocol",
            method="load_module",
            args=("thermocyclerModuleV1",),
            result="reaction_module",
        ),
        Call(
            target="reaction_module",
            method="load_labware",
            args=(profile.thermocycler_labware,),
            result="reactions",
        ),
        Call(
            target="protocol",
            method="load_labware",
            args=("opentrons_96_filtertiprack_20ul", profile.small_tiprack_position),
            result="small_tips",
        ),
        Call(
            target="protocol",
            method="load_labware",
            args=("opentrons_96_filtertiprack_200ul", profile.large_tiprack_position),
            result="large_tips",
        ),
    ]
    for instrument, pipette, mount, tip in (
        ("small", "p20_single_gen2", "left", profile.initial_small_tip),
        ("large", "p300_single_gen2", "right", profile.initial_large_tip),
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
    tube = next(c for c in plan.containers if c.id == "tube_rack")
    calls.append(
        Call(
            target="protocol",
            method="load_labware",
            args=(tube.definition_id, tube.parent),
            result=tube.id,
        )
    )
    bacteria_index = 0
    for sample in plan.protocol.samples:
        if sample.role == "broth":
            calls.extend(
                load_liquid(
                    sample.id,
                    name="liquid_broth",
                    description="Liquid broth for dilutions",
                    color="#D2B48C",
                    volume=sample.initial_volume_ul,
                )
            )
        elif sample.role == "bacteria":
            calls.extend(
                load_liquid(
                    sample.id,
                    name="transformed_bacteria",
                    description=sample.liquid_label,
                    color=COLORS[bacteria_index % len(COLORS)],
                    volume=sample.initial_volume_ul,
                )
            )
            bacteria_index += 1
    for container in sorted(
        (c for c in plan.containers if c.id.startswith(("dilution_", "agar_"))),
        key=lambda c: (not c.id.startswith("dilution_"), c.id),
    ):
        calls.append(
            Call(
                target="protocol",
                method="load_labware",
                args=(container.definition_id, container.parent),
                result=container.id,
            )
        )
    calls.extend(lower_operations(plan, capacities={"small": 20, "large": 200}))
    return OpentronsProgram(
        api_level=profile.api_level, instructions=tuple(calls), wells=well_aliases(plan)
    )
