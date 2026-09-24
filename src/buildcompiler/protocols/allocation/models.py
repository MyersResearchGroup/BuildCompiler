"""Allocation records are data, independent of any robot SDK."""

from dataclasses import dataclass

from buildcompiler.protocols.materials import Sample
from buildcompiler.protocols.plans import ProtocolPlan


@dataclass(frozen=True, slots=True, kw_only=True)
class WellRef:
    container_id: str
    well_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SamplePlacement:
    sample_id: str
    location: WellRef


@dataclass(frozen=True, slots=True, kw_only=True)
class ContainerSpec:
    id: str
    definition_id: str
    parent: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputManifest:
    protocol_id: str
    samples: tuple[Sample, ...]
    placements: tuple[SamplePlacement, ...]

    def __post_init__(self) -> None:
        ids = {s.id for s in self.samples}
        if (
            len(ids) != len(self.samples)
            or len(self.placements) != len(ids)
            or {p.sample_id for p in self.placements} != ids
        ):
            raise ValueError(
                "Manifest samples need unique ids and exactly one placement each."
            )
        if len({p.location for p in self.placements}) != len(self.placements):
            raise ValueError("Manifest sample locations must be unique.")

    def to_dict(self) -> dict:
        locations = {p.sample_id: p.location for p in self.placements}
        return {
            "schema_version": "1.0",
            "protocol_id": self.protocol_id,
            "state": "planned",
            "outputs": [
                {
                    "sample_id": sample.id,
                    "material_identity": sample.material.identity,
                    "label": sample.material.label,
                    "parent_sample_ids": list(sample.parent_ids),
                    "replicate": sample.replicate,
                    "source_sample_id": sample.source_sample_id,
                    "contents": list(sample.contents),
                    "dilution": sample.dilution,
                    "container_id": locations[sample.id].container_id,
                    "well_name": locations[sample.id].well_name,
                }
                for sample in self.samples
            ],
        }

    def plasmid_locations(self) -> dict[str, list[str]]:
        """Export the PUDU handoff only when one container is unambiguous."""
        locations = {p.sample_id: p.location for p in self.placements}
        if len({p.location.container_id for p in self.placements}) > 1:
            raise ValueError(
                "PUDU's location format cannot represent multiple containers."
            )
        result: dict[str, list[str]] = {}
        for sample in self.samples:
            result.setdefault(sample.material.identity, []).append(
                locations[sample.id].well_name
            )
        return result

    def bacterium_locations(self) -> dict[str, list[str]]:
        if len({p.location.container_id for p in self.placements}) > 1:
            raise ValueError(
                "PUDU's location format cannot represent multiple containers."
            )
        locations = {p.sample_id: p.location for p in self.placements}
        return {
            locations[s.id].well_name: list(s.contents or (s.material.label,))
            for s in self.samples
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class AllocatedProtocolPlan:
    protocol: ProtocolPlan
    containers: tuple[ContainerSpec, ...]
    placements: tuple[SamplePlacement, ...]

    def __post_init__(self) -> None:
        sample_ids = {sample.id for sample in self.protocol.samples}
        if (
            len(self.placements) != len(sample_ids)
            or {p.sample_id for p in self.placements} != sample_ids
        ):
            raise ValueError("Every sample must have exactly one placement.")
        if len({p.location for p in self.placements}) != len(self.placements):
            raise ValueError("Two samples cannot occupy the same location.")
        container_ids = {container.id for container in self.containers}
        if len(container_ids) != len(self.containers):
            raise ValueError("Container ids must be unique.")
        if any(p.location.container_id not in container_ids for p in self.placements):
            raise ValueError("Placements must reference declared containers.")

    def output_manifest(self) -> OutputManifest:
        ids = set(self.protocol.output_sample_ids)
        return OutputManifest(
            protocol_id=self.protocol.id,
            samples=tuple(s for s in self.protocol.samples if s.id in ids),
            placements=tuple(p for p in self.placements if p.sample_id in ids),
        )
