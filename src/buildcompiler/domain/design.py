"""Design identity/type contracts."""

from enum import Enum


class DesignKind(str, Enum):
    """Supported SBOL design source kinds for build requests."""

    COMPONENT_DEFINITION = "component_definition"
    MODULE_DEFINITION = "module_definition"
    COMBINATORIAL_DERIVATION = "combinatorial_derivation"
    UNSUPPORTED = "unsupported"
