"""Render a review document directly from the same plan used by automation."""

from buildcompiler.protocols.allocation.models import AllocatedProtocolPlan
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.steps import (
    DeactivateSourceModule,
    DropTip,
    LidAction,
    OperatorAction,
    RunTemperatureProgram,
    SetTemperature,
    Transfer,
    Distribute,
    PickUpTip,
    Mix,
)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


def render_markdown(
    plan: ProtocolPlan, *, allocation: AllocatedProtocolPlan | None = None
) -> str:
    """Render planned operations, never claim that an experiment has run."""
    if allocation is not None and allocation.protocol != plan:
        raise ValueError("Allocation belongs to a different protocol plan.")
    samples = {sample.id: sample for sample in plan.samples}
    locations = (
        {p.sample_id: p.location for p in allocation.placements} if allocation else {}
    )

    def describe(sample_id: str) -> str:
        sample = samples[sample_id]
        result = _escape(sample.material.label)
        if sample.replicate is not None:
            result += f" (replicate {sample.replicate})"
        if sample_id in locations:
            location = locations[sample_id]
            result += f" [{location.container_id}/{location.well_name}]"
        return result

    lines = [
        f"# Protocol {_escape(plan.id)}",
        "",
        "Status: planned. This document describes the compiled protocol; it is not an execution record.",
        "",
        "## Operations",
        "",
    ]
    for index, step in enumerate(plan.steps, 1):
        if isinstance(step, Transfer):
            action = f"Transfer {step.volume_ul:g} µL from {describe(step.source.sample_id)} to {describe(step.destination.sample_id)}."
            if step.limit_to_pipette_capacity:
                action += " Limit each movement to the selected pipette capacity."
            if step.mix_before_ul:
                action += f" Mix source {step.mix_repetitions} times at {step.mix_before_ul:g} µL first."
            action += " Use a new tip." if step.new_tip else " Retain the attached tip."
            if step.drop_tip:
                action += " Discard the tip afterward."
        elif isinstance(step, Distribute):
            action = (
                f"Distribute {step.volume_ul:g} µL from {describe(step.source.sample_id)} to each of: "
                + "; ".join(describe(d.sample_id) for d in step.destinations)
                + "."
            )
            if step.mix_before:
                action += f" Mix source {step.mix_before[0]} times at {step.mix_before[1]:g} µL first."
            action += f" Tip policy: {step.new_tip}; disposal volume: {step.disposal_volume_ul:g} µL."
            if step.air_gap_ul:
                action += f" Air gap: {step.air_gap_ul:g} µL."
        elif isinstance(step, Mix):
            action = f"Mix {describe(step.location.sample_id)} {step.repetitions} times at {step.volume_ul:g} µL."
        elif isinstance(step, PickUpTip):
            action = f"Pick up a tip on {step.instrument}."
        elif isinstance(step, DropTip):
            action = "Discard the attached tip."
        elif isinstance(step, SetTemperature):
            action = f"Set {step.module} temperature to {step.celsius:g} °C."
        elif isinstance(step, RunTemperatureProgram):
            program = "; ".join(
                f"{s.celsius:g} °C for {s.minutes:g} minutes"
                for s in step.program.steps
            )
            action = f"Run {program}; repetitions: {step.program.repetitions}."
        elif isinstance(step, LidAction):
            action = f"{step.action.capitalize()} the thermocycler lid."
        elif isinstance(step, DeactivateSourceModule):
            action = "Deactivate the source temperature module."
        elif isinstance(step, OperatorAction):
            action = step.instruction
        else:
            raise TypeError(f"Unsupported operation: {type(step).__name__}")
        if getattr(step, "skip_during_simulation", False):
            action += " Omitted during Opentrons simulation (PUDU behavior)."
        lines.append(f"{index}. {action}")
    lines.extend(("", "## Planned outputs", ""))
    for sample_id in plan.output_sample_ids:
        sample = samples[sample_id]
        lines.append(
            f"- {describe(sample_id)} — `{sample.material.identity}`; sample `{sample.id}`"
        )
    return "\n".join(lines) + "\n"
