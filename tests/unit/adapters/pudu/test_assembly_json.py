from buildcompiler.adapters.pudu import assembly_route_to_pudu_json
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
