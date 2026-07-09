"""In-memory adapter for compiler-level PUDU assembly JSON payloads."""

from collections.abc import Sequence

from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent


def _stable_identifier(identity: str, display_id: str | None) -> str:
    return identity or display_id or ""


def assembly_route_to_pudu_json(
    *,
    product_identity: str,
    part_plasmids: Sequence[IndexedPlasmid],
    backbone: IndexedBackbone,
    restriction_enzyme: IndexedReagent,
) -> dict[str, object]:
    """Adapt a selected lvl1 route into legacy-compatible assembly JSON keys."""

    parts_list = [
        _stable_identifier(identity=part.identity, display_id=part.display_id)
        for part in part_plasmids
    ]
    return {
        "Product": product_identity,
        "Backbone": _stable_identifier(
            identity=backbone.identity, display_id=backbone.display_id
        ),
        "PartsList": parts_list,
        "Restriction Enzyme": (
            restriction_enzyme.name
            or _stable_identifier(
                identity=restriction_enzyme.identity,
                display_id=restriction_enzyme.display_id,
            )
        ),
    }


def assembly_routes_to_pudu_json(
    *,
    product_identities: Sequence[str],
    part_plasmid_routes: Sequence[Sequence[IndexedPlasmid]],
    backbones: Sequence[IndexedBackbone],
    restriction_enzymes: Sequence[IndexedReagent],
) -> list[dict[str, object]]:
    """Batch helper for deterministic in-memory assembly JSON payloads."""

    return [
        assembly_route_to_pudu_json(
            product_identity=product_identity,
            part_plasmids=part_plasmids,
            backbone=backbone,
            restriction_enzyme=restriction_enzyme,
        )
        for product_identity, part_plasmids, backbone, restriction_enzyme in zip(
            product_identities,
            part_plasmid_routes,
            backbones,
            restriction_enzymes,
            strict=True,
        )
    ]
