"""SBOL domestication service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sbol2

from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent, MaterialState


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
        product_identity = f"{component.identity}/domesticated"
        product_display_id = f"{job.part_display_id or component.displayId or component.identity.rsplit('/', 1)[-1]}_lvl0"

        product_component = sbol2.ComponentDefinition(product_identity)
        product_component.displayId = product_display_id
        product_component.name = f"Domesticated {component.displayId or component.identity.rsplit('/', 1)[-1]}"
        product_component.roles = list(component.roles)
        job.target_document.addComponentDefinition(product_component)

        implementation_identity = f"{product_identity}_implementation"
        product_implementation = sbol2.Implementation(implementation_identity)
        product_implementation.built = product_component.identity
        job.target_document.addImplementation(product_implementation)

        metadata = {
            "source_stage": "domestication",
            "source_part_identity": job.part_identity,
            "insert_identities": [job.part_identity],
            "implementation_identity": product_implementation.identity,
            "backbone_identity": job.backbone.identity,
            "restriction_enzyme": {
                "identity": job.restriction_enzyme.identity,
                "name": job.restriction_enzyme.name,
            },
            "ligase": {"identity": job.ligase.identity, "name": job.ligase.name},
            "sequence_edit_proposals": [proposal.__dict__.copy() for proposal in job.sequence_edit_proposals],
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
            logs=[f"Generated domesticated lvl0 product {product_identity}."],
        )

    def _ensure_component(self, component: Any) -> sbol2.ComponentDefinition:
        if not isinstance(component, sbol2.ComponentDefinition):
            raise ValueError("DomesticationJob.part_component must be an sbol2.ComponentDefinition")
        return component
