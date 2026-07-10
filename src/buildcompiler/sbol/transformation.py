"""SBOL transformation service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import sbol2

from buildcompiler.domain import IndexedPlasmid, IndexedStrain, MaterialState


@dataclass
class TransformationJob:
    plasmid: IndexedPlasmid
    chassis_identity: str
    chassis_display_id: str
    source_document: Any
    target_document: Any


@dataclass
class TransformationSbolResult:
    product: IndexedStrain
    stage_document: Any
    activity_identity: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


class TransformationService:
    """Create SBOL records for transforming a chassis with one plasmid."""

    def run(self, job: TransformationJob) -> TransformationSbolResult:
        plasmid_component = self._plasmid_component(job)
        plasmid_impl = self._plasmid_implementation(job, plasmid_component)
        chassis_module = self._chassis_module(job)
        chassis_impl = self._chassis_implementation(job, chassis_module)

        product_display_id = (
            f"{job.chassis_display_id}_with_"
            f"{job.plasmid.display_id or plasmid_component.displayId}"
        )
        product_identity = (
            f"{job.chassis_identity}/transformed/{plasmid_component.displayId}"
        )

        transformed_module = sbol2.ModuleDefinition(product_identity)
        transformed_module.displayId = product_display_id
        transformed_module.name = product_display_id
        transformed_module.roles = list(getattr(chassis_module, "roles", []))

        inherited_chassis = transformed_module.modules.create("chassis")
        inherited_chassis.definition = chassis_module.identity
        plasmid_fc = transformed_module.functionalComponents.create("engineered_plasmid")
        plasmid_fc.definition = plasmid_component.identity
        transformed_module.wasDerivedFrom = chassis_module.identity

        plan = sbol2.Plan(f"{product_identity}/transformation_plan")
        plan.displayId = f"{product_display_id}_transformation_plan"
        plan.description = "Transform chassis with engineered plasmid."

        agent = sbol2.Agent("BuildCompiler")
        association = sbol2.Association(f"{product_identity}/association")
        association.agent = agent.identity
        association.plan = plan.identity

        activity = sbol2.Activity(f"{product_identity}/transformation_activity")
        activity.displayId = f"transform_{product_display_id}"
        activity.name = "Bacterial transformation"
        activity.associations.add(association)
        activity.usages.add(
            sbol2.Usage(
                uri="chassis",
                entity=chassis_impl.identity,
                role=sbol2.SBO_REACTANT,
            )
        )
        activity.usages.add(
            sbol2.Usage(
                uri="plasmid",
                entity=plasmid_impl.identity,
                role=sbol2.SBO_REACTANT,
            )
        )

        transformed_impl = sbol2.Implementation(f"{product_identity}/implementation")
        transformed_impl.displayId = f"{product_display_id}_implementation"
        transformed_impl.built = transformed_module.identity
        transformed_impl.wasGeneratedBy = activity.identity

        for obj in (
            chassis_module,
            chassis_impl,
            plasmid_component,
            plasmid_impl,
            transformed_module,
            transformed_impl,
            plan,
            agent,
            activity,
        ):
            self._add_if_missing(job.target_document, obj)

        metadata = {
            "source_stage": "transformation",
            "implementation_identity": transformed_impl.identity,
            "chassis_identity": chassis_module.identity,
            "chassis_implementation_identity": chassis_impl.identity,
            "plasmid_identity": plasmid_component.identity,
            "plasmid_implementation_identity": plasmid_impl.identity,
            "transformation_activity_identity": activity.identity,
        }
        product = IndexedStrain(
            identity=transformed_module.identity,
            display_id=product_display_id,
            name=transformed_module.name,
            state=MaterialState.TRANSFORMED,
            roles=list(transformed_module.roles),
            metadata=metadata,
            sbol_module=transformed_module,
        )
        return TransformationSbolResult(
            product=product,
            stage_document=job.target_document,
            activity_identity=activity.identity,
            artifacts={"transformation": metadata},
            logs=[f"Generated transformed strain {transformed_module.identity}."],
        )

    def _plasmid_component(self, job: TransformationJob) -> sbol2.ComponentDefinition:
        component = job.plasmid.sbol_component or job.source_document.find(
            job.plasmid.identity
        )
        if isinstance(component, sbol2.ComponentDefinition):
            return component
        fallback = sbol2.ComponentDefinition(job.plasmid.identity)
        fallback.displayId = (
            job.plasmid.display_id or job.plasmid.identity.rsplit("/", 1)[-1]
        )
        fallback.name = job.plasmid.name
        fallback.roles = list(job.plasmid.roles)
        return fallback

    def _plasmid_implementation(
        self, job: TransformationJob, component: sbol2.ComponentDefinition
    ) -> sbol2.Implementation:
        impl_identity = job.plasmid.metadata.get("implementation_identity")
        implementation = job.source_document.find(impl_identity) if impl_identity else None
        if isinstance(implementation, sbol2.Implementation):
            return implementation
        for candidate in job.source_document.implementations:
            if (
                isinstance(candidate, sbol2.Implementation)
                and candidate.built == component.identity
            ):
                return candidate
        implementation = sbol2.Implementation(f"{component.identity}/implementation")
        implementation.displayId = f"{component.displayId}_implementation"
        implementation.built = component.identity
        return implementation

    def _chassis_module(self, job: TransformationJob) -> sbol2.ModuleDefinition:
        module = job.source_document.find(job.chassis_identity)
        if isinstance(module, sbol2.ModuleDefinition):
            return module
        module = sbol2.ModuleDefinition(job.chassis_identity)
        module.displayId = job.chassis_display_id
        module.name = job.chassis_display_id
        return module

    def _chassis_implementation(
        self, job: TransformationJob, module: sbol2.ModuleDefinition
    ) -> sbol2.Implementation:
        for candidate in job.source_document.implementations:
            if (
                isinstance(candidate, sbol2.Implementation)
                and candidate.built == module.identity
            ):
                return candidate
        implementation = sbol2.Implementation(f"{module.identity}/implementation")
        implementation.displayId = f"{module.displayId}_implementation"
        implementation.built = module.identity
        return implementation

    def _add_if_missing(self, document: sbol2.Document, obj: Any) -> None:
        if document.find(obj.identity) is None:
            document.add(obj)
