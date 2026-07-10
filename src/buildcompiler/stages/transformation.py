"""Transformation stage orchestration."""

from __future__ import annotations

from typing import Any

import sbol2

from buildcompiler.adapters.pudu import transformation_to_pudu_json
from buildcompiler.api.options import BuildOptions
from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    IndexedPlasmid,
    MissingBuildInput,
    StageResult,
    StageStatus,
)
from buildcompiler.sbol.transformation import TransformationJob, TransformationService


class TransformationStage:
    def __init__(
        self,
        *,
        transformation_service: TransformationService | None = None,
        options: BuildOptions | None = None,
    ) -> None:
        self.transformation_service = transformation_service or TransformationService()
        self.options = options or BuildOptions()

    def run(
        self,
        plasmid_or_request: IndexedPlasmid | BuildRequest,
        *,
        source_document: sbol2.Document | None = None,
        target_document: sbol2.Document | None = None,
    ) -> StageResult:
        source = source_document or sbol2.Document()
        target = target_document or source
        request_id = (
            plasmid_or_request.id
            if isinstance(plasmid_or_request, BuildRequest)
            else f"transform:{plasmid_or_request.identity}"
        )
        plasmid = self._plasmid_from_input(plasmid_or_request)
        if plasmid is None:
            return StageResult(
                id=f"{request_id}:{BuildStage.TRANSFORMATION.value}",
                stage=BuildStage.TRANSFORMATION,
                status=StageStatus.FAILED,
                request_ids=[request_id],
                logs=["Transformation input must be an IndexedPlasmid."],
            )

        chassis_identity = self.options.transformation.chassis_identity
        chassis_display_id = self.options.transformation.chassis_display_id
        if not chassis_identity:
            return StageResult(
                id=f"{request_id}:{BuildStage.TRANSFORMATION.value}",
                stage=BuildStage.TRANSFORMATION,
                status=StageStatus.BLOCKED,
                request_ids=[request_id],
                missing_inputs=[
                    MissingBuildInput(
                        source_stage=BuildStage.TRANSFORMATION,
                        source_design_identity=plasmid.identity,
                        missing_identity="chassis",
                        missing_display_id=None,
                        missing_kind="chassis",
                        required_stage="fatal",
                        reason="Transformation requires options.transformation.chassis_identity.",
                    )
                ],
                logs=["Transformation blocked on missing chassis identity."],
            )

        result = self.transformation_service.run(
            TransformationJob(
                plasmid=plasmid,
                chassis_identity=chassis_identity,
                chassis_display_id=chassis_display_id
                or chassis_identity.rsplit("/", 1)[-1],
                source_document=source,
                target_document=target,
            )
        )
        json_intermediate = transformation_to_pudu_json(
            strain_identity=result.product.identity,
            chassis_identity=chassis_identity,
            plasmids=[plasmid],
        )
        return StageResult(
            id=f"{request_id}:{BuildStage.TRANSFORMATION.value}",
            stage=BuildStage.TRANSFORMATION,
            status=StageStatus.SUCCESS,
            request_ids=[request_id],
            products=[result.product],
            sbol_document=result.stage_document,
            json_intermediate=json_intermediate,
            protocol_artifacts=result.artifacts,
            logs=result.logs,
        )

    def _plasmid_from_input(
        self, value: IndexedPlasmid | BuildRequest
    ) -> IndexedPlasmid | None:
        if isinstance(value, IndexedPlasmid):
            return value
        raw = value.constraints.get("plasmid") if value.constraints else None
        return raw if isinstance(raw, IndexedPlasmid) else None
