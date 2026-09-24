"""Assembly method: configuration, planning and well allocation."""

import math
from dataclasses import dataclass

from buildcompiler.domain.protocol_requests import AssemblyRequest, MaterialRef
from buildcompiler.protocols.models import (
    BLOCK_24,
    PLATE_96,
    ConfigOverrides,
    ContainerSpec,
    DeactivateSourceModule,
    DropTip,
    LidAction,
    OperatorAction,
    ProtocolPlan,
    RunTemperatureProgram,
    Sample,
    SamplePoint,
    SetTemperature,
    Step,
    TemperatureProgram,
    TemperatureStep,
    Transfer,
    WellRef,
    positive,
    positive_integer,
    validate_slots,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyConfig(ConfigOverrides):
    """Reaction volumes, replicate count and assembly incubation programs."""

    volume_total_reaction: float = 20
    volume_part: float = 2
    volume_restriction_enzyme: float = 2
    volume_t4_dna_ligase: float = 4
    volume_t4_dna_ligase_buffer: float = 2
    replicates: int = 1
    aspiration_rate: float = 0.5
    dispense_rate: float = 1
    water_testing: bool = False
    source_temperature: float = 4
    lid_temperature: float = 42
    hold_temperature: float = 4
    cycling: TemperatureProgram = TemperatureProgram(
        steps=(
            TemperatureStep(celsius=42, minutes=2),
            TemperatureStep(celsius=16, minutes=5),
        ),
        repetitions=75,
        block_max_volume_ul=30,
    )
    finishing: TemperatureProgram = TemperatureProgram(
        steps=(
            TemperatureStep(celsius=60, minutes=10),
            TemperatureStep(celsius=80, minutes=10),
        ),
        repetitions=1,
        block_max_volume_ul=30,
    )

    def __post_init__(self) -> None:
        positive_integer(self.replicates, "replicates")
        if type(self.water_testing) is not bool:
            raise ValueError("water_testing must be a boolean.")
        for name in (
            "volume_total_reaction",
            "volume_part",
            "volume_restriction_enzyme",
            "volume_t4_dna_ligase",
            "volume_t4_dna_ligase_buffer",
            "aspiration_rate",
            "dispense_rate",
        ):
            positive(getattr(self, name), name)
        for name in ("source_temperature", "lid_temperature", "hold_temperature"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        for program in (self.cycling, self.finishing):
            if not isinstance(program, TemperatureProgram):
                raise TypeError(
                    "Temperature programs must be TemperatureProgram records."
                )
            if not isinstance(program.steps, tuple) or not program.steps:
                raise ValueError(
                    "Temperature programs require a nonempty tuple of steps."
                )
            if type(program.repetitions) is not int or program.repetitions < 1:
                raise ValueError("Program repetitions must be positive integers.")
            if (
                not math.isfinite(program.block_max_volume_ul)
                or program.block_max_volume_ul <= 0
            ):
                raise ValueError("Program block volume must be finite and positive.")
            for step in program.steps:
                if (
                    not math.isfinite(step.celsius)
                    or not math.isfinite(step.minutes)
                    or step.minutes < 0
                ):
                    raise ValueError("Invalid temperature program step.")


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsAssemblyProfile:
    """Assembly deck slots, pipette mount and starting well/tip offsets."""

    api_level: str = "2.21"
    temperature_module_position: str = "1"
    thermocycler_starting_well: int = 0
    tiprack_positions: tuple[str, ...] = ("2", "3", "4", "5", "6", "9")
    pipette_position: str = "left"
    initial_tip: str = "A1"

    def __post_init__(self) -> None:
        if self.api_level != "2.21":
            raise ValueError("This backend currently supports API 2.21.")
        if self.pipette_position not in ("left", "right"):
            raise ValueError("Invalid pipette mount.")
        PLATE_96.name(self.thermocycler_starting_well)
        PLATE_96.index(self.initial_tip)
        if not isinstance(self.tiprack_positions, tuple) or not self.tiprack_positions:
            raise ValueError("tiprack_positions must be a nonempty tuple.")
        validate_slots((self.temperature_module_position, *self.tiprack_positions))

    @property
    def max_volume_ul(self) -> float:
        """Maximum transfer volume of the supported assembly pipette."""

        return 20


WATER = MaterialRef(identity="urn:buildcompiler:water", label="Deionized Water")


BUFFER = MaterialRef(
    identity="urn:buildcompiler:ligase-buffer", label="T4 DNA Ligase Buffer"
)


LIGASE = MaterialRef(identity="urn:buildcompiler:ligase", label="T4 DNA Ligase")


def plan_assembly(request: AssemblyRequest, *, config: AssemblyConfig) -> ProtocolPlan:
    """Expand ordered reactions into a logical plan with stable sample lineage."""
    enzymes = {}
    parts = {}
    for reaction in request.reactions:
        enzymes[reaction.restriction_enzyme.identity] = reaction.restriction_enzyme
        for material in (reaction.backbone, *reaction.parts):
            previous = parts.get(material.identity)
            if previous is not None and previous != material:
                raise ValueError(f"Conflicting labels for {material.identity}.")
            parts[material.identity] = material
    # Sort labels for stable source positions; retain identities for lookups.
    ordered = (
        WATER,
        BUFFER,
        LIGASE,
        *sorted(enzymes.values(), key=lambda item: (item.label, item.identity)),
        *sorted(parts.values(), key=lambda item: (item.label, item.identity)),
    )
    if len({material.identity for material in ordered}) != len(ordered):
        raise ValueError("Source roles require distinct material identities.")
    samples = [
        Sample(
            id=f"{request.id}/source/{index}",
            material=material,
            initial_volume_ul=1000,
            liquid_label=f"Restriction Enzyme {material.label}"
            if material.identity in enzymes
            else material.label,
        )
        for index, material in enumerate(ordered)
    ]
    sources = {sample.material.identity: sample for sample in samples}
    input_ids = tuple(sample.id for sample in samples)
    output_ids = []
    steps: list[Step] = [LidAction(id="open-lid", action="open")]
    if not config.water_testing:
        steps.extend(
            (
                SetTemperature(
                    id="cool-source", module="source", celsius=config.source_temperature
                ),
                SetTemperature(
                    id="cool-reaction",
                    module="reaction",
                    celsius=config.source_temperature,
                ),
            )
        )

    for index, reaction in enumerate(request.reactions):
        components = (reaction.backbone, *reaction.parts)
        fixed_volume = (
            config.volume_t4_dna_ligase_buffer
            + config.volume_t4_dna_ligase
            + config.volume_restriction_enzyme
        )
        water_volume = (
            config.volume_total_reaction
            - fixed_volume
            - config.volume_part * len(components)
        )
        if water_volume <= 0:
            raise ValueError(
                f"Reaction {reaction.id} has no remaining volume for water."
            )
        additions = (
            (WATER, water_volume, False),
            (BUFFER, config.volume_t4_dna_ligase_buffer, True),
            (LIGASE, config.volume_t4_dna_ligase, True),
            (reaction.restriction_enzyme, config.volume_restriction_enzyme, True),
            *((part, config.volume_part, True) for part in components),
        )
        for replicate in range(1, config.replicates + 1):
            sample = Sample(
                id=f"{request.id}/reaction/{index}/replicate/{replicate}",
                material=reaction.product,
                parent_ids=tuple(sources[part.identity].id for part in components),
                replicate=replicate,
            )
            samples.append(sample)
            output_ids.append(sample.id)
            for addition_index, (material, volume, mix) in enumerate(additions):
                steps.append(
                    Transfer(
                        id=f"{sample.id}/addition/{addition_index}",
                        source=SamplePoint(sample_id=sources[material.identity].id),
                        destination=SamplePoint(sample_id=sample.id),
                        volume_ul=volume,
                        aspiration_rate=config.aspiration_rate,
                        dispense_rate=config.dispense_rate,
                        mix_before_ul=volume if mix else 0,
                        drop_tip=addition_index != len(additions) - 1,
                    )
                )
            # Finish mixing with the tip retained from the final addition.
            for mix_index in range(int(config.volume_total_reaction / 10)):
                steps.append(
                    Transfer(
                        id=f"{sample.id}/finish/{mix_index}",
                        source=SamplePoint(sample_id=sample.id, bottom_mm=0),
                        destination=SamplePoint(sample_id=sample.id, bottom_mm=8),
                        volume_ul=config.volume_total_reaction,
                        aspiration_rate=1,
                        dispense_rate=1,
                        new_tip=False,
                        drop_tip=False,
                        limit_to_pipette_capacity=True,
                    )
                )
            steps.append(DropTip(id=f"{sample.id}/drop-tip"))

    steps.append(
        OperatorAction(
            id="remove-reagents",
            instruction="Remove the reagents before the source temperature module is deactivated.",
        )
    )
    if not config.water_testing:
        steps.extend(
            (
                LidAction(id="close-lid", action="close"),
                SetTemperature(
                    id="heat-lid", module="lid", celsius=config.lid_temperature
                ),
                DeactivateSourceModule(id="deactivate-source"),
                RunTemperatureProgram(id="cycling", program=config.cycling),
                RunTemperatureProgram(id="finishing", program=config.finishing),
                SetTemperature(
                    id="hold", module="reaction", celsius=config.hold_temperature
                ),
            )
        )
    return ProtocolPlan(
        id=request.id,
        request_id=request.id,
        samples=tuple(samples),
        input_sample_ids=input_ids,
        output_sample_ids=tuple(output_ids),
        steps=tuple(steps),
    )


def allocate_assembly(
    plan: ProtocolPlan, *, profile: OpentronsAssemblyProfile
) -> ProtocolPlan:
    """Assign sources and reactions in column-major order on their plates."""
    if len(plan.input_sample_ids) > BLOCK_24.capacity:
        raise ValueError("Assembly source block capacity exceeded.")
    if (
        len(plan.output_sample_ids) + profile.thermocycler_starting_well
        > PLATE_96.capacity
    ):
        raise ValueError("Assembly reaction plate capacity exceeded.")
    locations = {
        sample_id: WellRef(container_id="sources", well_name=BLOCK_24.name(i))
        for i, sample_id in enumerate(plan.input_sample_ids)
    }
    locations.update(
        {
            sample_id: WellRef(
                container_id="reactions",
                well_name=PLATE_96.name(i + profile.thermocycler_starting_well),
            )
            for i, sample_id in enumerate(plan.output_sample_ids)
        }
    )
    return plan.with_locations(
        (
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
        locations,
    )
