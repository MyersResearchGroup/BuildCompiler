"""Thin lvl1 assembly stage orchestration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sbol2

from buildcompiler.adapters.pudu import assembly_route_to_pudu_json
from buildcompiler.api.options import BuildOptions
from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    BuildWarning,
    MissingBuildInput,
    StageResult,
    StageStatus,
)
from buildcompiler.inventory import CompatibilitySelector, Inventory
from buildcompiler.sbol import AssemblyJob, AssemblyService


class AssemblyLvl1Stage:
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
        warnings = self._extract_warnings(request=request, constraints=constraints)
        part_identities = self._extract_part_identities(constraints)
        if not part_identities:
            return StageResult(
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL1.value}",
                stage=BuildStage.ASSEMBLY_LVL1,
                status=StageStatus.FAILED,
                request_ids=[request.id],
                warnings=warnings,
                logs=[
                    "Missing ordered_part_identities/part_identities constraint for lvl1 assembly."
                ],
            )

        route_selection = self.selector.select_lvl1_route(
            request_id=request.id,
            part_identities=part_identities,
            constraints=constraints,
        )
        route = route_selection.selected
        if route is None:
            return StageResult(
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL1.value}",
                stage=BuildStage.ASSEMBLY_LVL1,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                warnings=warnings,
                logs=["No lvl1 route selected by CompatibilitySelector."],
            )

        missing_inputs: list[MissingBuildInput] = []
        for missing_identity in route.missing_part_identities:
            missing_component = source_document.find(missing_identity)
            missing_display_id = getattr(missing_component, "displayId", None)
            if missing_display_id is None:
                stripped_identity = missing_identity.rstrip("/")
                if stripped_identity.endswith("/1"):
                    missing_display_id = stripped_identity.rsplit("/", 2)[-2]
                else:
                    missing_display_id = stripped_identity.rsplit("/", 1)[-1]
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL1,
                    source_design_identity=request.source_identity,
                    missing_identity=missing_identity,
                    missing_display_id=missing_display_id,
                    missing_kind=self._infer_missing_kind(missing_identity),
                    required_stage=BuildStage.DOMESTICATION,
                    reason="No compatible lvl1 part plasmid found in inventory.",
                )
            )

        if route.backbone is None:
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL1,
                    source_design_identity=request.source_identity,
                    missing_identity="backbone",
                    missing_display_id=None,
                    missing_kind="backbone",
                    required_stage="fatal",
                    reason="No compatible lvl1 backbone found in inventory.",
                )
            )

        restriction_enzyme_name = self.options.reagents.default_restriction_enzyme
        restriction_enzyme = self.inventory.find_restriction_enzyme(
            restriction_enzyme_name
        )
        if restriction_enzyme is None:
            missing_inputs.append(
                MissingBuildInput(
                    source_stage=BuildStage.ASSEMBLY_LVL1,
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
                    source_stage=BuildStage.ASSEMBLY_LVL1,
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
                id=f"{request.id}:{BuildStage.ASSEMBLY_LVL1.value}",
                stage=BuildStage.ASSEMBLY_LVL1,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=missing_inputs,
                warnings=warnings,
                logs=[
                    f"Blocked lvl1 assembly for {request.id}; missing {len(missing_inputs)} required input(s)."
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
                stage=BuildStage.ASSEMBLY_LVL1,
                product_identity=product_identity,
                product_display_id=product_display_id,
                part_plasmids=list(route.selected_part_plasmids),
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
            self.inventory.add_generated_product(product)

        json_intermediate = assembly_route_to_pudu_json(
            product_identity=product_identity,
            part_plasmids=route.selected_part_plasmids,
            backbone=route.backbone,
            restriction_enzyme=restriction_enzyme,
        )

        logs = [
            f"Selected lvl1 route with {len(route.selected_part_plasmids)} part plasmid(s).",
            *assembly_result.logs,
        ]
        return StageResult(
            id=f"{request.id}:{BuildStage.ASSEMBLY_LVL1.value}",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=assembly_result.products,
            warnings=warnings,
            sbol_document=assembly_result.stage_document,
            json_intermediate=json_intermediate,
            logs=logs,
        )

    def _extract_part_identities(self, constraints: Mapping[str, Any]) -> list[str]:
        ordered = constraints.get("ordered_part_identities")
        if ordered:
            return list(ordered)
        planner_order = constraints.get("part_order")
        if planner_order:
            return list(planner_order)
        unordered = constraints.get("part_identities")
        if unordered:
            return list(unordered)
        return []

    def _extract_warnings(
        self, *, request: BuildRequest, constraints: Mapping[str, Any]
    ) -> list[BuildWarning]:
        warnings: list[BuildWarning] = []
        for item in constraints.get("ordering_warnings", []):
            if isinstance(item, BuildWarning):
                warnings.append(item)
            elif isinstance(item, Mapping):
                warnings.append(
                    BuildWarning(
                        code=str(item.get("code", "ordering_warning")),
                        message=str(item.get("message", "Ordering warning.")),
                        stage=BuildStage.ASSEMBLY_LVL1,
                        source_identity=request.source_identity,
                        metadata=dict(item.get("metadata", {})),
                    )
                )
        return warnings

    def _infer_missing_kind(self, part_identity: str) -> str:
        text = part_identity.lower()
        for role in ("promoter", "rbs", "cds", "terminator"):
            if role in text:
                return role
        return "reagent"
