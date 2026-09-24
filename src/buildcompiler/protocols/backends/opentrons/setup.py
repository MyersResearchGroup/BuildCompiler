"""Shared resource loading and validation for Opentrons targets."""

from buildcompiler.protocols.allocation.models import AllocatedProtocolPlan
from buildcompiler.protocols.allocation.wells import PLATE_96
from buildcompiler.protocols.steps import Distribute, PickUpTip, Transfer
from buildcompiler.protocols.backends.opentrons.program import Call, Reference


def well_aliases(plan: AllocatedProtocolPlan) -> tuple[tuple[str, Reference], ...]:
    return tuple(
        (
            f"well:{p.sample_id}",
            Reference(p.location.container_id, p.location.well_name),
        )
        for p in plan.placements
    )


def load_liquid(
    sample_id: str,
    *,
    name: str,
    color: str,
    volume: float,
    description: str | None = None,
    liquid_id: str | None = None,
    define: bool = True,
) -> tuple[Call, ...]:
    liquid_id = liquid_id or f"liquid:{sample_id}"
    calls = []
    if define:
        kwargs = [("name", name), ("display_color", color)]
        if description is not None:
            kwargs.append(("description", description))
        calls.append(
            Call(
                target="protocol",
                method="define_liquid",
                kwargs=tuple(kwargs),
                result=liquid_id,
            )
        )
    calls.append(
        Call(
            target=f"well:{sample_id}",
            method="load_liquid",
            kwargs=(("liquid", Reference(liquid_id)), ("volume", volume)),
        )
    )
    return tuple(calls)


def validate_tip_capacity(
    plan: AllocatedProtocolPlan, *, starts: dict[str, str | None]
) -> None:
    counts = dict.fromkeys(starts, 0)
    for step in plan.protocol.steps:
        if (
            isinstance(step, PickUpTip)
            or isinstance(step, Transfer)
            and step.new_tip
            or isinstance(step, Distribute)
            and step.new_tip == "once"
        ):
            counts[step.instrument] += 1
    for instrument, count in counts.items():
        available = 96 - PLATE_96.index(starts[instrument] or "A1")
        if count > available:
            raise ValueError(
                f"{instrument} requires {count} tips but only {available} remain."
            )
