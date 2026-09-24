"""PUDU heat-shock method parameters; no labware or deck configuration."""

from dataclasses import dataclass

from buildcompiler.protocols.steps import TemperatureStep
from buildcompiler.protocols.validation import (
    ConfigOverrides,
    positive,
    positive_integer,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationConfig(ConfigOverrides):
    volume_dna: float = 20
    transfer_volume_dna: float = 2
    transfer_volume_competent_cell: float = 20
    tube_volume_competent_cell: float = 100
    transfer_volume_recovery_media: float = 60
    tube_volume_recovery_media: float = 1200
    replicates: int = 2
    aspiration_rate: float = 0.5
    dispense_rate: float = 1
    water_testing: bool = False
    cold_incubation1: TemperatureStep = TemperatureStep(celsius=4, minutes=30)
    heat_shock: TemperatureStep = TemperatureStep(celsius=42, minutes=1)
    cold_incubation2: TemperatureStep = TemperatureStep(celsius=4, minutes=2)
    recovery_incubation: TemperatureStep = TemperatureStep(celsius=37, minutes=60)

    def __post_init__(self) -> None:
        positive_integer(self.replicates, "replicates")
        for name in (
            "volume_dna",
            "transfer_volume_dna",
            "transfer_volume_competent_cell",
            "tube_volume_competent_cell",
            "transfer_volume_recovery_media",
            "tube_volume_recovery_media",
            "aspiration_rate",
            "dispense_rate",
        ):
            positive(getattr(self, name), name)
        if type(self.water_testing) is not bool:
            raise ValueError("water_testing must be a boolean.")
        if self.tube_volume_competent_cell < self.transfer_volume_competent_cell:
            raise ValueError("A cell tube must supply at least one transfer.")
        if self.tube_volume_recovery_media < self.transfer_volume_recovery_media:
            raise ValueError("A media tube must supply at least one transfer.")
        for step in (
            self.cold_incubation1,
            self.heat_shock,
            self.cold_incubation2,
            self.recovery_incubation,
        ):
            if not isinstance(step, TemperatureStep):
                raise TypeError("Incubations must be TemperatureStep records.")
