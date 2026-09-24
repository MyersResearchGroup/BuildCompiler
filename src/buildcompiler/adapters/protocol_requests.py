"""Translate selected build routes into typed protocol requests."""

from collections.abc import Sequence

from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent
from buildcompiler.domain.protocol_requests import (
    AssemblyReaction,
    AssemblyRequest,
    MaterialRef,
)


def assembly_request_from_route(
    *,
    stage_id: str,
    products: Sequence[IndexedPlasmid],
    parts: Sequence[IndexedPlasmid],
    backbone: IndexedBackbone,
    restriction_enzyme: IndexedReagent,
) -> AssemblyRequest:
    """Use actual produced identities and preserve the selected component order."""

    def material(record) -> MaterialRef:
        return MaterialRef(
            identity=record.identity,
            label=record.name or record.display_id or record.identity,
        )

    return AssemblyRequest(
        id=stage_id,
        source_stage_id=stage_id,
        reactions=tuple(
            AssemblyReaction(
                id=f"{stage_id}/product/{index}",
                product=material(product),
                backbone=material(backbone),
                parts=tuple(material(part) for part in parts),
                restriction_enzyme=material(restriction_enzyme),
            )
            for index, product in enumerate(products)
        ),
    )
