"""Explicit tip schedules and rack replacement boundaries."""

from dataclasses import dataclass

from buildcompiler.protocols.allocation.wells import PLATE_96
from buildcompiler.protocols.backends.opentrons.profile import OpentronsAssemblyProfile
from buildcompiler.protocols.backends.opentrons.program import Call, Reference


@dataclass(frozen=True, slots=True, kw_only=True)
class TipSchedule:
    setup: tuple[Call, ...]
    pickups: tuple[tuple[Call, ...], ...]


def schedule_tips(count: int, *, profile: OpentronsAssemblyProfile) -> TipSchedule:
    """Assign exact tips, accounting for a partially used first rack."""
    first = PLATE_96.index(profile.initial_tip)
    rack_count = (first + count + 95) // 96
    slots = profile.tiprack_positions
    setup = tuple(
        Call(
            target="protocol",
            method="load_labware",
            args=(
                "opentrons_96_tiprack_20ul",
                slots[index] if index < len(slots) else Reference("OFF_DECK"),
            ),
            result=f"tips_{index}",
        )
        for index in range(rack_count)
    )
    pickups = []
    active_batch = 0
    for index in range(first, first + count):
        rack, well = divmod(index, 96)
        batch = rack // len(slots)
        calls = []
        if batch != active_batch:
            for old in range(
                active_batch * len(slots),
                min((active_batch + 1) * len(slots), rack_count),
            ):
                calls.append(
                    Call(
                        target="protocol",
                        method="move_labware",
                        kwargs=(
                            ("labware", Reference(f"tips_{old}")),
                            ("new_location", Reference("OFF_DECK")),
                        ),
                    )
                )
            for new in range(
                batch * len(slots), min((batch + 1) * len(slots), rack_count)
            ):
                calls.append(
                    Call(
                        target="protocol",
                        method="move_labware",
                        kwargs=(
                            ("labware", Reference(f"tips_{new}")),
                            ("new_location", slots[new % len(slots)]),
                        ),
                    )
                )
            active_batch = batch
        calls.append(
            Call(
                target="pipette",
                method="pick_up_tip",
                args=(Reference(f"tips_{rack}", PLATE_96.name(well)),),
            )
        )
        pickups.append(tuple(calls))
    return TipSchedule(setup=setup, pickups=tuple(pickups))
