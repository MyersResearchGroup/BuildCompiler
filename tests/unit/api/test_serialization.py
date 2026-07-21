import json
from pathlib import Path

from buildcompiler.api import (
    deserialize_build_plan,
    dumps_json_dto,
    serialize_build_plan,
    serialize_build_result,
    serialize_reagent,
    serialize_stage_result,
)
from buildcompiler.domain import (
    ApprovalStatus,
    BuildRequest,
    BuildStage,
    BuildStatus,
    BuildWarning,
    DesignKind,
    FullBuildResult,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
    MissingBuildInput,
    RequiredApproval,
    StageResult,
    StageStatus,
)
from buildcompiler.planning import BuildPlan, UnsupportedPlanningRecord
from buildcompiler.reporting import build_graph, build_report, build_summary


def _plan():
    request = BuildRequest(
        id="req-1",
        stage=BuildStage.ASSEMBLY_LVL1,
        source_identity="https://example.org/design",
        source_display_id="design",
        source_kind=DesignKind.COMPONENT_DEFINITION,
        constraints={
            "output": Path("artifacts/plan.json"),
            "stages": {BuildStage.DOMESTICATION, BuildStage.ASSEMBLY_LVL1},
        },
    )
    return BuildPlan(
        lvl1_requests=[request],
        unsupported=[
            UnsupportedPlanningRecord(
                source_identity="https://example.org/unsupported",
                source_display_id=None,
                source_kind=DesignKind.UNSUPPORTED,
                reason="unsupported",
            )
        ],
        warnings=[BuildWarning("planning_warning", "Review the design")],
    )


def _result():
    plan = _plan()
    product = IndexedPlasmid(
        identity="https://example.org/product",
        display_id="product",
        state=MaterialState.GENERATED,
        roles=["role-b", "role-a"],
        metadata={"paths": {Path("b.json"), Path("a.json")}},
        sbol_component=object(),
    )
    missing = MissingBuildInput(
        source_stage=BuildStage.ASSEMBLY_LVL1,
        source_design_identity="https://example.org/design",
        missing_identity="https://example.org/backbone",
        missing_display_id="backbone",
        missing_kind="backbone",
        required_stage="fatal",
        reason="No compatible backbone",
    )
    approval = RequiredApproval(
        ApprovalStatus.REQUIRED,
        "sequence_edit",
        "Approval required",
        metadata={"auth_token": "never-serialize-this"},
    )
    warning = BuildWarning(
        "warning", "Review", BuildStage.ASSEMBLY_LVL1, metadata={"z": 2, "a": 1}
    )
    stage = StageResult(
        id="stage-1",
        stage=BuildStage.ASSEMBLY_LVL1,
        status=StageStatus.BLOCKED,
        request_ids=["req-1"],
        products=[product],
        missing_inputs=[missing],
        required_approvals=[approval],
        warnings=[warning],
        sbol_document=object(),
        json_intermediate={"reagents": {"BsaI", "T4 ligase"}},
        protocol_artifacts={"protocol": Path("protocol.py")},
    )
    result = FullBuildResult(
        status=BuildStatus.PARTIAL_SUCCESS,
        plan=plan,
        build_document=object(),
        stage_results=[stage],
        final_products=[product],
        missing_inputs=[missing],
        required_approvals=[approval],
        warnings=[warning],
    )
    result.graph = build_graph(result)
    result.summary = build_summary(result)
    result.report = build_report(result, graph=result.graph)
    return result


def test_build_plan_serialization_is_deterministic_json_and_round_trips():
    plan = _plan()

    first = serialize_build_plan(plan)
    second = serialize_build_plan(plan)
    encoded = json.dumps(first, allow_nan=False)
    restored = deserialize_build_plan(json.loads(encoded))

    assert first == second
    assert serialize_build_plan(restored) == first
    assert first["lvl1_requests"][0]["constraints"]["output"] == "artifacts/plan.json"
    assert first["lvl1_requests"][0]["constraints"]["stages"] == [
        "assembly_lvl1",
        "domestication",
    ]


def test_representative_stage_and_build_results_are_json_safe_and_redacted():
    result = _result()

    stage_dto = serialize_stage_result(result.stage_results[0])
    result_dto = serialize_build_result(result)
    encoded = dumps_json_dto(result)

    json.dumps(stage_dto, allow_nan=False)
    json.dumps(result_dto, allow_nan=False)
    assert result_dto == serialize_build_result(result)
    assert "never-serialize-this" not in encoded
    assert "auth_token" not in encoded
    assert "sbol_component" not in encoded
    assert "sbol_document" not in encoded
    assert "build_document" not in encoded
    assert "object at 0x" not in encoded
    assert result_dto["summary"]["status"] == "partial_success"
    assert result_dto["report"]["status"] == "partial_success"
    assert result_dto["graph"]["nodes"]


def test_reagent_serialization_uses_stable_fields_and_omits_credentials():
    reagent = IndexedReagent(
        identity="https://example.org/bsai",
        display_id="bsai",
        name="BsaI",
        reagent_type="restriction_enzyme",
        metadata={"token": "secret", "vendor": "NEB"},
    )

    assert serialize_reagent(reagent) == {
        "display_id": "bsai",
        "identity": "https://example.org/bsai",
        "kind": "reagent",
        "metadata": {"vendor": "NEB"},
        "name": "BsaI",
        "reagent_type": "restriction_enzyme",
    }
