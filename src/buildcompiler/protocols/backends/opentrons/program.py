"""Immutable SDK call records produced by lowering; never live SDK objects."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Reference:
    name: str
    well: str | None = None
    bottom_mm: float | None = None
    top_mm: float | None = None
    track_conical_height: bool = False


@dataclass(frozen=True, slots=True)
class Record:
    entries: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Call:
    target: str
    method: str
    args: tuple = ()
    kwargs: tuple[tuple[str, object], ...] = ()
    result: str | None = None
    skip_during_simulation: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class SetStartingTip:
    pipette: str
    tip: Reference


@dataclass(frozen=True, slots=True, kw_only=True)
class OpentronsProgram:
    api_level: str
    instructions: tuple[Call | SetStartingTip, ...]
    wells: tuple[tuple[str, Reference], ...] = ()
