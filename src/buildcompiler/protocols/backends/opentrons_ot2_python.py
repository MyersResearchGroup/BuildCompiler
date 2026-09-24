"""Render allocated plans directly as standalone Opentrons Python protocols."""

import keyword
import math

from buildcompiler.protocols.backends import COLORS, TargetProfile, validate_tips
from buildcompiler.protocols.methods.assembly import OpentronsAssemblyProfile
from buildcompiler.protocols.methods.plating import OpentronsPlatingProfile
from buildcompiler.protocols.methods.transformation import (
    OpentronsTransformationProfile,
)
from buildcompiler.protocols.models import (
    PLATE_96,
    DeactivateSourceModule,
    Distribute,
    DropTip,
    LidAction,
    Mix,
    OperatorAction,
    PickUpTip,
    ProtocolPlan,
    RunTemperatureProgram,
    Sample,
    SamplePoint,
    SetTemperature,
    Transfer,
)


def _well(sample: Sample, point: SamplePoint | None = None) -> str:
    """Format a bound well and its optional aspiration or dispense offset."""
    location = sample.location
    if location is None:
        raise ValueError(f"Sample {sample.id} has not been allocated.")
    expression = f"{location.container_id}[{location.well_name!r}]"
    if point is not None:
        if point.bottom_mm is not None:
            expression += f".bottom({point.bottom_mm!r})"
        elif point.top_mm is not None:
            expression += f".top({point.top_mm!r})"
        elif point.track_conical_height:
            expression = f"_conical_source({expression})"
    return expression


def _assembly_tips(
    count: int, profile: OpentronsAssemblyProfile
) -> tuple[list[str], list[list[str]]]:
    """Schedule exact tips and rack swaps, including a partially used first rack."""
    first = PLATE_96.index(profile.initial_tip)
    rack_count = (first + count + 95) // 96
    slots = profile.tiprack_positions
    setup = []
    for index in range(rack_count):
        slot = repr(slots[index]) if index < len(slots) else "protocol_api.OFF_DECK"
        setup.append(
            f"tips_{index} = protocol.load_labware('opentrons_96_tiprack_20ul', {slot})"
        )
    racks = ", ".join(f"tips_{index}" for index in range(rack_count))
    setup.append(
        f"pipette = protocol.load_instrument('p20_single_gen2', {profile.pipette_position!r}, tip_racks=[{racks}])"
    )
    setup.append(f"pipette.starting_tip = tips_0[{profile.initial_tip!r}]")
    pickups = []
    active_batch = 0
    for index in range(first, first + count):
        rack, well = divmod(index, 96)
        batch = rack // len(slots)
        lines = []
        if batch != active_batch:
            # Clear the occupied slots before bringing the next racks on deck.
            for old in range(
                active_batch * len(slots),
                min((active_batch + 1) * len(slots), rack_count),
            ):
                lines.append(
                    f"protocol.move_labware(labware=tips_{old}, new_location=protocol_api.OFF_DECK)"
                )
            for new in range(
                batch * len(slots), min((batch + 1) * len(slots), rack_count)
            ):
                lines.append(
                    f"protocol.move_labware(labware=tips_{new}, new_location={slots[new % len(slots)]!r})"
                )
            active_batch = batch
        lines.append(f"pipette.pick_up_tip(tips_{rack}[{PLATE_96.name(well)!r}])")
        pickups.append(lines)
    return setup, pickups


def _instruments(
    small_slot: str, large_slot: str, starts: dict[str, str | None], *, filtered: bool
) -> list[str]:
    """Load the two pipettes and apply each rack's starting tip."""
    small_rack = (
        "opentrons_96_filtertiprack_20ul" if filtered else "opentrons_96_tiprack_20ul"
    )
    lines = [
        f"small_tips = protocol.load_labware({small_rack!r}, {small_slot!r})",
        f"large_tips = protocol.load_labware('opentrons_96_filtertiprack_200ul', {large_slot!r})",
    ]
    for name, model, mount in (
        ("small", "p20_single_gen2", "left"),
        ("large", "p300_single_gen2", "right"),
    ):
        lines.append(
            f"{name} = protocol.load_instrument({model!r}, {mount!r}, tip_racks=[{name}_tips])"
        )
        if starts[name]:
            lines.append(f"{name}.starting_tip = {name}_tips[{starts[name]!r}]")
    return lines


def _liquid(
    sample: Sample,
    variable: str,
    *,
    name: str,
    color: str,
    description: str | None = None,
    define: bool = True,
) -> list[str]:
    """Define display metadata once and register a sample's initial volume."""
    lines = []
    if define:
        arguments = f"name={name!r}, display_color={color!r}"
        if description is not None:
            arguments += f", description={description!r}"
        lines.append(f"{variable} = protocol.define_liquid({arguments})")
    lines.append(
        f"{_well(sample)}.load_liquid(liquid={variable}, volume={sample.initial_volume_ul!r})"
    )
    return lines


def _operations(
    plan: ProtocolPlan,
    capacities: dict[str, float],
    liquids: dict[str, str],
    pickups: list[list[str]] | None = None,
) -> list[str]:
    """Emit operations in order while checking volumes and tip ownership."""
    samples = {s.id: s for s in plan.samples}
    attached = dict.fromkeys(capacities, False)
    tip_index = 0
    lines = []

    def point(value: SamplePoint) -> str:
        """Resolve a logical sample point to its allocated well expression."""
        return _well(samples[value.sample_id], value)

    def check_volume(instrument: str, *volumes: float) -> None:
        """Check each individual pipette movement against the loaded capacity."""
        for volume in volumes:
            if not math.isfinite(volume) or not 0 <= volume <= capacities[instrument]:
                raise ValueError(
                    f"Operation exceeds supported {instrument} pipette capacity."
                )

    def require_tip(instrument: str) -> None:
        """Reject operations that assume a tip without first attaching one."""
        if not attached[instrument]:
            raise ValueError(f"An attached tip is required on {instrument}.")

    def pickup(instrument: str) -> None:
        """Attach the next tip, including any scheduled rack replacement."""
        nonlocal tip_index
        if attached[instrument]:
            raise ValueError(f"A tip is already attached to {instrument}.")
        if pickups is None:
            lines.append(f"{instrument}.pick_up_tip()")
        else:
            lines.extend(pickups[tip_index])
            tip_index += 1
        attached[instrument] = True

    def drop(instrument: str) -> None:
        """Emit a drop and clear the instrument's tracked tip state."""
        require_tip(instrument)
        lines.append(f"{instrument}.drop_tip()")
        attached[instrument] = False

    for step in plan.steps:
        start = len(lines)
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
                lines.append(
                    f"{instrument}.mix({step.mix_repetitions!r}, {step.mix_before_ul!r}, {source})"
                )
            lines.extend(
                (
                    f"{instrument}.aspirate({volume!r}, {source}, rate={step.aspiration_rate!r})",
                    f"{instrument}.dispense({volume!r}, {destination}, rate={step.dispense_rate!r})",
                )
            )
            if step.blow_out:
                lines.append(f"{instrument}.blow_out()")
            if step.touch_tip:
                lines.append(
                    f"{instrument}.touch_tip(radius=0.5, v_offset=-14, speed=20)"
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
            lines.append(
                f"{step.instrument}.mix(repetitions={step.repetitions!r}, volume={step.volume_ul!r}, location={point(step.location)})"
            )
        elif isinstance(step, Distribute):
            # The SDK splits a group into refills; capacity applies to one
            # destination plus disposal volume and air, not the whole group.
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
            destinations = ", ".join(point(d) for d in step.destinations)
            arguments = f"volume={step.volume_ul!r}, source={point(step.source)}, dest=[{destinations}], disposal_volume={step.disposal_volume_ul!r}, new_tip={step.new_tip!r}"
            if step.mix_before:
                arguments += f", mix_before={step.mix_before!r}"
            if step.air_gap_ul is not None:
                arguments += f", air_gap={step.air_gap_ul!r}"
            lines.append(f"{step.instrument}.distribute({arguments})")
            if step.track_liquid_sample_id:
                liquid = liquids[step.track_liquid_sample_id]
                for destination in step.destinations:
                    lines.append(
                        f"{point(destination)}.load_liquid(liquid={liquid}, volume={step.volume_ul!r})"
                    )
        elif isinstance(step, LidAction):
            if step.action not in ("open", "close"):
                raise ValueError("Unsupported lid action.")
            lines.append(f"reaction_module.{step.action}_lid()")
        elif isinstance(step, SetTemperature):
            target = {
                "source": "source_module.set_temperature",
                "reaction": "reaction_module.set_block_temperature",
                "lid": "reaction_module.set_lid_temperature",
            }[step.module]
            lines.append(f"{target}({step.celsius!r})")
        elif isinstance(step, DeactivateSourceModule):
            lines.append("source_module.deactivate()")
        elif isinstance(step, RunTemperatureProgram):
            program = step.program
            stages = [
                {"temperature": s.celsius, "hold_time_minutes": s.minutes}
                for s in program.steps
            ]
            lines.append(
                f"reaction_module.execute_profile(steps={stages!r}, repetitions={program.repetitions!r}, block_max_volume={program.block_max_volume_ul!r})"
            )
        elif isinstance(step, OperatorAction):
            lines.append(f"protocol.comment({step.instruction!r})")
        else:
            raise TypeError(f"Unsupported protocol operation: {type(step).__name__}")
        if getattr(step, "skip_during_simulation", False):
            lines[start:] = [
                "if not protocol.is_simulating():",
                *(f"    {line}" for line in lines[start:]),
            ]
    if any(attached.values()):
        raise ValueError("Protocol ends with an attached tip.")
    return lines


def render_python(plan: ProtocolPlan, *, profile: TargetProfile) -> str:
    """Generate a standalone script without importing or running the robot SDK."""
    containers = {c.id: c for c in plan.containers}
    for name in containers:
        if not name.isidentifier() or keyword.iskeyword(name):
            raise ValueError(f"Invalid container identifier: {name!r}")
    samples = {s.id: s for s in plan.samples}
    liquids = {}
    pickups = None
    lines = []

    def load(name: str) -> None:
        """Load a declared container on its module or deck slot."""
        container = containers[name]
        if container.parent in ("source_module", "reaction_module"):
            lines.append(
                f"{name} = {container.parent}.load_labware({container.definition_id!r})"
            )
        else:
            lines.append(
                f"{name} = protocol.load_labware({container.definition_id!r}, {container.parent!r})"
            )

    if isinstance(profile, (OpentronsAssemblyProfile, OpentronsTransformationProfile)):
        lines.append(
            f"source_module = protocol.load_module('temperature module', {profile.temperature_module_position!r})"
        )
        load("sources")
        lines.append("reaction_module = protocol.load_module('thermocycler module')")
        load("reactions")
    else:
        lines.append("reaction_module = protocol.load_module('thermocyclerModuleV1')")
        load("reactions")

    if isinstance(profile, OpentronsAssemblyProfile):
        setup, pickups = _assembly_tips(
            sum(isinstance(s, Transfer) and s.new_tip for s in plan.steps), profile
        )
        lines.extend(setup)
        capacities = {"pipette": profile.max_volume_ul}
        for index, sample_id in enumerate(plan.input_sample_ids):
            sample = samples[sample_id]
            label = sample.liquid_label or sample.material.label
            variable = f"liquid_{index}"
            liquids[sample_id] = variable
            lines.extend(
                _liquid(
                    sample,
                    variable,
                    name=label,
                    description=label,
                    color=COLORS[index % len(COLORS)],
                )
            )
    elif isinstance(profile, OpentronsTransformationProfile):
        if "dna_plate" in containers:
            load("dna_plate")
        load("tube_rack")
        starts = {"small": profile.initial_tip_p20, "large": profile.initial_tip_p300}
        validate_tips(plan, starts)
        lines.extend(
            _instruments(
                profile.tiprack_p20_position,
                profile.tiprack_p200_position,
                starts,
                filtered=False,
            )
        )
        capacities = {"small": 20, "large": 200}
        dna_liquids = {}
        for sample_id in plan.input_sample_ids:
            sample = samples[sample_id]
            variable = f"liquid_{len(liquids)}"
            if sample.role == "dna":
                define = sample.material.identity not in dna_liquids
                if define:
                    dna_liquids[sample.material.identity] = (variable, len(dna_liquids))
                variable, color_index = dna_liquids[sample.material.identity]
                lines.extend(
                    _liquid(
                        sample,
                        variable,
                        name=sample.material.label,
                        description=f"{sample.material.label} DNA construct",
                        color=COLORS[color_index % len(COLORS)],
                        define=define,
                    )
                )
            else:
                lines.extend(
                    _liquid(
                        sample,
                        variable,
                        name=sample.liquid_label,
                        color=COLORS[(sample.replicate - 1) % len(COLORS)],
                    )
                )
            liquids[sample_id] = variable
    elif isinstance(profile, OpentronsPlatingProfile):
        starts = {
            "small": profile.initial_small_tip,
            "large": profile.initial_large_tip,
        }
        validate_tips(plan, starts)
        lines.extend(
            _instruments(
                profile.small_tiprack_position,
                profile.large_tiprack_position,
                starts,
                filtered=True,
            )
        )
        capacities = {"small": 20, "large": 200}
        load("tube_rack")
        bacteria_index = 0
        for sample_id in plan.input_sample_ids:
            sample = samples[sample_id]
            variable = f"liquid_{len(liquids)}"
            liquids[sample_id] = variable
            if sample.role == "broth":
                lines.extend(
                    _liquid(
                        sample,
                        variable,
                        name="liquid_broth",
                        description="Liquid broth for dilutions",
                        color="#D2B48C",
                    )
                )
            else:
                lines.extend(
                    _liquid(
                        sample,
                        variable,
                        name="transformed_bacteria",
                        description=sample.liquid_label,
                        color=COLORS[bacteria_index % len(COLORS)],
                    )
                )
                bacteria_index += 1
        for name in sorted(
            (name for name in containers if name.startswith(("dilution_", "agar_"))),
            key=lambda name: (not name.startswith("dilution_"), name),
        ):
            load(name)
    else:
        raise TypeError(f"Unsupported profile: {type(profile).__name__}")

    lines.extend(_operations(plan, capacities, liquids, pickups))
    metadata = {
        "protocolName": plan.id,
        "author": "BuildCompiler",
        "apiLevel": profile.api_level,
    }
    header = [
        "# Generated by BuildCompiler.",
        "from opentrons import protocol_api",
        "",
        f"metadata = {metadata!r}",
        "",
    ]
    if isinstance(profile, OpentronsPlatingProfile):
        header.extend(
            [
                "def _conical_source(well):",
                '    """Follow the liquid surface, falling back to the default below 20%."""',
                "    try:",
                "        volume = well.current_liquid_volume()",
                "        if volume is None or volume < well.max_volume * 0.2:",
                "            return well",
                "        return well.bottom(max((volume / well.max_volume) * (well.depth - 10) - 10, 3))",
                "    except Exception:",
                "        return well",
                "",
            ]
        )
    header.extend(
        [
            "def run(protocol: protocol_api.ProtocolContext):",
            '    """Load the deck and execute the compiled protocol in order."""',
        ]
    )
    return "\n".join([*header, *(f"    {line}" for line in lines)]) + "\n"
