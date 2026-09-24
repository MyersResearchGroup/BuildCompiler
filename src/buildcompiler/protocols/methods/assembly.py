"""Assembly planning extracted from PUDU's SBOLLoopAssembly.

The operation order and default parameters preserve that implementation.
No robot, filesystem, or mutable inventory is used while planning.
"""

from buildcompiler.domain.protocol_requests import AssemblyRequest, MaterialRef

from buildcompiler.protocols.config import AssemblyConfig
from buildcompiler.protocols.materials import Sample, SamplePoint
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.steps import (
    DeactivateSourceModule,
    DropTip,
    LidAction,
    OperatorAction,
    RunTemperatureProgram,
    SetTemperature,
    Step,
    Transfer,
)

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
    # Match PUDU's source ordering, but retain full identities as keys.
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
            # PUDU finishes using the final addition's tip. This is explicit
            # in the plan rather than hidden inside a liquid-transfer helper.
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
            instruction="Take out the reagents since the temperature module will be turn off",
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
