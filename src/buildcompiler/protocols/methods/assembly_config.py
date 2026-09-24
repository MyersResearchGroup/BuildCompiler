"""Resolved, immutable method configuration. Defaults preserve PUDU assembly.

Assembly defaults and operation ordering originate in PUDU (MIT, Rudge Lab).
See buildcompiler.protocols.attribution. A method configuration intentionally contains no deck layout.
"""

import math
from dataclasses import dataclass

from buildcompiler.protocols.steps import TemperatureProgram, TemperatureStep
from buildcompiler.protocols.validation import ConfigOverrides


@dataclass(frozen=True, slots=True, kw_only=True)
class AssemblyConfig(ConfigOverrides):
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
        if type(self.replicates) is not int or self.replicates < 1:
            raise ValueError("replicates must be a positive integer.")
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
            value = getattr(self, name)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number.")
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
