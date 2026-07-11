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


def test_lvl2_promoted_lvl1_request_inherits_region_part_identities():
    captured = {}
    missing_region = "https://x/regions/tu2"
    part_order = [
        "https://x/parts/promoter",
        "https://x/parts/rbs",
        "https://x/parts/cds",
        "https://x/parts/terminator",
    ]
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
                        missing_region,
                        "tu2",
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
        captured["request"] = request
        return StageResult(
            id="r1",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[plasmid(missing_region)],
        )

    doc = __import__("sbol2").Document()
    ctx = BuildContext(
        sbol=SbolResolver(doc),
        inventory=Inventory(),
        build_document=doc,
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
                constraints={"lvl1_region_part_identities": {missing_region: part_order}},
            )
        ]
    )

    result = ex.execute(plan)

    assert result.status == BuildStatus.SUCCESS
    promoted = captured["request"]
    assert promoted.source_identity == missing_region
    assert promoted.constraints["ordered_part_identities"] == part_order
    assert promoted.constraints["product_identity"] == missing_region
    assert promoted.constraints["product_display_id"] == "tu2"


def test_nested_lvl2_lvl1_domestication_promotion_stack():
    calls = {"lvl2": 0, "lvl1": 0}
    missing_region = "https://x/regions/tu2"
    missing_part = "https://x/parts/promoter"
    stage_path = []

    def lvl2(request):
        calls["lvl2"] += 1
        if calls["lvl2"] < 3:
            result = StageResult(
                id=f"lvl2-{calls['lvl2']}",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=[
                    MissingBuildInput(
                        BuildStage.ASSEMBLY_LVL2,
                        request.source_identity,
                        missing_region,
                        "tu2",
                        "engineered_region",
                        BuildStage.ASSEMBLY_LVL1,
                        "missing region",
                    )
                ],
            )
        else:
            result = StageResult(
                id="lvl2-success",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.SUCCESS,
                request_ids=[request.id],
                products=[plasmid("https://x/lvl2")],
            )
        stage_path.append(f"{result.stage.value}:{result.status.value}")
        return result

    def lvl1(request):
        calls["lvl1"] += 1
        if calls["lvl1"] == 1:
            result = StageResult(
                id="lvl1-blocked",
                stage=BuildStage.ASSEMBLY_LVL1,
                status=StageStatus.BLOCKED,
                request_ids=[request.id],
                missing_inputs=[
                    MissingBuildInput(
                        BuildStage.ASSEMBLY_LVL1,
                        request.source_identity,
                        missing_part,
                        "promoter",
                        "promoter",
                        BuildStage.DOMESTICATION,
                        "missing part",
                    )
                ],
            )
        else:
            result = StageResult(
                id="lvl1-success",
                stage=BuildStage.ASSEMBLY_LVL1,
                status=StageStatus.SUCCESS,
                request_ids=[request.id],
                products=[plasmid(missing_region)],
            )
        stage_path.append(f"{result.stage.value}:{result.status.value}")
        return result

    def domestication(request):
        result = StageResult(
            id="dom-success",
            stage=BuildStage.DOMESTICATION,
            status=StageStatus.SUCCESS,
            request_ids=[request.id],
            products=[plasmid(missing_part)],
        )
        stage_path.append(f"{result.stage.value}:{result.status.value}")
        return result

    doc = __import__("sbol2").Document()
    ctx = BuildContext(
        sbol=SbolResolver(doc),
        inventory=Inventory(),
        build_document=doc,
        options=BuildOptions(),
    )
    ex = FullBuildExecutor(
        context=ctx,
        lvl2_stage=FakeStage(lvl2),
        lvl1_stage=FakeStage(lvl1),
        domestication_stage=FakeStage(domestication),
    )
    plan = BuildPlan(
        lvl2_requests=[
            BuildRequest(
                id="req-l2",
                stage=BuildStage.ASSEMBLY_LVL2,
                source_identity="https://x/mod",
                source_display_id="mod",
                source_kind=DesignKind.MODULE_DEFINITION,
                constraints={
                    "lvl1_region_part_identities": {
                        missing_region: [
                            missing_part,
                            "https://x/parts/rbs",
                            "https://x/parts/cds",
                            "https://x/parts/terminator",
                        ]
                    }
                },
            )
        ]
    )

    result = ex.execute(plan)

    assert result.status == BuildStatus.SUCCESS
    assert stage_path == [
        "assembly_lvl2:blocked",
        "assembly_lvl1:blocked",
        "domestication:success",
        "assembly_lvl2:blocked",
        "assembly_lvl1:success",
        "assembly_lvl2:success",
    ]
    assert [product.identity for product in result.final_products] == [
        missing_part,
        missing_region,
        "https://x/lvl2",
    ]


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
