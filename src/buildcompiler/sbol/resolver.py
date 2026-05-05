"""SBOL document resolver with deterministic pull policy."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

import sbol2


class PullPolicy(str, Enum):
    """Resolver behavior for remote pull attempts."""

    NEVER = "never"
    MISSING_ONLY = "missing_only"
    ALWAYS_REFRESH = "always_refresh"


class SbolResolver:
    """Resolve SBOL objects by identity from a local document with optional pull fallback."""

    def __init__(
        self,
        document: sbol2.Document,
        *,
        pull_policy: PullPolicy = PullPolicy.MISSING_ONLY,
        pull_client: Callable[[str], Any] | None = None,
    ) -> None:
        self.document = document
        self.pull_policy = pull_policy
        self.pull_client = pull_client

    def maybe_pull(self, identity: str) -> Any | None:
        if self.pull_policy == PullPolicy.NEVER:
            return None
        if self.pull_client is None:
            return None
        return self.pull_client(identity)

    def _get(self, identity: str, expected_type: type) -> Any:
        if self.pull_policy == PullPolicy.ALWAYS_REFRESH:
            self.maybe_pull(identity)

        obj = self.document.find(identity)
        if isinstance(obj, expected_type):
            return obj

        if self.pull_policy == PullPolicy.MISSING_ONLY:
            self.maybe_pull(identity)
            obj = self.document.find(identity)
            if isinstance(obj, expected_type):
                return obj

        raise LookupError(
            f"Could not resolve {expected_type.__name__} with identity '{identity}'"
        )

    def get_component(self, identity: str) -> sbol2.ComponentDefinition:
        return self._get(identity, sbol2.ComponentDefinition)

    def get_module(self, identity: str) -> sbol2.ModuleDefinition:
        return self._get(identity, sbol2.ModuleDefinition)

    def get_combinatorial_derivation(
        self, identity: str
    ) -> sbol2.CombinatorialDerivation:
        return self._get(identity, sbol2.CombinatorialDerivation)

    def get_implementation(self, identity: str) -> sbol2.Implementation:
        return self._get(identity, sbol2.Implementation)
