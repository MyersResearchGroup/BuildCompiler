"""Shared lowering of liquid handling, tip lifecycle and module operations."""

import math
from collections.abc import Mapping

from buildcompiler.protocols.allocation.models import AllocatedProtocolPlan
from buildcompiler.protocols.materials import SamplePoint
from buildcompiler.protocols.steps import (
    DeactivateSourceModule,
    Distribute,
    DropTip,
    LidAction,
    Mix,
    OperatorAction,
    PickUpTip,
    RunTemperatureProgram,
    SetTemperature,
    Transfer,
)
from buildcompiler.protocols.backends.opentrons.program import Call, Record, Reference


def lower_operations(
    plan: AllocatedProtocolPlan,
    *,
    capacities: Mapping[str, float],
    pickups: Mapping[str, tuple[tuple[Call, ...], ...]] | None = None,
) -> tuple[Call, ...]:
    locations = {p.sample_id: p.location for p in plan.placements}
    instructions = []
    attached = {instrument: False for instrument in capacities}
    tip_indices = dict.fromkeys(capacities, 0)

    def point(value: SamplePoint) -> Reference:
        location = locations[value.sample_id]
        return Reference(
            location.container_id,
            location.well_name,
            value.bottom_mm,
            value.top_mm,
            value.track_conical_height,
        )

    def check_volume(instrument: str, *volumes: float) -> None:
        for volume in volumes:
            if not math.isfinite(volume) or not 0 <= volume <= capacities[instrument]:
                raise ValueError(
                    f"Operation exceeds supported {instrument} pipette capacity."
                )

    def pickup(instrument: str) -> None:
        if attached[instrument]:
            raise ValueError(f"A tip is already attached to {instrument}.")
        if pickups is None or instrument not in pickups:
            instructions.append(Call(target=instrument, method="pick_up_tip"))
        else:
            instructions.extend(pickups[instrument][tip_indices[instrument]])
        tip_indices[instrument] += 1
        attached[instrument] = True

    def require_tip(instrument: str) -> None:
        if not attached[instrument]:
            raise ValueError(f"An attached tip is required on {instrument}.")

    def drop(instrument: str) -> None:
        require_tip(instrument)
        instructions.append(Call(target=instrument, method="drop_tip"))
        attached[instrument] = False

    for step in plan.protocol.steps:
        if isinstance(step, Transfer):
            instrument = step.instrument
            volume = (
                min(step.volume_ul, capacities[instrument])
                if step.limit_to_pipette_capacity
                else step.volume_ul
            )
            check_volume(instrument, volume, step.mix_before_ul)
            source, destination = point(step.source), point(step.destination)
            if step.new_tip:
                pickup(instrument)
            require_tip(instrument)
            if step.mix_before_ul:
                instructions.append(
                    Call(
                        target=instrument,
                        method="mix",
                        args=(step.mix_repetitions, step.mix_before_ul, source),
                    )
                )
            instructions.extend(
                (
                    Call(
                        target=instrument,
                        method="aspirate",
                        args=(volume, source),
                        kwargs=(("rate", step.aspiration_rate),),
                    ),
                    Call(
                        target=instrument,
                        method="dispense",
                        args=(volume, destination),
                        kwargs=(("rate", step.dispense_rate),),
                    ),
                )
            )
            if step.blow_out:
                instructions.append(Call(target=instrument, method="blow_out"))
            if step.touch_tip:
                instructions.append(
                    Call(
                        target=instrument,
                        method="touch_tip",
                        kwargs=(("radius", 0.5), ("v_offset", -14), ("speed", 20)),
                    )
                )
            if step.drop_tip:
                drop(instrument)
        elif isinstance(step, PickUpTip):
            pickup(step.instrument)
        elif isinstance(step, DropTip):
            drop(step.instrument)
        elif isinstance(step, Mix):
            require_tip(step.instrument)
            check_volume(step.instrument, step.volume_ul)
            instructions.append(
                Call(
                    target=step.instrument,
                    method="mix",
                    kwargs=(
                        ("repetitions", step.repetitions),
                        ("volume", step.volume_ul),
                        ("location", point(step.location)),
                    ),
                )
            )
        elif isinstance(step, Distribute):
            check_volume(
                step.instrument,
                step.volume_ul + step.disposal_volume_ul + (step.air_gap_ul or 0),
            )
            if step.mix_before:
                check_volume(step.instrument, step.mix_before[1])
            if step.new_tip == "never":
                require_tip(step.instrument)
            elif step.new_tip != "once" or attached[step.instrument]:
                raise ValueError(
                    "A distribution with new_tip='once' requires an empty pipette."
                )
            kwargs = [
                ("volume", step.volume_ul),
                ("source", point(step.source)),
                ("dest", tuple(point(d) for d in step.destinations)),
                ("disposal_volume", step.disposal_volume_ul),
                ("new_tip", step.new_tip),
            ]
            if step.mix_before:
                kwargs.append(("mix_before", step.mix_before))
            if step.air_gap_ul is not None:
                kwargs.append(("air_gap", step.air_gap_ul))
            instructions.append(
                Call(target=step.instrument, method="distribute", kwargs=tuple(kwargs))
            )
            if step.track_liquid_sample_id:
                for destination in step.destinations:
                    instructions.append(
                        Call(
                            target=f"well:{destination.sample_id}",
                            method="load_liquid",
                            kwargs=(
                                (
                                    "liquid",
                                    Reference(f"liquid:{step.track_liquid_sample_id}"),
                                ),
                                ("volume", step.volume_ul),
                            ),
                        )
                    )
        elif isinstance(step, LidAction):
            instructions.append(
                Call(target="reaction_module", method=f"{step.action}_lid")
            )
        elif isinstance(step, SetTemperature):
            target, method = {
                "source": ("source_module", "set_temperature"),
                "reaction": ("reaction_module", "set_block_temperature"),
                "lid": ("reaction_module", "set_lid_temperature"),
            }[step.module]
            instructions.append(
                Call(
                    target=target,
                    method=method,
                    args=(step.celsius,),
                    skip_during_simulation=step.skip_during_simulation,
                )
            )
        elif isinstance(step, DeactivateSourceModule):
            instructions.append(Call(target="source_module", method="deactivate"))
        elif isinstance(step, RunTemperatureProgram):
            instructions.append(
                Call(
                    target="reaction_module",
                    method="execute_profile",
                    kwargs=(
                        (
                            "steps",
                            tuple(
                                Record(
                                    (
                                        ("temperature", s.celsius),
                                        ("hold_time_minutes", s.minutes),
                                    )
                                )
                                for s in step.program.steps
                            ),
                        ),
                        ("repetitions", step.program.repetitions),
                        ("block_max_volume", step.program.block_max_volume_ul),
                    ),
                    skip_during_simulation=step.skip_during_simulation,
                )
            )
        elif isinstance(step, OperatorAction):
            instructions.append(
                Call(target="protocol", method="comment", args=(step.instruction,))
            )
        else:
            raise TypeError(f"Unsupported protocol operation: {type(step).__name__}")
    if any(attached.values()):
        raise ValueError("Protocol ends with an attached tip.")
    return tuple(instructions)
