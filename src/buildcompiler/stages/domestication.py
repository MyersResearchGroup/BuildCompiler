"""Domestication stage orchestration."""

from __future__ import annotations

import sbol2

from buildcompiler.api.options import BuildOptions, ProtocolMode
from buildcompiler.constants import AMP
from buildcompiler.domain import (
    ApprovalStatus,
    BuildRequest,
    BuildStage,
    BuildWarning,
    MissingBuildInput,
    RequiredApproval,
    StageResult,
    StageStatus,
)
from buildcompiler.inventory import Inventory
from buildcompiler.planning.domestication import DomesticationPlanner
from buildcompiler.sbol.domestication import (
    FUSION_SITE_SEQUENCE_TO_NAME,
    ROLE_TO_FUSION_SITE_SEQUENCES,
    DomesticationJob,
    DomesticationService,
)


class DomesticationStage:
    def __init__(
        self,
        *,
        inventory: Inventory,
        domestication_planner: DomesticationPlanner | None = None,
        domestication_service: DomesticationService | None = None,
        options: BuildOptions | None = None,
    ) -> None:
        self.inventory = inventory
        self.domestication_planner = domestication_planner or DomesticationPlanner()
        self.domestication_service = domestication_service or DomesticationService()
        self.options = options or BuildOptions()

    def run(self, request: BuildRequest, *, source_document: sbol2.Document, target_document: sbol2.Document) -> StageResult:
        part_component = source_document.find(request.source_identity)
        if not isinstance(part_component, sbol2.ComponentDefinition):
            for candidate in source_document.componentDefinitions:
                if (
                    candidate.identity == request.source_identity
                    or candidate.persistentIdentity == request.source_identity
                    or candidate.displayId == request.source_identity
                    or candidate.identity.endswith(f"/{request.source_identity}/1")
                    or candidate.persistentIdentity.endswith(f"/{request.source_identity}")
                ):
                    part_component = candidate
                    break
        if not isinstance(part_component, sbol2.ComponentDefinition):
            return StageResult(
                id=f"{request.id}:{BuildStage.DOMESTICATION.value}",
                stage=BuildStage.DOMESTICATION,
                status=StageStatus.FAILED,
                request_ids=[request.id],
                logs=[f"Failed domestication: source part {request.source_identity} not found."],
            )
        try:
            plan = self.domestication_planner.plan(part_component)
        except ValueError as exc:
            return StageResult(
                id=f"{request.id}:{BuildStage.DOMESTICATION.value}",
                stage=BuildStage.DOMESTICATION,
                status=StageStatus.FAILED,
                request_ids=[request.id],
                warnings=[BuildWarning(code="domestication.invalid_input", message=str(exc), stage=BuildStage.DOMESTICATION, source_identity=request.source_identity)],
                logs=[str(exc)],
            )

        missing_inputs: list[MissingBuildInput] = []
        fusion_site_sequences = ROLE_TO_FUSION_SITE_SEQUENCES[plan.part_role]
        fusion_site_names = tuple(
            FUSION_SITE_SEQUENCE_TO_NAME[site] for site in fusion_site_sequences
        )
        backbone = self.inventory.find_backbone(
            fusion_sites=fusion_site_names,
            antibiotic=AMP,
        )
        if backbone is None:
            missing_inputs.append(MissingBuildInput(
                BuildStage.DOMESTICATION,
                request.source_identity,
                "backbone",
                None,
                "backbone",
                "fatal",
                "No compatible Ampicillin domestication backbone found in inventory "
                f"for fusion sites {fusion_site_names}.",
            ))

        restriction = self.inventory.find_restriction_enzyme(self.options.reagents.default_restriction_enzyme)
        if restriction is None:
            missing_inputs.append(MissingBuildInput(BuildStage.DOMESTICATION, request.source_identity, self.options.reagents.default_restriction_enzyme, self.options.reagents.default_restriction_enzyme, "restriction_enzyme", "fatal", "Required domestication restriction enzyme missing from inventory."))

        ligase = self.inventory.find_ligase(self.options.reagents.default_ligase)
        if ligase is None:
            missing_inputs.append(MissingBuildInput(BuildStage.DOMESTICATION, request.source_identity, self.options.reagents.default_ligase, self.options.reagents.default_ligase, "ligase", "fatal", "Required domestication ligase missing from inventory."))

        if missing_inputs:
            return StageResult(
                id=f"{request.id}:{BuildStage.DOMESTICATION.value}",
                stage=BuildStage.DOMESTICATION,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=missing_inputs,
                logs=["Domestication blocked on missing backbone/reagents."],
                protocol_artifacts={"sequence_edit_proposals": [proposal.__dict__.copy() for proposal in plan.sequence_edit_proposals]},
            )

        approvals: list[RequiredApproval] = []
        if plan.sequence_edit_proposals:
            approval_id = f"domestication-edit:{request.source_identity}"
            process_approved = "domestication_sequence_edit" in self.options.approvals.approved_processes
            id_approved = approval_id in self.options.approvals.approved_approval_ids
            allow_edits = self.options.domestication.allow_sequence_domestication_edits
            protocol_mode_active = self.options.protocol.mode != ProtocolMode.NONE
            if (not allow_edits) or (protocol_mode_active and not (process_approved or id_approved)):
                approvals.append(
                    RequiredApproval(
                        status=ApprovalStatus.REQUIRED,
                        process="domestication_sequence_edit",
                        reason="Sequence edits were proposed and require explicit human approval.",
                        metadata={
                            "approval_id": approval_id,
                            "part_identity": request.source_identity,
                            "proposals": [proposal.__dict__.copy() for proposal in plan.sequence_edit_proposals],
                        },
                    )
                )

        if approvals:
            return StageResult(
                id=f"{request.id}:{BuildStage.DOMESTICATION.value}",
                stage=BuildStage.DOMESTICATION,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                required_approvals=approvals,
                protocol_artifacts={"sequence_edit_proposals": [proposal.__dict__.copy() for proposal in plan.sequence_edit_proposals]},
                logs=["Domestication blocked pending sequence-edit approval."],
            )

        result = self.domestication_service.run(
            DomesticationJob(
                part_identity=request.source_identity,
                part_display_id=request.source_display_id,
                part_component=part_component,
                backbone=backbone,
                restriction_enzyme=restriction,
                ligase=ligase,
                source_document=source_document,
                target_document=target_document,
                part_role=plan.part_role,
                fusion_site_sequences=fusion_site_sequences,
                fusion_site_names=fusion_site_names,
                sequence_edit_proposals=plan.sequence_edit_proposals,
            )
        )
        self.inventory.add_generated_product(result.product)
        return StageResult(
            id=f"{request.id}:{BuildStage.DOMESTICATION.value}",
            stage=BuildStage.DOMESTICATION,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[result.product],
            sbol_document=result.stage_document,
            protocol_artifacts={"sequence_edit_proposals": [proposal.__dict__.copy() for proposal in plan.sequence_edit_proposals], **result.artifacts},
            logs=result.logs,
        )
