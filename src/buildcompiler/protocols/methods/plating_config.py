"""Immutable dilution and plating configuration, preserving PUDU defaults."""

from dataclasses import dataclass

from buildcompiler.protocols.validation import (
    ConfigOverrides,
    positive,
    positive_integer,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class PlatingConfig(ConfigOverrides):
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
                "PUDU plating supports at most eight replicates and two dilutions."
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
        return self.volume_bacteria_transfer * (self.dilution_factor - 1)

    @property
    def dilution_volume(self) -> float:
        return self.volume_bacteria_transfer * self.dilution_factor

    @property
    def mix_volume(self) -> float:
        return min(19, self.dilution_volume - 1)
