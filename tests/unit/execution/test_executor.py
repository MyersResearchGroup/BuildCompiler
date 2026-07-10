from buildcompiler.api import BuildOptions
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
from buildcompiler.inventory import Inventory
from buildcompiler.planning import BuildPlan
from buildcompiler.sbol import SbolResolver


class FakeStage:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    def run(self, request, *, source_document, target_document):
        self.calls.append(request.id)
        return self.fn(request)


def plasmid(identity):
    return IndexedPlasmid(
        identity=identity,
        display_id=identity.split("/")[-1],
        state=MaterialState.GENERATED,
    )


def test_imports_smoke():
    assert BuildContext
    assert FullBuildExecutor


def test_promote_and_retry_flow():
    lvl2_count = {"n": 0}

    def lvl2(request):
        lvl2_count["n"] += 1
        if lvl2_count["n"] == 1:
            return StageResult(
                id="r",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=[
                    MissingBuildInput(
                        BuildStage.ASSEMBLY_LVL2,
                        request.source_identity,
                        "https://x/region",
                        "region",
                        "engineered_region",
                        BuildStage.ASSEMBLY_LVL1,
                        "missing",
                    )
                ],
            )
        return StageResult(
            id="r",
            stage=BuildStage.ASSEMBLY_LVL2,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[plasmid("https://x/lvl2")],
        )

    def lvl1(request):
        return StageResult(
            id="r1",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[plasmid("https://x/region")],
        )

    ctx = BuildContext(
        sbol=SbolResolver(__import__("sbol2").Document()),
        inventory=Inventory(),
        build_document=__import__("sbol2").Document(),
        options=BuildOptions(),
    )
    ex = FullBuildExecutor(
        context=ctx,
        lvl2_stage=FakeStage(lvl2),
        lvl1_stage=FakeStage(lvl1),
        domestication_stage=FakeStage(
            lambda r: StageResult(
                id="d",
                stage=BuildStage.DOMESTICATION,
                status=StageStatus.BLOCKED,
                request_ids=[r.id],
            )
        ),
    )
    plan = BuildPlan(
        lvl2_requests=[
            BuildRequest(
                id="req-l2",
                stage=BuildStage.ASSEMBLY_LVL2,
                source_identity="https://x/mod",
                source_display_id="mod",
                source_kind=DesignKind.MODULE_DEFINITION,
            )
        ]
    )
    result = ex.execute(plan)
    assert result.status == BuildStatus.SUCCESS
    assert any(r.stage == BuildStage.ASSEMBLY_LVL1 for r in result.stage_results)
    assert len(result.final_products) == 2


def test_max_iteration_stops():
    options = BuildOptions()
    options.execution.max_iterations = 2
    blocked = FakeStage(
        lambda r: StageResult(
            id="b", stage=r.stage, status=StageStatus.BLOCKED, request_ids=[r.id]
        )
    )
    ctx = BuildContext(
        sbol=SbolResolver(__import__("sbol2").Document()),
        inventory=Inventory(),
        build_document=__import__("sbol2").Document(),
        options=options,
    )
    ex = FullBuildExecutor(
        context=ctx, lvl2_stage=blocked, lvl1_stage=blocked, domestication_stage=blocked
    )
    plan = BuildPlan(
        lvl2_requests=[
            BuildRequest(
                id="req",
                stage=BuildStage.ASSEMBLY_LVL2,
                source_identity="x",
                source_display_id="x",
                source_kind=DesignKind.MODULE_DEFINITION,
            )
        ]
    )
    result = ex.execute(plan)
    assert result.status == BuildStatus.FAILED


def test_executor_chains_transformation_when_enabled():
    options = BuildOptions()
    options.transformation.enabled = True
    options.transformation.chassis_identity = "dh5alpha"
    options.transformation.chassis_display_id = "dh5alpha"
    assembly = FakeStage(
        lambda r: StageResult(
            id="asm",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            request_ids=[r.id],
            products=[plasmid("https://x/plasmid/a")],
        )
    )
    blocked = FakeStage(
        lambda r: StageResult(
            id="blocked",
            stage=r.stage,
            status=StageStatus.BLOCKED,
            request_ids=[r.id],
        )
    )
    doc = __import__("sbol2").Document()
    ctx = BuildContext(
        sbol=SbolResolver(doc),
        inventory=Inventory(),
        build_document=doc,
        options=options,
    )
    ex = FullBuildExecutor(
        context=ctx,
        lvl2_stage=blocked,
        lvl1_stage=assembly,
        domestication_stage=blocked,
    )
    plan = BuildPlan(
        lvl1_requests=[
            BuildRequest(
                id="req-l1",
                stage=BuildStage.ASSEMBLY_LVL1,
                source_identity="https://x/design",
                source_display_id="design",
                source_kind=DesignKind.COMPONENT_DEFINITION,
            )
        ]
    )

    result = ex.execute(plan)

    assert result.status == BuildStatus.SUCCESS
    assert any(sr.stage == BuildStage.TRANSFORMATION for sr in result.stage_results)
    assert any(
        product.metadata.get("source_stage") == "transformation"
        for product in result.final_products
    )
