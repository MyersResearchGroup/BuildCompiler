"""SBOL assembly service wrapping legacy Golden Gate behavior."""

from dataclasses import dataclass, field

import sbol2

from buildcompiler.domain import (
    BuildStage,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
)
from buildcompiler.sbol2build import Assembly


@dataclass
class _LegacyPlasmidAdapter:
    plasmid_definition: sbol2.ComponentDefinition
    plasmid_implementations: list[sbol2.Implementation]


@dataclass
class AssemblyJob:
    """Normalized assembly inputs plus source/target SBOL documents."""

    stage: BuildStage
    product_identity: str
    product_display_id: str
    part_plasmids: list[IndexedPlasmid]
    backbone: IndexedBackbone
    restriction_enzyme: IndexedReagent
    ligase: IndexedReagent
    source_document: sbol2.Document
    target_document: sbol2.Document
    include_extracted_parts: bool = False


@dataclass
class AssemblySbolResult:
    """Assembly output contract: normalized products plus stage document."""

    products: list[IndexedPlasmid]
    stage_document: sbol2.Document
    activity_identity: str
    logs: list[str] = field(default_factory=list)


class AssemblyService:
    """Service wrapper that preserves legacy assembly internals behind normalized contracts."""

    def run(self, job: AssemblyJob) -> AssemblySbolResult:
        if not job.part_plasmids:
            raise ValueError(
                "AssemblyJob.part_plasmids must contain at least one plasmid"
            )

        legacy_parts = [
            self._record_to_legacy_plasmid(record, job.source_document, "part_plasmids")
            for record in job.part_plasmids
        ]
        legacy_backbone = self._record_to_legacy_plasmid(
            IndexedPlasmid(
                identity=job.backbone.identity,
                display_id=job.backbone.display_id,
                name=job.backbone.name,
                metadata=job.backbone.metadata,
                sbol_component=job.backbone.sbol_component,
            ),
            job.source_document,
            "backbone",
        )

        restriction_impl = self._implementation_from_record(
            job.restriction_enzyme, job.source_document
        )
        ligase_impl = self._implementation_from_record(job.ligase, job.source_document)

        composite_prefix = job.product_display_id or job.product_identity.split("/")[-1]
        legacy_assembly = Assembly(
            part_plasmids=legacy_parts,
            backbone_plasmid=legacy_backbone,
            restriction_enzyme=restriction_impl,
            ligase=ligase_impl,
            source_document=job.source_document,
            final_document=job.target_document,
            composite_prefix=composite_prefix,
        )
        legacy_products, final_doc = legacy_assembly.run(
            include_extracted_parts=job.include_extracted_parts
        )

        products = [
            self._indexed_product_from_legacy_product(plasmid, job)
            for plasmid in legacy_products
        ]
        logs = [
            f"Assembled {len(products)} product(s) at stage {job.stage.value}.",
            f"Assembly activity: {legacy_assembly.assembly_activity.identity}",
        ]

        return AssemblySbolResult(
            products=products,
            stage_document=final_doc,
            activity_identity=legacy_assembly.assembly_activity.identity,
            logs=logs,
        )

    def _record_to_legacy_plasmid(
        self,
        record: IndexedPlasmid,
        source_document: sbol2.Document,
        field_name: str,
    ) -> _LegacyPlasmidAdapter:
        component = self._component_from_record(record, source_document, field_name)
        implementation = self._implementation_from_plasmid_record(
            record, source_document
        )
        return _LegacyPlasmidAdapter(component, [implementation])

    def _component_from_record(
        self,
        record: IndexedPlasmid,
        source_document: sbol2.Document,
        field_name: str,
    ) -> sbol2.ComponentDefinition:
        component = record.sbol_component or source_document.find(record.identity)
        if component is None:
            raise ValueError(
                f"Missing SBOL ComponentDefinition for {field_name} record {record.identity}"
            )
        if not isinstance(component, sbol2.ComponentDefinition):
            raise ValueError(
                f"{field_name} record {record.identity} must resolve to sbol2.ComponentDefinition"
            )
        return component

    def _implementation_from_plasmid_record(
        self, record: IndexedPlasmid, source_document: sbol2.Document
    ) -> sbol2.Implementation:
        impl_identity = record.metadata.get("implementation_identity")
        implementation = source_document.find(impl_identity) if impl_identity else None

        if implementation is None:
            component = self._component_from_record(record, source_document, "plasmid")
            matches = [
                impl
                for impl in source_document.implementations
                if isinstance(impl, sbol2.Implementation)
                and impl.built == component.identity
            ]
            implementation = matches[0] if matches else None

        if implementation is None:
            raise ValueError(
                f"Missing SBOL Implementation for plasmid {record.identity}; "
                "set metadata['implementation_identity'] or include implementation in source_document"
            )
        return implementation

    def _implementation_from_record(
        self, record: IndexedReagent, source_document: sbol2.Document
    ) -> sbol2.Implementation:
        impl_identity = (
            record.metadata.get("implementation_identity") or record.identity
        )
        implementation = source_document.find(impl_identity)
        if not isinstance(implementation, sbol2.Implementation):
            raise ValueError(
                "Missing SBOL Implementation for reagent "
                f"{record.identity}; expected metadata['implementation_identity'] or identity to resolve"
            )
        return implementation

    def _indexed_product_from_legacy_product(
        self, product, job: AssemblyJob
    ) -> IndexedPlasmid:
        component = product.plasmid_definition
        return IndexedPlasmid(
            identity=component.identity,
            display_id=component.displayId,
            name=component.name,
            state=MaterialState.GENERATED,
            roles=list(component.roles),
            metadata={
                "source_stage": job.stage.value,
                "source_product_identity": job.product_identity,
                "source_product_display_id": job.product_display_id,
                "assembly_activity_identity": product.plasmid_implementations[
                    0
                ].wasGeneratedBy,
            },
            sbol_component=component,
        )
