"""Plating method: configuration, planning and well allocation."""

from collections import Counter
from dataclasses import dataclass

from buildcompiler.domain.protocol_requests import MaterialRef, PlatingRequest
from buildcompiler.protocols.models import (
    PLATE_96,
    ConfigOverrides,
    ContainerSpec,
    Distribute,
    DropTip,
    LidAction,
    Mix,
    OutputManifest,
    PickUpTip,
    ProtocolPlan,
    Sample,
    SamplePoint,
    SetTemperature,
    Transfer,
    WellGrid,
    WellRef,
    positive,
    positive_integer,
    validate_slots,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatingConfig(ConfigOverrides):
    """Dilution volumes, spotting replicates and liquid-handling rates."""

    volume_total_reaction: float = 20
    volume_bacteria_transfer: float = 2
    volume_colony: float = 4
    dilution_factor: float = 10
    volume_lb: float = 10000
    replicates: int = 1
    number_dilutions: int = 2
    max_colonies: int = 192
    aspiration_rate: float = 0.5
    dispense_rate: float = 1

    def __post_init__(self) -> None:
        for name in (
            "volume_total_reaction",
            "volume_bacteria_transfer",
            "volume_colony",
            "dilution_factor",
            "volume_lb",
            "aspiration_rate",
            "dispense_rate",
        ):
            positive(getattr(self, name), name)
        for name in ("replicates", "number_dilutions", "max_colonies"):
            positive_integer(getattr(self, name), name)
        if self.replicates > 8 or self.number_dilutions > 2:
            raise ValueError(
                "Plating supports at most eight replicates and two dilutions."
            )
        if self.dilution_factor <= 1 or self.dilution_volume <= 1:
            raise ValueError("Dilution factor and dilution volume must exceed one.")
        required = self.volume_colony * self.replicates
        if self.number_dilutions == 2:
            required += self.volume_bacteria_transfer
        if self.dilution_volume < required:
            raise ValueError(
                "Dilution volume is insufficient for plating and subsequent seeding."
            )

    @property
    def volume_lb_transfer(self) -> float:
        """Broth added before inoculating each dilution well."""

        return self.volume_bacteria_transfer * (self.dilution_factor - 1)

    @property
    def dilution_volume(self) -> float:
        """Final volume of a dilution before seeding or spotting."""

        return self.volume_bacteria_transfer * self.dilution_factor

    @property
    def mix_volume(self) -> float:
        """Mix below the liquid volume and the small-pipette limit."""

        return min(19, self.dilution_volume - 1)


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsPlatingProfile:
    """Plating source labware, deck slots and starting tip/tube positions."""

    api_level: str = "2.21"
    thermocycler_labware: str = "biorad_96_wellplate_200ul_pcr"
    small_tiprack_position: str = "9"
    large_tiprack_position: str = "1"
    initial_small_tip: str | None = None
    initial_large_tip: str | None = None
    dilution_plate_position1: str = "2"
    dilution_plate_position2: str = "3"
    agar_plate_position1: str = "5"
    agar_plate_position2: str = "6"
    tube_rack_position: str = "4"
    lb_tube_position: int = 0

    def __post_init__(self) -> None:
        if self.api_level != "2.21":
            raise ValueError("This backend currently supports API 2.21.")
        if self.thermocycler_labware not in (
            "biorad_96_wellplate_200ul_pcr",
            "nest_96_wellplate_100ul_pcr_full_skirt",
        ):
            raise ValueError("Unsupported plating source labware.")
        if (
            type(self.lb_tube_position) is not int
            or not 0 <= self.lb_tube_position < 15
        ):
            raise ValueError("lb_tube_position must index the 15-tube rack.")
        for tip in (self.initial_small_tip, self.initial_large_tip):
            if tip is not None:
                PLATE_96.index(tip)
        validate_slots(
            (
                self.small_tiprack_position,
                self.large_tiprack_position,
                self.dilution_plate_position1,
                self.dilution_plate_position2,
                self.agar_plate_position1,
                self.agar_plate_position2,
                self.tube_rack_position,
            )
        )


def plan_plating(
    request: PlatingRequest, *, config: PlatingConfig, inputs: tuple[Sample, ...]
) -> ProtocolPlan:
    """Build dilution intermediates and plated replicates with explicit lineage."""

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
        """Keep the current tip and use the agar offset only for spotting."""
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
        # Finish seeding the dilution series before removing volume for spots.
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
        # Retain the seeding tip for the first dilution's spots; subsequent
        # dilution groups each start with a fresh tip.
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


def allocate_plating(
    plan: ProtocolPlan, *, profile: OpentronsPlatingProfile, inputs: OutputManifest
) -> ProtocolPlan:
    """Place each dilution in a plate half or on its own plate when needed."""

    upstream = {p.id: p.location for p in inputs.samples}
    selected = [s for s in plan.samples if s.role == "bacteria"]
    if len({upstream[s.source_sample_id].container_id for s in selected}) != 1:
        raise ValueError("The plating target accepts one source plate.")
    containers = [
        ContainerSpec(
            id="reactions",
            definition_id=profile.thermocycler_labware,
            parent="reaction_module",
        ),
        ContainerSpec(
            id="tube_rack",
            definition_id="opentrons_15_tuberack_falcon_15ml_conical",
            parent=profile.tube_rack_position,
        ),
    ]
    counts = Counter((s.role, s.dilution) for s in plan.samples)
    indices = Counter()
    locations = {}
    for sample in plan.samples:
        if sample.role == "broth":
            location = WellRef(
                container_id="tube_rack",
                well_name=WellGrid(rows=3, columns=5).name(profile.lb_tube_position),
            )
            if sample.initial_volume_ul > 15000:
                raise ValueError("Broth loading exceeds tube capacity.")
        elif sample.role == "bacteria":
            well = upstream[sample.source_sample_id].well_name
            PLATE_96.index(well)
            location = WellRef(container_id="reactions", well_name=well)
        elif sample.role in ("dilution", "agar"):
            per_dilution = counts[sample.role, sample.dilution]
            if per_dilution > 96:
                raise ValueError("A dilution exceeds plate capacity.")
            # Two dilutions share opposite plate halves until either needs
            # more than half a plate; then each gets its own plate.
            two_plates = counts[sample.role, 2] and per_dilution > 48
            plate = sample.dilution if two_plates else 1
            index = indices[sample.role, sample.dilution]
            indices[sample.role, sample.dilution] += 1
            if sample.dilution == 2 and not two_plates:
                index += 48
            name = f"{sample.role}_{plate}"
            if name not in {c.id for c in containers}:
                containers.append(
                    ContainerSpec(
                        id=name,
                        definition_id="nest_96_wellplate_100ul_pcr_full_skirt",
                        parent=getattr(profile, f"{sample.role}_plate_position{plate}"),
                    )
                )
            location = WellRef(container_id=name, well_name=PLATE_96.name(index))
        else:
            raise ValueError(f"Unknown plating sample role {sample.role!r}.")
        locations[sample.id] = location
    return plan.with_locations(tuple(containers), locations)


def plating_layout(plan: ProtocolPlan, *, dilution_factor: float) -> dict:
    """Export agar wells by tracing each spot back to its source culture."""

    samples = {s.id: s for s in plan.samples}
    locations = {s.id: s.location for s in plan.samples}
    plates = {}
    outputs = [samples[sid] for sid in plan.output_sample_ids]
    # Group by dilution while preserving source and replicate order.
    for sample in sorted(outputs, key=lambda s: s.dilution):
        source = samples[sample.parent_ids[0]]
        while source.role == "dilution":
            source = samples[source.parent_ids[0]]
        location = locations[sample.id]
        plate = location.container_id.replace("agar_", "plate_")
        factor = dilution_factor**sample.dilution
        factor = int(factor) if float(factor).is_integer() else factor
        entry = plates.setdefault(plate, {}).setdefault(
            f"dilution_{sample.dilution}", {"ratio": f"1/{factor}", "wells": {}}
        )
        entry["wells"][location.well_name] = {
            "construct": ", ".join(source.contents),
            "source_well": locations[source.id].well_name,
            "replicate": sample.replicate,
        }
    return {"agar_plates": plates}
