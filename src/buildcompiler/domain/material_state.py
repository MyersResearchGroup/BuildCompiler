"""Material lifecycle states used across stages."""

from enum import Enum


class MaterialState(str, Enum):
    """Normalized lifecycle states for build materials."""

    PLANNED = "planned"
    GENERATED = "generated"
    ASSEMBLED = "assembled"
    TRANSFORMED = "transformed"
    PLATED = "plated"
