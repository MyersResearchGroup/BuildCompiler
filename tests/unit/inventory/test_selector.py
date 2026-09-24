from buildcompiler.api import BuildOptions
from buildcompiler.domain import IndexedPlasmid, MaterialState
from buildcompiler.inventory import CompatibilitySelector, Inventory


def _plasmid(
    identity: str,
    insert: str,
    *,
    state=MaterialState.PLANNED,
    source="collection",
    fusion_sites=(),
) -> IndexedPlasmid:
    return IndexedPlasmid(
        identity=identity,
        state=state,
        metadata={
            "insert_identities": [insert],
            "source": source,
            "antibiotic": "Ampicillin",
            "fusion_sites": fusion_sites,
        },
    )


def test_lvl1_missing_parts_are_reported_not_raised():
    inv = Inventory(plasmids=[_plasmid("https://e/p1", "https://e/part1")])
    sel = CompatibilitySelector(inv)
    route = sel.select_lvl1_route(
        request_id="r1", part_identities=["https://e/part1", "https://e/part2"]
    ).selected
    assert route is not None
    assert route.missing_part_identities == ("https://e/part2",)


def test_lvl1_prefers_existing_material_in_tie():
    inv = Inventory(
        plasmids=[
            _plasmid(
                "https://e/a",
                "https://e/part",
                source="generated",
                state=MaterialState.GENERATED,
            ),
            _plasmid(
                "https://e/b",
                "https://e/part",
                source="collection",
                state=MaterialState.GENERATED,
            ),
        ]
    )
    sel = CompatibilitySelector(inv)
    route = sel.select_lvl1_route(
        request_id="r1", part_identities=["https://e/part"]
    ).selected
    assert route.selected_part_plasmids[0].identity == "https://e/b"


def test_lvl1_hard_constraints_override_selection_preference():
    inv = Inventory(
        plasmids=[_plasmid("https://e/a", "https://e/part", source="generated")]
    )
    opts = BuildOptions()
    opts.selection.prefer_existing_collection_material = True
    sel = CompatibilitySelector(inv, options=opts)
    route = sel.select_lvl1_route(
        request_id="r1",
        part_identities=["https://e/part"],
        constraints={"allowed_identities": ["https://e/a"]},
    ).selected
    assert route.selected_part_plasmids[0].identity == "https://e/a"


def test_lvl2_large_order_search_not_silent_without_opt_in():
    inv = Inventory()
    sel = CompatibilitySelector(inv)
    out = sel.select_lvl2_route(
        request_id="r2", region_identities=["a", "b", "c", "d", "e"]
    )
    assert out.selected is None
    assert out.rejected


def test_lvl2_rejected_alternatives_capped_at_3():
    inv = Inventory(
        plasmids=[_plasmid(f"https://e/p{i}", f"https://e/r{i}") for i in range(4)]
    )
    sel = CompatibilitySelector(inv)
    out = sel.select_lvl2_route(
        request_id="r3",
        region_identities=[
            "https://e/r0",
            "https://e/r1",
            "https://e/r2",
            "https://e/r3",
        ],
    )
    assert out.selected is not None
    assert len(out.rejected) == 3


def test_lvl2_constrained_order_must_match_requested_regions():
    inv = Inventory(
        plasmids=[
            _plasmid("https://e/p0", "https://e/r0"),
            _plasmid("https://e/p1", "https://e/r1"),
        ]
    )
    sel = CompatibilitySelector(inv)
    out = sel.select_lvl2_route(
        request_id="r4",
        region_identities=["https://e/r0", "https://e/r1"],
        constraints={"region_order": ["https://e/r0"]},
    )
    assert out.selected is None
    assert out.rejected
    assert out.rejected[0].missing_region_identities == ("https://e/r0", "https://e/r1")


def test_lvl1_route_rejects_broken_fusion_site_adjacency():
    inv = Inventory(
        plasmids=[
            _plasmid("https://e/p1", "https://e/part1", fusion_sites=("A", "B")),
            _plasmid("https://e/p2", "https://e/part2", fusion_sites=("C", "D")),
        ]
    )

    route = (
        CompatibilitySelector(inv)
        .select_lvl1_route(
            request_id="broken",
            part_identities=["https://e/part1", "https://e/part2"],
        )
        .selected
    )

    assert route is not None
    assert route.selected_part_plasmids == ()
    assert route.missing_part_identities == (
        "https://e/part1",
        "https://e/part2",
    )
    assert route.score.constraint_violations == 1


def test_lvl1_route_selects_complete_compatible_chain_and_backbone():
    from buildcompiler.domain import BuildStage, IndexedBackbone

    inv = Inventory(
        plasmids=[
            _plasmid("https://e/a_bad", "https://e/part1", fusion_sites=("A", "X")),
            _plasmid("https://e/a_good", "https://e/part1", fusion_sites=("A", "B")),
            _plasmid("https://e/b", "https://e/part2", fusion_sites=("B", "C")),
        ],
        backbones=[
            IndexedBackbone(
                "https://e/backbone",
                metadata={
                    "fusion_sites": ("A", "C"),
                    "antibiotic": "Ampicillin",
                    "stage": BuildStage.ASSEMBLY_LVL1.value,
                },
            )
        ],
    )

    route = (
        CompatibilitySelector(inv)
        .select_lvl1_route(
            request_id="compatible",
            part_identities=["https://e/part1", "https://e/part2"],
            constraints={"antibiotic": "Ampicillin"},
        )
        .selected
    )

    assert route is not None
    assert [item.identity for item in route.selected_part_plasmids] == [
        "https://e/a_good",
        "https://e/b",
    ]
    assert route.backbone is not None
    assert route.backbone.identity == "https://e/backbone"


def test_lvl1_route_selects_chain_whose_outer_sites_have_a_backbone():
    from buildcompiler.domain import BuildStage, IndexedBackbone

    inv = Inventory(
        plasmids=[
            _plasmid("https://e/a", "https://e/part1", fusion_sites=("A", "B")),
            _plasmid("https://e/bc", "https://e/part2", fusion_sites=("B", "C")),
            _plasmid("https://e/bd", "https://e/part2", fusion_sites=("B", "D")),
        ],
        backbones=[
            IndexedBackbone(
                "https://e/backbone-ad",
                metadata={
                    "fusion_sites": ("A", "D"),
                    "antibiotic": "Ampicillin",
                    "stage": BuildStage.ASSEMBLY_LVL1.value,
                },
            )
        ],
    )

    route = (
        CompatibilitySelector(inv)
        .select_lvl1_route(
            request_id="backbone-aware",
            part_identities=["https://e/part1", "https://e/part2"],
            constraints={"antibiotic": "Ampicillin"},
        )
        .selected
    )

    assert route is not None
    assert route.selected_part_plasmids[-1].identity == "https://e/bd"
    assert route.backbone is not None


def test_lvl2_route_selects_compatible_chain_and_matching_backbone():
    from buildcompiler.domain import BuildStage, IndexedBackbone

    inv = Inventory(
        plasmids=[
            _plasmid("https://e/r1_bad", "https://e/r1", fusion_sites=("A", "X")),
            _plasmid("https://e/r1_good", "https://e/r1", fusion_sites=("A", "B")),
            _plasmid("https://e/r2", "https://e/r2", fusion_sites=("B", "C")),
        ],
        backbones=[
            IndexedBackbone(
                "https://e/lvl2_backbone",
                metadata={
                    "fusion_sites": ("A", "C"),
                    "antibiotic": "Ampicillin",
                    "stage": BuildStage.ASSEMBLY_LVL2.value,
                },
            )
        ],
    )

    route = (
        CompatibilitySelector(inv)
        .select_lvl2_route(
            request_id="lvl2-compatible",
            region_identities=["https://e/r1", "https://e/r2"],
            constraints={
                "region_order": ["https://e/r1", "https://e/r2"],
                "antibiotic": "Ampicillin",
            },
        )
        .selected
    )

    assert route is not None
    assert [item.identity for item in route.selected_lvl1_plasmids] == [
        "https://e/r1_good",
        "https://e/r2",
    ]
    assert route.backbone is not None
    assert route.backbone.identity == "https://e/lvl2_backbone"


def test_lvl2_route_selects_chain_whose_outer_sites_have_a_backbone():
    from buildcompiler.domain import BuildStage, IndexedBackbone

    inv = Inventory(
        plasmids=[
            _plasmid("https://e/r1", "https://e/region1", fusion_sites=("A", "B")),
            _plasmid("https://e/r2-c", "https://e/region2", fusion_sites=("B", "C")),
            _plasmid("https://e/r2-d", "https://e/region2", fusion_sites=("B", "D")),
        ],
        backbones=[
            IndexedBackbone(
                "https://e/lvl2-backbone-ad",
                metadata={
                    "fusion_sites": ("A", "D"),
                    "antibiotic": "Ampicillin",
                    "stage": BuildStage.ASSEMBLY_LVL2.value,
                },
            )
        ],
    )

    route = (
        CompatibilitySelector(inv)
        .select_lvl2_route(
            request_id="lvl2-backbone-aware",
            region_identities=["https://e/region1", "https://e/region2"],
            constraints={
                "region_order": ["https://e/region1", "https://e/region2"],
                "antibiotic": "Ampicillin",
            },
        )
        .selected
    )

    assert route is not None
    assert route.selected_lvl1_plasmids[-1].identity == "https://e/r2-d"
    assert route.backbone is not None
