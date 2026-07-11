import json

from buildcompiler.adapters.pudu import (
    assembly_route_to_pudu_json,
    domestication_artifact_to_pudu_json,
    legacy_assembly_route_to_pudu_json,
    write_assembly_pudu_input_json,
)
from buildcompiler.domain import IndexedBackbone, IndexedPlasmid, IndexedReagent


def test_assembly_route_to_pudu_json_shape_and_values():
    payload = assembly_route_to_pudu_json(
        product_identity="https://example.org/products/p1",
        part_plasmids=[
            IndexedPlasmid(identity="https://example.org/plasmids/part1"),
            IndexedPlasmid(identity="https://example.org/plasmids/part2"),
        ],
        backbone=IndexedBackbone(identity="https://example.org/backbones/b1"),
        restriction_enzyme=IndexedReagent(
            identity="https://example.org/reagents/re1", name="BsaI"
        ),
    )

    assert payload == {
        "Product": "https://example.org/products/p1",
        "Backbone": "https://example.org/backbones/b1",
        "PartsList": [
            "https://example.org/plasmids/part1",
            "https://example.org/plasmids/part2",
        ],
        "Restriction Enzyme": "BsaI",
    }


class _SbolLike:
    def __init__(self, identity):
        self.identity = identity


class _LegacyPlasmid:
    def __init__(self, identity):
        self.plasmid_definition = _SbolLike(identity)


class _LegacyImplementation:
    def __init__(self, *, identity, built):
        self.identity = identity
        self.built = built


def test_legacy_assembly_route_to_pudu_json_uses_route_uris():
    payload = legacy_assembly_route_to_pudu_json(
        product_plasmid=_LegacyPlasmid("https://example.org/products/p1"),
        backbone=_LegacyPlasmid("https://example.org/backbones/b1"),
        part_plasmids=[
            _LegacyPlasmid("https://example.org/plasmids/part1"),
            _LegacyPlasmid("https://example.org/plasmids/part2"),
        ],
        restriction_enzyme=_LegacyImplementation(
            identity="https://example.org/implementations/bsai_impl",
            built="https://example.org/reagents/BsaI",
        ),
    )

    assert payload == {
        "Product": "https://example.org/products/p1",
        "Backbone": "https://example.org/backbones/b1",
        "PartsList": [
            "https://example.org/plasmids/part1",
            "https://example.org/plasmids/part2",
        ],
        "Restriction Enzyme": "https://example.org/reagents/BsaI",
    }


def test_write_assembly_pudu_input_json_is_deterministic(tmp_path):
    payload = [
        {
            "Product": "https://example.org/products/p1",
            "Backbone": "https://example.org/backbones/b1",
            "PartsList": [
                "https://example.org/plasmids/part1",
                "https://example.org/plasmids/part2",
            ],
            "Restriction Enzyme": "https://example.org/reagents/BsaI",
        }
    ]

    output_path = tmp_path / "pudu_input.json"
    returned_path = write_assembly_pudu_input_json(payload, output_path)

    assert returned_path == output_path
    assert (
        output_path.read_text(encoding="utf-8") == json.dumps(payload, indent=4) + "\n"
    )


def test_domestication_artifact_to_pudu_json_shape_and_values():
    payload = domestication_artifact_to_pudu_json(
        {
            "domestication": {
                "product_identity": "https://example.org/products/domesticated",
                "backbone_identity": "https://example.org/backbones/dva_ab",
                "generated_insert_identity": "https://example.org/inserts/domesticated_insert",
                "generated_insert_sequence": "NNNNGGTCTCGGAGAAAATACTGAGACCNNNN",
                "restriction_enzyme": {
                    "identity": "https://example.org/reagents/BsaI",
                    "name": "BsaI",
                },
            }
        }
    )

    assert payload == {
        "Product": "https://example.org/products/domesticated",
        "Backbone": "https://example.org/backbones/dva_ab",
        "PartsList": ["https://example.org/inserts/domesticated_insert"],
        "Generated Insert Sequence": "NNNNGGTCTCGGAGAAAATACTGAGACCNNNN",
        "Restriction Enzyme": "https://example.org/reagents/BsaI",
    }
