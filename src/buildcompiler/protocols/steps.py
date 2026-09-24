"""Serializable operations; no live robot or SBOL objects belong here."""

from dataclasses import dataclass
import math
from typing import Literal

from buildcompiler.protocols.materials import SamplePoint


@dataclass(frozen=True, slots=True, kw_only=True)
class Transfer:
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
    id: str
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class PickUpTip:
    id: str
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class Mix:
    id: str
    location: SamplePoint
    volume_ul: float
    repetitions: int
    instrument: str = "pipette"


@dataclass(frozen=True, slots=True, kw_only=True)
class Distribute:
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
    steps: tuple[TemperatureStep, ...]
    repetitions: int
    block_max_volume_ul: float


@dataclass(frozen=True, slots=True, kw_only=True)
class RunTemperatureProgram:
    id: str
    program: TemperatureProgram
    skip_during_simulation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SetTemperature:
    id: str
    module: Literal["source", "reaction", "lid"]
    celsius: float
    skip_during_simulation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class LidAction:
    id: str
    action: Literal["open", "close"]


@dataclass(frozen=True, slots=True, kw_only=True)
class DeactivateSourceModule:
    id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorAction:
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
