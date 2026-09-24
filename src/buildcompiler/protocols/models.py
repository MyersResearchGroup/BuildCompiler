"""Shared protocol data: samples, operations, placement and output handoffs.

Planning leaves Sample.location unset. Allocation fills it on a new immutable
plan; both renderers then read that same plan.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from typing import Literal

from buildcompiler.domain.protocol_requests import MaterialRef


def positive(value: object, name: str) -> None:
    """Validate finite positive volumes and rate parameters."""

    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number.")


def positive_integer(value: object, name: str) -> None:
    """Validate counts without accepting booleans as integers."""

    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer.")


class ConfigOverrides:
    """Replace only explicitly supplied fields, including False and defaults."""

    __slots__ = ()

    def with_overrides(self, overrides: Mapping[str, object]):
        """Return a validated copy, rejecting misspelled or unsupported options."""
        unknown = set(overrides) - {field.name for field in fields(self)}
        if unknown:
            raise ValueError(f"Unknown configuration fields: {sorted(unknown)}")
        return replace(self, **overrides)


@dataclass(frozen=True, slots=True, kw_only=True)
class WellGrid:
    """Column-major well names and indices for a rectangular plate or rack."""

    rows: int
    columns: int

    def __post_init__(self) -> None:
        if type(self.rows) is not int or not 1 <= self.rows <= 26:
            raise ValueError("rows must be an integer between 1 and 26.")
        if type(self.columns) is not int or self.columns < 1:
            raise ValueError("columns must be a positive integer.")

    @property
    def capacity(self) -> int:
        """Number of wells in the grid."""

        return self.rows * self.columns

    def name(self, index: int) -> str:
        """Return the well name at a zero-based column-major index."""

        if type(index) is not int or not 0 <= index < self.capacity:
            raise ValueError(f"Well index {index} is outside this grid.")
        return f"{chr(ord('A') + index % self.rows)}{index // self.rows + 1}"

    def index(self, name: str) -> int:
        """Return the column-major index of a validated well name."""

        match = re.fullmatch(r"([A-Z])([1-9][0-9]*)", name)
        if not match:
            raise ValueError(f"Invalid well name: {name!r}")
        row = ord(match[1]) - ord("A")
        column = int(match[2]) - 1
        if row >= self.rows or column >= self.columns:
            raise ValueError(f"Well {name} is outside this grid.")
        return column * self.rows + row


PLATE_96 = WellGrid(rows=8, columns=12)
BLOCK_24 = WellGrid(rows=4, columns=6)


@dataclass(frozen=True, slots=True, kw_only=True)
class WellRef:
    """A physical well qualified by its container within this protocol."""

    container_id: str
    well_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContainerSpec:
    """Labware definition and its parent module or deck slot."""

    id: str
    definition_id: str
    parent: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Sample:
    """One physical aliquot, with material identity, lineage and optional location."""

    id: str
    material: MaterialRef
    parent_ids: tuple[str, ...] = ()
    replicate: int | None = None
    initial_volume_ul: float | None = None
    liquid_label: str | None = None
    role: str = "material"
    source_sample_id: str | None = None
    contents: tuple[str, ...] = ()
    dilution: int | None = None
    location: WellRef | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SamplePoint:
    """A sample reference with an optional vertical liquid-handling offset."""

    sample_id: str
    bottom_mm: float | None = None
    top_mm: float | None = None
    track_conical_height: bool = False

    def __post_init__(self) -> None:
        if (
            sum(
                (
                    self.bottom_mm is not None,
                    self.top_mm is not None,
                    self.track_conical_height,
                )
            )
            > 1
        ):
            raise ValueError("A sample point requires one location policy.")


@dataclass(frozen=True, slots=True, kw_only=True)
class Transfer:
    """One liquid transfer, including mixing and tip reuse decisions."""

    id: str
    source: SamplePoint
    destination: SamplePoint
    volume_ul: float
    aspiration_rate: float = 0.5
    dispense_rate: float = 1.0
    mix_before_ul: float = 0.0
    mix_repetitions: int = 3
    new_tip: bool = True
    drop_tip: bool = True
    blow_out: bool = True
    touch_tip: bool = True
    limit_to_pipette_capacity: bool = False
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class DropTip:
    """Discard the tip currently attached to the named instrument."""

    id: str
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class PickUpTip:
    """Attach a fresh tip to the named instrument."""

    id: str
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class Mix:
    """Mix an existing sample without changing its volume or tip."""

    id: str
    location: SamplePoint
    volume_ul: float
    repetitions: int
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class Distribute:
    """Fill a destination group from one source using an explicit tip policy."""

    id: str
    source: SamplePoint
    destinations: tuple[SamplePoint, ...]
    volume_ul: float
    instrument: str = "large"
    disposal_volume_ul: float = 0
    new_tip: Literal["once", "never"] = "once"
    mix_before: tuple[int, float] | None = None
    air_gap_ul: float | None = None
    track_liquid_sample_id: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class TemperatureStep:
    """One temperature hold within an incubation program."""

    celsius: float
    minutes: float

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.celsius)
            or not math.isfinite(self.minutes)
            or self.minutes < 0
        ):
            raise ValueError(
                "Temperature steps require finite temperatures and nonnegative durations."
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class TemperatureProgram:
    """Temperature holds, repetition count and thermocycler volume setting."""

    steps: tuple[TemperatureStep, ...]
    repetitions: int
    block_max_volume_ul: float


@dataclass(frozen=True, slots=True, kw_only=True)
class RunTemperatureProgram:
    """Run an incubation program, optionally skipping it during simulation."""

    id: str
    program: TemperatureProgram
    skip_during_simulation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SetTemperature:
    """Set a module or lid temperature without a timed hold."""

    id: str
    module: Literal["source", "reaction", "lid"]
    celsius: float
    skip_during_simulation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class LidAction:
    """Open or close the thermocycler lid."""

    id: str
    action: Literal["open", "close"]


@dataclass(frozen=True, slots=True, kw_only=True)
class DeactivateSourceModule:
    """Turn off source-module temperature control."""

    id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorAction:
    """An instruction displayed to the operator during the protocol."""

    id: str
    instruction: str


Step = (
    Transfer
    | PickUpTip
    | Mix
    | Distribute
    | DropTip
    | RunTemperatureProgram
    | SetTemperature
    | LidAction
    | DeactivateSourceModule
    | OperatorAction
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolPlan:
    """Ordered operations and samples, before or after well allocation."""

    id: str
    request_id: str
    samples: tuple[Sample, ...]
    input_sample_ids: tuple[str, ...]
    output_sample_ids: tuple[str, ...]
    steps: tuple[Step, ...]
    containers: tuple[ContainerSpec, ...] = ()

    def __post_init__(self) -> None:
        sample_ids = {sample.id for sample in self.samples}
        if len(sample_ids) != len(self.samples):
            raise ValueError("Sample ids must be unique within a plan.")
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Step ids must be unique within a plan.")
        if not set(self.input_sample_ids + self.output_sample_ids) <= sample_ids:
            raise ValueError("Plan inputs and outputs must reference declared samples.")
        for sample in self.samples:
            if not set(sample.parent_ids) <= sample_ids:
                raise ValueError(f"Unknown parent for sample {sample.id}.")
        for step in self.steps:
            referenced = set()
            if isinstance(step, Transfer):
                referenced = {step.source.sample_id, step.destination.sample_id}
            elif isinstance(step, Distribute):
                referenced = {
                    step.source.sample_id,
                    *(d.sample_id for d in step.destinations),
                }
                if step.track_liquid_sample_id:
                    referenced.add(step.track_liquid_sample_id)
            elif isinstance(step, Mix):
                referenced = {step.location.sample_id}
            if referenced - sample_ids:
                raise ValueError(f"Unknown sample in operation {step.id}.")

    def with_locations(
        self, containers: tuple[ContainerSpec, ...], locations: Mapping[str, WellRef]
    ) -> ProtocolPlan:
        """Bind every sample exactly once and return a plan ready to render."""
        if set(locations) != {s.id for s in self.samples}:
            raise ValueError("Every sample must have exactly one placement.")
        if len(set(locations.values())) != len(locations):
            raise ValueError("Two samples cannot occupy the same location.")
        container_ids = {c.id for c in containers}
        if len(container_ids) != len(containers):
            raise ValueError("Container ids must be unique.")
        if any(
            location.container_id not in container_ids
            for location in locations.values()
        ):
            raise ValueError("Placements must reference declared containers.")
        return replace(
            self,
            containers=containers,
            samples=tuple(replace(s, location=locations[s.id]) for s in self.samples),
        )

    def output_manifest(self) -> OutputManifest:
        """Return the located outputs for use as inputs to the next protocol."""
        samples = {s.id: s for s in self.samples}
        return OutputManifest(
            protocol_id=self.id,
            samples=tuple(samples[sid] for sid in self.output_sample_ids),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputManifest:
    """Planned output samples, retaining identities, lineage and physical wells."""

    protocol_id: str
    samples: tuple[Sample, ...]

    def __post_init__(self) -> None:
        if len({s.id for s in self.samples}) != len(self.samples):
            raise ValueError("Manifest sample ids must be unique.")
        if any(s.location is None for s in self.samples):
            raise ValueError("Manifest samples need a physical location.")
        if len({s.location for s in self.samples}) != len(self.samples):
            raise ValueError("Manifest sample locations must be unique.")

    def to_dict(self) -> dict:
        """Serialize the manifest without implying that the protocol has run."""
        return {
            "schema_version": "1.0",
            "protocol_id": self.protocol_id,
            "state": "planned",
            "outputs": [
                {
                    "sample_id": s.id,
                    "material_identity": s.material.identity,
                    "label": s.material.label,
                    "parent_sample_ids": list(s.parent_ids),
                    "replicate": s.replicate,
                    "source_sample_id": s.source_sample_id,
                    "contents": list(s.contents),
                    "dilution": s.dilution,
                    "container_id": s.location.container_id,
                    "well_name": s.location.well_name,
                }
                for s in self.samples
            ],
        }

    def _require_single_container(self) -> None:
        """Well-name-only exports cannot distinguish different source plates."""
        if len({s.location.container_id for s in self.samples}) > 1:
            raise ValueError(
                "This location format cannot represent multiple containers."
            )

    def plasmid_locations(self) -> dict[str, list[str]]:
        """Group source wells by plasmid identity, preserving replicate order."""
        self._require_single_container()
        result = {}
        for sample in self.samples:
            result.setdefault(sample.material.identity, []).append(
                sample.location.well_name
            )
        return result

    def bacterium_locations(self) -> dict[str, list[str]]:
        """Export the contents of each culture well for downstream plating."""
        self._require_single_container()
        return {
            s.location.well_name: list(s.contents or (s.material.label,))
            for s in self.samples
        }


def validate_slots(slots: tuple[str, ...]) -> None:
    """Reject slot overlap with another resource, the thermocycler or trash."""
    if len(set(slots)) != len(slots) or not set(slots) <= {
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "9",
    }:
        raise ValueError("Deck slots collide or overlap the thermocycler/trash.")
