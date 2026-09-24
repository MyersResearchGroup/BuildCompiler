"""Pure plating plan, with explicit intermediate samples and shared operations.

Derived from pudu/plating.py (MIT); see protocols/attribution.py.
"""

from buildcompiler.domain.protocol_requests import MaterialRef, PlatingRequest
from buildcompiler.protocols.materials import Sample, SamplePoint
from buildcompiler.protocols.methods.plating_config import PlatingConfig
from buildcompiler.protocols.plans import ProtocolPlan
from buildcompiler.protocols.steps import (
    Distribute,
    DropTip,
    LidAction,
    Mix,
    PickUpTip,
    SetTemperature,
    Transfer,
)


def plan_plating(
    request: PlatingRequest, *, config: PlatingConfig, inputs: tuple[Sample, ...]
) -> ProtocolPlan:
    available = {s.id: s for s in inputs}
    if set(request.sample_ids) - available.keys():
        raise ValueError("Plating sources are missing from the source manifest.")
    if (
        len(request.sample_ids) * config.replicates * config.number_dilutions
        > config.max_colonies
    ):
        raise ValueError("Plating exceeds max_colonies.")
    broth = Sample(
        id=f"{request.id}/broth",
        role="broth",
        initial_volume_ul=config.volume_lb,
        material=MaterialRef(
            identity="urn:buildcompiler:liquid-broth", label="liquid_broth"
        ),
    )
    sources = []
    dilutions, spots = {}, {}
    for index, sample_id in enumerate(request.sample_ids):
        upstream = available[sample_id]
        source = Sample(
            id=f"{request.id}/source/{index}",
            role="bacteria",
            material=upstream.material,
            initial_volume_ul=config.volume_total_reaction,
            source_sample_id=upstream.id,
            contents=upstream.contents or (upstream.material.label,),
            liquid_label=upstream.liquid_label
            or str(list(upstream.contents or (upstream.material.label,))),
        )
        sources.append(source)
        parent = source
        for dilution in range(1, config.number_dilutions + 1):
            diluted = Sample(
                id=f"{request.id}/dilution/{index}/{dilution}",
                role="dilution",
                material=source.material,
                parent_ids=(parent.id, broth.id),
                dilution=dilution,
                contents=source.contents,
            )
            dilutions[index, dilution] = diluted
            parent = diluted
            for replicate in range(1, config.replicates + 1):
                spots[index, dilution, replicate] = Sample(
                    id=f"{request.id}/agar/{index}/{dilution}/{replicate}",
                    role="agar",
                    material=source.material,
                    parent_ids=(diluted.id,),
                    dilution=dilution,
                    replicate=replicate,
                    contents=source.contents,
                )
    steps = [
        SetTemperature(id="chill-reactions", module="reaction", celsius=4),
        LidAction(id="open-lid", action="open"),
        PickUpTip(id="broth-tip", instrument="large"),
    ]
    ordered_dilutions = [
        dilutions[index, dilution]
        for dilution in range(1, config.number_dilutions + 1)
        for index in range(len(sources))
    ]
    for start in range(0, len(ordered_dilutions), 8):
        steps.append(
            Distribute(
                id=f"broth/{start}",
                source=SamplePoint(sample_id=broth.id, track_conical_height=True),
                destinations=tuple(
                    SamplePoint(sample_id=s.id)
                    for s in ordered_dilutions[start : start + 8]
                ),
                volume_ul=config.volume_lb_transfer,
                disposal_volume_ul=4,
                new_tip="never",
                track_liquid_sample_id=broth.id,
            )
        )
    steps.append(DropTip(id="broth-tip-drop", instrument="large"))

    def transfer(id, source, destination, volume, *, agar=False):
        return Transfer(
            id=id,
            source=SamplePoint(sample_id=source.id),
            destination=SamplePoint(
                sample_id=destination.id, top_mm=-8 if agar else None
            ),
            volume_ul=volume,
            aspiration_rate=config.aspiration_rate,
            dispense_rate=config.dispense_rate,
            instrument="small",
            new_tip=False,
            drop_tip=False,
            touch_tip=False,
            blow_out=agar,
        )

    for index, source in enumerate(sources):
        steps.append(PickUpTip(id=f"dilution-tip/{index}", instrument="small"))
        parent = source
        for dilution in range(1, config.number_dilutions + 1):
            destination = dilutions[index, dilution]
            steps.append(
                transfer(
                    f"seed/{index}/{dilution}",
                    parent,
                    destination,
                    config.volume_bacteria_transfer,
                )
            )
            steps.append(
                Mix(
                    id=f"mix/{index}/{dilution}",
                    location=SamplePoint(sample_id=destination.id),
                    volume_ul=config.mix_volume,
                    repetitions=5,
                    instrument="small",
                )
            )
            parent = destination
        for dilution in range(1, config.number_dilutions + 1):
            if dilution > 1:
                steps.append(
                    PickUpTip(id=f"agar-tip/{index}/{dilution}", instrument="small")
                )
            for replicate in range(1, config.replicates + 1):
                steps.append(
                    transfer(
                        f"spot/{index}/{dilution}/{replicate}",
                        dilutions[index, dilution],
                        spots[index, dilution, replicate],
                        config.volume_colony,
                        agar=True,
                    )
                )
            steps.append(
                DropTip(id=f"agar-drop/{index}/{dilution}", instrument="small")
            )
    return ProtocolPlan(
        id=request.id,
        request_id=request.id,
        samples=(broth, *sources, *ordered_dilutions, *spots.values()),
        input_sample_ids=(broth.id, *(s.id for s in sources)),
        output_sample_ids=tuple(s.id for s in spots.values()),
        steps=tuple(steps),
    )
