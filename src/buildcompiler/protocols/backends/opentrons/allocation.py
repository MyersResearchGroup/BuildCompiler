"""Deterministic allocation for the supported assembly hardware profile."""

from buildcompiler.protocols.allocation.models import (
    AllocatedProtocolPlan,
    ContainerSpec,
    SamplePlacement,
    WellRef,
)
from buildcompiler.protocols.allocation.wells import BLOCK_24, PLATE_96
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.backends.opentrons.profile import OpentronsAssemblyProfile


def allocate(
    plan: ProtocolPlan, *, profile: OpentronsAssemblyProfile
) -> AllocatedProtocolPlan:
    if len(plan.input_sample_ids) > BLOCK_24.capacity:
        raise ValueError("Assembly source block capacity exceeded.")
    if (
        len(plan.output_sample_ids) + profile.thermocycler_starting_well
        > PLATE_96.capacity
    ):
        raise ValueError("Assembly reaction plate capacity exceeded.")
    placements = tuple(
        SamplePlacement(
            sample_id=sample_id,
            location=WellRef(container_id="sources", well_name=BLOCK_24.name(index)),
        )
        for index, sample_id in enumerate(plan.input_sample_ids)
    ) + tuple(
        SamplePlacement(
            sample_id=sample_id,
            location=WellRef(
                container_id="reactions",
                well_name=PLATE_96.name(index + profile.thermocycler_starting_well),
            ),
        )
        for index, sample_id in enumerate(plan.output_sample_ids)
    )
    return AllocatedProtocolPlan(
        protocol=plan,
        containers=(
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
        ),
        placements=placements,
    )
