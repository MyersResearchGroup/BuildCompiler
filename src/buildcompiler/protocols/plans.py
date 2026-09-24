"""Immutable logical plans with explicit input and output sample identities."""

from dataclasses import dataclass

from buildcompiler.protocols.materials import Sample
from buildcompiler.protocols.steps import Distribute, Mix, Step, Transfer


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtocolPlan:
    id: str
    request_id: str
    samples: tuple[Sample, ...]
    input_sample_ids: tuple[str, ...]
    output_sample_ids: tuple[str, ...]
    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        sample_ids = {sample.id for sample in self.samples}
        if len(sample_ids) != len(self.samples):
            raise ValueError("Sample ids must be unique within a plan.")
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Step ids must be unique within a plan.")
        if not set(self.input_sample_ids + self.output_sample_ids) <= sample_ids:
            raise ValueError("Plan inputs and outputs must reference declared samples.")
        for sample in self.samples:
            if not set(sample.parent_ids) <= sample_ids:
                raise ValueError(f"Unknown parent for sample {sample.id}.")
        for step in self.steps:
            referenced = set()
            if isinstance(step, Transfer):
                referenced = {step.source.sample_id, step.destination.sample_id}
            elif isinstance(step, Distribute):
                referenced = {
                    step.source.sample_id,
                    *(d.sample_id for d in step.destinations),
                }
                if step.track_liquid_sample_id:
                    referenced.add(step.track_liquid_sample_id)
            elif isinstance(step, Mix):
                referenced = {step.location.sample_id}
            if referenced - sample_ids:
                raise ValueError(f"Unknown sample in operation {step.id}.")
