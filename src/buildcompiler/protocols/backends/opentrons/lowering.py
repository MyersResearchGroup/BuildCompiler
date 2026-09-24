"""Lower shared operations into explicit SDK calls, preserving PUDU ordering."""

from buildcompiler.protocols.backends.opentrons.operations import lower_operations

from buildcompiler.protocols.allocation.models import AllocatedProtocolPlan
from buildcompiler.protocols.steps import (
    Transfer,
)
from buildcompiler.protocols.backends.opentrons.profile import OpentronsAssemblyProfile
from buildcompiler.protocols.backends.opentrons.program import (
    Call,
    OpentronsProgram,
    Reference,
    SetStartingTip,
)
from buildcompiler.protocols.backends.opentrons.tips import schedule_tips

from buildcompiler.protocols.backends.opentrons.palette import COLORS


def lower(
    plan: AllocatedProtocolPlan, *, profile: OpentronsAssemblyProfile
) -> OpentronsProgram:
    logical = plan.protocol
    tips = schedule_tips(
        sum(isinstance(s, Transfer) and s.new_tip for s in logical.steps),
        profile=profile,
    )
    instructions: list[Call | SetStartingTip] = [
        Call(
            target="protocol",
            method="load_module",
            kwargs=(
                ("module_name", "temperature module"),
                ("location", profile.temperature_module_position),
            ),
            result="source_module",
        ),
        Call(
            target="source_module",
            method="load_labware",
            args=(plan.containers[0].definition_id,),
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
            args=(plan.containers[1].definition_id,),
            result="reactions",
        ),
        *tips.setup,
        Call(
            target="protocol",
            method="load_instrument",
            args=("p20_single_gen2", profile.pipette_position),
            kwargs=(("tip_racks", tuple(Reference(c.result) for c in tips.setup)),),
            result="pipette",
        ),
        SetStartingTip(pipette="pipette", tip=Reference("tips_0", profile.initial_tip)),
    ]
    locations = {
        placement.sample_id: placement.location for placement in plan.placements
    }
    samples = {sample.id: sample for sample in logical.samples}
    for index, sample_id in enumerate(logical.input_sample_ids):
        sample = samples[sample_id]
        label = sample.liquid_label or sample.material.label
        liquid_id = f"liquid_{index}"
        instructions.extend(
            (
                Call(
                    target="protocol",
                    method="define_liquid",
                    kwargs=(
                        ("name", label),
                        ("description", label),
                        ("display_color", COLORS[index % len(COLORS)]),
                    ),
                    result=liquid_id,
                ),
                Call(
                    target=f"well:{sample_id}",
                    method="load_liquid",
                    args=(Reference(liquid_id),),
                    kwargs=(("volume", sample.initial_volume_ul),),
                ),
            )
        )
    well_references = {
        f"well:{sample_id}": Reference(location.container_id, location.well_name)
        for sample_id, location in locations.items()
    }
    instructions.extend(
        lower_operations(
            plan,
            capacities={"pipette": profile.max_volume_ul},
            pickups={"pipette": tips.pickups},
        )
    )
    return OpentronsProgram(
        api_level=profile.api_level,
        instructions=tuple(instructions),
        wells=tuple(well_references.items()),
    )
