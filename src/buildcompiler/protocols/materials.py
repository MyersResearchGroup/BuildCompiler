"""Samples retain material identity independently of their physical placement."""

from dataclasses import dataclass

from buildcompiler.domain.protocol_requests import MaterialRef


@dataclass(frozen=True, slots=True, kw_only=True)
class Sample:
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


@dataclass(frozen=True, slots=True, kw_only=True)
class SamplePoint:
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
