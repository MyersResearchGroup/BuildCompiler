"""Shared OT-2 target contracts and rendering utilities."""

from typing import Literal

from buildcompiler.protocols.methods.assembly import OpentronsAssemblyProfile
from buildcompiler.protocols.methods.plating import OpentronsPlatingProfile
from buildcompiler.protocols.methods.transformation import (
    OpentronsTransformationProfile,
)
from buildcompiler.protocols.models import (
    PLATE_96,
    Distribute,
    PickUpTip,
    ProtocolPlan,
    Transfer,
)

ProtocolBackend = Literal["opentrons_ot2_python", "opentrons_ot2_json"]

# Colors are display metadata; all lookups use sample or material identities.
COLORS = (
    "#4040BF",
    "#BF4040",
    "#40BF40",
    "#A640BF",
    "#BFBF40",
    "#BF7340",
    "#40BFBF",
    "#BF40A6",
    "#73BF40",
    "#4073BF",
    "#BF8C40",
    "#40BF73",
    "#7340BF",
    "#A6BF40",
    "#BF5940",
    "#40A6BF",
    "#BF4073",
    "#59BF40",
    "#BFA640",
    "#40BFA6",
    "#8CBF40",
    "#40BF59",
    "#40BF8C",
    "#BF40A6",
)

TargetProfile = (
    OpentronsAssemblyProfile | OpentronsTransformationProfile | OpentronsPlatingProfile
)


def validate_tips(plan: ProtocolPlan, starts: dict[str, str | None]) -> None:
    """Reject a batch that would exhaust a pipette's single on-deck rack."""
    counts = dict.fromkeys(starts, 0)
    for step in plan.steps:
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
