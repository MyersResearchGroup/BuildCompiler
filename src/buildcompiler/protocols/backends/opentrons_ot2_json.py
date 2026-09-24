"""Lower allocated plans to self-contained OT-2 JSON protocols.

Protocol schema 8 and command schema 10 are qualified with Opentrons 8.8.2.
The builder expands SDK conveniences into explicit commands; it never generates
or executes Python. Compilation needs shared-data, not the robot SDK.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
from typing import Literal

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
    WellRef,
)

# Explicit versions reproduce API 2.21 geometry instead of silently adopting
# the newest definitions in the installed labware library.
LABWARE_VERSIONS = {
    "opentrons_24_aluminumblock_nest_1.5ml_snapcap": 1,
    "nest_96_wellplate_100ul_pcr_full_skirt": 2,
    "biorad_96_wellplate_200ul_pcr": 2,
    "opentrons_24_tuberack_eppendorf_1.5ml_safelock_snapcap": 1,
    "opentrons_15_tuberack_falcon_15ml_conical": 1,
    "opentrons_96_tiprack_20ul": 1,
    "opentrons_96_filtertiprack_20ul": 1,
    "opentrons_96_filtertiprack_200ul": 1,
}


@lru_cache(maxsize=1)
def _validators() -> dict:
    """Load the pinned offline schemas only when the JSON backend is selected."""
    try:
        from jsonschema import Draft7Validator
        from opentrons_shared_data import load_shared_data
    except ImportError as exc:
        raise ImportError(
            "Install synbio-buildcompiler[automation] to compile JSON protocols."
        ) from exc
    if version("opentrons-shared-data") != "8.8.2":
        raise RuntimeError("JSON compilation requires opentrons-shared-data==8.8.2.")
    schemas = {
        name: json.loads(load_shared_data(path))
        for name, path in {
            "protocol": "protocol/schemas/8.json",
            "command": "command/schemas/10.json",
            "labware": "labware/schemas/2.json",
            "liquid": "liquid/schemas/1.json",
        }.items()
    }
    result = {name: Draft7Validator(schema) for name, schema in schemas.items()}
    # Select the command's branch directly: validating every oneOf branch for
    # each pipetting movement is both slow and produces unhelpful errors.
    command_schema = schemas["command"]
    # Vendor schemas allow extra keys in command parameters. Tighten our authoring
    # boundary so a misspelled optional field cannot silently change behavior.
    for definition in command_schema["definitions"].values():
        if definition.get("type") == "object" and "properties" in definition:
            definition.setdefault("additionalProperties", False)
    for reference in command_schema["oneOf"]:
        definition = command_schema["definitions"][reference["$ref"].split("/")[-1]]
        command_type = definition["properties"]["commandType"]["enum"][0]
        result[command_type] = Draft7Validator({**command_schema, "oneOf": [reference]})
    return result


@dataclass(slots=True)
class _Pipette:
    """Mutable state confined to one compilation, including its tip schedule."""

    capacity: float
    flow_rate: float
    racks: tuple[str, ...]
    slots: tuple[str, ...]
    next_tip: int
    attached: bool = False
    volume: float = 0
    active_batch: int = 0


@dataclass(frozen=True, slots=True)
class _Point:
    """A physical well with a vertical offset, resolved before command emission."""

    well: WellRef
    origin: Literal["bottom", "top"] = "bottom"
    z: float = 1

    def params(self) -> dict:
        """Return the location fields shared by liquid-handling commands."""
        return {
            "labwareId": self.well.container_id,
            "wellName": self.well.well_name,
            "wellLocation": {
                "origin": self.origin,
                "offset": {"x": 0, "y": 0, "z": self.z},
            },
        }


class OpentronsProtocolBuilder:
    """Build and validate commands for the supported OT-2 hardware profiles."""

    def __init__(self, plan: ProtocolPlan, profile: TargetProfile) -> None:
        self.plan = plan
        self.profile = profile
        self.samples = {sample.id: sample for sample in plan.samples}
        self.commands: list[dict] = []
        self.definitions: dict[str, dict] = {}
        self.labware: dict[str, dict] = {}
        self.liquids: dict[str, dict] = {}
        self.sample_liquids: dict[str, str] = {}
        self.volumes: dict[WellRef, float] = {}
        self.pipettes: dict[str, _Pipette] = {}
        self.validators = _validators()

    def _emit(self, command_type: str, **params) -> None:
        """Validate each command at the boundary to the vendor wire format."""
        command = {
            "commandType": command_type,
            "key": f"command-{len(self.commands):05d}",
            "params": params,
        }
        self.validators[command_type].validate(command)
        self.commands.append(command)

    def _load_labware(self, name: str, load_name: str, parent: str) -> None:
        """Embed the qualified definition and bind its stable resource identifier."""
        from opentrons_shared_data.labware import load_definition

        if name in self.labware:
            raise ValueError(f"Duplicate labware identifier: {name}")
        if load_name not in LABWARE_VERSIONS:
            raise ValueError(f"Unqualified OT-2 labware definition: {load_name}")
        definition = load_definition(load_name, LABWARE_VERSIONS[load_name])
        self.validators["labware"].validate(definition)
        self.definitions[f"opentrons/{load_name}/{definition['version']}"] = definition
        self.labware[name] = definition
        location = (
            {"moduleId": parent}
            if parent in ("source_module", "reaction_module")
            else "offDeck"
            if parent == "offDeck"
            else {"slotName": parent}
        )
        self._emit(
            "loadLabware",
            labwareId=name,
            loadName=load_name,
            namespace="opentrons",
            version=definition["version"],
            location=location,
        )

    def _well(self, sample: Sample) -> WellRef:
        """Reject unallocated samples and references absent from loaded labware."""
        well = sample.location
        if well is None:
            raise ValueError(f"Sample {sample.id} has not been allocated.")
        if well.well_name not in self.labware[well.container_id]["wells"]:
            raise ValueError(f"Unknown well: {well}")
        return well

    def _point(self, point: SamplePoint) -> _Point:
        """Resolve conical source height once per operation, before its refills."""
        well = self._well(self.samples[point.sample_id])
        if point.top_mm is not None:
            return _Point(well, "top", point.top_mm)
        if point.bottom_mm is not None:
            return _Point(well, "bottom", point.bottom_mm)
        if point.track_conical_height:
            definition = self.labware[well.container_id]["wells"][well.well_name]
            volume = self.volumes.get(well)
            maximum = definition["totalLiquidVolume"]
            if volume is not None and volume >= maximum * 0.2:
                height = max(volume / maximum * (definition["depth"] - 10) - 10, 3)
                return _Point(well, "bottom", height)
        return _Point(well)

    def _liquid(
        self,
        sample: Sample,
        liquid_id: str,
        *,
        name: str,
        color: str,
        description: str = "",
    ) -> None:
        """Define display metadata once and register the initial well volume."""
        if liquid_id not in self.liquids:
            liquid = {
                "displayName": name,
                "description": description,
                "displayColor": color,
            }
            self.validators["liquid"].validate(liquid)
            self.liquids[liquid_id] = liquid
        self.sample_liquids[sample.id] = liquid_id
        self._load_liquid(self._well(sample), liquid_id, sample.initial_volume_ul)

    def _load_liquid(self, well: WellRef, liquid: str, volume: float) -> None:
        """Record a liquid annotation and its tracked starting volume."""
        self._emit(
            "loadLiquid",
            labwareId=well.container_id,
            liquidId=liquid,
            volumeByWell={well.well_name: volume},
        )
        self.volumes[well] = volume

    def _load_pipette(
        self,
        name: str,
        model: str,
        mount: str,
        racks: tuple[str, ...],
        slots: tuple[str, ...],
        initial_tip: str | None,
    ) -> None:
        """Pin tip overlap and flow rates to the Python API 2.21 behavior."""
        self._emit(
            "loadPipette",
            pipetteId=name,
            pipetteName=model,
            mount=mount,
            tipOverlapNotAfterVersion="v3",
            liquidPresenceDetection=False,
        )
        small = model == "p20_single_gen2"
        self.pipettes[name] = _Pipette(
            capacity=20 if small else 200,
            flow_rate=7.56 if small else 92.86,
            racks=racks,
            slots=slots,
            next_tip=PLATE_96.index(initial_tip or "A1"),
        )

    def _setup(self) -> None:
        """Load the deck and liquids in the same order as the Python backend."""
        profile = self.profile
        containers = {c.id: c for c in self.plan.containers}

        def load(name: str) -> None:
            """Resolve one allocated container's hardware declaration."""
            container = containers[name]
            self._load_labware(name, container.definition_id, container.parent)

        if isinstance(
            profile, (OpentronsAssemblyProfile, OpentronsTransformationProfile)
        ):
            self._emit(
                "loadModule",
                moduleId="source_module",
                model="temperatureModuleV1",
                location={"slotName": profile.temperature_module_position},
            )
            load("sources")
        self._emit(
            "loadModule",
            moduleId="reaction_module",
            model="thermocyclerModuleV1",
            location={"slotName": "7"},
        )
        load("reactions")
        if isinstance(profile, OpentronsAssemblyProfile):
            count = sum(isinstance(s, Transfer) and s.new_tip for s in self.plan.steps)
            rack_count = (PLATE_96.index(profile.initial_tip) + count + 95) // 96
            slots = profile.tiprack_positions
            racks = tuple(f"tips_{i}" for i in range(rack_count))
            for i, rack in enumerate(racks):
                self._load_labware(
                    rack,
                    "opentrons_96_tiprack_20ul",
                    slots[i] if i < len(slots) else "offDeck",
                )
            self._load_pipette(
                "pipette",
                "p20_single_gen2",
                profile.pipette_position,
                racks,
                slots,
                profile.initial_tip,
            )
        else:
            if isinstance(profile, OpentronsTransformationProfile):
                if "dna_plate" in containers:
                    load("dna_plate")
                load("tube_rack")
                starts = {
                    "small": profile.initial_tip_p20,
                    "large": profile.initial_tip_p300,
                }
                slots = (profile.tiprack_p20_position, profile.tiprack_p200_position)
                small_rack = "opentrons_96_tiprack_20ul"
            elif isinstance(profile, OpentronsPlatingProfile):
                starts = {
                    "small": profile.initial_small_tip,
                    "large": profile.initial_large_tip,
                }
                slots = (profile.small_tiprack_position, profile.large_tiprack_position)
                small_rack = "opentrons_96_filtertiprack_20ul"
            else:
                raise TypeError(f"Unsupported profile: {type(profile).__name__}")
            validate_tips(self.plan, starts)
            self._load_labware("small_tips", small_rack, slots[0])
            self._load_labware(
                "large_tips", "opentrons_96_filtertiprack_200ul", slots[1]
            )
            for name, model, mount, slot in (
                ("small", "p20_single_gen2", "left", slots[0]),
                ("large", "p300_single_gen2", "right", slots[1]),
            ):
                self._load_pipette(
                    name, model, mount, (f"{name}_tips",), (slot,), starts[name]
                )
            if isinstance(profile, OpentronsPlatingProfile):
                load("tube_rack")

        dna_liquids = {}
        bacteria_index = 0
        for index, sample_id in enumerate(self.plan.input_sample_ids):
            sample = self.samples[sample_id]
            liquid_id = f"liquid_{index}"
            if isinstance(profile, OpentronsAssemblyProfile):
                label = sample.liquid_label or sample.material.label
                self._liquid(
                    sample,
                    liquid_id,
                    name=label,
                    description=label,
                    color=COLORS[index % len(COLORS)],
                )
            elif isinstance(profile, OpentronsTransformationProfile):
                if sample.role == "dna":
                    liquid_id, color_index = dna_liquids.setdefault(
                        sample.material.identity, (liquid_id, len(dna_liquids))
                    )
                    self._liquid(
                        sample,
                        liquid_id,
                        name=sample.material.label,
                        description=f"{sample.material.label} DNA construct",
                        color=COLORS[color_index % len(COLORS)],
                    )
                else:
                    self._liquid(
                        sample,
                        liquid_id,
                        name=sample.liquid_label,
                        color=COLORS[(sample.replicate - 1) % len(COLORS)],
                    )
            elif sample.role == "broth":
                self._liquid(
                    sample,
                    liquid_id,
                    name="liquid_broth",
                    description="Liquid broth for dilutions",
                    color="#D2B48C",
                )
            else:
                self._liquid(
                    sample,
                    liquid_id,
                    name="transformed_bacteria",
                    description=sample.liquid_label,
                    color=COLORS[bacteria_index % len(COLORS)],
                )
                bacteria_index += 1
        if isinstance(profile, OpentronsPlatingProfile):
            for name in sorted(
                (n for n in containers if n.startswith(("dilution_", "agar_"))),
                key=lambda n: (not n.startswith("dilution_"), n),
            ):
                load(name)
        for sample in self.plan.samples:
            self._well(sample)

    def _require_tip(self, instrument: str) -> _Pipette:
        """Check that the instrument exists and owns an attached tip."""
        pipette = self.pipettes[instrument]
        if not pipette.attached:
            raise ValueError(f"An attached tip is required on {instrument}.")
        return pipette

    def _pickup(self, instrument: str) -> None:
        """Consume the next tip, pausing for manual rack swaps when needed."""
        pipette = self.pipettes[instrument]
        if pipette.attached:
            raise ValueError(f"A tip is already attached to {instrument}.")
        rack, well = divmod(pipette.next_tip, 96)
        if rack >= len(pipette.racks):
            raise ValueError(f"No tips remain for {instrument}.")
        batch = rack // len(pipette.slots)
        if batch != pipette.active_batch:
            size = len(pipette.slots)
            for old in pipette.racks[
                pipette.active_batch * size : (pipette.active_batch + 1) * size
            ]:
                self._emit(
                    "moveLabware",
                    labwareId=old,
                    newLocation="offDeck",
                    strategy="manualMoveWithPause",
                )
            for index in range(
                batch * size, min((batch + 1) * size, len(pipette.racks))
            ):
                self._emit(
                    "moveLabware",
                    labwareId=pipette.racks[index],
                    newLocation={"slotName": pipette.slots[index % size]},
                    strategy="manualMoveWithPause",
                )
            pipette.active_batch = batch
        self._emit(
            "pickUpTip",
            pipetteId=instrument,
            **_Point(
                WellRef(
                    container_id=pipette.racks[rack], well_name=PLATE_96.name(well)
                ),
                "top",
                0,
            ).params(),
        )
        pipette.next_tip += 1
        pipette.attached = True

    def _drop(self, instrument: str) -> None:
        """Preserve the SDK's alternating fixed-trash drop positions."""
        pipette = self._require_tip(instrument)
        self._emit(
            "moveToAddressableAreaForDropTip",
            pipetteId=instrument,
            addressableAreaName="fixedTrash",
            alternateDropLocation=True,
        )
        self._emit("dropTipInPlace", pipetteId=instrument)
        pipette.attached = False
        pipette.volume = 0

    def _pipette(
        self,
        action: Literal["aspirate", "dispense"],
        instrument: str,
        point: _Point,
        volume: float,
        *,
        rate: float = 1,
        push_out: float | None = None,
        air: bool = False,
    ) -> None:
        """Check tip capacity and update volume accounting for one movement."""
        pipette = self._require_tip(instrument)
        after = pipette.volume + (volume if action == "aspirate" else -volume)
        if (
            not math.isfinite(volume)
            or volume < 0
            or not -1e-8 <= after <= pipette.capacity + 1e-8
        ):
            raise ValueError(
                f"Operation exceeds supported {instrument} pipette capacity."
            )
        params = {
            "pipetteId": instrument,
            **point.params(),
            "volume": volume,
            "flowRate": pipette.flow_rate * rate,
        }
        if push_out is not None:
            params["pushOut"] = push_out
        self._emit(action, **params)
        pipette.volume = max(0, after)
        if not air and point.well in self.volumes:
            self.volumes[point.well] += -volume if action == "aspirate" else volume

    def _mix(
        self, instrument: str, point: _Point, volume: float, repetitions: int
    ) -> None:
        """Suppress push-out until the final dispense, as API 2.21 mix does."""
        for repetition in range(repetitions):
            self._pipette("aspirate", instrument, point, volume)
            self._pipette(
                "dispense",
                instrument,
                point,
                volume,
                push_out=0 if repetition < repetitions - 1 else None,
            )

    def _blow_out(self, instrument: str, point: _Point | None = None) -> None:
        """Empty a tip at its current well position or at fixed trash."""
        pipette = self._require_tip(instrument)
        if point is None:
            self._emit(
                "moveToAddressableAreaForDropTip",
                pipetteId=instrument,
                addressableAreaName="fixedTrash",
                offset={"x": 0, "y": 0, "z": 0},
            )
            self._emit(
                "blowOutInPlace", pipetteId=instrument, flowRate=pipette.flow_rate
            )
        else:
            self._emit(
                "blowout",
                pipetteId=instrument,
                **point.params(),
                flowRate=pipette.flow_rate,
            )
            if point.well in self.volumes:
                self.volumes[point.well] += pipette.volume
        pipette.volume = 0

    def _air_gap(self, instrument: str, well: WellRef, volume: float) -> None:
        """API 2.21 acquires air five millimetres above the last visited well."""
        point = _Point(well, "top", 5)
        self._emit("moveToWell", pipetteId=instrument, **point.params())
        self._pipette("aspirate", instrument, point, volume, air=True)

    def _distribute(self, step: Distribute) -> None:
        """Expand uniform destinations into refills, retaining one tip per group."""
        pipette = self.pipettes[step.instrument]
        air = step.air_gap_ul or 0
        usable = pipette.capacity - step.disposal_volume_ul - air
        if step.volume_ul <= 0 or step.volume_ul > usable or not step.destinations:
            raise ValueError(
                "Distribution exceeds pipette capacity or has no destinations."
            )
        if step.new_tip == "once":
            self._pickup(step.instrument)
        elif step.new_tip != "never":
            raise ValueError(f"Unsupported distribution tip policy: {step.new_tip}")
        self._require_tip(step.instrument)
        source = self._point(step.source)
        destinations = [self._point(p) for p in step.destinations]
        # Accumulate in destination order. Floor division can choose a different
        # refill boundary for fractional volumes near the pipette's capacity.
        groups: list[tuple[list[_Point], float]] = []
        group: list[_Point] = []
        total = 0.0
        for destination in destinations:
            if (
                total + step.disposal_volume_ul + air + step.volume_ul
                > pipette.capacity
            ):
                groups.append((group, total))
                group, total = [], 0.0
            group.append(destination)
            total += step.volume_ul
        groups.append((group, total))
        for group, total in groups:
            if step.mix_before and pipette.volume == 0:
                repetitions, volume = step.mix_before
                self._mix(step.instrument, source, volume, repetitions)
            self._pipette(
                "aspirate",
                step.instrument,
                source,
                total + step.disposal_volume_ul,
            )
            if air:
                self._air_gap(step.instrument, source.well, air)
            for index, destination in enumerate(group):
                self._pipette(
                    "dispense", step.instrument, destination, step.volume_ul + air
                )
                if air and index < len(group) - 1:
                    self._air_gap(step.instrument, destination.well, air)
            if step.disposal_volume_ul:
                self._blow_out(step.instrument)
        if step.new_tip == "once":
            self._drop(step.instrument)
        if step.track_liquid_sample_id:
            for destination in destinations:
                self._load_liquid(
                    destination.well,
                    self.sample_liquids[step.track_liquid_sample_id],
                    step.volume_ul,
                )

    def _operations(self) -> None:
        """Lower all planned operations, including the full thermal program."""
        for step in self.plan.steps:
            if isinstance(step, Transfer):
                if step.new_tip:
                    self._pickup(step.instrument)
                source, destination = (
                    self._point(step.source),
                    self._point(step.destination),
                )
                volume = (
                    min(step.volume_ul, self.pipettes[step.instrument].capacity)
                    if step.limit_to_pipette_capacity
                    else step.volume_ul
                )
                if step.mix_before_ul:
                    self._mix(
                        step.instrument,
                        source,
                        step.mix_before_ul,
                        step.mix_repetitions,
                    )
                self._pipette(
                    "aspirate",
                    step.instrument,
                    source,
                    volume,
                    rate=step.aspiration_rate,
                )
                self._pipette(
                    "dispense",
                    step.instrument,
                    destination,
                    volume,
                    rate=step.dispense_rate,
                )
                if step.blow_out:
                    self._blow_out(step.instrument, destination)
                if step.touch_tip:
                    self._emit(
                        "touchTip",
                        pipetteId=step.instrument,
                        **_Point(destination.well, "top", -14).params(),
                        radius=0.5,
                        speed=20,
                    )
                if step.drop_tip:
                    self._drop(step.instrument)
            elif isinstance(step, PickUpTip):
                self._pickup(step.instrument)
            elif isinstance(step, DropTip):
                self._drop(step.instrument)
            elif isinstance(step, Mix):
                self._mix(
                    step.instrument,
                    self._point(step.location),
                    step.volume_ul,
                    step.repetitions,
                )
            elif isinstance(step, Distribute):
                self._distribute(step)
            elif isinstance(step, LidAction):
                self._emit(f"thermocycler/{step.action}Lid", moduleId="reaction_module")
            elif isinstance(step, SetTemperature):
                commands = {
                    "source": ("temperatureModule", "Temperature", "source_module"),
                    "reaction": ("thermocycler", "BlockTemperature", "reaction_module"),
                    "lid": ("thermocycler", "LidTemperature", "reaction_module"),
                }
                module, target, resource = commands[step.module]
                params = {"moduleId": resource, "celsius": step.celsius}
                if step.module == "reaction":
                    params["holdTimeSeconds"] = 0
                self._emit(f"{module}/setTarget{target}", **params)
                self._emit(f"{module}/waitFor{target}", moduleId=resource)
            elif isinstance(step, DeactivateSourceModule):
                self._emit("temperatureModule/deactivate", moduleId="source_module")
            elif isinstance(step, RunTemperatureProgram):
                program = step.program
                self._emit(
                    "thermocycler/runExtendedProfile",
                    moduleId="reaction_module",
                    profileElements=[
                        {
                            "steps": [
                                {"celsius": s.celsius, "holdSeconds": s.minutes * 60}
                                for s in program.steps
                            ],
                            "repetitions": program.repetitions,
                        }
                    ],
                    blockMaxVolumeUl=program.block_max_volume_ul,
                )
            elif isinstance(step, OperatorAction):
                self._emit("comment", message=step.instruction)
            else:
                raise TypeError(
                    f"Unsupported protocol operation: {type(step).__name__}"
                )
        if any(p.attached for p in self.pipettes.values()):
            raise ValueError("Protocol ends with an attached tip.")

    def build(self) -> dict:
        """Return a validated document; builders are single-use compilation objects."""
        if self.commands:
            raise RuntimeError("This protocol builder has already been used.")
        self._setup()
        self._operations()
        document = {
            "$otSharedSchema": "#/protocol/schemas/8",
            "schemaVersion": 8,
            "metadata": {"protocolName": self.plan.id, "author": "BuildCompiler"},
            "robot": {"model": "OT-2 Standard", "deckId": "ot2_standard"},
            "labwareDefinitionSchemaId": "opentronsLabwareSchemaV2",
            "labwareDefinitions": self.definitions,
            "liquidSchemaId": "opentronsLiquidSchemaV1",
            "liquids": self.liquids,
            "commandSchemaId": "opentronsCommandSchemaV10",
            "commands": self.commands,
            "commandAnnotationSchemaId": "opentronsCommandAnnotationSchemaV1",
            "commandAnnotations": [],
        }
        self.validators["protocol"].validate(document)
        return document


def render_json(plan: ProtocolPlan, *, profile: TargetProfile) -> str:
    """Serialize a deterministic, standalone protocol without running a simulator."""
    document = OpentronsProtocolBuilder(plan, profile).build()
    return json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n"
