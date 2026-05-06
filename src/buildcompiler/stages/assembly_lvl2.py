"""Thin lvl2 assembly stage orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sbol2

from buildcompiler.adapters.pudu import assembly_route_to_pudu_json
from buildcompiler.api import BuildOptions
from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    MissingBuildInput,
    StageResult,
    StageStatus,
)
from buildcompiler.inventory import CompatibilitySelector, Inventory
from buildcompiler.inventory.compatibility import Lvl2Route
from buildcompiler.sbol import AssemblyJob, AssemblyService


class AssemblyLvl2Stage:
    def __init__(
        self,
        *,
        inventory: Inventory,
        selector: CompatibilitySelector | None = None,
        assembly_service: AssemblyService | None = None,
        options: BuildOptions | None = None,
    ) -> None:
        self.inventory = inventory
        self.options = options or BuildOptions()
        self.selector = selector or CompatibilitySelector(
            inventory, options=self.options
        )
        self.assembly_service = assembly_service or AssemblyService()

    def run(
        self,
        request: BuildRequest,
        *,
        source_document: sbol2.Document,
        target_document: sbol2.Document,
    ) -> StageResult:
        constraints = request.constraints or {}
        module_definition = source_document.find(request.source_identity)
        if not isinstance(module_definition, sbol2.ModuleDefinition):
            return StageResult(
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL2.value}",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.FAILED,
                request_ids=[request.id],
                logs=[
                    f"Source identity is not a ModuleDefinition: {request.source_identity}"
                ],
            )

        region_identities = self._extract_region_identities(
            module_definition, constraints
        )
        if not region_identities:
            return StageResult(
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL2.value}",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.FAILED,
                request_ids=[request.id],
                logs=["No engineered-region identities found for lvl2 assembly."],
            )

        route_selection = self.selector.select_lvl2_route(
            request_id=request.id,
            region_identities=region_identities,
            constraints=constraints,
        )
        route = route_selection.selected
        artifacts = self._route_artifacts(route, route_selection.rejected)
        if route is None:
            return StageResult(
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL2.value}",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                protocol_artifacts=artifacts,
                logs=[
                    "No lvl2 route selected by CompatibilitySelector. Provide explicit region_order "
                    "or enable large-order search for large designs."
                ],
            )

        missing_inputs: list[MissingBuildInput] = []
        for missing_identity in route.missing_region_identities:
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL2,
                    source_design_identity=request.source_identity,
                    missing_identity=missing_identity,
                    missing_display_id=missing_identity.rsplit("/", 1)[-1],
                    missing_kind="engineered_region",
                    required_stage=BuildStage.ASSEMBLY_LVL1,
                    reason="No compatible lvl1 engineered-region plasmid found in inventory.",
                )
            )

        if route.backbone is None:
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL2,
                    source_design_identity=request.source_identity,
                    missing_identity="backbone",
                    missing_display_id=None,
                    missing_kind="backbone",
                    required_stage="fatal",
                    reason="No compatible lvl2 backbone found in inventory.",
                )
            )

        restriction_enzyme_name = self.options.reagents.default_restriction_enzyme
        restriction_enzyme = self.inventory.find_restriction_enzyme(
            restriction_enzyme_name
        )
        if restriction_enzyme is None:
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL2,
                    source_design_identity=request.source_identity,
                    missing_identity=restriction_enzyme_name,
                    missing_display_id=restriction_enzyme_name,
                    missing_kind="restriction_enzyme",
                    required_stage="fatal",
                    reason="Required restriction enzyme is missing from inventory.",
                )
            )

        ligase_name = self.options.reagents.default_ligase
        ligase = self.inventory.find_ligase(ligase_name)
        if ligase is None:
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL2,
                    source_design_identity=request.source_identity,
                    missing_identity=ligase_name,
                    missing_display_id=ligase_name,
                    missing_kind="ligase",
                    required_stage="fatal",
                    reason="Required ligase is missing from inventory.",
                )
            )

        if missing_inputs:
            return StageResult(
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL2.value}",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=missing_inputs,
                protocol_artifacts=artifacts,
                logs=[
                    f"Blocked lvl2 assembly for {request.id}; missing {len(missing_inputs)} required input(s)."
                ],
            )

        product_identity = (
            constraints.get("product_identity") or request.source_identity
        )
        product_display_id = (
            constraints.get("product_display_id")
            or request.source_display_id
            or product_identity.rsplit("/", 1)[-1]
        )
        assembly_result = self.assembly_service.run(
            AssemblyJob(
                stage=BuildStage.ASSEMBLY_LVL2,
                product_identity=product_identity,
                product_display_id=product_display_id,
                part_plasmids=list(route.selected_lvl1_plasmids),
                backbone=route.backbone,
                restriction_enzyme=restriction_enzyme,
                ligase=ligase,
                source_document=source_document,
                target_document=target_document,
            )
        )

        for product in assembly_result.products:
            insert_identities = list(product.metadata.get("insert_identities", []))
            if request.source_identity not in insert_identities:
                insert_identities.append(request.source_identity)
            product.metadata["insert_identities"] = insert_identities
            product.metadata.setdefault("source_stage", BuildStage.ASSEMBLY_LVL2.value)
            self.inventory.add_generated_product(product)

        json_intermediate = assembly_route_to_pudu_json(
            product_identity=product_identity,
            part_plasmids=route.selected_lvl1_plasmids,
            backbone=route.backbone,
            restriction_enzyme=restriction_enzyme,
        )

        return StageResult(
            id=f"{request.id}:{BuildStage.ASSEMBLY_LVL2.value}",
            stage=BuildStage.ASSEMBLY_LVL2,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=assembly_result.products,
            sbol_document=assembly_result.stage_document,
            json_intermediate=json_intermediate,
            protocol_artifacts=artifacts,
            logs=[
                f"Selected lvl2 route with {len(route.selected_lvl1_plasmids)} lvl1 plasmid(s).",
                *assembly_result.logs,
            ],
        )

    def _extract_region_identities(
        self, module_definition: sbol2.ModuleDefinition, constraints: Mapping[str, Any]
    ) -> list[str]:
        for key in ("engineered_region_identities", "region_identities"):
            values = constraints.get(key)
            if values:
                return list(values)

        identities: list[str] = []
        for functional_component in module_definition.functionalComponents:
            definition = functional_component.definition
            if definition:
                identities.append(definition)
        return identities

    def _route_artifacts(
        self, selected: Lvl2Route | None, rejected: tuple[Any, ...]
    ) -> dict[str, Any]:
        return {
            "selected_route": self._route_to_dict(selected),
            "rejected_routes": [self._route_to_dict(route) for route in rejected[:3]],
        }

    def _route_to_dict(self, route: Lvl2Route | None) -> dict[str, Any] | None:
        if route is None:
            return None
        return {
            "region_order": list(route.region_order),
            "selected_lvl1_plasmids": [
                p.identity for p in route.selected_lvl1_plasmids
            ],
            "missing_region_identities": list(route.missing_region_identities),
            "score": {
                "missing_required_products": route.score.missing_required_products,
                "missing_domestications": route.score.missing_domestications,
                "missing_lvl1_plasmids": route.score.missing_lvl1_plasmids,
                "generated_or_planned_materials": route.score.generated_or_planned_materials,
                "lower_material_state_penalty": route.score.lower_material_state_penalty,
                "constraint_violations": route.score.constraint_violations,
                "total_assemblies": route.score.total_assemblies,
                "identity_tiebreak": list(route.score.identity_tiebreak),
            },
        }
