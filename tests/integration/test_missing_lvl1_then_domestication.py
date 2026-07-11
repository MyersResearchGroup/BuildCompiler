from __future__ import annotations

from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    BuildStatus,
    DesignKind,
    IndexedPlasmid,
    MaterialState,
    MissingBuildInput,
    StageResult,
    StageStatus,
)
from buildcompiler.execution import BuildContext, FullBuildExecutor
from buildcompiler.planning import BuildPlan
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import SbolResolver


class FakeStage:
    def __init__(self, fn):
        self.fn = fn

    def run(self, request, *, source_document, target_document):
        return self.fn(request)


def plasmid(identity: str) -> IndexedPlasmid:
    return IndexedPlasmid(
        identity=identity,
        display_id=identity.rsplit("/", 1)[-1],
        state=MaterialState.GENERATED,
    )


def test_missing_lvl1_promotes_domestication_and_retries(
    default_build_options, minimal_sbol_document
):
    lvl1_attempts = {"n": 0}

    def lvl1_fn(request):
        lvl1_attempts["n"] += 1
        if lvl1_attempts["n"] == 1:
            return StageResult(
                id="lvl1-blocked",
                stage=BuildStage.ASSEMBLY_LVL1,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=[
                    MissingBuildInput(
                        source_stage=BuildStage.ASSEMBLY_LVL1,
                        source_design_identity=request.source_identity,
                        missing_identity="https://example.org/part/promoterA",
                        missing_display_id="promoterA",
                        missing_kind="promoter",
                        required_stage=BuildStage.DOMESTICATION,
                        reason="missing part",
                    )
                ],
            )
        return StageResult(
            id="lvl1-success",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[plasmid("https://example.org/plasmid/lvl1_after_dom")],
        )

    def domestication_fn(request):
        return StageResult(
            id="dom-success",
            stage=BuildStage.DOMESTICATION,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[plasmid("https://example.org/plasmid/dom_promoterA")],
        )

    context = BuildContext(
        sbol=SbolResolver(minimal_sbol_document),
        inventory=Inventory(),
        build_document=minimal_sbol_document,
        options=default_build_options,
    )
    executor = FullBuildExecutor(
        context=context,
        lvl2_stage=FakeStage(
            lambda request: StageResult(
                id="unused-lvl2",
                stage=request.stage,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
            )
        ),
        lvl1_stage=FakeStage(lvl1_fn),
        domestication_stage=FakeStage(domestication_fn),
    )

    plan = BuildPlan(
        lvl1_requests=[
            BuildRequest(
                id="req-lvl1",
                stage=BuildStage.ASSEMBLY_LVL1,
                source_identity="https://example.org/engineered/region1",
                source_display_id="region1",
                source_kind=DesignKind.COMPONENT_DEFINITION,
            )
        ]
    )

    result = executor.execute(plan)

    assert lvl1_attempts["n"] >= 2
    assert any(sr.stage == BuildStage.DOMESTICATION for sr in result.stage_results)
    assert any(p.display_id == "dom_promoterA" for p in result.final_products)
    assert result.status in {BuildStatus.SUCCESS, BuildStatus.PARTIAL_SUCCESS}
