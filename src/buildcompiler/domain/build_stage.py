"""Build stage enum contracts."""

from enum import Enum


class BuildStage(str, Enum):
    """Planned v1 build stages for full-build execution."""

    DOMESTICATION = "domestication"
    ASSEMBLY_LVL1 = "assembly_lvl1"
    ASSEMBLY_LVL2 = "assembly_lvl2"
    TRANSFORMATION = "transformation"
    PLATING = "plating"
