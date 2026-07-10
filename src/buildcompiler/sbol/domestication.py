"""SBOL domestication service."""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Any

import sbol2

from buildcompiler.constants import FUSION_SITES
from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent, MaterialState


ROLE_TO_FUSION_SITE_SEQUENCES = {
    "promoter": ("GGAG", "TACT"),
    "rbs": ("TACT", "AATG"),
    "cds": ("AATG", "AGGT"),
    "terminator": ("AGGT", "GCTT"),
}
FUSION_SITE_SEQUENCE_TO_NAME = {sequence: name for name, sequence in FUSION_SITES.items()}


@dataclass
class DomesticationJob:
    part_identity: str
    part_display_id: str | None
    part_component: Any
    backbone: IndexedBackbone
    restriction_enzyme: IndexedReagent
    ligase: IndexedReagent
    source_document: Any
    target_document: Any
    part_role: str | None = None
    fusion_site_sequences: tuple[str, str] | None = None
    fusion_site_names: tuple[str, str] | None = None
    sequence_edit_proposals: list[Any] = field(default_factory=list)


@dataclass
class DomesticationSbolResult:
    product: IndexedPlasmid
    stage_document: Any
    artifacts: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


class DomesticationService:
    def run(self, job: DomesticationJob) -> DomesticationSbolResult:
        component = self._ensure_component(job.part_component)
        fusion_site_sequences = self._fusion_site_sequences(job)
        fusion_site_names = self._fusion_site_names(job, fusion_site_sequences)
        source_sequence = self._resolve_sequence(component)
        generated_insert_sequence = self._apply_sequence_edit_proposals(
            source_sequence, job.sequence_edit_proposals
        )
        generated_synthesis_insert_sequence = self._build_synthesis_insert_sequence(
            insert_sequence=generated_insert_sequence,
            fusion_site_sequences=fusion_site_sequences,
        )
        backbone_sequence = self._backbone_sequence(
            job.backbone,
            source_document=job.source_document,
            target_document=job.target_document,
        )
        final_plasmid_sequence = self._assemble_final_plasmid_sequence(
            backbone_sequence=backbone_sequence,
            insert_sequence=self._assembled_insert_sequence(
                insert_sequence=generated_insert_sequence,
                fusion_site_sequences=fusion_site_sequences,
            ),
            insertion_index=self._backbone_insertion_index(job.backbone),
        )
        source_display_id = (
            job.part_display_id
            or component.displayId
            or component.identity.rstrip("/").rsplit("/", 1)[-1]
        )
        product_display_id = f"{source_display_id}_lvl0"

        product_component = sbol2.ComponentDefinition(product_display_id)
        product_component.displayId = product_display_id
        product_component.name = f"Domesticated {component.displayId or component.identity.rsplit('/', 1)[-1]}"
        product_component.roles = list(component.roles)
        job.target_document.addComponentDefinition(product_component)

        insert_sequence = sbol2.Sequence(f"{product_display_id}_insert_sequence")
        insert_sequence.elements = generated_synthesis_insert_sequence
        insert_sequence.encoding = sbol2.SBOL_ENCODING_IUPAC
        job.target_document.addSequence(insert_sequence)

        insert_component = sbol2.ComponentDefinition(f"{product_display_id}_insert")
        insert_component.name = f"{source_display_id} domestication insert"
        insert_component.roles = list(component.roles)
        insert_component.wasDerivedFrom = component.identity
        insert_component.sequences = [insert_sequence.identity]
        job.target_document.addComponentDefinition(insert_component)

        product_sequence = sbol2.Sequence(f"{product_display_id}_sequence")
        product_sequence.elements = final_plasmid_sequence
        product_sequence.encoding = sbol2.SBOL_ENCODING_IUPAC
        job.target_document.addSequence(product_sequence)
        product_component.sequences = [product_sequence.identity]

        product_implementation = sbol2.Implementation(
            f"{product_display_id}_implementation"
        )
        product_implementation.built = product_component.identity
        job.target_document.addImplementation(product_implementation)

        metadata = {
            "source_stage": "domestication",
            "product_identity": product_component.identity,
            "product_display_id": product_component.displayId,
            "source_part_identity": job.part_identity,
            "insert_identities": [job.part_identity],
            "generated_insert_identity": insert_component.identity,
            "generated_insert_display_id": insert_component.displayId,
            "implementation_identity": product_implementation.identity,
            "backbone_identity": job.backbone.identity,
            "restriction_enzyme": {
                "identity": job.restriction_enzyme.identity,
                "name": job.restriction_enzyme.name,
            },
            "ligase": {"identity": job.ligase.identity, "name": job.ligase.name},
            "sequence_edit_proposals": [proposal.__dict__.copy() for proposal in job.sequence_edit_proposals],
            "part_role": job.part_role,
            "fusion_site_sequences": list(fusion_site_sequences),
            "fusion_site_names": list(fusion_site_names),
            "source_sequence": source_sequence,
            "domesticated_part_sequence": generated_insert_sequence,
            "generated_insert_sequence": generated_synthesis_insert_sequence,
            "generated_insert_sequence_identity": insert_sequence.identity,
            "backbone_sequence": backbone_sequence,
            "final_plasmid_sequence": final_plasmid_sequence,
            "final_plasmid_sequence_identity": product_sequence.identity,
        }
        product = IndexedPlasmid(
            identity=product_component.identity,
            display_id=product_display_id,
            name=product_component.name,
            state=MaterialState.GENERATED,
            roles=list(component.roles),
            metadata=metadata,
            sbol_component=product_component,
        )
        return DomesticationSbolResult(
            product=product,
            stage_document=job.target_document,
            artifacts={"domestication": metadata},
            logs=[f"Generated domesticated lvl0 product {product_component.identity}."],
        )

    def _ensure_component(self, component: Any) -> sbol2.ComponentDefinition:
        if not isinstance(component, sbol2.ComponentDefinition):
            raise ValueError("DomesticationJob.part_component must be an sbol2.ComponentDefinition")
        return component

    def _resolve_sequence(self, component: sbol2.ComponentDefinition) -> str:
        for sequence_ref in component.sequences:
            sequence = component.doc.find(sequence_ref) if component.doc else None
            elements = getattr(sequence, "elements", None)
            if isinstance(elements, str) and elements:
                return elements.upper()
        raise ValueError(f"Part {component.identity} is missing a usable DNA sequence")

    def _apply_sequence_edit_proposals(
        self, source_sequence: str, sequence_edit_proposals: list[Any]
    ) -> str:
        sequence = source_sequence.upper()
        for proposal in sorted(
            sequence_edit_proposals,
            key=lambda item: int(getattr(item, "position", 0)),
            reverse=True,
        ):
            position = int(getattr(proposal, "position"))
            original = str(getattr(proposal, "original_sequence")).upper()
            proposed = str(getattr(proposal, "proposed_sequence")).upper()
            if sequence[position : position + len(original)] != original:
                raise ValueError(
                    "Sequence edit proposal does not match source sequence at "
                    f"position {position}."
                )
            sequence = sequence[:position] + proposed + sequence[position + len(original) :]
        return sequence

    def _fusion_site_sequences(self, job: DomesticationJob) -> tuple[str, str]:
        if job.fusion_site_sequences is not None:
            return tuple(job.fusion_site_sequences)
        if job.part_role in ROLE_TO_FUSION_SITE_SEQUENCES:
            return ROLE_TO_FUSION_SITE_SEQUENCES[job.part_role]
        raise ValueError(
            "DomesticationJob requires part_role or fusion_site_sequences for MoClo insert design."
        )

    def _fusion_site_names(
        self, job: DomesticationJob, fusion_site_sequences: tuple[str, str]
    ) -> tuple[str, str]:
        if job.fusion_site_names is not None:
            return tuple(job.fusion_site_names)
        return tuple(FUSION_SITE_SEQUENCE_TO_NAME[site] for site in fusion_site_sequences)

    def _random_dna(self, length: int) -> str:
        return "".join(random.choices("ACGT", k=length))

    def _build_synthesis_insert_sequence(
        self, *, insert_sequence: str, fusion_site_sequences: tuple[str, str]
    ) -> str:
        return (
            self._random_dna(35)
            + "GGTCTC"
            + fusion_site_sequences[0]
            + insert_sequence
            + fusion_site_sequences[1]
            + "GAGACC"
            + self._random_dna(35)
        )

    def _assembled_insert_sequence(
        self, *, insert_sequence: str, fusion_site_sequences: tuple[str, str]
    ) -> str:
        return fusion_site_sequences[0] + insert_sequence + fusion_site_sequences[1]

    def _backbone_sequence(
        self,
        backbone: IndexedBackbone,
        *,
        source_document: Any,
        target_document: Any,
    ) -> str | None:
        component = self._find_backbone_component(
            backbone,
            source_document=source_document,
            target_document=target_document,
        )
        if component is not None:
            sequence = self._component_sequence(component)
            if sequence is not None:
                return sequence

        sequence = backbone.metadata.get("sequence")
        if isinstance(sequence, str) and sequence:
            return sequence.upper()
        return None

    def _find_backbone_component(
        self,
        backbone: IndexedBackbone,
        *,
        source_document: Any,
        target_document: Any,
    ) -> sbol2.ComponentDefinition | None:
        for document in (source_document, target_document):
            candidate = document.find(backbone.identity) if document is not None else None
            if isinstance(candidate, sbol2.ComponentDefinition):
                return candidate

        if isinstance(backbone.sbol_component, sbol2.ComponentDefinition):
            return backbone.sbol_component
        return None

    def _component_sequence(self, component: sbol2.ComponentDefinition) -> str | None:
        for sequence_ref in component.sequences:
            sequence_obj = component.doc.find(sequence_ref) if component.doc else None
            elements = getattr(sequence_obj, "elements", None)
            if isinstance(elements, str) and elements:
                return elements.upper()
        return None

    def _backbone_insertion_index(self, backbone: IndexedBackbone) -> int | None:
        index = backbone.metadata.get("insertion_index")
        return int(index) if index is not None else None

    def _assemble_final_plasmid_sequence(
        self,
        *,
        backbone_sequence: str | None,
        insert_sequence: str,
        insertion_index: int | None,
    ) -> str:
        if backbone_sequence is None:
            return insert_sequence
        index = len(backbone_sequence) if insertion_index is None else insertion_index
        if index < 0 or index > len(backbone_sequence):
            raise ValueError("Backbone insertion_index is outside the backbone sequence.")
        return backbone_sequence[:index] + insert_sequence + backbone_sequence[index:]
