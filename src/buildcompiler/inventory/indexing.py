"""Index SBOL inventory documents into normalized clean-domain records."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

import sbol2

from buildcompiler.constants import (
    ANTIBIOTIC_MAP,
    ANTIBIOTIC_RESISTANCE,
    ENGINEERED_INSERT,
    ENGINEERED_PLASMID,
    ENGINEERED_REGION,
    FUSION_SITES,
    LIGASE,
    LVL2_FUSION_SITE_ORDER,
    PART_ROLES,
    PLASMID_CLONING_VECTOR,
    PLASMID_VECTOR,
    RESTRICTION_ENZYME,
    RESTRICTION_ENZYME_ASSEMBLY_SCAR,
)
from buildcompiler.domain import (
    BuildStage,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
)
from buildcompiler.sbol.resolver import SbolResolver

from .inventory import Inventory


def index_collections(
    document: sbol2.Document,
    *,
    collection_identities: Iterable[str] = (),
    resolver: SbolResolver | None = None,
) -> Inventory:
    """Build a deterministic inventory from downloaded SBOL collection contents.

    Only implemented materials are treated as physical inventory. Collection
    identities are recorded as provenance and are not dereferenced here; remote
    hydration belongs to the SynBioHub boundary.
    """

    active_resolver = resolver or SbolResolver(document)
    provenance = sorted(set(collection_identities))
    implementations_by_built: dict[str, list[sbol2.Implementation]] = defaultdict(list)
    for implementation in sorted(
        document.implementations, key=lambda item: item.identity
    ):
        built_identity = str(implementation.built)
        if built_identity:
            implementations_by_built[built_identity].append(implementation)

    plasmids: list[IndexedPlasmid] = []
    backbones: list[IndexedBackbone] = []
    reagents: list[IndexedReagent] = []
    for built_identity in sorted(implementations_by_built):
        built = _resolve_built(active_resolver, document, built_identity)
        implementations = implementations_by_built[built_identity]
        implementation_ids = sorted(item.identity for item in implementations)
        common_metadata = {
            "collection_identities": provenance,
            "implementation_identities": implementation_ids,
        }

        if not isinstance(built, sbol2.ComponentDefinition):
            continue
        roles = sorted(str(role) for role in built.roles)
        if sbol2.BIOPAX_PROTEIN in built.types:
            reagent_type = _reagent_type(roles)
            if reagent_type:
                reagents.append(
                    IndexedReagent(
                        identity=built.identity,
                        display_id=built.displayId or None,
                        name=built.name or built.displayId or None,
                        reagent_type=reagent_type,
                        metadata=common_metadata,
                    )
                )
            continue

        if not (
            {ENGINEERED_PLASMID, PLASMID_CLONING_VECTOR, PLASMID_VECTOR} & set(roles)
        ):
            continue

        fusion_sites = _fusion_sites(built, document)
        antibiotic = _antibiotic(built, document)
        material_metadata = common_metadata | {
            "antibiotic": antibiotic,
            "fusion_sites": fusion_sites,
        }
        if PLASMID_CLONING_VECTOR in roles or (
            PLASMID_VECTOR in roles and ENGINEERED_PLASMID not in roles
        ):
            material_metadata["stage"] = _backbone_stage(fusion_sites).value
            backbones.append(
                IndexedBackbone(
                    identity=built.identity,
                    display_id=built.displayId or None,
                    name=built.name or None,
                    metadata=material_metadata,
                    sbol_component=built,
                )
            )
        else:
            material_metadata["insert_identities"] = _insert_identities(built, document)
            plasmids.append(
                IndexedPlasmid(
                    identity=built.identity,
                    display_id=built.displayId or None,
                    name=built.name or None,
                    state=MaterialState.ASSEMBLED,
                    roles=roles,
                    metadata=material_metadata,
                    sbol_component=built,
                )
            )

    return Inventory(plasmids=plasmids, backbones=backbones, reagents=reagents)


def _resolve_built(
    resolver: SbolResolver, document: sbol2.Document, identity: str
) -> object | None:
    existing = document.find(identity)
    if existing is not None:
        return existing
    for getter in (resolver.get_component, resolver.get_module):
        try:
            return getter(identity)
        except LookupError:
            continue
    return None


def _reagent_type(roles: list[str]) -> str | None:
    if RESTRICTION_ENZYME in roles:
        return "restriction_enzyme"
    if LIGASE in roles:
        return "ligase"
    return None


def _children(
    component: sbol2.ComponentDefinition, document: sbol2.Document
) -> list[sbol2.ComponentDefinition]:
    children: list[sbol2.ComponentDefinition] = []
    for child in component.components:
        definition = document.find(child.definition)
        if isinstance(definition, sbol2.ComponentDefinition):
            children.append(definition)
    return children


def _walk_components(
    component: sbol2.ComponentDefinition, document: sbol2.Document
) -> Iterable[sbol2.ComponentDefinition]:
    seen: set[str] = set()
    pending = [component]
    while pending:
        current = pending.pop(0)
        if current.identity in seen:
            continue
        seen.add(current.identity)
        yield current
        pending.extend(_children(current, document))


def _sequence(
    component: sbol2.ComponentDefinition, document: sbol2.Document
) -> str | None:
    if not component.sequences:
        return None
    sequence = document.find(component.sequences[0])
    if isinstance(sequence, sbol2.Sequence):
        return sequence.elements.upper()
    return None


def _fusion_sites(
    component: sbol2.ComponentDefinition, document: sbol2.Document
) -> tuple[str, ...]:
    sequence_to_name = {value: key for key, value in FUSION_SITES.items()}
    sites: list[str] = []
    for child in _walk_components(component, document):
        if RESTRICTION_ENZYME_ASSEMBLY_SCAR not in child.roles:
            continue
        sequence = _sequence(child, document)
        if sequence in sequence_to_name:
            sites.append(sequence_to_name[sequence])
    if len(sites) > 1:
        return (sites[0], sites[-1])
    return tuple(sites)


def _antibiotic(
    component: sbol2.ComponentDefinition, document: sbol2.Document
) -> str | None:
    for child in _walk_components(component, document):
        if ANTIBIOTIC_RESISTANCE not in child.roles:
            continue
        display_id = child.displayId or ""
        match = re.search(
            r"\b(" + "|".join(sorted(ANTIBIOTIC_MAP)) + r")_?",
            display_id,
            re.IGNORECASE,
        )
        return ANTIBIOTIC_MAP[match.group(1).lower()] if match else "Unknown"
    return None


def _insert_identities(
    component: sbol2.ComponentDefinition, document: sbol2.Document
) -> list[str]:
    insert_roles = PART_ROLES | {ENGINEERED_INSERT, ENGINEERED_REGION}
    identities = {
        child.identity
        for child in _children(component, document)
        if insert_roles & set(str(role) for role in child.roles)
    }
    return sorted(identities)


def _backbone_stage(fusion_sites: tuple[str, ...]) -> BuildStage:
    return (
        BuildStage.ASSEMBLY_LVL2
        if list(fusion_sites) in LVL2_FUSION_SITE_ORDER
        else BuildStage.ASSEMBLY_LVL1
    )
