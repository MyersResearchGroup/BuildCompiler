import pytest

from buildcompiler.domain import (
    ApprovalStatus,
    BuildStage,
    BuildStatus,
    BuildWarning,
    FullBuildResult,
    IndexedPlasmid,
    MaterialState,
    MissingBuildInput,
    RequiredApproval,
    StageResult,
    StageStatus,
)


@pytest.fixture
def fake_full_build_result():
    def _make(
        status=BuildStatus.PARTIAL_SUCCESS, with_duplicates=False, with_routes=False
    ):
        p1 = IndexedPlasmid(
            identity="https://x/plasmidA",
            display_id="plasmidA",
            state=MaterialState.GENERATED,
        )
        products = [p1, p1] if with_duplicates else [p1]
        missing = MissingBuildInput(
            source_stage=BuildStage.ASSEMBLY_LVL2,
            source_design_identity="https://x/mod",
            missing_identity="https://x/regionA",
            missing_display_id="regionA",
            missing_kind="engineered_region",
            required_stage=BuildStage.ASSEMBLY_LVL1,
            reason="missing region",
        )
        approval = RequiredApproval(
            status=ApprovalStatus.REQUIRED, process="biosafety", reason="needed"
        )
        warning = BuildWarning(
            code="w1", message="warn", stage=BuildStage.ASSEMBLY_LVL2
        )
        artifacts = {}
        if with_routes:
            artifacts = {
                "selected_route": {"id": "route-1"},
                "rejected_routes": [{"id": "route-2"}],
            }
        stage_result = StageResult(
            id="stage-1",
            stage=BuildStage.ASSEMBLY_LVL2,
            status=StageStatus.BLOCKED,
            request_ids=["req-1"],
            products=products,
            missing_inputs=[missing],
            required_approvals=[approval],
            warnings=[warning],
            protocol_artifacts=artifacts,
            logs=["log1"],
        )
        return FullBuildResult(
            status=status,
            plan=object(),
            build_document=None,
            stage_results=[stage_result],
            graph=None,
            final_products=products,
            missing_inputs=[missing, missing] if with_duplicates else [missing],
            required_approvals=[approval],
            warnings=[warning],
            summary=None,
            report=None,
        )

    return _make
