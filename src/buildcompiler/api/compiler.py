"""Public BuildCompiler API skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import Any

import sbol2

from buildcompiler.domain import BuildRequest, BuildStage, DesignKind, IndexedPlasmid
from buildcompiler.errors import SynBioHubConfigurationError
from buildcompiler.inventory import Inventory, index_collections
from buildcompiler.planning import FullBuildPlanner
from buildcompiler.planning.validation import ordered_lvl1_parts
from buildcompiler.sbol import PullPolicy, SbolResolver, load_synbiohub_collections
from buildcompiler.stages import (
    AssemblyLvl1Stage,
    AssemblyLvl2Stage,
    DomesticationStage,
    TransformationStage,
)

from .options import BuildOptions


@dataclass
class BuildCompiler:
    inventory: Any = None
    sbol_document: Any = None
    planner: Any = None
    executor: Any = None
    adapters: Any = None
    resolver: SbolResolver | None = None
    options: BuildOptions = field(default_factory=BuildOptions)

    @classmethod
    def from_synbiohub(
        cls,
        *,
        collections: list[str] | None = None,
        sbh_registry: str | None = None,
        auth_token: str | None = None,
        sbol_doc: sbol2.Document | None = None,
        options: BuildOptions | None = None,
    ) -> "BuildCompiler":
        """Create a compiler from token-authenticated SynBioHub collections.

        The token is assigned only to a transient ``sbol2.PartShop`` while the
        collections and their references are downloaded. It is neither retained
        by the compiler nor included in any returned domain object.
        """

        if collections is not None and not isinstance(collections, list):
            raise SynBioHubConfigurationError(
                "collections must be a list of SBOL identities."
            )
        collection_ids = list(collections or [])
        if any(
            not isinstance(identity, str) or not identity for identity in collection_ids
        ):
            raise SynBioHubConfigurationError(
                "collections must contain only nonempty SBOL identity strings."
            )
        if collection_ids and not sbh_registry:
            raise SynBioHubConfigurationError(
                "sbh_registry is required when SynBioHub collections are supplied."
            )
        if collection_ids and not auth_token:
            raise SynBioHubConfigurationError(
                "auth_token is required when SynBioHub collections are supplied."
            )

        document = sbol_doc or sbol2.Document()
        if collection_ids:
            load_synbiohub_collections(
                collection_ids,
                sbh_registry=sbh_registry or "",
                auth_token=auth_token or "",
                document=document,
            )
        resolver = SbolResolver(document, pull_policy=PullPolicy.NEVER)
        inventory = index_collections(
            document,
            collection_identities=collection_ids,
            resolver=resolver,
        )
        compiler_options = options or BuildOptions()
        return cls(
            inventory=inventory,
            sbol_document=document,
            planner=FullBuildPlanner(options=compiler_options, resolver=resolver),
            resolver=resolver,
            options=compiler_options,
        )

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
                resolver=self.resolver,
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
        )
        compiler.inventory = inventory or compiler.inventory
        compiler.planner = planner or compiler.planner
        compiler.executor = executor or compiler.executor
        compiler.adapters = adapters
        for name, value in kwargs.items():
            if name in {"username", "password"}:
                raise TypeError(f"full_build() does not accept {name}")
            setattr(compiler, name, value)
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


def domestication(
    part: sbol2.ComponentDefinition | str | Sequence[sbol2.ComponentDefinition | str],
    *,
    inventory: Inventory,
    source_document: sbol2.Document,
    target_document: sbol2.Document | None = None,
    options: BuildOptions | None = None,
) -> Any:
    """Run independent domestication stage(s) and return StageResult object(s)."""

    if isinstance(part, Sequence) and not isinstance(part, (str, bytes)):
        return [
            domestication(
                item,
                inventory=inventory,
                source_document=source_document,
                target_document=target_document,
                options=options,
            )
            for item in part
        ]

    component = _resolve_component(part, source_document)
    request = BuildRequest(
        id=f"{BuildStage.DOMESTICATION.value}:{component.displayId or component.identity}",
        stage=BuildStage.DOMESTICATION,
        source_identity=component.identity,
        source_display_id=component.displayId,
        source_kind=DesignKind.COMPONENT_DEFINITION,
    )
    return DomesticationStage(
        inventory=inventory, options=options or BuildOptions()
    ).run(
        request,
        source_document=source_document,
        target_document=target_document or source_document,
    )


def assembly_lvl1(
    design: sbol2.ComponentDefinition | str,
    *,
    inventory: Inventory,
    source_document: sbol2.Document,
    target_document: sbol2.Document | None = None,
    options: BuildOptions | None = None,
    constraints: dict[str, Any] | None = None,
) -> Any:
    """Run one independent assembly level-1 stage and return a StageResult."""

    component = _resolve_component(design, source_document)
    active_constraints = dict(constraints or {})
    if (
        "ordered_part_identities" not in active_constraints
        and "part_order" not in active_constraints
    ):
        ordered, warnings = ordered_lvl1_parts(component)
        active_constraints["ordered_part_identities"] = ordered or [
            child.definition for child in component.components
        ]
        if warnings:
            active_constraints["ordering_warnings"] = [
                warning.__dict__.copy() for warning in warnings
            ]
    active_constraints.setdefault("product_identity", component.identity)
    active_constraints.setdefault("product_display_id", component.displayId)
    request = BuildRequest(
        id=f"{BuildStage.ASSEMBLY_LVL1.value}:{component.displayId or component.identity}",
        stage=BuildStage.ASSEMBLY_LVL1,
        source_identity=component.identity,
        source_display_id=component.displayId,
        source_kind=DesignKind.COMPONENT_DEFINITION,
        constraints=active_constraints,
    )
    return AssemblyLvl1Stage(
        inventory=inventory, options=options or BuildOptions()
    ).run(
        request,
        source_document=source_document,
        target_document=target_document or source_document,
    )


def assembly_lvl2(
    design: sbol2.ModuleDefinition | str,
    *,
    inventory: Inventory,
    source_document: sbol2.Document,
    target_document: sbol2.Document | None = None,
    options: BuildOptions | None = None,
    constraints: dict[str, Any] | None = None,
) -> Any:
    """Run one independent assembly level-2 stage and return a StageResult."""

    module = _resolve_module(design, source_document)
    request = BuildRequest(
        id=f"{BuildStage.ASSEMBLY_LVL2.value}:{module.displayId or module.identity}",
        stage=BuildStage.ASSEMBLY_LVL2,
        source_identity=module.identity,
        source_display_id=module.displayId,
        source_kind=DesignKind.MODULE_DEFINITION,
        constraints=dict(constraints or {}),
    )
    return AssemblyLvl2Stage(
        inventory=inventory, options=options or BuildOptions()
    ).run(
        request,
        source_document=source_document,
        target_document=target_document or source_document,
    )


def transformation(
    plasmid: IndexedPlasmid,
    *,
    source_document: sbol2.Document,
    target_document: sbol2.Document | None = None,
    options: BuildOptions | None = None,
    chassis_identity: str | None = None,
    chassis_display_id: str | None = None,
) -> Any:
    """Run one independent transformation stage and return a StageResult."""

    active_options = options or BuildOptions()
    if chassis_identity is not None:
        active_options.transformation.chassis_identity = chassis_identity
    if chassis_display_id is not None:
        active_options.transformation.chassis_display_id = chassis_display_id
    return TransformationStage(options=active_options).run(
        plasmid,
        source_document=source_document,
        target_document=target_document or source_document,
    )


def _resolve_component(
    value: sbol2.ComponentDefinition | str, document: sbol2.Document
) -> sbol2.ComponentDefinition:
    component = (
        value if isinstance(value, sbol2.ComponentDefinition) else document.find(value)
    )
    if not isinstance(component, sbol2.ComponentDefinition):
        raise ValueError(f"ComponentDefinition not found: {value}")
    return component


def _resolve_module(
    value: sbol2.ModuleDefinition | str, document: sbol2.Document
) -> sbol2.ModuleDefinition:
    module = (
        value if isinstance(value, sbol2.ModuleDefinition) else document.find(value)
    )
    if not isinstance(module, sbol2.ModuleDefinition):
        raise ValueError(f"ModuleDefinition not found: {value}")
    return module
