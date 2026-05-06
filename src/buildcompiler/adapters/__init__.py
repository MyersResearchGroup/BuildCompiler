"""Adapter package exports without optional dependency side effects."""

from .protocols import ProtocolArtifact, maybe_write_protocol_artifacts

__all__ = ["ProtocolArtifact", "maybe_write_protocol_artifacts"]
