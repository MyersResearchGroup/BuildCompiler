import sys

import pytest

from buildcompiler.api import BuildCompiler, BuildOptions, full_build


class FakePlanner:
    def __init__(self):
        self.calls = []

    def plan(self, abstract_designs, *, options):
        self.calls.append((abstract_designs, options))
        return {"plan": abstract_designs, "options": options}


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, plan, *, options):
        self.calls.append((plan, options))
        return {"result": plan, "options": options}


def test_import_smoke():
    assert BuildCompiler is not None
    assert full_build is not None
    assert BuildOptions is not None


def test_constructor_defaults_and_injected_dependencies():
    compiler = BuildCompiler()
    assert compiler.inventory is None
    assert compiler.sbol_document is None
    assert compiler.planner is None
    assert compiler.executor is None
    assert compiler.adapters is None
    assert isinstance(compiler.options, BuildOptions)

    inventory = object()
    sbol_document = object()
    planner = object()
    executor = object()
    adapters = object()

    injected = BuildCompiler(
        inventory=inventory,
        sbol_document=sbol_document,
        planner=planner,
        executor=executor,
        adapters=adapters,
    )

    assert injected.inventory is inventory
    assert injected.sbol_document is sbol_document
    assert injected.planner is planner
    assert injected.executor is executor
    assert injected.adapters is adapters


def test_api_import_does_not_load_optional_automation_modules():
    assert "pudupy" not in sys.modules
    assert "opentrons" not in sys.modules
    assert "SBOLInventory" not in sys.modules


def test_from_synbiohub_placeholder_without_collection_loading():
    compiler = BuildCompiler.from_synbiohub(
        collections=[],
        sbh_registry=None,
        auth_token=None,
        sbol_doc=None,
    )
    assert isinstance(compiler, BuildCompiler)


def test_from_synbiohub_raises_when_collection_loading_is_requested():
    with pytest.raises(NotImplementedError, match="collection loading/indexing"):
        BuildCompiler.from_synbiohub(collections=["https://example.org/collection"])


def test_execute_raises_clear_error_without_dependencies():
    compiler = BuildCompiler()
    compiler.plan([object()])
    with pytest.raises(ValueError, match="inventory"):
        compiler.execute({"plan": 1})


def test_plan_execute_full_build_delegate_to_injected_dependencies():
    planner = FakePlanner()
    executor = FakeExecutor()
    options = BuildOptions()
    compiler = BuildCompiler(planner=planner, executor=executor, options=options)

    plan = compiler.plan("design")
    result = compiler.execute(plan)
    full = compiler.full_build("design")

    assert plan["plan"] == "design"
    assert result["result"]["plan"] == "design"
    assert full["result"]["plan"] == "design"
    assert planner.calls
    assert executor.calls


def test_module_level_full_build_uses_lightweight_constructor_path():
    planner = FakePlanner()
    executor = FakeExecutor()

    result = full_build("design", planner=planner, executor=executor)

    assert result["result"]["plan"] == "design"


def test_module_level_full_build_uses_synbiohub_factory_path_when_requested():
    planner = FakePlanner()
    executor = FakeExecutor()

    result = full_build(
        "design",
        planner=planner,
        executor=executor,
        collections=[],
        sbh_registry=None,
        auth_token=None,
        sbol_doc=None,
    )

    assert result["result"]["plan"] == "design"
