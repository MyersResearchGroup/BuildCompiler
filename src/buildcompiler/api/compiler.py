"""Public BuildCompiler API skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from buildcompiler.planning import FullBuildPlanner
from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import PartShopRepositoryClient

from .options import BuildOptions


@dataclass
class BuildCompiler:
    inventory: Any = None
    sbol_document: Any = None
    planner: Any = None
    executor: Any = None
    adapters: Any = None
    repository_client: PartShopRepositoryClient | None = None
    options: BuildOptions = field(default_factory=BuildOptions)

    @classmethod
    def from_synbiohub(
        cls,
        *,
        collections: list[str] | None = None,
        sbh_registry: str | None = None,
        repository_url: str | None = None,
        auth_token: str | None = None,
        email: str | None = None,
        password: str | None = None,
        sbol_doc: Any = None,
        options: BuildOptions | None = None,
        **kwargs: Any,
    ) -> "BuildCompiler":
        resolved_repository_url = repository_url or sbh_registry
        if auth_token and (email or password):
            raise ValueError(
                "Specify either auth_token or email/password credentials, not both."
            )
        if (email and not password) or (password and not email):
            raise ValueError("Both email and password are required for login.")

        needs_repository = bool(collections) or bool(auth_token) or bool(email) or bool(password)
        if needs_repository and not resolved_repository_url:
            raise ValueError("repository_url (or sbh_registry) is required for repository access.")

        document = sbol_doc
        if document is None:
            import sbol2

            document = sbol2.Document()

        repository_client = None
        if resolved_repository_url:
            repository_client = PartShopRepositoryClient(
                repository_url=resolved_repository_url,
                document=document,
                auth_token=auth_token,
                email=email,
                password=password,
            )

        if collections and repository_client is not None:
            for identity in collections:
                repository_client.pull_identity(identity)

        inventory = kwargs.pop("inventory", None)
        if inventory is None and collections and resolved_repository_url:
            inventory = _inventory_from_collections(
                collections=collections,
                repository_url=resolved_repository_url,
                auth_token=repository_client.auth_token if repository_client else None,
                sbol_doc=document,
            )

        return cls(
            inventory=inventory,
            sbol_document=document,
            repository_client=repository_client,
            options=options or BuildOptions(),
            **kwargs,
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
                pull_client=(
                    self.repository_client.pull_identity
                    if self.repository_client is not None
                    else None
                ),
            )
        return executor.execute(plan, options=effective_options)

    def full_build(
        self, abstract_designs: Any, options: BuildOptions | None = None
    ) -> Any:
        plan = self.plan(abstract_designs, options=options)
        return self.execute(plan, options=options)


def _inventory_from_collections(
    *,
    collections: list[str],
    repository_url: str,
    auth_token: str | None,
    sbol_doc: Any,
) -> Inventory:
    from buildcompiler.buildcompiler import BuildCompiler as LegacyBuildCompiler

    legacy = LegacyBuildCompiler(
        collections=collections,
        sbh_registry=repository_url,
        auth_token=auth_token or "",
        sbol_doc=sbol_doc,
    )

    plasmids = []
    for entry in legacy.indexed_plasmids:
        plasmids.append(
            IndexedPlasmid(
                identity=entry.plasmid_definition.identity,
                display_id=entry.plasmid_definition.displayId,
                name=entry.name,
                metadata={
                    "fusion_sites": list(entry.fusion_sites or []),
                    "antibiotic": entry.antibiotic_resistance,
                    "insert_identities": [
                        c.definition for c in entry.plasmid_definition.components
                    ],
                    "implementation_identity": (
                        entry.plasmid_implementations[0].identity
                        if entry.plasmid_implementations
                        else None
                    ),
                },
                sbol_component=entry.plasmid_definition,
            )
        )

    backbones = []
    for entry in legacy.indexed_backbones:
        backbones.append(
            IndexedBackbone(
                identity=entry.plasmid_definition.identity,
                display_id=entry.plasmid_definition.displayId,
                name=entry.name,
                metadata={
                    "fusion_sites": list(entry.fusion_sites or []),
                    "antibiotic": entry.antibiotic_resistance,
                    "implementation_identity": (
                        entry.plasmid_implementations[0].identity
                        if entry.plasmid_implementations
                        else None
                    ),
                },
                sbol_component=entry.plasmid_definition,
            )
        )

    reagents = []
    for impl in legacy.restriction_enzyme_implementations:
        built = sbol_doc.find(impl.built)
        reagents.append(
            IndexedReagent(
                identity=impl.identity,
                display_id=impl.displayId,
                name=getattr(built, "displayId", None),
                reagent_type="restriction_enzyme",
                metadata={"implementation_identity": impl.identity},
            )
        )
    for impl in legacy.ligase_implementations:
        built = sbol_doc.find(impl.built)
        reagents.append(
            IndexedReagent(
                identity=impl.identity,
                display_id=impl.displayId,
                name=getattr(built, "displayId", None),
                reagent_type="ligase",
                metadata={"implementation_identity": impl.identity},
            )
        )
    return Inventory(plasmids=plasmids, backbones=backbones, reagents=reagents)


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
    email: str | None = None,
    password: str | None = None,
    repository_url: str | None = None,
    sbol_doc: Any = None,
    **kwargs: Any,
) -> Any:
    compiler_options = options or BuildOptions()
    if (
        collections is not None
        or sbh_registry is not None
        or auth_token is not None
        or email is not None
        or password is not None
        or repository_url is not None
        or sbol_doc is not None
    ):
        compiler = BuildCompiler.from_synbiohub(
            collections=collections,
            sbh_registry=sbh_registry,
            repository_url=repository_url,
            auth_token=auth_token,
            email=email,
            password=password,
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
