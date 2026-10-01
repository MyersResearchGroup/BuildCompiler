"""Bounded fixed-point full-build executor."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any

from buildcompiler.api.options import BuildOptions
from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    BuildStatus,
    DesignKind,
    FullBuildResult,
    IndexedPlasmid,
    MissingBuildInput,
    StageResult,
    StageStatus,
)
from buildcompiler.execution.context import BuildContext
from buildcompiler.inventory import Inventory
from buildcompiler.planning import BuildPlan
from buildcompiler.sbol import SbolResolver
from buildcompiler.stages import (
    AssemblyLvl1Stage,
    AssemblyLvl2Stage,
    DomesticationStage,
    TransformationStage,
)


class FullBuildExecutor:
    def __init__(
        self,
        *,
        context: BuildContext,
        lvl2_stage: Any | None = None,
        lvl1_stage: Any | None = None,
        domestication_stage: Any | None = None,
        transformation_stage: Any | None = None,
        plating_stage: Any | None = None,
    ) -> None:
        self.context = context
        options = context.options
        self.lvl2_stage = lvl2_stage or AssemblyLvl2Stage(
            inventory=context.inventory, options=options
        )
        self.lvl1_stage = lvl1_stage or AssemblyLvl1Stage(
            inventory=context.inventory, options=options
        )
        self.domestication_stage = domestication_stage or DomesticationStage(
            inventory=context.inventory, options=options
        )
        self._transformation_stage_injected = transformation_stage is not None
        self.transformation_stage = transformation_stage
        if self.transformation_stage is None and options.transformation.enabled:
            self.transformation_stage = TransformationStage(options=options)
        self.plating_stage = plating_stage

    @classmethod
    def from_dependencies(
        cls,
        *,
        inventory: Inventory,
        sbol_document: Any,
        options: BuildOptions,
        adapters: Any = None,
        graph: Any = None,
        logger: Any = None,
        resolver: SbolResolver | None = None,
        **stage_overrides: Any,
    ) -> FullBuildExecutor:
        active_resolver = resolver or SbolResolver(sbol_document)
        return cls(
            context=BuildContext(
                sbol=active_resolver,
                inventory=inventory,
                build_document=sbol_document,
                options=options,
                adapters=adapters,
                graph=graph,
                logger=logger,
            ),
            **stage_overrides,
        )

    def execute(
        self, plan: BuildPlan, *, options: BuildOptions | None = None
    ) -> FullBuildResult:
        if options is not None:
            self._apply_options(options)

        pending = {
            BuildStage.ASSEMBLY_LVL2: OrderedDict(
                (r.id, r) for r in plan.lvl2_requests
            ),
            BuildStage.ASSEMBLY_LVL1: OrderedDict(
                (r.id, r) for r in plan.lvl1_requests
            ),
            BuildStage.DOMESTICATION: OrderedDict(
                (r.id, r) for r in plan.domestication_requests
            ),
        }
        completed: set[str] = set()
        stage_results: list[StageResult] = []
        final_products: dict[str, Any] = {}
        missing_by_key: dict[tuple, MissingBuildInput] = {}
        approvals: dict[str, Any] = {}
        warnings: list[Any] = list(plan.warnings)
        seen_products: set[str] = set()
        transformed: set[str] = set()
        plated: set[str] = set()

        for _ in range(self.context.options.execution.max_iterations):
            progress = False
            for stage in (
                BuildStage.ASSEMBLY_LVL2,
                BuildStage.ASSEMBLY_LVL1,
                BuildStage.DOMESTICATION,
            ):
                runner = {
                    BuildStage.ASSEMBLY_LVL2: self.lvl2_stage,
                    BuildStage.ASSEMBLY_LVL1: self.lvl1_stage,
                    BuildStage.DOMESTICATION: self.domestication_stage,
                }[stage]
                for request in list(pending[stage].values()):
                    result = self._run_stage(runner, request)
                    stage_results.append(result)
                    warnings.extend(result.warnings)
                    for approval in result.required_approvals:
                        approvals[str(approval)] = approval
                    if result.status in (
                        StageStatus.SUCCESS,
                        StageStatus.PARTIAL_SUCCESS,
                    ):
                        if request.id not in completed:
                            completed.add(request.id)
                            progress = True
                        pending[stage].pop(request.id, None)
                        progress = (
                            self._index_products(result, final_products, seen_products)
                            or progress
                        )
                        progress = (
                            self._chain(
                                result.products,
                                stage_results,
                                transformed,
                                plated,
                                final_products,
                                seen_products,
                                missing_by_key,
                                approvals,
                                warnings,
                            )
                            or progress
                        )
                    else:
                        for missing in result.missing_inputs:
                            missing_by_key[self._missing_key(missing)] = missing
                            promoted = self._promote(request, missing)
                            if (
                                promoted is not None
                                and promoted.id not in pending[promoted.stage]
                                and promoted.id not in completed
                            ):
                                pending[promoted.stage][promoted.id] = promoted
                                progress = True

            if not any(pending[s] for s in pending):
                break
            if not progress:
                break

        unresolved = [
            m
            for m in missing_by_key.values()
            if self._promote(None, m) is None
            or self._promote(None, m).id not in completed
        ]
        products = list(final_products.values())
        target_request_ids = {
            request.id
            for request in (
                plan.lvl2_requests or plan.lvl1_requests or plan.domestication_requests
            )
        }
        target_by_identity: dict[str, Any] = {}
        for stage_result in stage_results:
            if stage_result.status in (
                StageStatus.SUCCESS,
                StageStatus.PARTIAL_SUCCESS,
            ) and target_request_ids.intersection(stage_result.request_ids):
                for product in stage_result.products:
                    target_by_identity[product.identity] = product

        artifact_bundle = None
        try:
            from buildcompiler.adapters import build_protocol_bundle

            artifact_bundle = build_protocol_bundle(
                stage_results=stage_results,
                options=self.context.options.protocol,
            )
        except Exception as exc:  # noqa: BLE001 - Report backend failures as stage results.
            stage_results.append(
                StageResult(
                    id="protocol:bundle",
                    stage=BuildStage.PROTOCOL,
                    status=StageStatus.FAILED,
                    logs=[f"Protocol bundle generation failed: {exc}"],
                )
            )
            if not self.context.options.execution.continue_on_error:
                # Protocol failures are represented in the result contract so callers
                # can inspect otherwise valid compiler artifacts.
                artifact_bundle = None

        failed = any(result.status == StageStatus.FAILED for result in stage_results)
        incomplete = bool(unresolved or any(pending[s] for s in pending))
        status = (
            BuildStatus.SUCCESS
            if not failed and not incomplete
            else (BuildStatus.PARTIAL_SUCCESS if products else BuildStatus.FAILED)
        )
        from buildcompiler.reporting import build_graph, build_report, build_summary

        preliminary_result = FullBuildResult(
            status=status,
            plan=plan,
            build_document=self.context.build_document,
            stage_results=stage_results,
            graph=None,
            final_products=products,
            target_products=list(target_by_identity.values()),
            all_products=products,
            missing_inputs=unresolved,
            required_approvals=list(approvals.values()),
            warnings=warnings,
            summary=None,
            report=None,
            artifact_bundle=artifact_bundle,
        )
        graph = build_graph(preliminary_result)
        report = (
            build_report(preliminary_result, graph=graph)
            if self.context.options.reporting.include_detailed_report
            else None
        )
        final_result = FullBuildResult(
            status=status,
            plan=plan,
            build_document=self.context.build_document,
            stage_results=stage_results,
            graph=graph,
            final_products=products,
            target_products=list(target_by_identity.values()),
            all_products=products,
            missing_inputs=unresolved,
            required_approvals=list(approvals.values()),
            warnings=warnings,
            summary=None,
            report=report,
            artifact_bundle=artifact_bundle,
        )
        final_result.summary = build_summary(final_result)
        return final_result

    def _apply_options(self, options: BuildOptions) -> None:
        self.context.options = options
        for stage in (self.lvl2_stage, self.lvl1_stage, self.domestication_stage):
            if hasattr(stage, "options"):
                stage.options = options
            selector = getattr(stage, "selector", None)
            if selector is not None and hasattr(selector, "options"):
                selector.options = options
        if self._transformation_stage_injected:
            if self.transformation_stage is not None and hasattr(
                self.transformation_stage, "options"
            ):
                self.transformation_stage.options = options
        elif options.transformation.enabled:
            self.transformation_stage = TransformationStage(options=options)
        else:
            self.transformation_stage = None

    def _run_stage(self, stage: Any, request: BuildRequest) -> StageResult:
        source_document = (
            getattr(self.context.sbol, "document", None) or self.context.build_document
        )
        try:
            return stage.run(
                request,
                source_document=source_document,
                target_document=self.context.build_document,
            )
        except Exception:
            if not self.context.options.execution.continue_on_error:
                raise
            return StageResult(
                id=f"{request.id}:{request.stage.value}",
                stage=request.stage,
                status=StageStatus.FAILED,
                request_ids=[request.id],
                logs=["Unexpected execution error."],
            )

    def _index_products(
        self,
        result: StageResult,
        final_products: dict[str, Any],
        seen_products: set[str],
    ) -> bool:
        progress = False
        for product in result.products:
            if product.identity not in seen_products:
                seen_products.add(product.identity)
                if isinstance(product, IndexedPlasmid):
                    self.context.inventory.add_generated_product(product)
                final_products[product.identity] = product
                progress = True
        return progress

    def _promote(
        self, request: BuildRequest | None, missing: MissingBuildInput
    ) -> BuildRequest | None:
        if missing.required_stage not in (
            BuildStage.ASSEMBLY_LVL1,
            BuildStage.DOMESTICATION,
        ):
            return None
        prefix = (
            "lvl1"
            if missing.required_stage == BuildStage.ASSEMBLY_LVL1
            else "domestication"
        )
        digest = hashlib.sha1(missing.missing_identity.encode()).hexdigest()[:12]
        constraints = {
            "promoted_from_stage": missing.source_stage.value,
            "promoted_from_design_identity": missing.source_design_identity,
            "candidates_tried": list(missing.candidates_tried),
        }
        if (
            request is not None
            and missing.required_stage == BuildStage.ASSEMBLY_LVL1
            and request.constraints
        ):
            part_map = request.constraints.get(
                "lvl1_region_part_identities",
                request.constraints.get("region_part_identities", {}),
            )
            part_identities = part_map.get(missing.missing_identity)
            if part_identities:
                constraints["ordered_part_identities"] = list(part_identities)
                constraints["product_identity"] = missing.missing_identity
                constraints["product_display_id"] = (
                    missing.missing_display_id
                    or missing.missing_identity.rstrip("/").rsplit("/", 1)[-1]
                )
        return BuildRequest(
            id=f"promoted:{prefix}:{digest}",
            stage=missing.required_stage,
            source_identity=missing.missing_identity,
            source_display_id=missing.missing_display_id,
            source_kind=DesignKind.COMPONENT_DEFINITION,
            parent_group=request.id if request else missing.source_design_identity,
            constraints=constraints,
        )

    def _missing_key(self, missing: MissingBuildInput) -> tuple:
        return (
            missing.source_stage.value,
            missing.source_design_identity,
            missing.missing_identity,
            missing.missing_kind,
            str(missing.required_stage),
            missing.reason,
        )

    def _chain(
        self,
        products: list[Any],
        stage_results: list[StageResult],
        transformed: set[str],
        plated: set[str],
        final_products: dict[str, Any],
        seen_products: set[str],
        missing_by_key: dict[tuple, MissingBuildInput],
        approvals: dict[str, Any],
        warnings: list[Any],
    ) -> bool:
        progress = False
        if (
            self.transformation_stage is None
            or not self.context.options.transformation.enabled
        ):
            return False
        for product in products:
            if not isinstance(product, IndexedPlasmid):
                continue
            transform_key = (
                product.identity,
                self.context.options.transformation.chassis_identity,
            )
            if str(transform_key) in transformed:
                continue
            transformed.add(str(transform_key))
            try:
                t_result = self.transformation_stage.run(
                    product,
                    source_document=self.context.build_document,
                    target_document=self.context.build_document,
                )
            except Exception as exc:
                if not self.context.options.execution.continue_on_error:
                    raise
                t_result = StageResult(
                    id=f"transform:{product.identity}:failed",
                    stage=BuildStage.TRANSFORMATION,
                    status=StageStatus.FAILED,
                    request_ids=[product.identity],
                    logs=[f"Unexpected transformation error: {exc}"],
                )
            stage_results.append(t_result)
            warnings.extend(t_result.warnings)
            for approval in t_result.required_approvals:
                approvals[str(approval)] = approval
            for missing in t_result.missing_inputs:
                missing_by_key[self._missing_key(missing)] = missing
            for transformed_product in t_result.products:
                if transformed_product.identity not in seen_products:
                    seen_products.add(transformed_product.identity)
                    final_products[transformed_product.identity] = transformed_product
            progress = True
            if self.plating_stage is None:
                continue
            for out in t_result.products:
                if out.identity in plated:
                    continue
                plated.add(out.identity)
                try:
                    plating_result = self.plating_stage.run(out)
                except Exception as exc:
                    if not self.context.options.execution.continue_on_error:
                        raise
                    plating_result = StageResult(
                        id=f"plate:{out.identity}:failed",
                        stage=BuildStage.PLATING,
                        status=StageStatus.FAILED,
                        request_ids=[out.identity],
                        logs=[f"Unexpected plating error: {exc}"],
                    )
                stage_results.append(plating_result)
                progress = True
        return progress
