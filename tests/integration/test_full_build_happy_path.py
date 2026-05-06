from __future__ import annotations

import sys

from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    BuildStatus,
    DesignKind,
    IndexedPlasmid,
    MaterialState,
    StageResult,
    StageStatus,
)
from buildcompiler.execution import BuildContext, FullBuildExecutor
from buildcompiler.planning import BuildPlan
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import SbolResolver


class FakeStage:
    def __init__(self, result_factory):
        self.result_factory = result_factory

    def run(self, request, *, source_document, target_document):
        return self.result_factory(request)


def _product(identity: str) -> IndexedPlasmid:
    return IndexedPlasmid(
        identity=identity,
        display_id=identity.rsplit("/", 1)[-1],
        state=MaterialState.GENERATED,
    )


def test_full_build_happy_path_offline(default_build_options, minimal_sbol_document):
    lvl2_request = BuildRequest(
        id="req-lvl2",
        stage=BuildStage.ASSEMBLY_LVL2,
        source_identity="https://example.org/module/target",
        source_display_id="target",
        source_kind=DesignKind.MODULE_DEFINITION,
    )
    ctx = BuildContext(
        sbol=SbolResolver(minimal_sbol_document),
        inventory=Inventory(),
        build_document=minimal_sbol_document,
        options=default_build_options,
    )
    executor = FullBuildExecutor(
        context=ctx,
        lvl2_stage=FakeStage(
            lambda request: StageResult(
                id="res-lvl2",
                stage=BuildStage.ASSEMBLY_LVL2,
                status=StageStatus.SUCCESS,
                request_ids=[request.id],
                products=[_product("https://example.org/plasmid/lvl2_target")],
            )
        ),
        lvl1_stage=FakeStage(lambda request: StageResult(id="unused1", stage=request.stage, status=StageStatus.BLOCKED, request_ids=[request.id])),
        domestication_stage=FakeStage(lambda request: StageResult(id="unused2", stage=request.stage, status=StageStatus.BLOCKED, request_ids=[request.id])),
    )

    result = executor.execute(BuildPlan(lvl2_requests=[lvl2_request]))

    assert result.status == BuildStatus.SUCCESS
    assert result.summary is not None
    assert result.final_products
    assert "pudupy" not in sys.modules
    assert "opentrons" not in sys.modules
    assert "SBOLInventory" not in sys.modules
