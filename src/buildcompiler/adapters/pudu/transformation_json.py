"""In-memory adapter for compiler-level PUDU transformation JSON payloads."""

from collections.abc import Sequence

from buildcompiler.domain import IndexedPlasmid


def _stable_identifier(identity: str, display_id: str | None) -> str:
    return identity or display_id or ""


def _plasmid_identifier(plasmid: IndexedPlasmid | str) -> str:
    if isinstance(plasmid, str):
        return plasmid
    return _stable_identifier(identity=plasmid.identity, display_id=plasmid.display_id)


def transformation_to_pudu_json(
    *,
    strain_identity: str,
    chassis_identity: str,
    plasmids: Sequence[IndexedPlasmid | str],
) -> dict[str, object]:
    """Adapt a transformation record into legacy-compatible PUDU JSON keys."""

    return {
        "Strain": strain_identity,
        "Chassis": chassis_identity,
        "Plasmids": [_plasmid_identifier(plasmid) for plasmid in plasmids],
    }


def transformations_to_pudu_json(
    *,
    strain_identities: Sequence[str],
    chassis_identities: Sequence[str],
    plasmid_sets: Sequence[Sequence[IndexedPlasmid | str]],
) -> list[dict[str, object]]:
    """Batch helper for deterministic in-memory transformation JSON payloads."""

    return [
        transformation_to_pudu_json(
            strain_identity=strain_identity,
            chassis_identity=chassis_identity,
            plasmids=plasmids,
        )
        for strain_identity, chassis_identity, plasmids in zip(
            strain_identities,
            chassis_identities,
            plasmid_sets,
            strict=True,
        )
    ]
