from buildcompiler.adapters.pudu import (
    plasmid_locations_to_pudu_json,
    transformation_to_pudu_json,
    transformations_to_pudu_json,
)
from buildcompiler.domain import IndexedPlasmid


def test_transformation_to_pudu_json_shape_and_values():
    payload = transformation_to_pudu_json(
        strain_identity="https://example.org/strain/s1",
        chassis_identity="https://example.org/chassis/c1",
        plasmids=[
            IndexedPlasmid(identity="https://example.org/plasmids/p1"),
            "https://example.org/plasmids/p2",
        ],
    )

    assert payload == {
        "Strain": "https://example.org/strain/s1",
        "Chassis": "https://example.org/chassis/c1",
        "Plasmids": [
            "https://example.org/plasmids/p1",
            "https://example.org/plasmids/p2",
        ],
    }


def test_transformations_to_pudu_json_batch_helper_is_deterministic():
    payloads = transformations_to_pudu_json(
        strain_identities=["s1", "s2"],
        chassis_identities=["c1", "c2"],
        plasmid_sets=[["p1"], ["p2", "p3"]],
    )

    assert payloads == [
        {"Strain": "s1", "Chassis": "c1", "Plasmids": ["p1"]},
        {"Strain": "s2", "Chassis": "c2", "Plasmids": ["p2", "p3"]},
    ]


def test_plasmid_locations_to_pudu_json_uses_deterministic_wells():
    payload = plasmid_locations_to_pudu_json(["p1", "p2", "p3"])

    assert payload == {
        "p1": ["A1"],
        "p2": ["B1"],
        "p3": ["C1"],
    }


def test_plasmid_locations_to_pudu_json_accepts_explicit_wells_and_duplicates():
    payload = plasmid_locations_to_pudu_json(
        ["p1", "p1", "p2"], wells=["A1", "B1", "C1"]
    )

    assert payload == {
        "p1": ["A1", "B1"],
        "p2": ["C1"],
    }
