"""The initial, explicitly supported PUDU assembly hardware profile."""

from dataclasses import dataclass

from buildcompiler.protocols.allocation.wells import PLATE_96


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsAssemblyProfile:
    api_level: str = "2.21"
    temperature_module_position: str = "1"
    thermocycler_starting_well: int = 0
    tiprack_positions: tuple[str, ...] = ("2", "3", "4", "5", "6", "9")
    pipette_position: str = "left"
    initial_tip: str = "A1"

    def __post_init__(self) -> None:
        if self.api_level != "2.21":
            raise ValueError("This backend currently supports API 2.21.")
        if self.pipette_position not in ("left", "right"):
            raise ValueError("Invalid pipette mount.")
        PLATE_96.name(self.thermocycler_starting_well)
        PLATE_96.index(self.initial_tip)
        if not isinstance(self.tiprack_positions, tuple) or not self.tiprack_positions:
            raise ValueError("tiprack_positions must be a nonempty tuple.")
        slots = (self.temperature_module_position, *self.tiprack_positions)
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

    @property
    def max_volume_ul(self) -> float:
        return 20


def validate_slots(slots: tuple[str, ...]) -> None:
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


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsTransformationProfile:
    api_level: str = "2.21"
    temperature_module_position: str = "1"
    dna_plate_position: str = "2"
    tube_rack_position: str = "3"
    tiprack_p20_position: str = "9"
    tiprack_p200_position: str = "6"
    thermocycler_starting_well: int = 0
    initial_dna_well: int = 0
    initial_tip_p20: str | None = None
    initial_tip_p300: str | None = None

    def __post_init__(self) -> None:
        from buildcompiler.protocols.allocation.wells import BLOCK_24

        if self.api_level != "2.21":
            raise ValueError("This backend currently supports API 2.21.")
        PLATE_96.name(self.thermocycler_starting_well)
        BLOCK_24.name(self.initial_dna_well)
        for tip in (self.initial_tip_p20, self.initial_tip_p300):
            if tip is not None:
                PLATE_96.index(tip)
        validate_slots(
            (
                self.temperature_module_position,
                self.dna_plate_position,
                self.tube_rack_position,
                self.tiprack_p20_position,
                self.tiprack_p200_position,
            )
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsPlatingProfile:
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
