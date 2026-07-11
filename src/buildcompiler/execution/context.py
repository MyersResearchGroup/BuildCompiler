"""Execution context contract for full-build orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from buildcompiler.inventory import Inventory
from buildcompiler.sbol import SbolResolver


@dataclass
class BuildContext:
    sbol: SbolResolver
    inventory: Inventory
    build_document: Any
    options: Any
    adapters: Any = None
    graph: Any = None
    logger: Any = None
