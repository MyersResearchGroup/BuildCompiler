"""Typed, versioned protocol specifications shared by all output adapters."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("Protocol quantities cannot be negative.")
        if not self.unit:
            raise ValueError("Protocol quantities require an explicit unit.")


@dataclass(frozen=True)
class AssemblyProtocolSpec:
    product_identity: str
    backbone_identity: str
    part_identities: tuple[str, ...]
    restriction_enzyme: str
    ligase: str
    total_reaction: Quantity = field(default_factory=lambda: Quantity(20, "uL"))
    part_volume: Quantity = field(default_factory=lambda: Quantity(2, "uL"))
    restriction_enzyme_volume: Quantity = field(
        default_factory=lambda: Quantity(2, "uL")
    )
    ligase_volume: Quantity = field(default_factory=lambda: Quantity(4, "uL"))
    ligase_buffer_volume: Quantity = field(default_factory=lambda: Quantity(2, "uL"))
    replicates: int = 1
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransformationProtocolSpec:
    strain_identity: str
    chassis_identity: str
    plasmid_identities: tuple[str, ...]
    competent_cells: Quantity = field(default_factory=lambda: Quantity(20, "uL"))
    dna: Quantity = field(default_factory=lambda: Quantity(2, "uL"))
    recovery_medium: Quantity = field(default_factory=lambda: Quantity(60, "uL"))
    heat_shock_temperature: Quantity = field(
        default_factory=lambda: Quantity(42, "degC")
    )
    heat_shock_duration: Quantity = field(
        default_factory=lambda: Quantity(60, "second")
    )
    recovery_temperature: Quantity = field(default_factory=lambda: Quantity(37, "degC"))
    recovery_duration: Quantity = field(default_factory=lambda: Quantity(60, "minute"))
    replicates: int = 2
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlatingProtocolSpec:
    bacterium_locations: tuple[tuple[str, str], ...]
    transfer_volume: Quantity
    medium: str
    antibiotic: str
    incubation_temperature: Quantity
    incubation_duration: Quantity
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
