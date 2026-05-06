from buildcompiler.api import BuildOptions
from buildcompiler.domain import BuildStatus
from buildcompiler.execution import BuildContext, FullBuildExecutor
from buildcompiler.inventory import Inventory
from buildcompiler.planning import BuildPlan
from buildcompiler.sbol import SbolResolver


class _NoopStage:
    def run(self, request, *, source_document, target_document):
        raise AssertionError("No stage runs expected")


def _executor(include_detailed_report: bool) -> FullBuildExecutor:
    options = BuildOptions()
    options.reporting.include_detailed_report = include_detailed_report
    ctx = BuildContext(
        sbol=SbolResolver(__import__("sbol2").Document()),
        inventory=Inventory(),
        build_document=__import__("sbol2").Document(),
        options=options,
    )
    return FullBuildExecutor(context=ctx, lvl2_stage=_NoopStage(), lvl1_stage=_NoopStage(), domestication_stage=_NoopStage())


def test_executor_always_returns_summary():
    result = _executor(False).execute(BuildPlan())
    assert result.summary is not None
    assert result.summary.status == BuildStatus.SUCCESS


def test_executor_report_optional_off():
    result = _executor(False).execute(BuildPlan())
    assert result.report is None


def test_executor_report_optional_on():
    result = _executor(True).execute(BuildPlan())
    assert result.report is not None
