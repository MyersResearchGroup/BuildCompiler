"""Public BuildCompiler API skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from buildcompiler.planning import FullBuildPlanner

from .options import BuildOptions


@dataclass
class BuildCompiler:
    inventory: Any = None
    sbol_document: Any = None
    planner: Any = None
    executor: Any = None
    adapters: Any = None
    options: BuildOptions = field(default_factory=BuildOptions)

    @classmethod
    def from_synbiohub(
        cls,
        *,
        collections: list[str] | None = None,
        sbh_registry: str | None = None,
        auth_token: str | None = None,
        sbol_doc: Any = None,
        options: BuildOptions | None = None,
        **kwargs: Any,
    ) -> "BuildCompiler":
        if collections:
            raise NotImplementedError(
                "Automatic SynBioHub collection loading/indexing is not implemented yet. Inject inventory dependencies directly for now."
            )
        return cls(sbol_document=sbol_doc, options=options or BuildOptions(), **kwargs)

    def plan(self, abstract_designs: Any, options: BuildOptions | None = None) -> Any:
        effective_options = options or self.options
        planner = self.planner or FullBuildPlanner(options=effective_options)
        return planner.plan(abstract_designs, options=effective_options)

    def execute(self, plan: Any, options: BuildOptions | None = None) -> Any:
        effective_options = options or self.options
        executor = self.executor
        if executor is None:
            if self.inventory is None:
                raise ValueError(
                    "BuildCompiler.execute requires an inventory when no executor is injected."
                )
            if self.sbol_document is None:
                raise ValueError(
                    "BuildCompiler.execute requires an sbol_document when no executor is injected."
                )
            from buildcompiler.execution import FullBuildExecutor

            executor = FullBuildExecutor.from_dependencies(
                inventory=self.inventory,
                sbol_document=self.sbol_document,
                options=effective_options,
                adapters=self.adapters,
            )
        return executor.execute(plan, options=effective_options)

    def full_build(
        self, abstract_designs: Any, options: BuildOptions | None = None
    ) -> Any:
        plan = self.plan(abstract_designs, options=options)
        return self.execute(plan, options=options)


def full_build(
    abstract_designs: Any,
    *,
    inventory: Any = None,
    sbol_document: Any = None,
    planner: Any = None,
    executor: Any = None,
    adapters: Any = None,
    options: BuildOptions | None = None,
    collections: list[str] | None = None,
    sbh_registry: str | None = None,
    auth_token: str | None = None,
    sbol_doc: Any = None,
    **kwargs: Any,
) -> Any:
    compiler_options = options or BuildOptions()
    if (
        collections is not None
        or sbh_registry is not None
        or auth_token is not None
        or sbol_doc is not None
    ):
        compiler = BuildCompiler.from_synbiohub(
            collections=collections,
            sbh_registry=sbh_registry,
            auth_token=auth_token,
            sbol_doc=sbol_doc,
            options=compiler_options,
            inventory=inventory,
            planner=planner,
            executor=executor,
            adapters=adapters,
            **kwargs,
        )
    else:
        compiler = BuildCompiler(
            inventory=inventory,
            sbol_document=sbol_document,
            planner=planner,
            executor=executor,
            adapters=adapters,
            options=compiler_options,
            **kwargs,
        )
    return compiler.full_build(abstract_designs, options=compiler_options)
