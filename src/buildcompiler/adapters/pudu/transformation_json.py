"""In-memory adapter for compiler-level PUDU transformation JSON payloads."""

from collections.abc import Sequence

from buildcompiler.domain import IndexedPlasmid


PUDU_96_WELL_ORDER = tuple(
    f"{row}{column}" for column in range(1, 13) for row in "ABCDEFGH"
)


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


def plasmid_locations_to_pudu_json(
    plasmids: Sequence[IndexedPlasmid | str],
    *,
    wells: Sequence[str] | None = None,
) -> dict[str, list[str]]:
    """Create PUDU's assembly-output plasmid location map.

    PUDU's transformation protocol optionally consumes the
    ``transformation_input.json`` emitted by its assembly simulation.  The shape
    is ``{"plasmid_uri": ["A1"]}``, where each value is a list because one
    plasmid may be available in multiple source wells.
    """

    if wells is None:
        wells = PUDU_96_WELL_ORDER[: len(plasmids)]
    if len(plasmids) != len(wells):
        raise ValueError("plasmids and wells must have the same length.")

    locations: dict[str, list[str]] = {}
    for plasmid, well in zip(plasmids, wells, strict=True):
        plasmid_id = _plasmid_identifier(plasmid)
        if not plasmid_id:
            raise ValueError("plasmid identity cannot be empty.")
        locations.setdefault(plasmid_id, []).append(well)

    return locations
