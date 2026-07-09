"""Deterministic domestication planning helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

import sbol2

from buildcompiler.domain import BuildStage, BuildWarning
from buildcompiler.planning.validation import classify_part_role


@dataclass
class SequenceEditProposal:
    source_identity: str
    enzyme_name: str
    site_sequence: str
    position: int
    original_sequence: str
    proposed_sequence: str
    reason: str
    approved: bool = False


@dataclass
class DomesticationPlan:
    part_identity: str
    part_display_id: str | None
    part_role: str
    backbone_identity: str | None = None
    restriction_enzyme_name: str = "BsaI"
    ligase_name: str = "T4_DNA_ligase"
    sequence_edit_proposals: list[SequenceEditProposal] = field(default_factory=list)
    warnings: list[BuildWarning] = field(default_factory=list)


class DomesticationPlanner:
    """Pure planner for domestication requirements for a single part."""

    _BSAI_SITES = ("GGTCTC", "GAGACC")

    def plan(self, part_component: sbol2.ComponentDefinition) -> DomesticationPlan:
        part_role = classify_part_role(part_component)
        if part_role is None:
            raise ValueError(
                f"Unsupported domestication role for part {part_component.identity}; expected promoter/rbs/cds/terminator"
            )

        sequence = self._resolve_sequence(part_component)
        proposals: list[SequenceEditProposal] = []
        for site in self._BSAI_SITES:
            start = 0
            while True:
                index = sequence.find(site, start)
                if index < 0:
                    break
                proposals.append(
                    SequenceEditProposal(
                        source_identity=part_component.identity,
                        enzyme_name="BsaI",
                        site_sequence=site,
                        position=index,
                        original_sequence=site,
                        proposed_sequence=f"{site[:-1]}A",
                        reason="Internal BsaI recognition site detected; human-reviewed edit required.",
                    )
                )
                start = index + 1

        return DomesticationPlan(
            part_identity=part_component.identity,
            part_display_id=part_component.displayId,
            part_role=part_role,
            sequence_edit_proposals=proposals,
        )

    def _resolve_sequence(self, part_component: sbol2.ComponentDefinition) -> str:
        for sequence_ref in part_component.sequences:
            sequence_obj = part_component.doc.find(sequence_ref) if part_component.doc else None
            elements = getattr(sequence_obj, "elements", None)
            if isinstance(elements, str) and elements:
                return elements.upper()
        raise ValueError(f"Part {part_component.identity} is missing a usable DNA sequence")
