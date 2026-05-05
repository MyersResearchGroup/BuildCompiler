"""Public BuildCompiler API skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .options import BuildOptions


@dataclass
class BuildCompiler:
    """Lightweight dependency-injected compiler facade."""

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
        """Factory boundary reserved for future SynBioHub loading/indexing."""
        if collections:
            raise NotImplementedError(
                "Automatic SynBioHub collection loading/indexing is not implemented yet. "
                "Inject inventory dependencies directly for now."
            )

        return cls(
            sbol_document=sbol_doc,
            options=options or BuildOptions(),
            **kwargs,
        )

    def plan(self, abstract_designs: Any, options: BuildOptions | None = None) -> Any:
        """Plan a build request via injected planner (placeholder in skeleton)."""
        if self.planner is None:
            raise NotImplementedError(
                "Build planning is not implemented in the API skeleton. "
                "Inject a planner dependency to use BuildCompiler.plan()."
            )

        effective_options = options or self.options
        return self.planner.plan(abstract_designs, options=effective_options)

    def execute(self, plan: Any, options: BuildOptions | None = None) -> Any:
        """Execute a build plan via injected executor (placeholder in skeleton)."""
        if self.executor is None:
            raise NotImplementedError(
                "Build execution is not implemented in the API skeleton. "
                "Inject an executor dependency to use BuildCompiler.execute()."
            )

        effective_options = options or self.options
        return self.executor.execute(plan, options=effective_options)

    def full_build(self, abstract_designs: Any, options: BuildOptions | None = None) -> Any:
        """Convenience skeleton method: plan then execute."""
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
    """Module-level full-build entry point for the public API skeleton."""
    compiler_options = options or BuildOptions()

    if collections is not None or sbh_registry is not None or auth_token is not None or sbol_doc is not None:
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
            planner=planner,
            executor=executor,
            adapters=adapters,
            options=compiler_options,
            **kwargs,
        )

    return compiler.full_build(abstract_designs, options=compiler_options)
